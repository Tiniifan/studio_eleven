import os

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, EnumProperty, CollectionProperty

import bmesh

from ..formats import xmpr, xpck, mbn, imgc, res
from .fileio_xmpr import *
from ..utils.img_format import *
from ..utils.img_tool import *
from ..templates import templates

##########################################
# XPCK Function
##########################################

def create_files_dict(extension, data_list):
    output = {}
    
    for i in range(len(data_list)):
        output[str(i).rjust(3,'0') + extension] = data_list[i]
        
    return output

def fileio_write_xpck(context, filepath, template, library_dict):
    armatures = []
    meshes = []
    
    # Get armature and meshes
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE":
            armatures.append(obj)
        elif obj.type == "MESH":
            meshes.append(obj)
    
    # Try to generate bones
    bones = {}
    if armatures is not []:
        for armature in armatures:
            for bone in armature.pose.bones:
                bones[bone.name] = mbn.write(bone)
    
    # Try to generate images and libraries
    images = {}
    libraries = {}
    if meshes is not []:
        for mesh in meshes:
            materials = []
            for mat_slot in mesh.material_slots:
                if mat_slot.material:
                    if mat_slot.material.node_tree:             
                        for x in mat_slot.material.node_tree.nodes:
                            if x.type=='TEX_IMAGE':
                                materials.append(x.image.name[:-4])
                                
                                if x.image.name[:-4] not in images:
                                    images[x.image.name[:-4]] = imgc.write(x.image, RGB565)
                                
                                libraries[library_dict[mesh.name]] = materials
                                
    
    # Try to generate .prm
    xmprs = []
    if meshes is not []:
        for mesh in meshes:          
                xmprs.append(fileio_write_xmpr(context, mesh.name, library_dict[mesh.name], template))
    
    # Create res
    resources = {}
    resources["libraries"] = libraries
    resources["textures"] = list(images.keys())
    resources["meshes"] = [mesh.name for mesh in meshes]
    resources["bones"] = list(bones.keys())
    my_res = res.write(resources)
    
    # Create files dict
    files = {}
    files.update(create_files_dict(".mbn", list(bones.values()) ))
    files.update(create_files_dict(".xi", list(images.values()) ))
    files.update(create_files_dict(".prm", xmprs))
    files["RES.bin"] = my_res
    for i in range(len(meshes)):
        formatted_num = "{:03d}".format(i)
        files[formatted_num + ".atr"] = bytes.fromhex("41545243303100000C000000E3010000054080FF0000C0C13C80BF0137F72F406005FFFFF0FFFF56")
        files[formatted_num + ".mtr"] = bytes.fromhex("4D545243303000001800000000000000000000000000000041070000350000F001501301801C0340037E04800B5013F043F055F0673079F819FEFE3E5003B08B803F5003F0F023F0B5F0C770D9E8891DA70000004C555443")
    
    # create xpck
    xpck.pack(files, filepath)
     
    return {'FINISHED'}

def fileio_open_xpck(context, filepath):
    file_name = os.path.splitext(os.path.basename(filepath))[0]
    obj = bpy.data.objects.new(name=file_name, object_data=None)
    
    archive = xpck.open_file(filepath)
    for file_name in archive:
        if file_name.endswith('.prm'):
            print(file_name)
            model_data = xmpr.open(archive[file_name])

            # Créer un nouvel objet mesh pour chaque fichier .prm
            mesh = bpy.data.meshes.new(name=model_data['name'])
            mesh_obj = bpy.data.objects.new(name=model_data['name'], object_data=mesh)

            # Ajouter le nouvel objet mesh à la scène
            bpy.context.collection.objects.link(mesh_obj)

            # Définir l'objet principal comme parent du nouvel objet mesh
            mesh_obj.parent = obj

            # Initialiser les listes pour stocker les données des sommets
            positions = []
            normals = []
            uv_data = []
            weights = []
            bone_indices = []
            color_data = []

            # Remplir les listes avec les données de model_data['vertices']
            for vertex_data in model_data['vertices']:
                positions.append(vertex_data['positions'])
                normals.append(vertex_data['normals'])
                uv_data.append(vertex_data['uv_data'])
                weights.append(vertex_data['weights'])
                bone_indices.append(vertex_data['bone_indices'])
                color_data.append(vertex_data['color_data'])

            # Select the object and make it active
            bpy.context.view_layer.objects.active = mesh_obj
            mesh_obj.select_set(True)

            bpy.ops.object.mode_set(mode='EDIT')
            
            bm = bmesh.from_edit_mesh(mesh)

            # Create vertices
            vertices = [bm.verts.new(pos) for pos in positions]
            
            # Update normals
            bm.normal_update()            
            
            # Create uv layers
            uv_layer = bm.loops.layers.uv.verify()
            
            # Create colors layer
            colors_layer = bm.loops.layers.color.new('Color')            

            # Create faces using triangle indices
            for face_indices in model_data['triangles']:
                v1_idx, v2_idx, v3_idx = face_indices
                v1 = vertices[v1_idx]
                v2 = vertices[v2_idx]
                v3 = vertices[v3_idx]

                # Créer la face avec les normales associées aux sommets
                face = bm.faces.new((v1, v2, v3))  

                # Affecter les normales aux sommets
                for i, vert in enumerate(face.verts):
                    vert.normal = normals[face_indices[i]]
                    
                # Affecter les coordonnées UV aux sommets
                for i, loop in enumerate(face.loops):
                    loop[uv_layer].uv = uv_data[face_indices[i]]
                    
                # Affecter les couleurs aux sommets
                for i, loop in enumerate(face.loops):
                    loop[colors_layer] = color_data[face_indices[i]]                  
            
            # Update the mesh
            bmesh.update_edit_mesh(mesh)
            
            bm.free()

            # Switch back to object mode
            bpy.ops.object.mode_set(mode='OBJECT')
                
    # Ajouter l'objet principal à la scène
    bpy.context.collection.objects.link(obj)
    
    return {'FINISHED'}

       
##########################################
# Register class
##########################################

class LibraryCollectionProperty(bpy.types.PropertyGroup):
    mesh_name: StringProperty(name="", default="")
    library_name: StringProperty(name="", default="")     
    
class ExportXC(bpy.types.Operator, ExportHelper):
    bl_idname = "export.xc"
    bl_label = "Export to xc"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".xc"
    filter_glob: StringProperty(default="*.xc", options={'HIDDEN'})

    def template_items_callback(self, context):
        my_templates = templates.get_templates()
        items = [(template.name, template.name, "") for template in my_templates]
        return items   
    
    template_name: EnumProperty(
        name="Templates",
        description="Choose a template",
        items=template_items_callback,
        default=0,
    )
    
    prop_collection: CollectionProperty(type=LibraryCollectionProperty)
    
    def invoke(self, context, event):
        wm = context.window_manager        
        self.prop_collection.clear()
        
        meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        for mesh in meshes:
            item = self.prop_collection.add()
            item.mesh_name = mesh.name
            item.library_name = "DefaultLib." + mesh.name
            
        wm.fileselect_add(self)    

        return {'RUNNING_MODAL'}
    
    def draw(self, context):
        layout = self.layout
        
        layout.prop(self, "template_name", text="Template")   
        
        lib_names_box = layout.box()
        lib_names_box.label(text="Librairies names")

        for prop in self.prop_collection:
            row = lib_names_box.row()
            row.prop(prop, "library_name", text=prop.mesh_name)
        
    def execute(self, context):
        if (self.template_name == ""):
            self.report({'ERROR'}, "No template found")
            return {'FINISHED'}
            
        if all(not prop.library_name for prop in self.prop_collection):
            self.report({'ERROR'}, "All library names are empty")
            return {'FINISHED'}    
        
        library_dict = {prop.mesh_name: prop.library_name for prop in self.prop_collection}
        return fileio_write_xpck(context, self.filepath, templates.get_template_by_name(self.template_name), library_dict)
        
class ImportXC(bpy.types.Operator, ImportHelper):
    bl_idname = "import.xc"
    bl_label = "Import a .xc"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".xc"
    filter_glob: StringProperty(default="*.xc", options={'HIDDEN'})
    
    def execute(self, context):
            return fileio_open_xpck(context, self.filepath)