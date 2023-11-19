import os

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, EnumProperty

import bmesh

from math import radians

from ..formats import xmpr
from ..templates import templates

##########################################
# XMPR Function
##########################################

def get_bone_names(armature):
    for bone in armature.pose.bones:
        yield(bone.name)

def get_weights(mesh, bone_names):
    bone_indices = {name: i for i, name in enumerate(bone_names)}
    vertices_dict = {}  # Dictionnaire pour stocker les indices de boucle par vertex

    for face in mesh.data.polygons:
        for loop_index in face.loop_indices:
            vertex_index = mesh.data.loops[loop_index].vertex_index
            if vertex_index not in vertices_dict:
                vertices_dict[vertex_index] = len(vertices_dict)

    weights = {}  # Dictionnaire pour stocker les poids par vertex
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

def make_mesh(mesh, model_data, armature=None, texture=None):
    # Initialize lists to store vertex data
    positions = []
    normals = []
    uv_data = []
    weights = []
    bone_indices = []
    color_data = []

    # Fill the lists with data from model_data['vertices']
    for vertex_data in model_data['vertices']:
        positions.append(vertex_data['positions'])
        normals.append(vertex_data['normals'])
        uv_data.append(vertex_data['uv_data'])
        weights.append(vertex_data['weights'])
        bone_indices.append(vertex_data['bone_indices'])
        color_data.append(vertex_data['color_data'])
                
    bm = bmesh.from_edit_mesh(mesh)

    # Create vertices
    vertices = [bm.verts.new(pos) for pos in positions]
            
    # Update normals
    bm.normal_update()            
            
    # Create UV layers
    uv_layer = bm.loops.layers.uv.verify()
            
    # Create colors layer
    colors_layer = bm.loops.layers.color.new('Color')            

    # Create faces using triangle indices
    for face_indices in model_data['triangles']:
        v1_idx, v2_idx, v3_idx = face_indices
        v1 = vertices[v1_idx]
        v2 = vertices[v2_idx]
        v3 = vertices[v3_idx]

        # Create the face with normals associated with vertices
        face = bm.faces.new((v1, v2, v3))  

        # Assign normals to vertices
        for i, vert in enumerate(face.verts):
            vert.normal = normals[face_indices[i]]
                    
        # Assign UV coordinates to vertices
        for i, loop in enumerate(face.loops):
            loop[uv_layer].uv = uv_data[face_indices[i]]
                    
        # Assign colors to vertices
        for i, loop in enumerate(face.loops):
            loop[colors_layer] = color_data[face_indices[i]]                  
            
    # Update the mesh
    bmesh.update_edit_mesh(mesh)
            
    bm.free()
  
def fileio_write_xmpr(context, mesh_name, library_name, template):
    # Get Mesh
    mesh = bpy.data.objects[mesh_name]
    
    indices, vertices, uvs, normals, colors = get_mesh_information(mesh)
            
    bone_names = []
    if mesh.parent:
        if mesh.parent.type == 'ARMATURE':
            bone_names = list(get_bone_names(mesh.parent))
            
    weights = dict(get_weights(mesh, bone_names))  
            
    return xmpr.write(mesh.name_full, indices, vertices, uvs, normals, colors, weights, bone_names, library_name, template)

def fileio_open_xmpr(context, filepath):
    # Extract the file name without extension
    file_name = os.path.splitext(os.path.basename(filepath))[0]

    with open(filepath, 'rb') as file:
        # Open the XMPr file and read model data
        model_data = xmpr.open(file.read())

        # Create a new mesh object for each .prm file
        mesh = bpy.data.meshes.new(name=model_data['name'])
        mesh_obj = bpy.data.objects.new(name=model_data['name'], object_data=mesh)

        # Add the new mesh object to the scene
        bpy.context.collection.objects.link(mesh_obj)

        # Select the object and make it active
        bpy.context.view_layer.objects.active = mesh_obj
        mesh_obj.select_set(True)

        # Switch to edit mode
        bpy.ops.object.mode_set(mode='EDIT')

        # Create the mesh using the model data
        make_mesh(mesh, model_data)

        # Switch back to object mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        # Rotate the object 90 degrees around the X axis
        mesh_obj.rotation_euler = (radians(90), 0, 0)

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
        my_templates = templates.get_templates()
        items = [(template.name, template.name, "") for template in my_templates]
        return items        
        
    mesh_name: EnumProperty(
        name="Meshes",
        description="Choose mesh",
        items=item_callback,
        default=0,
    )
    
    template_name: EnumProperty(
        name="Templates",
        description="Choose a template",
        items=template_items_callback,
        default=0,
    )
    
    library_name: StringProperty(
        name="Library",
        description="Write a library name",
        default="",
    )    

    def execute(self, context):
        if (self.mesh_name == ""):
            self.report({'ERROR'}, "No mesh found")
            return {'FINISHED'}
            
        if (self.template_name == ""):
            self.report({'ERROR'}, "No template found")
            return {'FINISHED'}
            
        if (self.library_name == ""):
            self.report({'ERROR'}, "Library name cannot be null")
            return {'FINISHED'}               
            
        with open(self.filepath, "wb") as f:
            f.write(fileio_write_xmpr(context, self.mesh_name, self.library_name, templates.get_template_by_name(self.template_name)))
            return {'FINISHED'}  

class ImportXMPR(bpy.types.Operator, ImportHelper):
    bl_idname = "import.prm"
    bl_label = "Import a .prm"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".prm"
    filter_glob: StringProperty(default="*.prm", options={'HIDDEN'})
    
    def execute(self, context):
            return fileio_open_xmpr(context, self.filepath)            