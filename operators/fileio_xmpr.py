import io
import os

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, EnumProperty

import bmesh

from math import radians
from mathutils import Matrix, Quaternion, Vector

from ..formats import xmpr
from ..templates import *

##########################################
# XMPR Function
##########################################

def get_bone_names(armature):
    for bone in armature.pose.bones:
        yield(bone.name)

def get_mesh_info_and_weights(mesh, bone_names=None):
    vertex_map = {}
    vertices_info = []
    uv_info = []
    normal_info = []
    color_info = []
    face_indices = []

    if not mesh or not mesh.data:
        return face_indices, vertices_info, uv_info, normal_info, color_info, {}

    # Vertex colors
    has_vertex_colors = hasattr(mesh.data, 'vertex_colors') and mesh.data.vertex_colors and mesh.data.vertex_colors.active
    if has_vertex_colors:
        vertex_colors = mesh.data.vertex_colors.active.data

    # UVs
    has_uv_layers = hasattr(mesh.data, 'uv_layers') and mesh.data.uv_layers and mesh.data.uv_layers.active
    if has_uv_layers:
        uv_data = mesh.data.uv_layers.active.data

    mesh.data.calc_normals()
    mesh.data.calc_normals_split()

    vertex_to_unique_indices = {}

    # Bone indices mapping
    bone_indices = {name: i for i, name in enumerate(bone_names)} if bone_names else {}

    weights = {}

    for face in mesh.data.polygons:
        face_idx = []
        for loop_index in face.loop_indices:
            vertex_index = mesh.data.loops[loop_index].vertex_index

            v = tuple(round(coord, 3) for coord in mesh.data.vertices[vertex_index].co)
            n = tuple(round(coord, 3) for coord in mesh.data.loops[loop_index].normal)
            uv = tuple(round(coord, 3) for coord in (uv_data[loop_index].uv if has_uv_layers else (0.0, 0.0)))
            color = tuple(round(c, 3) for c in (vertex_colors[loop_index].color if has_vertex_colors else (0.0, 0.0, 0.0, 0.0)))

            key = (v, n, uv, color)

            if key not in vertex_map:
                unique_index = len(vertex_map)
                vertex_map[key] = unique_index
                vertices_info.append(v)
                normal_info.append(n)
                uv_info.append(uv)
                color_info.append(color)

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

    return face_indices, vertices_info, uv_info, normal_info, color_info, weights
    
def make_mesh(model_data, armature=None, bones=None, lib=None, txp_data=None):
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
    single_bind = model_data["single_bind"]
    draw_priority = model_data["draw_priority"]
    mesh_type = model_data["mesh_type"]
    
    mesh.level5_properties.draw_priority = draw_priority
    mesh.level5_properties.mesh_type = mesh_type
    
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

    if color_data:
        color_layer = mesh.vertex_colors.new(name="Col")
        flat_colors = []
        
        for loop in mesh.loops:
            vert_idx = loop.vertex_index
            flat_colors.extend(color_data[vert_idx])  # r, g, b, a

        color_layer.data.foreach_set("color", flat_colors)
    
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
    
    if lib:
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

        # Create texture node
        texture_node = None
        for texture in lib:
            texture_node = material.node_tree.nodes.new('ShaderNodeTexImage')
            texture_node.image = texture

        # Link only the last texture to principled bsdf then to material
        if texture_node:
            if texture.alpha_mode != "NONE":
                links.new(alpha_multiplier.outputs[0], bsdf.inputs["Alpha"])
                links.new(texture_node.outputs["Alpha"], alpha_multiplier.inputs[0])           
                material.show_transparent_back = True
            else:
                links.new(mix_shader.outputs[0], material_output.inputs[0])
                links.new(bsdf.outputs[0], mix_shader.inputs[1])
                links.new(transparent_bsdf.outputs[0], mix_shader.inputs[2])           
                material.show_transparent_back = False
                
            material.node_tree.links.new(texture_node.outputs[0], bsdf.inputs[0])
        
        # Set default material properties
        material.blend_method = 'BLEND'
        material.shadow_method = 'CLIP'
        material.alpha_threshold = 0.5
        material.use_backface_culling = False       
        
        # Add material
        mesh_obj.data.materials.append(material)
    
    return mesh_obj

def fileio_write_xmpr(context, mesh_name, library_name, mode):
    mesh = bpy.data.objects[mesh_name]

    bone_names = []
    if mesh.parent and mesh.parent.type == 'ARMATURE':
        bone_names = list(get_bone_names(mesh.parent))

    indices, vertices, uvs, normals, colors, weights = get_mesh_info_and_weights(mesh, bone_names)

    # Cancel if mesh info is empty
    if not (indices or vertices or uvs or normals or colors):
        self.report({'ERROR'}, f"Mesh {mesh_name} has invalid or empty data, export canceled")
        return {'CANCELLED'}

    single_bind = None
    if mesh.parent_type == 'BONE' and mesh.parent_bone:
        single_bind = mesh.parent_bone

    draw_priority = mesh.data.level5_properties.draw_priority
    mesh_type = mesh.data.level5_properties.mesh_type

    texspace_array = [
        list(mesh.data.texspace_location),
        list(mesh.data.texspace_size)
    ]

    return xmpr.write(
        mesh.name_full, texspace_array,
        indices, vertices, uvs, normals, colors,
        weights, bone_names, library_name, mode,
        single_bind, draw_priority, mesh_type
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
        
    def template_items_callback(self, context):
        my_templates = get_templates()
        items = [(template.name, template.name, "") for template in my_templates]
        return items        

    def template_mode_items_callback(self, context):
        my_template = get_template_by_name(self.template_name)
        items = [(mode, mode, "") for mode in my_template.modes.keys()]
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
    
    template_name: EnumProperty(
        name="Templates",
        description="Choose a template",
        items=template_items_callback,
        default=0,
    )
    
    template_mode_name: EnumProperty(
        name="Mode",
        description="Choose a mode",
        items=template_mode_items_callback,
        default=0,
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
            
        if not self.template_name:
            self.report({'ERROR'}, "No template found")
            return {'FINISHED'}
            
        if not self.material_name:
            self.report({'ERROR'}, "Material name cannot be null")
            return {'FINISHED'}               
            
        with open(self.filepath, "wb") as f:
            template = get_template_by_name(self.template_name)
            mode = template.modes[self.template_mode_name]
            f.write(fileio_write_xmpr(context, self.mesh_name, self.material_name, mode))
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
