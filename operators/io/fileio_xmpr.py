import io
import os
import json

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, EnumProperty

import bmesh
import numpy as np

from math import radians
from mathutils import Matrix, Quaternion, Vector

from ...formats import xmpr, atr, res
from ...rendering import project as rendering_project
from ...utils.mesh_faces_utils import MeshFaceUtils
from ..panels.material_textures import apply_material_textures, suspend_updates, resume_updates, sampler_to_properties
from ..panels.material_render import state_to_properties, detect_render_mode

##########################################
# CONST
##########################################

MESH_TYPE_INT_TO_ENUM = {
    0: 'UNK',
    1: 'MODEL',
    2: 'COLLISION',
}

MESH_TYPE_ENUM_TO_INT = {v: k for k, v in MESH_TYPE_INT_TO_ENUM.items()}

# Property of a skinned mesh: the name of its parent node, which hides it
PARENT_NODE_PROPERTY = "level5_parent_node"

# The bone palette of the shaders holds 24 bones, past it some engines overwrite other uniforms
MAX_MESH_BONES = 24

##########################################
# XMPR Function
##########################################

def get_bone_names(armature):
    for bone in armature.pose.bones:
        yield(bone.name)

def get_used_bone_count(mesh):
    """Number of bones written in the node table of the exported mesh."""
    if mesh.parent is None or mesh.parent.type != 'ARMATURE':
        return 0

    bone_names = set(get_bone_names(mesh.parent))
    used = set()

    for polygon in mesh.data.polygons:
        for vertex_index in polygon.vertices:
            for group in mesh.data.vertices[vertex_index].groups:
                if group.weight != 0 and mesh.vertex_groups[group.group].name in bone_names:
                    used.add(group.group)

    return len(used)

def report_bone_limit(operator, mesh_names):
    """Warn about the meshes that use more bones than the bone palette of the games holds."""
    too_many = []

    for mesh_name in mesh_names:
        bone_count = get_used_bone_count(bpy.data.objects[mesh_name])

        if bone_count > MAX_MESH_BONES:
            too_many.append(f"{mesh_name} ({bone_count} bones)")

    if len(too_many) == 0:
        return

    operator.report({'WARNING'}, f"Meshes over the limit of {MAX_MESH_BONES} bones, depending on the game they can be unstable in game, reducing their bones is advised: {', '.join(too_many)}")

def get_mesh_info_and_weights(mesh, bone_names=None):
    vertex_map = {}
    vertices_info = []
    uv_info = []
    normal_info = []
    color_info = []
    tint_info = []
    face_indices = []

    if not mesh or not mesh.data:
        return face_indices, vertices_info, uv_info, normal_info, color_info, tint_info, {}

    # Ensure the mesh data is in the correct state
    mesh.data.update()
    
    # Get blender version
    blender_version = bpy.app.version
            
    # Get vertex colors
    vertex_colors = None
    tint_colors = None
    if hasattr(mesh.data, 'vertex_colors') and mesh.data.vertex_colors:
        color_layer = mesh.data.vertex_colors.get("Col") or mesh.data.vertex_colors.active
        # Tint is a layer of its own, it must never be taken as the vertex color layer
        if color_layer is not None and color_layer.name != "Tint":
            vertex_colors = color_layer.data

        tint_layer = mesh.data.vertex_colors.get("Tint")
        if tint_layer is not None:
            tint_colors = tint_layer.data

    # Get UVs
    has_uv_layers = False
    uv_data = None
    if hasattr(mesh.data, 'uv_layers') and mesh.data.uv_layers:
        if mesh.data.uv_layers.active:
            has_uv_layers = True
            uv_data = mesh.data.uv_layers.active.data
        elif len(mesh.data.uv_layers) > 0:
            # Take first UV layer if none is active
            has_uv_layers = True
            uv_data = mesh.data.uv_layers[0].data

    vertex_to_unique_indices = {}
    
    # Bone indices mapping
    bone_indices = {name: i for i, name in enumerate(bone_names)} if bone_names else {}
    
    weights = {}

    for face in mesh.data.polygons:
        face_idx = []
        for loop_index in face.loop_indices:
            vertex_index = mesh.data.loops[loop_index].vertex_index

            # Get vertex
            v = tuple(round(coord, 3) for coord in mesh.data.vertices[vertex_index].co)
            
            # Get normals according to the Blender version
            if blender_version >= (4, 1, 0):
                # Blender 4.1+: uses corner_normals to be more precise
                n = tuple(round(coord, 3) for coord in mesh.data.corner_normals[loop_index].vector)
            else:
                # Blender 4.0 and previous: use vertex normal
                n = tuple(round(coord, 3) for coord in mesh.data.vertices[vertex_index].normal)
            
            # Get UV
            if has_uv_layers and uv_data:
                try:
                    uv = tuple(round(coord, 3) for coord in uv_data[loop_index].uv)
                except (IndexError, AttributeError):
                    uv = (0.0, 0.0)
            else:
                uv = (0.0, 0.0)
                
            # Get Color
            if vertex_colors:
                try:
                    color = tuple(round(c, 3) for c in vertex_colors[loop_index].color)
                except (IndexError, AttributeError):
                    color = (0.0, 0.0, 0.0, 1.0)
            else:
                color = (0.0, 0.0, 0.0, 1.0)

            # Get Tint
            if tint_colors:
                try:
                    tint = tuple(round(c, 3) for c in tint_colors[loop_index].color)
                except (IndexError, AttributeError):
                    tint = (1.0, 1.0, 1.0, 1.0)
            else:
                tint = (1.0, 1.0, 1.0, 1.0)

            key = (v, n, uv, color, tint)

            if key not in vertex_map:
                unique_index = len(vertex_map)
                vertex_map[key] = unique_index
                vertices_info.append(v)
                normal_info.append(n)
                uv_info.append(uv)
                color_info.append(color)
                tint_info.append(tint)

                if vertex_index not in vertex_to_unique_indices:
                    vertex_to_unique_indices[vertex_index] = []
                vertex_to_unique_indices[vertex_index].append(unique_index)
            else:
                unique_index = vertex_map[key]
                if vertex_index not in vertex_to_unique_indices:
                    vertex_to_unique_indices[vertex_index] = []
                if unique_index not in vertex_to_unique_indices[vertex_index]:
                    vertex_to_unique_indices[vertex_index].append(unique_index)

            face_idx.append(unique_index)
        face_indices.append(tuple(face_idx))

    # Harmonize normals and UVs for faces with same positions
    position_map = {}
    for face_idx, face in enumerate(face_indices):
        positions = tuple(sorted([vertices_info[vertex_idx] for vertex_idx in face]))
        if positions not in position_map:
            position_map[positions] = []
        position_map[positions].append(face_idx)

    for positions, face_list in position_map.items():
        if len(face_list) > 1:
            ref_face = face_indices[face_list[0]]
            for face_idx in face_list[1:]:
                current_face = face_indices[face_idx]
                vertex_correspondence = {}
                for i, current_vertex_idx in enumerate(current_face):
                    current_pos = vertices_info[current_vertex_idx]
                    for j, ref_vertex_idx in enumerate(ref_face):
                        if current_pos == vertices_info[ref_vertex_idx]:
                            vertex_correspondence[current_vertex_idx] = ref_vertex_idx
                            break
                for current_vertex_idx, ref_vertex_idx in vertex_correspondence.items():
                    normal_info[current_vertex_idx] = normal_info[ref_vertex_idx]
                    uv_info[current_vertex_idx] = uv_info[ref_vertex_idx]

    # Calculate weights if bone_names provided
    if bone_names:
        for original_vertex_index, unique_indices in vertex_to_unique_indices.items():
            vertex = mesh.data.vertices[original_vertex_index]
            vertex_weights = {}
            for group in vertex.groups:
                if group.weight != 0:
                    bone_name = mesh.vertex_groups[group.group].name
                    bone_index = bone_indices.get(bone_name)
                    if bone_index is not None:
                        vertex_weights[bone_index] = group.weight
            for unique_index in unique_indices:
                weights[unique_index] = vertex_weights.copy()

    return face_indices, vertices_info, uv_info, normal_info, color_info, tint_info, weights
    
def apply_atr_state(material, atr_state):
    # The state is kept as it is in level5_atr, the Blender material is only a preview
    if hasattr(material, "level5_atr"):
        state_to_properties(atr_state, material.level5_atr)

        # Simple mode only if the imported settings are one of its render modes
        if detect_render_mode(material.level5_atr) != 'CUSTOM':
            material.level5_atr.panel_mode = 'SIMPLE'
        else:
            material.level5_atr.panel_mode = 'EXPERT'

    resolved = atr.resolve_state(atr_state)

    material.use_backface_culling = resolved["cull"]

    if resolved["alpha_test"]:
        material.blend_method = 'CLIP'
        material.alpha_threshold = resolved["alpha_ref"]
    elif resolved["blend_rgb_source"] == atr.GL_ONE and resolved["blend_rgb_destination"] == atr.GL_ZERO:
        # Blending is always on, an opaque material is ONE * src + ZERO * dst
        material.blend_method = 'OPAQUE'
    else:
        material.blend_method = 'BLEND'

    material.show_transparent_back = not resolved["depth_write"]

def apply_bind_offsets(model_data, bones, bind_offsets):
    """Move the vertices of a skinned mesh from the bind pose of the file to the rest pose Blender skins from."""
    vertices = model_data["vertices"]
    weights = vertices["weights"]
    bone_indices = vertices["bone_indices"]

    offsets = {}
    for bone_crc32, bone_name in bones.items():
        if bone_name in bind_offsets:
            offsets[bone_crc32] = np.array(bind_offsets[bone_name])

    if not offsets or not weights or not bone_indices:
        return

    # Each vertex takes the blend of the offsets of its bones
    identity = np.identity(4)
    blended = np.empty((len(weights), 4, 4))

    for vertex, (vertex_weights, vertex_bones) in enumerate(zip(weights, bone_indices)):
        total = sum(vertex_weights)

        if total <= 0.0:
            blended[vertex] = identity
            continue

        matrix = np.zeros((4, 4))
        for weight, bone_crc32 in zip(vertex_weights, vertex_bones):
            matrix += (weight / total) * offsets.get(bone_crc32, identity)

        blended[vertex] = matrix

    positions = np.array(vertices["positions"], dtype=float).reshape(-1, 3)
    positions = np.einsum('nij,nj->ni', blended[:, :3, :3], positions) + blended[:, :3, 3]
    vertices["positions"] = positions.tolist()

    if vertices["normals"]:
        normals = np.array(vertices["normals"], dtype=float).reshape(-1, 3)
        normals = np.einsum('nij,nj->ni', blended[:, :3, :3], normals)

        lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        lengths[lengths == 0.0] = 1.0
        vertices["normals"] = (normals / lengths).tolist()

def make_mesh(model_data, armature=None, bones=None, lib=None, txp_data=None, atr_state=None, mtr_material=None, bind_offsets=None):
    if bind_offsets and bones and model_data["node_table"] and model_data["single_bind"] is None:
        apply_bind_offsets(model_data, bones, bind_offsets)

    mesh = bpy.data.meshes.new(name=model_data['name'])
    mesh_obj = bpy.data.objects.new(name=model_data['name'], object_data=mesh)
    
    bpy.context.collection.objects.link(mesh_obj)
    
    bpy.context.view_layer.objects.active = mesh_obj
    mesh_obj.select_set(True)
    
    bpy.ops.object.mode_set(mode='OBJECT')
    
    positions = model_data["vertices"]["positions"]
    normals = model_data["vertices"]["normals"]
    uv_data0 = model_data["vertices"]["uv_data0"]
    uv_data1 = model_data["vertices"]["uv_data1"]
    weights = model_data["vertices"]["weights"]
    bone_indices = model_data["vertices"]["bone_indices"]
    color_data = model_data["vertices"]["color_data"]
    tint_data = model_data["vertices"]["tint_data"]
    single_bind = model_data["single_bind"]
    parent_node = model_data.get("parent_node")
    draw_priority = model_data["draw_priority"]
    mesh_type = model_data["mesh_type"]
    
    mesh.level5_properties.draw_priority = draw_priority
    mesh.level5_properties.mesh_type = MESH_TYPE_INT_TO_ENUM.get(mesh_type, 'UNK')
    rendering_project.assign_imported_render_program(mesh, model_data["render_program_hash"])
    
    mesh.from_pydata(positions, [], model_data["triangles"])  
    
    if normals:
        #mesh.use_auto_smooth = True
        #mesh.auto_smooth_angle = 180
        mesh.normals_split_custom_set_from_vertices(normals)
        #mesh.calc_normals_split()

    # prm can't have more than 4 UVMaps
    texprojs = ["UVMap0", "UVMap1", "UVMap2", "UVMap3"]
    
    if txp_data:
        for txp in txp_data:
            if txp[1] == model_data["material_name"]:
                texprojs[txp[2]] = txp[0]
    
    if uv_data0:
        uv_layer0 = mesh.uv_layers.new(name=texprojs[0])
        for loop in mesh.loops:
            vertex_index = loop.vertex_index
            if vertex_index < len(uv_data0):
                uv_layer0.data[loop.index].uv = uv_data0[vertex_index]
        mesh_obj.modifiers.new(name=texprojs[0], type="UV_WARP")
        mesh_obj.modifiers[texprojs[0]].uv_layer = texprojs[0]
        
    if uv_data1:
        uv_layer1 = mesh.uv_layers.new(name=texprojs[1])
        for loop in mesh.loops:
            vertex_index = loop.vertex_index
            if vertex_index < len(uv_data1):
                uv_layer1.data[loop.index].uv = uv_data1[vertex_index]
        mesh_obj.modifiers.new(name=texprojs[1], type="UV_WARP")
        mesh_obj.modifiers[texprojs[1]].uv_layer = texprojs[1]

    color_layer = None
    if color_data:
        color_layer = mesh.vertex_colors.new(name="Col")
        flat_colors = []
        
        for loop in mesh.loops:
            vert_idx = loop.vertex_index
            flat_colors.extend(color_data[vert_idx])  # r, g, b, a

        color_layer.data.foreach_set("color", flat_colors)

    # A white tint is what the engine uses when a mesh has none, no need for a layer
    has_tint = False
    for tint in tint_data:
        if tuple(tint) != (1.0, 1.0, 1.0, 1.0):
            has_tint = True

    if has_tint:
        tint_layer = mesh.vertex_colors.new(name="Tint")
        flat_tints = []

        for loop in mesh.loops:
            vert_idx = loop.vertex_index
            flat_tints.extend(tint_data[vert_idx])  # r, g, b, a

        tint_layer.data.foreach_set("color", flat_tints)

        if color_layer:
            mesh.vertex_colors.active = color_layer
    
    mesh_obj.rotation_euler = (radians(90), 0, 0)
    
    if armature:
        modifier = mesh_obj.modifiers.new(type="ARMATURE", name="Armature")
        modifier.object = armature
        if bones and model_data["node_table"]:
            for bone_crc32 in model_data["node_table"]:
                bone_name = bones[bone_crc32]
                if bone_name not in mesh_obj.vertex_groups:
                    mesh_obj.vertex_groups.new(name=bone_name)
            
            for vert_idx, (vertex_weights, vertex_bones) in enumerate(zip(weights, bone_indices)):
                for weight, bone_idx in zip(vertex_weights, vertex_bones):
                    bone_name = bones[bone_idx]
                    mesh_obj.vertex_groups[bone_name].add([vert_idx], weight, 'ADD')
        
        #if mesh_obj.vertex_groups:
            #bone_influences = {bone.name: 0.0 for bone in armature.data.bones}
            #for vertex in mesh_obj.data.vertices:
                #for group in vertex.groups:
                    #group_name = mesh_obj.vertex_groups[group.group].name
                    #if group_name in bone_influences:
                        #bone_influences[group_name] += group.weight
            
            #most_influential_bone = armature.pose.bones.get(max(bone_influences, key=bone_influences.get))
            
            #bone_world_matrix = armature.matrix_world @ most_influential_bone.matrix
            #bone_world_location = bone_world_matrix.translation
            
            #print(mesh_obj.name, bone_world_location.x, bone_world_location.y, bone_world_location.z, most_influential_bone.name)
            #if bone_world_location.y > 400:
                #mesh_obj.location.y = bone_world_location.y
        
        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        bpy.ops.object.parent_set(type='ARMATURE', keep_transform=True)
        
        if single_bind:
            mesh_obj.parent_type = 'BONE'
            mesh_obj.parent_bone = single_bind
            mesh_obj.rotation_euler = (0, 0, 0)

            # Blender puts the child of a bone at its tail, the game draws the mesh at the node
            bone = armature.data.bones.get(single_bind)
            if bone is not None:
                mesh_obj.location = mesh_obj.matrix_parent_inverse.inverted().to_3x3() @ Vector((0, -bone.length, 0))
        elif parent_node:
            # The node which hides a skinned mesh, the game doesn't draw it while this node is hidden
            mesh_obj[PARENT_NODE_PROPERTY] = parent_node
    
    if lib is not None:
        material = bpy.data.materials.new(name=model_data['material_name'])
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Get or create the Material Output node
        material_output = nodes.get("Material Output")
        if not material_output:
            material_output = nodes.new(type="ShaderNodeOutputMaterial")
            material_output.location = (400, 0)

        # Get or create the Principled BSDF node
        bsdf = nodes.get("Principled BSDF")
        if not bsdf:
            bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
            bsdf.location = (0, 0)
            bsdf.inputs["Alpha"].default_value = 1.0
            bsdf.inputs["Emission"].default_value = (0, 0, 0, 1.0)
            links.new(bsdf.outputs["BSDF"], material_output.inputs["Surface"])

        if len(lib) > 0:
            # Get or create the Mix Shader node
            mix_shader = nodes.get("Mix Shader")
            if not mix_shader:
                mix_shader = nodes.new(type="ShaderNodeMixShader")
                mix_shader.location = (200, 0)
                mix_shader.inputs[0].default_value = 0.2    

            # Get or create the Transparent BSDF node
            transparent_bsdf = nodes.get("Transparent BSDF")
            if not transparent_bsdf:
                transparent_bsdf = nodes.new(type="ShaderNodeBsdfTransparent")
                transparent_bsdf.location = (0, -200)

            # Get or create the Alpha Multiplier node
            alpha_multiplier = nodes.get("Alpha Multiplier")
            if not alpha_multiplier:
                alpha_multiplier = nodes.new(type="ShaderNodeMath")
                alpha_multiplier.name = "Alpha Multiplier"
                alpha_multiplier.operation = 'MULTIPLY'
                alpha_multiplier.location = (-300, 200)
                alpha_multiplier.inputs[1].default_value = 1.0            

            has_alpha = False
            for texture in lib:
                if texture["image"].alpha_mode != "NONE":
                    has_alpha = True

            if has_alpha:
                links.new(alpha_multiplier.outputs[0], bsdf.inputs["Alpha"])
                material.show_transparent_back = True
            else:
                links.new(mix_shader.outputs[0], material_output.inputs[0])
                links.new(bsdf.outputs[0], mix_shader.inputs[1])
                links.new(transparent_bsdf.outputs[0], mix_shader.inputs[2])           
                material.show_transparent_back = False
        
        # Set default material properties
        material.blend_method = 'BLEND'
        
        # shadow_method has been removed from Blender 4.3
        if bpy.app.version < (4, 3, 0):
            material.shadow_method = 'CLIP'        
        
        material.alpha_threshold = 0.5
        material.use_backface_culling = False       
        
        # Replace the defaults above when the archive has a render state for this material
        if atr_state is not None:
            apply_atr_state(material, atr_state)

        # The lighting material of the model, the export writes it back
        if mtr_material is not None:
            material.level5_mtr.data = json.dumps(mtr_material.to_dict())

        # An imported material keeps what the archive gives, the template doesn't replace it
        material.level5_mtr.initialized = True
        
        # The texture nodes are built from the texture slots of the material
        suspend_updates()

        material.level5_textures.initialized = True

        for texture in lib:
            slot = material.level5_textures.slots.add()
            slot.image = texture["image"]
            slot.pixel_format = texture["pixel_format"]
            slot.texture_mode = texture["texture_mode"]
            slot.show_expanded = False
            sampler_to_properties(texture["sampler"], slot)

        resume_updates()

        # Add material
        mesh_obj.data.materials.append(material)
        apply_material_textures(material)
    
    return mesh_obj

def get_skinned_name(skinned):
    if skinned:
        return "skinned"

    return "rigid"

def check_render_program(operator, mesh, render_default, skinned):
    # Rigid meshes never use a skinned program in the original models (0 out of 870), skinned meshes do in all but 4
    if mesh.data.level5_properties.unresolved_render_program or render_default.data.get("skinned") is None:
        return

    if render_default.data["skinned"] == skinned:
        return

    message = f"{mesh.name}: render default {render_default.name} is {get_skinned_name(render_default.data['skinned'])} but the mesh is {get_skinned_name(skinned)}"

    if operator:
        operator.report({'WARNING'}, message)
    else:
        print(f"[Studio Eleven] {message}")

def fileio_write_xmpr(context, mesh_name, library_name, operator=None):
    mesh = bpy.data.objects[mesh_name]

    bone_names = []
    if mesh.parent and mesh.parent.type == 'ARMATURE':
        bone_names = list(get_bone_names(mesh.parent))

    indices, vertices, uvs, normals, colors, tints, weights = get_mesh_info_and_weights(mesh, bone_names)

    # Cancel if mesh info is empty
    if not (indices or vertices or uvs or normals or colors):
        raise ValueError(f"Mesh {mesh_name} has invalid or empty data, export canceled")

    # The bone of a single bind mesh is its parent node
    single_bind = False
    if mesh.parent_type == 'BONE' and mesh.parent_bone:
        single_bind = True
        parent_node = mesh.parent_bone
    else:
        parent_node = mesh.get(PARENT_NODE_PROPERTY)

    engine_id = rendering_project.get_scene_engine_id(context.scene)
    render_default = rendering_project.get_mesh_render_default(mesh.data, engine_id)
    render_program_hash = rendering_project.get_mesh_render_program_hash(mesh.data, engine_id)

    # The program of the template is skinned, a single bind mesh that still has it uses the one of the maps of the template
    template = rendering_project.get_scene_template(context.scene)
    if single_bind and not rendering_project.is_studio_render_enabled() and render_program_hash == template["render_program_hash"]:
        render_program_hash = template["map_render_program_hash"]
    else:
        check_render_program(operator, mesh, render_default, len(xmpr.used_bones(weights, bone_names)) > 0)

    draw_priority = mesh.data.level5_properties.draw_priority
    mesh_type = MESH_TYPE_ENUM_TO_INT.get(mesh.data.level5_properties.mesh_type, 0)

    texspace_array = [
        list(mesh.data.texspace_location),
        list(mesh.data.texspace_size)
    ]

    return xmpr.write(
        mesh.name_full, texspace_array,
        indices, vertices, uvs, normals, colors,
        weights, bone_names, library_name, render_program_hash,
        parent_node, draw_priority, mesh_type, tints
    )
    
def fileio_open_xmpr(context, filepath):
    # Extract the file name without extension
    file_name = os.path.splitext(os.path.basename(filepath))[0]

    with open(filepath, 'rb') as file:
        # Open the XMPR file and read model data
        mesh_data = xmpr.open_xmpr(io.BytesIO(file.read()))

        # Create the mesh using the model data
        make_mesh(mesh_data)

    return {'FINISHED'}

##########################################
# Register class
##########################################     
    
class ExportXPRM(bpy.types.Operator, ExportHelper):
    bl_idname = "export.prm"
    bl_label = "Export to prm"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".prm"
    filter_glob: StringProperty(default="*.prm", options={'HIDDEN'})
    
    def item_callback(self, context):
        items = []
        for o in bpy.context.scene.objects:
            if o.type == "MESH":
                items.append((o.name, o.name, ""))
        return items
        
    def update_mesh_name(self, context):
        # Retrieve the mesh object by name
        obj = bpy.data.objects.get(self.mesh_name) 
        
        if obj and obj.type == 'MESH':
            # Access materials of the mesh
            materials = obj.data.materials 

            # Check if at least one material exists
            if materials and materials[0]:  
                self.material_name = materials[0].name
            else:
                # Default value if no material exists
                self.material_name = f"DefautLib.{self.mesh_name}"

    mesh_name: EnumProperty(
        name="Meshes",
        description="Choose mesh",
        items=item_callback,
        default=0,
        update=update_mesh_name,
    )
    
    material_name: StringProperty(
        name="Material",
        description="Write a material name",
        default="",
    )    

    def execute(self, context):
        if not self.mesh_name:
            self.report({'ERROR'}, "No mesh found")
            return {'FINISHED'}
            
        if not self.material_name:
            self.report({'ERROR'}, "Material name cannot be null")
            return {'FINISHED'}               
            
        try:
            data = fileio_write_xmpr(context, self.mesh_name, self.material_name, self)
        except ValueError as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

        with open(self.filepath, "wb") as f:
            f.write(data)

        report_bone_limit(self, [self.mesh_name])

        return {'FINISHED'}

    def invoke(self, context, event):
        """Ensure the update function is called on the menu launch."""
        self.update_mesh_name(context)
        return super().invoke(context, event)

class ImportXMPR(bpy.types.Operator, ImportHelper):
    bl_idname = "import.prm"
    bl_label = "Import a .prm"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".prm"
    filter_glob: StringProperty(default="*.prm", options={'HIDDEN'})
    
    def execute(self, context):
            return fileio_open_xmpr(context, self.filepath)

##########################################
# Register
##########################################

classes = (
    ExportXPRM,
    ImportXMPR,
)

def register_xmpr():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister_xmpr():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
