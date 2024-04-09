import os
import bpy
import math
from mathutils import Euler, Quaternion
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, EnumProperty, CollectionProperty

from ..formats import xcma

##########################################
# XPCK Function
##########################################

def fileio_write_xcma(context, filepath, hash_names, cam_values):     
    return {'FINISHED'}

def fileio_open_xcma(context, filepath):
    scene = bpy.context.scene
    
    hash_name, cam_values = xcma.open_file(filepath)
    
    camera = bpy.data.cameras.new(f"Camera_Frame_{hash_name}")
    camera_obj = bpy.data.objects.new(f"Camera_Frame_{hash_name}", camera)
    aim = bpy.data.meshes.new(f"Aim_Frame{hash_name}")
    aim_obj = bpy.data.objects.new(f"Aim_Frame{hash_name}", aim)
    scene.collection.objects.link(camera_obj)
    scene.collection.objects.link(aim_obj)


    for frame, location in cam_values['location'].items():
        bpy.context.scene.frame_set(frame)

        camera_obj.location = [location[0], location[2], location[1]]

        camera_obj.keyframe_insert(data_path="location")

    #max_key = max(list(cam_values['aim'].keys()))
    #last_aim = [cam_values['aim'][0][2]*-1, cam_values['aim'][0][1], cam_values['aim'][0][0]]
    for i in cam_values['aim']:
        bpy.context.scene.frame_set(i)
        
        if i in cam_values['aim']:
            x = cam_values['aim'][i][0]
            y = cam_values['aim'][i][2]
            z = cam_values['aim'][i][1]
            print(x**2 + y**2 + z**2)
            last_aim = [x, y, z]
            
        aim_obj.location = last_aim
        aim_obj.keyframe_insert(data_path="location")

    return {'FINISHED'}
      
##########################################
# Register class
##########################################
    
class ExportXCMA(bpy.types.Operator, ExportHelper):
    bl_idname = "export.cmr2"
    bl_label = "Export to cmr2"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".cmr2"
    filter_glob: StringProperty(default="*.cmr2", options={'HIDDEN'})

    def execute(self, context):
        return fileio_write_xcma(context, self.filepath, None, None)
        
class ImportXCMA(bpy.types.Operator, ImportHelper):
    bl_idname = "import.cmr2"
    bl_label = "Import a .cmr2"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".cmr2"
    filter_glob: StringProperty(default="*.cmr2", options={'HIDDEN'})
    
    def execute(self, context):
            return fileio_open_xcma(context, self.filepath)
