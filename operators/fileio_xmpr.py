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

def get_weights(mesh, bone_names):
    bone_indices = {name: i for i, name in enumerate(bone_names)}
    vertices_dict = {}

    for face in mesh.data.polygons:
        for loop_index in face.loop_indices:
            vertex_index = mesh.data.loops[loop_index].vertex_index
            if vertex_index not in vertices_dict:
                vertices_dict[vertex_index] = len(vertices_dict)

    weights = {}
    for vertex_index, vertex_dict_index in vertices_dict.items():
        vertex = mesh.data.vertices[vertex_index]
        weights[vertex_dict_index] = {}
        for group in vertex.groups:
            if group.weight != 0:
                bone_name = mesh.vertex_groups[group.group].name
                bone_index = bone_indices.get(bone_name)
                if bone_index is not None:
                    weights[vertex_dict_index][bone_index] = group.weight

    return weights
            
def get_mesh_information(mesh):
    vertices_dict = {}
    uv_dict = {}
    normal_dict = {}
    color_dict = {}
    face_indices = []

    vertices_info = {}
    uv_info = {}
    normal_info = {}
    color_info = {}
    
    obj_matrix = mesh.matrix_world

    if mesh.data.vertex_colors.active is not None:
        vertex_colors = mesh.data.vertex_colors.active.data

    for face in mesh.data.polygons:
        face_index = {}
        indices = []
        vt_indices = []
        vn_indices = []
        color_indices = []

        for loop_index in face.loop_indices:
            vertex_index = mesh.data.loops[loop_index].vertex_index
            
            if vertex_index not in vertices_dict:
                vertices_dict[vertex_index] = len(vertices_dict)
                vertices_info[vertices_dict[vertex_index]] = mesh.data.vertices[vertex_index].co 

            indices.append(vertices_dict[vertex_index])

            uv = tuple(mesh.data.uv_layers.active.data[loop_index].uv)
            if uv not in uv_dict:
                uv_dict[uv] = len(uv_dict)
                uv_info[uv_dict[uv]] = uv
            vt_indices.append(uv_dict[uv])

            normal = tuple(mesh.data.vertices[vertex_index].normal)
            if normal not in normal_dict:
                normal_dict[normal] = len(normal_dict)
                normal_info[normal_dict[normal]] = normal
            vn_indices.append(normal_dict[normal])

            if mesh.data.vertex_colors.active is not None:
                color = vertex_colors[loop_index].color
                if color not in color_dict:
                    color_dict[color] = len(color_dict)
                    color_info[color_dict[color]] = color
                color_indices.append(color_dict[color])

        face_index["v"] = indices
        face_index["vt"] = vt_indices
        face_index["vn"] = vn_indices
        face_index["vc"] = color_indices
        face_indices.append(face_index)

    return face_indices, vertices_info, uv_info, normal_info, color_info

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
    
    mesh.level5_properties.draw_priority = draw_priority
    
    mesh.from_pydata(positions, [], model_data["triangles"])
    
    if normals:
        mesh.normals_split_custom_set_from_vertices(normals)
    
    texprojs = ["UVMap0", "UVMap1", "UVMap2", "UVMap3"] # prm can't have more than 4 UVMaps
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
        for loop_idx, color in enumerate(color_data):
            color_layer.data[loop_idx].color = color
    
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
    # Get Mesh
    mesh = bpy.data.objects[mesh_name]
    
    indices, vertices, uvs, normals, colors = get_mesh_information(mesh)
    
    bone_names = []
    if mesh.parent:
        if mesh.parent.type == 'ARMATURE':
            bone_names = list(get_bone_names(mesh.parent))
            
    weights = dict(get_weights(mesh, bone_names))

    single_bind = None
    if mesh.parent_type == 'BONE':
       if mesh.parent_bone:
            single_bind = mesh.parent_bone
            
    draw_priority = mesh.level5_properties.draw_priority
    
    return xmpr.write(mesh.name_full, mesh.dimensions, indices, vertices, uvs, normals, colors, weights, bone_names, library_name, mode, single_bind, draw_priority)

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

    def update_mesh_name(self, context):
        """Update function for mesh_name property."""
        obj = bpy.data.objects.get(self.mesh_name)  # Retrieve the mesh object by name
        if obj and obj.type == 'MESH':
            materials = obj.data.materials  # Access materials of the mesh
            if materials and materials[0]:  # Check if at least one material exists
                self.material_name = materials[0].name
            else:
                self.material_name = f"DefautLib.{self.mesh_name}"  # Default value if no material exists

    mesh_name: EnumProperty(
        name="Meshes",
        description="Choose mesh",
        items=item_callback,
        default=0,
        update=update_mesh_name,  # Link the update function
    )
    
    template_name: EnumProperty(
        name="Templates",
        description="Choose a template",
        items=template_items_callback,
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
            f.write(fileio_write_xmpr(context, self.mesh_name, self.material_name, get_template_by_name(self.template_name)))
            return {'FINISHED'}

    def invoke(self, context, event):
        """Ensure the update function is called on the menu launch."""
        self.update_mesh_name(context)  # Call the update function to initialize values
        return super().invoke(context, event)

class ImportXMPR(bpy.types.Operator, ImportHelper):
    bl_idname = "import.prm"
    bl_label = "Import a .prm"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".prm"
    filter_glob: StringProperty(default="*.prm", options={'HIDDEN'})
    
    def execute(self, context):
            return fileio_open_xmpr(context, self.filepath)            
