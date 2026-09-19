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
    first_frame = bpy.context.scene.frame_end
    camera_animation = camera.animation_data
    
    # Check if the camera has animation data and an action
    if camera_animation is not None and camera_animation.action is not None:
        # Loop in each fcurve type
        for fcurve in camera_animation.action.fcurves:
            if len(fcurve.keyframe_points) > 0:
                # Get the first keyframe point of the fcurve
                first_keyframe = fcurve.keyframe_points[0]
                frame = int(first_keyframe.co[0])
                
                # Update the first_frame if the frame of this keyframe is smaller
                if frame < first_frame:
                    first_frame = frame
 
    return first_frame

def get_last_frame(cam_values):
    # Get the maximum frame number for each camera parameter
    max_location = 0
    max_aim = 0
    max_roll = 0
    max_focal_length = 0
    
    if 'location' in cam_values:
        max_location = max(list(cam_values['location'].keys()))
        
    if 'aim' in cam_values:    
        max_aim = max(list(cam_values['aim'].keys()))
        
    if 'roll' in cam_values:    
        max_roll = max(list(cam_values['roll'].keys()))
        
    if 'focal_length' in cam_values:
        max_focal_length = max(list(cam_values['focal_length'].keys()))
    
    # Return the maximum frame number among all parameters
    return max(max_location, max_aim, max_roll, max_focal_length)

def create_camera(frame_start, hash_name, cam_values):
    # Get the current scene
    scene = bpy.context.scene
    
    # Set render resolution
    scene.render.resolution_x = 400
    scene.render.resolution_y = 240
    
    # Create the camera object
    level5_camera = CameraElevenObject.create(hash_name, [0, 0, 0])
    
    # Set keyframes for camera location
    if 'location' in cam_values:
        for frame, location in cam_values['location'].items():
            bpy.context.scene.frame_set(frame_start + frame)
            level5_camera.camera_obj.location = [location[0], location[2]*-1, location[1]]
            level5_camera.camera_obj.keyframe_insert(data_path="location")
            
    # Set keyframes for focal length
    if 'focal_length' in cam_values:
        for frame, focal_length in cam_values['focal_length'].items():
            bpy.context.scene.frame_set(frame_start + frame)       
            level5_camera.camera_obj.data.lens = 33 + focal_length
            level5_camera.camera_obj.data.keyframe_insert(data_path="lens")

    # Set keyframes for camera roll
    if 'roll' in cam_values:
        for frame, roll in cam_values['roll'].items():
            bpy.context.scene.frame_set(frame_start + frame)       
            level5_camera.camera_obj.rotation_euler = (0, 0, roll) # the roll is in radians
            level5_camera.camera_obj.keyframe_insert(data_path="rotation_euler", index=2)       

    # Set keyframes for target location (aim)
    if 'aim' in cam_values:
        for frame, location in cam_values['aim'].items():
            bpy.context.scene.frame_set(frame_start +frame)       
            level5_camera.target_obj.location = [location[0], location[2]*-1, location[1]]
            level5_camera.target_obj.keyframe_insert(data_path="location")

    return level5_camera

def set_camera_settings(level5_camera, camera, archive_name=""):
    """Remember the animation of an imported camera (the file only stores the hash of its name)."""
    camera_eleven = level5_camera.camera_obj.parent

    if camera_eleven is None:
        return

    camera_eleven.level5_camera.animation_name = "0x%08X" % camera['hash']
    camera_eleven.level5_camera.speed = max(0.1, camera['speed'])
    camera_eleven.level5_camera.archive_name = archive_name

def fileio_open_xcma(context, filepath):
    file_name = os.path.splitext(os.path.basename(filepath))[0]
    
    # Open the XCMA file in binary mode
    with open(filepath, 'rb') as file:    
        # Read the contents of the file and extract hash name and camera values
        camera = xcma.read(file.read())
        level5_camera = create_camera(0, file_name, camera['values'])
        set_camera_settings(level5_camera, camera)

    return {'FINISHED'}
    
def fileio_write_xcma(context, animation_name, camera_speed, camera, target, version="V2"):
    # Get the current scene
    scene = context.scene
    
    # Dictionary to store camera and target data for each frame
    cam_values = {
        'location': {},
        'aim': {},
        'focal_length': {},
        'roll': {}
    }

    # Get the first frame of animation
    first_frame = get_first_frame(camera)

    # Process camera animation
    camera_animation = camera.animation_data
    if camera_animation is not None and camera_animation.action is not None:
        for fcurve in camera_animation.action.fcurves:
            num_keyframes = len(fcurve.keyframe_points)
            for idx, keyframe in enumerate(fcurve.keyframe_points):
                frame = int(keyframe.co[0])
                scene.frame_set(frame)

                # Check if the keyframe is the first or the last
                if idx == 0 or idx == num_keyframes - 1:
                    cam_values['location'][frame-first_frame] = [camera.location.x, camera.location.z, camera.location.y*-1]
                    cam_values['focal_length'][frame-first_frame] = camera.data.lens - 33
                    cam_values['roll'][frame-first_frame] = camera.rotation_euler.z # the roll is in radians
                else:
                    if 'location' in fcurve.data_path:
                        cam_values['location'][frame-first_frame] = [camera.location.x, camera.location.z, camera.location.y*-1]
                        
                    if 'lens' in fcurve.data_path:
                        cam_values['focal_length'][frame-first_frame] = camera.data.lens - 33
                        
                    if 'rotation_euler' in fcurve.data_path:
                        cam_values['roll'][frame-first_frame] = camera.rotation_euler.z # the roll is in radians

    # Process target animation
    target_animation = target.animation_data
    if target_animation is not None and target_animation.action is not None:
        for fcurve in target_animation.action.fcurves:
            num_keyframes = len(fcurve.keyframe_points)
            for idx, keyframe in enumerate(fcurve.keyframe_points):
                frame = int(keyframe.co[0])
                scene.frame_set(frame)
                
                # Check if the keyframe is the first or the last
                if idx == 0 or idx == num_keyframes - 1:
                    cam_values['aim'][frame-first_frame] = [target.location.x, target.location.z, target.location.y*-1]
                else:
                    if 'location' in fcurve.data_path:
                        cam_values['aim'][frame-first_frame] = [target.location.x, target.location.z, target.location.y*-1]

    # Sort keyframes
    for key in cam_values:
        cam_values[key] = dict(sorted(cam_values[key].items()))

    return xcma.write(animation_name, camera_speed, cam_values, version)
         
##########################################
# Register class
##########################################
    
class ExportXCMA(bpy.types.Operator, ExportHelper):
    bl_idname = "export.cmr2"
    bl_label = "Export to cmr2"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".cmr2"
    filter_glob: StringProperty(default="*.cmr2", options={'HIDDEN'})

    def item_callback(self, context):
        items = []
        
        # Get cameras
        for obj in bpy.context.scene.objects:
            if CameraElevenObject.is_camera_eleven(obj):
                items.append((obj.name, obj.name, ""))

        return items      
        
    camera_name: EnumProperty(
        name="Cameras",
        description="Choose camera",
        items=item_callback,
        default=0,
    )
    
    camera_speed: bpy.props.FloatProperty(
        name="Camera speed",
        description="Set the camera speed",
        default=1.0,
        min=0.1,
        precision=2
    )      
    
    animation_name: StringProperty(
        name="Animation name",
        description="Write a animation name (empty: use the name saved on the camera)",
        default="",
    )

    version: EnumProperty(
        name="Version",
        description="Camera format version",
        items=[
            ("V1", "V1", "Inazuma Eleven Go"),
            ("V2", "V2", "Other games"),
        ],
        default="V2",
    )

    def execute(self, context):
        if (self.camera_name == ""):
            self.report({'ERROR'}, "No camera found")
            return {'FINISHED'}

        camera_eleven = bpy.data.objects.get(self.camera_name)

        animation_name = self.animation_name
        if animation_name == "":
            animation_name = camera_eleven.level5_camera.animation_name

        if (animation_name == ""):
            self.report({'ERROR'}, "Animation name cannot be null")
            return {'FINISHED'}

        with open(self.filepath, "wb") as f:
            camera, target = CameraElevenObject.get_camera_and_target(camera_eleven)
            f.write(fileio_write_xcma(context, animation_name, self.camera_speed, camera, target, self.version))
            return {'FINISHED'}
        
class ImportXCMA(bpy.types.Operator, ImportHelper):
    bl_idname = "import.cmr2"
    bl_label = "Import a .cmr2"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".cmr2"
    filter_glob: StringProperty(default="*.cmr2", options={'HIDDEN'})
    
    def execute(self, context):
            return fileio_open_xcma(context, self.filepath)
