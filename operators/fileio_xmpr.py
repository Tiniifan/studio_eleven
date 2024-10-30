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
    # Create a new mesh object
    mesh = bpy.data.meshes.new(name=model_data['name'])
    mesh_obj = bpy.data.objects.new(name=model_data['name'], object_data=mesh)

    # Add the new mesh object to the scene
    bpy.context.collection.objects.link(mesh_obj)

    # Select the object and make it active
    bpy.context.view_layer.objects.active = mesh_obj
    mesh_obj.select_set(True)

    # Switch to edit mode
    bpy.ops.object.mode_set(mode='EDIT')

    # Initialize array to store vertex data
    positions = []
    normals = []
    uv_data = []
    weights = []
    bone_indices = []
    color_data = []
    single_bind = model_data['single_bind']

    # Fill the array with data from model_data['vertices']
    for vertex_data in model_data['vertices']:
        if 'positions' in vertex_data:
            positions.append(vertex_data['positions'])
      
        if 'normals' in vertex_data:
            normals.append(vertex_data['normals'])
            
        if 'uv_data' in vertex_data:    
            uv_data.append(vertex_data['uv_data'])
            
        if 'weights' in vertex_data:
            weights.append(vertex_data['weights'])
            
        if 'bone_indices' in vertex_data:    
            bone_indices.append(vertex_data['bone_indices'])
            
        if 'color_data' in vertex_data:
            color_data.append(vertex_data['color_data'])        
    
    bm = bmesh.from_edit_mesh(mesh)

    # Create vertices
    vertices = [bm.verts.new(pos) for pos in positions]
                        
    # Update normals
    bm.normal_update()            
            
    # Create uv layers
    uv_layer = bm.loops.layers.uv.verify()
    
    vertex_group_mapping = {}
                    
    # Create colors layer
    colors_layer = bm.loops.layers.color.new('Color')            

    # Create faces using triangle indices
    for face_indices in model_data['triangles']:
        if isinstance(face_indices, int):
            continue
        else:
            v1_idx, v2_idx, v3_idx = face_indices

        v1 = vertices[v1_idx]
        v2 = vertices[v2_idx]
        v3 = vertices[v3_idx]

        # Check if the face already exists
        existing_face = None
        for existing_face in bm.faces:
            if (existing_face.verts[0] == v1 and
                existing_face.verts[1] == v2 and
                existing_face.verts[2] == v3):
                break
        else:
            # Face doesn't exist, create a new one
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

            # Collect vertex and bone index mapping
            for i, vert in enumerate(face.verts):
                index = face_indices[i]
                vert_weights = weights[face_indices[i]]

                for j, weight in enumerate(vert_weights):
                    if face_indices[i] < len(bone_indices):
                        bone_crc32 = bone_indices[face_indices[i]][j]
                        
                        if bones != None:
                            if bone_crc32 in bones:
                                bone_name = bones[bone_crc32]
                                if index not in vertex_group_mapping:
                                    vertex_group_mapping[index] = []
                                vertex_group_mapping[index].append((bone_name, weight))
           
    # Update the mesh
    bmesh.update_edit_mesh(mesh)
    
    # Memory free
    bm.free()
    
    # Switch back to object mode
    bpy.ops.object.mode_set(mode='OBJECT')

    # Assign weights to vertex groups
    for vert_index, group_data in vertex_group_mapping.items():
        for bone_name, weight in group_data:
            vertex_group = mesh_obj.vertex_groups.get(bone_name)

            if not vertex_group:
                vertex_group = mesh_obj.vertex_groups.new(name=bone_name)

            # Assign weight to the vertex group
            if weight > 0:
                vertex_group.add([vert_index], weight, 'REPLACE')    

    # Rotate the mesh 90 degrees around the X axis
    mesh_obj.rotation_euler = (radians(90), 0, 0)
    
    # Link mesh to armature
    if armature:
        if mesh_obj.vertex_groups:
            # Créer un dictionnaire pour stocker les influences par os
            bone_influences = {bone.name: 0.0 for bone in armature.data.bones}

            # Parcourir tous les vertices de la mesh
            for vertex in mesh_obj.data.vertices:
                # Vérifier les groupes de vertices associés à chaque vertex
                for group in vertex.groups:
                    group_name = mesh_obj.vertex_groups[group.group].name
                    if group_name in bone_influences:
                        # Ajouter l'influence au total pour chaque os
                        bone_influences[group_name] += group.weight
            
            # Trouver l'os avec l'influence totale la plus élevée
            most_influential_bone = armature.pose.bones.get(max(bone_influences, key=bone_influences.get))
            
            # Récupérer la matrice de transformation du bone le plus influent en espace monde
            bone_world_matrix = armature.matrix_world @ most_influential_bone.matrix
            bone_world_location = bone_world_matrix.translation
            
            # déplacer la mesh vers le bone le plus influent
            print(mesh_obj.name, bone_world_location.x, bone_world_location.y, bone_world_location.z, most_influential_bone.name)
            if bone_world_location.y > 400:
                mesh_obj.location.y = bone_world_location.y  

        bpy.ops.object.select_all(action='DESELECT')
        mesh_obj.select_set(True)
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
        bpy.ops.object.parent_set(type='ARMATURE', keep_transform=True)
        
        # Créer une relation mesh au bone
        if single_bind != None:
            mesh_obj.parent_type = 'BONE'
            mesh_obj.parent_bone = single_bind
            mesh_obj.rotation_euler = (0, 0, 0)
    
    # Link textures to mesh
    if lib:
        # Create a new material for the mesh
        mat = bpy.data.materials.new(name=model_data['material_name'])
        mat.use_nodes=True 
        
        material_output = mat.node_tree.nodes.get('Material Output')
        principled_BSDF = mat.node_tree.nodes.get('Principled BSDF')

        for texture in lib:
            tex_node = mat.node_tree.nodes.new('ShaderNodeTexImage')
            tex_node.image = texture
            
            # Check if the texture has an alpha channel
            if texture.alpha_mode != "NONE":
                # Enable the use of the alpha channel in the material
                principled_BSDF.inputs["Alpha"].default_value = 1.0

                # Set the material blend mode to 'BLEND' for alpha blending
                mat.blend_method = 'BLEND'

                # Connect the alpha output of the texture to the Alpha input of Principled BSDF
                mat.node_tree.links.new(tex_node.outputs["Alpha"], principled_BSDF.inputs["Alpha"])
            
            # Connect the color output of the texture to the Base Color input of Principled BSDF
            mat.node_tree.links.new(tex_node.outputs[0], principled_BSDF.inputs[0])
        
        mesh_obj.data.materials.append(mat)
    
    # Rename uv layers and add uv warp modifier
    if txp_data:
        for txp in txp_data:
            if txp[1] == model_data['material_name']:
                mesh_obj.data.uv_layers[0].name = txp[0]
                #print(mesh_obj.modifiers)
                mesh_obj.modifiers.new(name=txp[0], type="UV_WARP")
                mesh_obj.modifiers[txp[0]].uv_layer = mesh_obj.data.uv_layers[0].name

def fileio_write_xmpr(context, mesh_name, library_name, mode):
    # Get Mesh
    mesh = bpy.data.objects[mesh_name]
    
    indices, vertices, uvs, normals, colors = get_mesh_information(mesh)
    
    bone_names = []
    if mesh.parent:
        if mesh.parent.type == 'ARMATURE':
            bone_names = list(get_bone_names(mesh.parent))
            
    weights = dict(get_weights(mesh, bone_names))  
    
    return xmpr.write(mesh.name_full, mesh.dimensions, indices, vertices, uvs, normals, colors, weights, bone_names, library_name, mode)

def fileio_open_xmpr(context, filepath):
    # Extract the file name without extension
    file_name = os.path.splitext(os.path.basename(filepath))[0]

    with open(filepath, 'rb') as file:
        # Open the XMPr file and read model data
        mesh_data = xmpr.open(file.read())

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
            f.write(fileio_write_xmpr(context, self.mesh_name, self.library_name, get_template_by_name(self.template_name)))
            return {'FINISHED'}  

class ImportXMPR(bpy.types.Operator, ImportHelper):
    bl_idname = "import.prm"
    bl_label = "Import a .prm"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".prm"
    filter_glob: StringProperty(default="*.prm", options={'HIDDEN'})
    
    def execute(self, context):
            return fileio_open_xmpr(context, self.filepath)            
