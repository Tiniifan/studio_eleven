import os
import bpy
import math
from mathutils import Euler, Quaternion
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, EnumProperty, CollectionProperty

from ..formats import xcma
from ..controls import CameraElevenObject

##########################################
# XPCK Function
##########################################

def get_first_frame(camera):
    location_data = camera.animation_data.action.fcurves.find('location', index=0)  # Assumant que vous
    
    if location_data is None:
        return None
    
    for point in location_data.keyframe_points:
        if point.co[1] != location_data.keyframe_points[0].co[1]:
            return int(point.co[0])
    
    return None

def get_last_frame(cam_values):
    max_location = max(list(cam_values['location'].keys()))
    max_aim = max(list(cam_values['aim'].keys()))
    max_roll = max(list(cam_values['roll'].keys()))
    max_focal_length = max(list(cam_values['focal_length'].keys()))
    return max(max_location, max_aim, max_roll, max_focal_length)

def create_camera(frame_start, hash_name, cam_values):
    scene = bpy.context.scene
    scene.render.resolution_x = 400
    scene.render.resolution_y = 240
    
    level5_camera = CameraElevenObject.create(hash_name, [0, 0, 0])
    
    for frame, location in cam_values['location'].items():
        bpy.context.scene.frame_set(frame_start + frame)
        level5_camera.camera_obj.location = [location[0], location[2]*-1, location[1]]
        level5_camera.camera_obj.keyframe_insert(data_path="location")
            
    for frame, focal_length in cam_values['focal_length'].items():
        bpy.context.scene.frame_set(frame_start + frame)       
        level5_camera.camera_obj.data.lens = 33 + focal_length
        level5_camera.camera_obj.data.keyframe_insert(data_path="lens")

    for frame, roll in cam_values['roll'].items():
        bpy.context.scene.frame_set(frame_start + frame)       
        level5_camera.camera_obj.rotation_euler = (0, 0, math.radians(roll))
        level5_camera.camera_obj.keyframe_insert(data_path="rotation_euler", index=2)       

    for frame, location in cam_values['aim'].items():
        bpy.context.scene.frame_set(frame_start +frame)       
        level5_camera.target_obj.location = [location[0], location[2]*-1, location[1]]
        level5_camera.target_obj.keyframe_insert(data_path="location")    

def fileio_open_xcma(context, filepath):
    with open(filepath, 'rb') as file:    
        hash_name, cam_values = xcma.open(file.read())
        create_camera(0, hash_name, cam_values)

    return {'FINISHED'}
    
def fileio_write_xcma(context, filepath, hash_names, cam_values):     
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
