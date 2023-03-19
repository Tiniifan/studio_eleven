import os
import bpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, EnumProperty

from ..formats import xmpr, xpck, mbn, imgc, res
from .fileio_xmpr import *

##########################################
# XPCK Function
##########################################

def create_files_dict(extension, data_list):
    output = {}
    
    for i in range(len(data_list)):
        output[str(i).rjust(3,'0') + extension] = data_list[i]
        
    return output

def fileio_write_xpck(context, filepath):
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
    
    # Try to generate images
    images = {}
    materials = {}
    if meshes is not []:
        for mesh in meshes:
            for mat_slot in mesh.material_slots:
                if mat_slot.material:
                    materials[mat_slot.name] = []
                    if mat_slot.material.node_tree:             
                        for x in mat_slot.material.node_tree.nodes:
                            if x.type=='TEX_IMAGE':
                                materials[mat_slot.name].append(x.image.name[:-4])
                                if x.image.name[:-4] not in images:
                                    images[x.image.name[:-4]] = imgc.write(x.image, RGB565)
    
    # Try to generate .prm
    xmprs = []
    if meshes is not []:
        for mesh in meshes:          
                xmprs.append(fileio_write_xmpr(context, mesh.name))
    
    # Create res
    library = {}
    library["material"] = materials
    library["material2"] = materials
    library["texture"] = list(images.keys())
    library["materialconfig"] = materials
    library["mesh"] = [mesh.name for mesh in meshes]
    library["bone"] = list(bones.keys())
    my_res = res.write(library)
    
    # Create files dict
    files = {}
    files.update(create_files_dict(".mbn", list(bones.values()) ))
    files.update(create_files_dict(".xi", list(images.values()) ))
    files.update(create_files_dict(".prm", xmprs))
    files["RES.bin"] = my_res
    files["000.atr"] = bytes.fromhex("41545243303100000C000000E3010000054080FF0000C0C13C80BF0137F72F406005FFFFF0FFFF56")
    files["000.mtr"] = bytes.fromhex("4D545243303000001800000000000000000000000000000041070000350000F001501301801C0340037E04800B5013F043F055F0673079F819FEFE3E5003B08B803F5003F0F023F0B5F0C770D9E8891DA70000004C555443")
    
    # create xpck
    xpck.pack(files, filepath)
     
    return {'FINISHED'}


##########################################
# Register class
##########################################     
    
class ExportXC(bpy.types.Operator, ExportHelper):
    bl_idname = "export.xc"
    bl_label = "Export to xc"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".xc"
    filter_glob: StringProperty(default="*.xc", options={'HIDDEN'})

    def execute(self, context):
        return fileio_write_xpck(context, self.filepath) 