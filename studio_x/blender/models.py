"""Build a Blender armature (one bone per Transform) and its meshes from a Unity hierarchy.

Bone rest matrices are rigid (Blender bones cannot store scale). Every pose basis is computed as
    basis = (rest_parent^-1 @ rest)^-1 @ unity_local
so that pose_bone.matrix equals the Unity world matrix, including scale, which is what the
Studio Eleven exporters read (parent.matrix^-1 @ pose_bone.matrix).
"""

import bpy
from mathutils import Matrix

from . import convert, materials, render_state
from .textures import rest_st
from ..unity.mesh import decode_mesh


# Studio Eleven's xmpr writer default
DEFAULT_DRAW_PRIORITY = 21
# Bone property Studio Eleven writes back as the .mbn node flag (fileio_animation_manager.BONE_FLAG_PROPERTY);
# 4 = visible node, 5 = billboard node
BONE_FLAG_PROPERTY = "level5_flag"
NODE_FLAG = 4


class RendererRecord:
    def __init__(self, node, obj, unity_materials, blender_materials, uv_layer):
        self.node = node
        self.object = obj
        self.unity_materials = unity_materials
        self.blender_materials = blender_materials
        self.uv_layer = uv_layer
        # Material slots already duplicated for per-renderer animation
        self.owned_slots = set()
        # Decoded Unity mesh (every UV channel), for the shaders converted with their own UVs (threshold.py)
        self.unity_mesh = None
        # Converted by mask_shaders.py (two texture units), and its foam copy for a threshold shader
        self.mask_converted = False
        self.foam = None


class ModelResult:
    def __init__(self, entry, armature):
        self.entry = entry
        self.armature = armature
        self.bone_names = {}     # id(node) -> bone name
        self.relative = {}       # id(node) -> rest_parent^-1 @ rest
        self.renderers = []
        self.draw_priorities = {}  # renderer path_id -> Studio Eleven draw priority
        self.cache = None


def _set_mode(obj, mode):
    bpy.context.view_layer.objects.active = obj
    if bpy.context.object and bpy.context.object.mode != mode:
        bpy.ops.object.mode_set(mode=mode)


def _world_matrices(root, scale):
    worlds = {}

    def walk(node, parent_matrix):
        matrix = parent_matrix @ convert.local_matrix(node.position, node.rotation, node.scale, scale)
        worlds[id(node)] = matrix
        for child in node.children:
            walk(child, matrix)

    walk(root, Matrix.Identity(4))
    return worlds


def _bind_pose_rests(entry, worlds, scale):
    """Rest matrices taken from SkinnedMeshRenderer bind poses, so skinning matches Unity."""
    rests = {}
    sfile = entry.sfile
    for node in entry.node.walk():
        info = node.get_component("SkinnedMeshRenderer")
        if info is None:
            continue
        renderer = info.read()
        mesh_info = sfile.get_object(renderer["m_Mesh"])
        if mesh_info is None:
            continue
        bind_poses = mesh_info.read().get("m_BindPose", [])
        for index, bone_ptr in enumerate(renderer["m_Bones"]):
            bone_node = entry.scene.nodes.get(bone_ptr["m_PathID"]) if bone_ptr["m_FileID"] == 0 else None
            if bone_node is None or index >= len(bind_poses) or id(bone_node) in rests:
                continue
            pose = bind_poses[index]
            rows = [[pose["e%d%d" % (r, c)] for c in range(4)] for r in range(4)]
            bind = convert.unity_matrix(rows, scale)
            try:
                rests[id(bone_node)] = convert.rigid(worlds[id(node)] @ bind.inverted())
            except ValueError:
                continue
    return rests


def build_armature(context, entry, environment, options, cache, report, with_renderers=True):
    """with_renderers False: bones only (the ball aura model, whose renderer is the ball the ball model draws)."""
    scale = options.scale
    root = entry.node
    nodes = list(root.walk())
    worlds = _world_matrices(root, scale)
    rests = {id(n): convert.rigid(worlds[id(n)]) for n in nodes}
    rests.update(_bind_pose_rests(entry, worlds, scale))

    armature_data = bpy.data.armatures.new(root.name)
    armature = bpy.data.objects.new(root.name, armature_data)
    context.collection.objects.link(armature)
    armature.rotation_euler = convert.ARMATURE_ROTATION
    armature["unity_model"] = entry.key
    result = ModelResult(entry, armature)
    result.cache = cache
    result.draw_priorities = render_state.draw_priorities(entry.sfile)

    used = set()
    for node in nodes:
        name = node.name or "bone"
        candidate, suffix = name, 1
        while candidate in used:
            candidate = "%s_%d" % (name, suffix)
            suffix += 1
        used.add(candidate)
        result.bone_names[id(node)] = candidate

    for obj in context.view_layer.objects:
        obj.select_set(False)
    armature.select_set(True)
    _set_mode(armature, "EDIT")
    length = 0.05 * scale
    for node in nodes:
        bone = armature_data.edit_bones.new(result.bone_names[id(node)])
        bone.head = (0.0, 0.0, 0.0)
        bone.tail = (0.0, length, 0.0)
        bone.matrix = rests[id(node)]
        if node.parent is not None and id(node.parent) in result.bone_names:
            bone.parent = armature_data.edit_bones[result.bone_names[id(node.parent)]]
    _set_mode(armature, "OBJECT")
    # Unity nodes are plain nodes (.mbn flag 4): Studio Eleven's export turns a bone without a flag named
    # "cam_rot" or "billboard" into a billboard node (5), but a Unity cam_rot already carries its facing
    # rotation in the clips; the game would add the camera rotation on top of it (Ocean Birth's ball glow
    # drawn off the ball)
    for bone in armature_data.bones:
        bone[BONE_FLAG_PROPERTY] = NODE_FLAG

    for node in nodes:
        parent_rest = rests[id(node.parent)] if node.parent is not None and id(node.parent) in rests else Matrix.Identity(4)
        relative = parent_rest.inverted() @ rests[id(node)]
        result.relative[id(node)] = relative
        pose_bone = armature.pose.bones[result.bone_names[id(node)]]
        pose_bone.rotation_mode = "QUATERNION"
        basis = relative.inverted() @ convert.local_matrix(node.position, node.rotation, node.scale, scale)
        location, rotation, bone_scale = basis.decompose()
        pose_bone.location = location
        pose_bone.rotation_quaternion = rotation
        pose_bone.scale = bone_scale

    material_cache = {}
    for node in nodes if with_renderers else ():
        for renderer_type in ("MeshRenderer", "SkinnedMeshRenderer"):
            info = node.get_component(renderer_type)
            if info is not None:
                record = _build_renderer(context, entry, node, info, renderer_type, result, worlds, rests,
                                         environment, options, cache, material_cache, report)
                if record:
                    result.renderers.append(record)
    return result


def _build_renderer(context, entry, node, info, renderer_type, result, worlds, rests, environment, options,
                    cache, material_cache, report):
    sfile = entry.sfile
    renderer = info.read()
    if renderer_type == "SkinnedMeshRenderer":
        mesh_ptr = renderer["m_Mesh"]
    else:
        filter_info = node.get_component("MeshFilter")
        mesh_ptr = filter_info.read()["m_Mesh"] if filter_info else None
    mesh_info = sfile.get_object(mesh_ptr)
    if mesh_info is None:
        report({"WARNING"}, "%s: mesh is stored in another file (load its bundle too)" % node.name)
        return None

    mesh = decode_mesh(mesh_info.read(), environment, sfile.version_tuple, sfile.endian)
    if not mesh.positions:
        return None
    scale = options.scale

    bones = []
    if renderer_type == "SkinnedMeshRenderer" and mesh.bone_weights:
        for ptr in renderer["m_Bones"]:
            bone_node = entry.scene.nodes.get(ptr["m_PathID"]) if ptr["m_FileID"] == 0 else None
            bones.append(result.bone_names.get(id(bone_node)) if bone_node else None)
    skinned = any(bones)
    # Skinned vertices are in renderer space. Rigid meshes stay in the local space of their own bone and
    # are parented to it: Studio Eleven then writes them as "single bind" meshes, like every effect mesh
    # of the game. As skinned meshes their bind pose would be the pose of the frame displayed
    # when exporting (mbn.write reads pose_bone.matrix), which moved or hid the effects in game.
    vertex_matrix = worlds[id(node)] if skinned else Matrix.Identity(4)

    positions = [vertex_matrix @ convert.position(p, scale) for p in mesh.positions]
    faces = []
    face_materials = []
    for material_index, triangles in enumerate(mesh.submeshes):
        for a, b, c in triangles:
            # Mirroring X flips the winding
            faces.append((a, c, b))
            face_materials.append(material_index)

    blender_mesh = bpy.data.meshes.new(mesh.name or node.name)
    blender_mesh.from_pydata([tuple(p) for p in positions], [], faces)
    blender_mesh.polygons.foreach_set("material_index", face_materials)

    loop_vertices = [0] * len(blender_mesh.loops)
    blender_mesh.loops.foreach_get("vertex_index", loop_vertices)

    unity_materials = []
    for ptr in renderer["m_Materials"]:
        material_info = sfile.get_object(ptr)
        unity_materials.append((material_info, material_info.read() if material_info else None))

    first_material = next((m for _, m in unity_materials if m), None)
    # Only the main UV channel is imported. Studio Eleven writes one texture projection (.txp) per UV
    # layer, and the game reads NNN.txp for the NNN-th mesh like the .atr: the extra channels of the
    # effect shaders (secondary masks, not baked) shifted every following mesh onto another mesh's
    # projection and UV animation (FireTornado: ball_wave_01/02, aura_wave_f1, ball_abi_01).
    uv_layer_name = None
    if mesh.uvs:
        uvs = mesh.uvs[min(mesh.uvs)]
        base = first_material.get("m_Name", node.name) if first_material else node.name
        uv_layer_name = "%s_texproj0" % base
        layer = blender_mesh.uv_layers.new(name=uv_layer_name)
        # The rest tiling/offset of the texture goes into the UVs: Studio Eleven only exports a UV_WARP
        # that is animated (a static tiling was lost in the game) and previews its scale as a product
        # where the shaders and the game divide (see rest_st)
        scale_u, scale_v, offset_u, offset_v = rest_st(first_material)
        flat = []
        for vertex in loop_vertices:
            u, v = uvs[vertex]
            flat.extend(((u - offset_u) / scale_u, (v - offset_v) / scale_v))
        layer.data.foreach_set("uv", flat)

    # The vertex colors of the shipped 3DS effects live in the tint (vertex buffer slot 1); slot 9, the
    # "Col" layer, is empty in every game file checked (whs0001_ef1, cn1199m, mr24b01), so only blended
    # materials get a layer and it is the tint. A solid shader (the character toon one) keeps other data
    # in its vertex colors, which the 3DS has no use for. The effect shaders also multiply the texture by
    # the material _Color, which the 3DS can only reproduce through the tint.
    if first_material is not None and render_state.is_blended(first_material):
        color = materials.material_color(first_material)
        if mesh.colors or color != (1.0, 1.0, 1.0, 1.0):
            flat = []
            for vertex in loop_vertices:
                vertex_color = tuple(mesh.colors[vertex]) if mesh.colors else ()
                vertex_color += (1.0,) * (4 - len(vertex_color))
                flat.extend(a * b for a, b in zip(vertex_color, color))
            tint_layer = blender_mesh.vertex_colors.new(name="Tint")
            tint_layer.data.foreach_set("color", flat)

    if mesh.normals:
        rotation = vertex_matrix.to_3x3().normalized()
        normals = [(rotation @ convert.normal(n)).normalized() for n in mesh.normals]
        if hasattr(blender_mesh, "use_auto_smooth"):
            blender_mesh.use_auto_smooth = True
        blender_mesh.normals_split_custom_set_from_vertices([tuple(n) for n in normals])
    blender_mesh.update()

    blender_mesh.level5_properties.draw_priority = result.draw_priorities.get(info.path_id, DEFAULT_DRAW_PRIORITY)
    blender_mesh.level5_properties.mesh_type = "MODEL"
    # Unity data carries no 3DS render program hash, so Studio Eleven would otherwise leave the
    # engine's default (a lit character shader, e.g. #FIX_TON_12_SIL on IE4, declared "skinned")
    # on every mesh: pick the unlit one that reads the texture colour and alpha directly instead
    # (#FIX_IMG exists in every engine, same one the field uses, and is declared rigid). Every
    # mesh built here is single_bind/rigid unless it actually carries bone weights (real,
    # non-retargeted Unity characters): leaving a rigid mesh on the engine's skinned default
    # mismatches the render program's own skinned/rigid flag (Studio Eleven's exporter warns:
    # "render default ... is skinned but the mesh is rigid"). Only true skinned characters keep
    # the engine default.
    if not skinned or (first_material is not None and render_state.is_blended(first_material)):
        blender_mesh.level5_properties.render_default = "#FIX_IMG"

    obj = bpy.data.objects.new(node.name, blender_mesh)
    context.collection.objects.link(obj)
    obj.parent = result.armature
    if skinned:
        modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
        modifier.object = result.armature
        groups = {}
        for vertex, (indices, weights) in enumerate(zip(mesh.bone_indices, mesh.bone_weights)):
            for bone_index, weight in zip(indices, weights):
                if weight <= 0.0 or bone_index >= len(bones) or bones[bone_index] is None:
                    continue
                groups.setdefault(bones[bone_index], {}).setdefault(weight, []).append(vertex)
        for bone_name, by_weight in groups.items():
            group = obj.vertex_groups.new(name=bone_name)
            for weight, vertices in by_weight.items():
                group.add(vertices, weight, "REPLACE")
    else:
        bone_name = result.bone_names[id(node)]
        obj.parent_type = "BONE"
        obj.parent_bone = bone_name
        # Blender attaches bone children to the tail: cancel it so the vertices sit in the bone space
        obj.matrix_parent_inverse = Matrix.Translation((0.0, -result.armature.data.bones[bone_name].length, 0.0))

    blender_materials = []
    for material_info, material in unity_materials:
        if material is None:
            blender_materials.append(None)
            continue
        key = material_info.path_id
        blender_material = material_cache.get(key)
        if blender_material is None:
            # The material's own texture PPtrs are relative to the file that holds it, not the renderer's
            # (a material can live in a different bundle, shared across techniques, e.g. an effect's ball)
            blender_material = materials.build_material(material.get("m_Name", "material"), material,
                                                        material_info.sfile, cache,
                                                        options.adapt_textures)
            material_cache[key] = blender_material
        blender_mesh.materials.append(blender_material)
        blender_materials.append(blender_material)
        # The tint preview reads the Tint layer of a mesh using the material, which exists only now
        render_state.refresh_preview(blender_material)

    if uv_layer_name:
        # Studio Eleven drives UV animations through a UV_WARP modifier named like the texproj; at rest it
        # is the identity (the rest _ST is in the UVs), animations.py keys the motion from there
        warp = obj.modifiers.new(name=uv_layer_name, type="UV_WARP")
        warp.uv_layer = uv_layer_name
        warp.center = (0.0, 0.0)
    record = RendererRecord(node, obj, unity_materials, blender_materials, uv_layer_name)
    record.unity_mesh = mesh
    return record
