"""Reduce the faces of Blender meshes with the simplifier of simplify.py.

Every face corner (loop) becomes a simplifier vertex carrying the loop normal, UVs, colors and the bone
weights of its Blender vertex; corners of the same Blender vertex with identical attributes are merged, and
different Blender vertices never are. As the collapses only remove vertices, the result reuses the original
vertices, so vertex groups, shape keys, UV_WARP modifiers and material animations keep working. The geometry
is rebuilt with triangles only.

Skinned meshes that use more bones than the games allow are split with bone_split.py.
"""

import bmesh
import bpy

from .bone_split import MAX_BONES, split_by_bones
from .simplify import DEFAULT_MAX_ERROR, MeshData, simplify_mesh

def _triangulate(mesh):
    if all(len(polygon.vertices) == 3 for polygon in mesh.polygons):
        return

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=[face for face in bm.faces if len(face.verts) > 3])
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

def _read(mesh, groups_object):
    """MeshData of the triangulated mesh, one vertex per loop."""
    loop_count = len(mesh.loops)
    loop_vertices = [0] * loop_count
    mesh.loops.foreach_get("vertex_index", loop_vertices)
    coordinates = [0.0] * (len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", coordinates)

    if hasattr(mesh, "calc_normals_split"):
        mesh.calc_normals_split()

    normals = [0.0] * (loop_count * 3)
    mesh.loops.foreach_get("normal", normals)

    data = MeshData(mesh.name)
    data.positions = [tuple(coordinates[3 * v:3 * v + 3]) for v in loop_vertices]
    data.normals = [tuple(normals[3 * i:3 * i + 3]) for i in range(loop_count)]

    for index, layer in enumerate(mesh.uv_layers):
        uvs = [0.0] * (loop_count * 2)
        layer.data.foreach_get("uv", uvs)
        data.uvs[index] = [tuple(uvs[2 * i:2 * i + 2]) for i in range(loop_count)]

    if len(mesh.vertex_colors):
        colors = []

        for layer in mesh.vertex_colors:
            values = [0.0] * (loop_count * 4)
            layer.data.foreach_get("color", values)
            colors.append(values)

        data.colors = [tuple(v for values in colors for v in values[4 * i:4 * i + 4]) for i in range(loop_count)]

    if groups_object is not None and groups_object.vertex_groups:
        indices, weights = [], []

        for vertex in loop_vertices:
            groups = [(g.group, g.weight) for g in mesh.vertices[vertex].groups if g.weight > 0.0]
            indices.append([g for g, _ in groups])
            weights.append([w for _, w in groups])

        data.bone_indices, data.bone_weights = indices, weights

    material_count = max(1, len(mesh.materials))
    data.submeshes = [[] for _ in range(material_count)]

    for polygon in mesh.polygons:
        start = polygon.loop_start
        data.submeshes[min(polygon.material_index, material_count - 1)].append((start, start + 1, start + 2))

    data.weld_ids = loop_vertices
    data.source_indices = list(range(loop_count))

    return data, loop_vertices

def reduce_mesh(mesh, objects, max_error=DEFAULT_MAX_ERROR):
    """Simplify a mesh datablock used by objects. Returns (triangles before, after)."""
    _triangulate(mesh)
    groups_object = next((obj for obj in objects if obj.vertex_groups), None)
    data, loop_vertices = _read(mesh, groups_object)
    before, after = simplify_mesh(data, max_error)

    if after >= before:
        return before, before

    # Everything the rebuild drops, read on the original loops and vertices
    loop_count = len(mesh.loops)
    loop_polygons = [0] * loop_count

    for polygon in mesh.polygons:
        for loop in range(polygon.loop_start, polygon.loop_start + polygon.loop_total):
            loop_polygons[loop] = polygon.index

    smooth = [polygon.use_smooth for polygon in mesh.polygons]
    uv_layers = []

    for layer in mesh.uv_layers:
        values = [0.0] * (loop_count * 2)
        layer.data.foreach_get("uv", values)
        uv_layers.append((layer.name, layer.active, layer.active_render, values))

    color_layers = []

    for layer in mesh.vertex_colors:
        values = [0.0] * (loop_count * 4)
        layer.data.foreach_get("color", values)
        color_layers.append((layer.name, layer.active, layer.active_render, values))

    custom_normals = getattr(mesh, "has_custom_normals", False)
    normals = [0.0] * (loop_count * 3)
    mesh.loops.foreach_get("normal", normals)
    shape_keys = []
    key_animation = None

    if mesh.shape_keys:
        key_animation = mesh.shape_keys.animation_data.action if mesh.shape_keys.animation_data else None

        for block in mesh.shape_keys.key_blocks:
            shape_keys.append((block.name, block.relative_key.name, block.value, block.slider_min, block.slider_max,
                               block.mute, block.interpolation, block.vertex_group, [tuple(p.co) for p in block.data]))

    group_weights = {}

    for vertex in mesh.vertices:
        group_weights[vertex.index] = [(g.group, g.weight) for g in vertex.groups]

    # Clearing the geometry also empties the vertex groups of the objects
    group_names = {obj.name: [(g.name, g.lock_weight) for g in obj.vertex_groups] for obj in objects}

    kept_loops = data.source_indices
    vertices = sorted({loop_vertices[loop] for loop in kept_loops})
    new_index = {old: new for new, old in enumerate(vertices)}
    coordinates = [tuple(mesh.vertices[v].co) for v in vertices]
    faces, face_loops, face_materials = [], [], []

    for material, triangles in enumerate(data.submeshes):
        for triangle in triangles:
            loops = [kept_loops[i] for i in triangle]
            faces.append(tuple(new_index[loop_vertices[loop]] for loop in loops))
            face_loops.append(loops)
            face_materials.append(material)

    mesh.clear_geometry()
    mesh.from_pydata(coordinates, [], faces)
    mesh.polygons.foreach_set("material_index", face_materials)
    mesh.polygons.foreach_set("use_smooth", [smooth[loop_polygons[loops[0]]] for loops in face_loops])

    # from_pydata keeps the corner order of each face: loop i of face f is face_loops[f][i]
    sources = [loop for loops in face_loops for loop in loops]

    for name, active, active_render, values in uv_layers:
        layer = mesh.uv_layers.new(name=name)
        layer.data.foreach_set("uv", [values[2 * s + i] for s in sources for i in range(2)])
        layer.active_render = active_render

        if active:
            mesh.uv_layers.active = layer

    for name, active, active_render, values in color_layers:
        layer = mesh.vertex_colors.new(name=name)
        layer.data.foreach_set("color", [values[4 * s + i] for s in sources for i in range(4)])
        layer.active_render = active_render

        if active:
            mesh.vertex_colors.active = layer

    for obj in objects:
        for name, lock in group_names[obj.name]:
            group = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
            group.lock_weight = lock

    if groups_object is not None:
        # Weights live in the mesh: writing them through one object is enough
        for vertex in vertices:
            for group, weight in group_weights[vertex]:
                if group < len(groups_object.vertex_groups):
                    groups_object.vertex_groups[group].add([new_index[vertex]], weight, "REPLACE")

    if shape_keys:
        owner = objects[0]
        blocks = {}

        for name, _, value, slider_min, slider_max, mute, interpolation, vertex_group, positions in shape_keys:
            block = owner.shape_key_add(name=name, from_mix=False)
            block.data.foreach_set("co", [c for v in vertices for c in positions[v]])
            block.slider_min, block.slider_max = slider_min, slider_max
            block.value, block.mute, block.interpolation, block.vertex_group = value, mute, interpolation, vertex_group
            blocks[name] = block

        for name, relative, *_ in shape_keys:
            if relative in blocks:
                blocks[name].relative_key = blocks[relative]

        if key_animation is not None:
            mesh.shape_keys.animation_data_create()
            mesh.shape_keys.animation_data.action = key_animation

    if custom_normals:
        if hasattr(mesh, "use_auto_smooth"):
            mesh.use_auto_smooth = True

        mesh.normals_split_custom_set([tuple(normals[3 * s:3 * s + 3]) for s in sources])

    mesh.update()

    return before, after

def _face_bones(obj):
    """Bone set of every face of a skinned object (the vertex groups named after a bone of its armature)."""
    armature = obj.find_armature()

    if armature is None:
        return None

    bone_names = {bone.name for bone in armature.data.bones}
    bone_groups = {group.index for group in obj.vertex_groups if group.name in bone_names}
    vertex_bones = [frozenset(g.group for g in vertex.groups if g.weight > 0.0 and g.group in bone_groups)
                    for vertex in obj.data.vertices]

    return [frozenset().union(*(vertex_bones[v] for v in polygon.vertices)) for polygon in obj.data.polygons]

def _keep_faces(mesh, faces):
    """Delete every face of the mesh that is not in faces, with the edges and vertices only they used."""
    kept = set(faces)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[face for face in bm.faces if face.index not in kept], context="FACES")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

def split_mesh(obj, context, max_bones=MAX_BONES):
    """Split a skinned mesh object in parts of at most max_bones bones. Returns the objects of the parts."""
    face_bones = _face_bones(obj)

    if face_bones is None:
        return [obj]

    groups = split_by_bones(face_bones, max_bones)

    if len(groups) < 2:
        return [obj]

    if obj.data.users > 1:
        obj.data = obj.data.copy()

    mesh = obj.data

    # Each part only sees its own faces: the normals of the cut are kept as custom normals
    if not getattr(mesh, "has_custom_normals", False):
        if hasattr(mesh, "calc_normals_split"):
            mesh.calc_normals_split()

        normals = [tuple(loop.normal) for loop in mesh.loops]

        if hasattr(mesh, "use_auto_smooth"):
            mesh.use_auto_smooth = True

        mesh.normals_split_custom_set(normals)

    parts = [obj]

    for index, faces in enumerate(groups[1:], 1):
        part = obj.copy()
        part.data = mesh.copy()
        part.name = "%s_%d" % (obj.name, index)

        for collection in obj.users_collection:
            collection.objects.link(part)

        _keep_faces(part.data, faces)
        part.select_set(True)
        parts.append(part)

    _keep_faces(mesh, groups[0])

    return parts

class STUDIOOPTIMIZER_OT_optimize_model(bpy.types.Operator):
    """Optimize the selected meshes for studio_eleven: reduce their faces and split the skinned meshes that use too many bones"""
    bl_idname = "object.studio_optimizer_optimize_model"
    bl_label = "Optimize the model for studio_eleven"
    bl_options = {"REGISTER", "UNDO"}

    reduce_faces: bpy.props.BoolProperty(
        name="Reduce Faces", default=True,
        description="Simplify the meshes with quadric error edge collapses (triangles only, animations are kept)")

    max_error: bpy.props.FloatProperty(
        name="Max Error", default=DEFAULT_MAX_ERROR, min=0.0001, max=1.0, precision=4, step=0.1,
        description="Largest allowed error, as a fraction of each mesh size. Higher removes more faces")

    split_bones: bpy.props.BoolProperty(
        name="Split Meshes Over %d Bones" % MAX_BONES, default=True,
        description="Split every skinned mesh that uses more than %d bones in several meshes: past this limit the model "
                    "can explode in some games" % MAX_BONES)

    @classmethod
    def poll(cls, context):
        return any(obj.type == "MESH" for obj in context.selected_objects)

    def invoke(self, context, event):
        # The options are chosen in a dialog first, the optimization only runs on OK
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "reduce_faces")

        row = layout.row()
        row.enabled = self.reduce_faces
        row.prop(self, "max_error")

        layout.prop(self, "split_bones")

    def execute(self, context):
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        objects = [obj for obj in context.selected_objects if obj.type == "MESH" and obj.data.polygons]
        messages = []

        if self.reduce_faces:
            users = {}

            for obj in objects:
                users.setdefault(obj.data.name, (obj.data, []))[1].append(obj)

            total_before = total_after = 0

            for mesh, mesh_objects in users.values():
                before, after = reduce_mesh(mesh, mesh_objects, self.max_error)
                total_before += before
                total_after += after

            messages.append("%d mesh(es): %d -> %d triangles" % (len(users), total_before, total_after))

        if self.split_bones:
            split_count = part_count = 0

            for obj in objects:
                parts = split_mesh(obj, context)

                if len(parts) > 1:
                    split_count += 1
                    part_count += len(parts)

            messages.append("%d mesh(es) split in %d parts of %d bones at most" % (split_count, part_count, MAX_BONES))

        if messages:
            self.report({"INFO"}, ", ".join(messages))

        return {"FINISHED"}

def menu_object(self, context):
    self.layout.operator(STUDIOOPTIMIZER_OT_optimize_model.bl_idname, text="Optimize the model for studio_eleven")

def register():
    bpy.utils.register_class(STUDIOOPTIMIZER_OT_optimize_model)
    bpy.types.VIEW3D_MT_object.append(menu_object)

def unregister():
    bpy.types.VIEW3D_MT_object.remove(menu_object)
    bpy.utils.unregister_class(STUDIOOPTIMIZER_OT_optimize_model)
