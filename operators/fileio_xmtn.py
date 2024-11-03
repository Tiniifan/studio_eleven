import io
import os
import zlib

from mathutils import Vector, Euler, Matrix, Quaternion

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, EnumProperty

from ..animation import *
from ..formats import  animation_manager, animation_support, res

##########################################
# XMTN Function
##########################################

def crc32_hash(name):
    return zlib.crc32(name.encode())

def find_bone_by_crc32(armature, crc32):
    for bone in armature.bones:
        if crc32_hash(bone.name) == crc32:
            return bone
            
    return None

def find_armatures_with_bones(bone_name_hashes):
    armatures = []

    for armature_obj in bpy.data.objects:
        if armature_obj.type == 'ARMATURE' and armature_obj.data:
            armature = armature_obj.data
            contains_any_bone = any(find_bone_by_crc32(armature, crc32) is not None for crc32 in bone_name_hashes)
            
            if contains_any_bone:
                armatures.append(armature_obj)

    return armatures

def calculate_transformed_location(pose_bone, location):
    parent = pose_bone.parent
    while parent and not parent.bone.use_deform:
        parent = parent.parent

    pose_matrix = pose_bone.matrix
    if parent:
        parent_matrix = parent.matrix
        pose_matrix = parent_matrix.inverted() @ pose_matrix

    return pose_matrix.inverted() @ location
    
def calculate_transformed_rotation(pose_bone, rotation):
    parent = pose_bone.parent
    while parent and not parent.bone.use_deform:
        parent = parent.parent

    pose_matrix = pose_bone.matrix
    if parent:
        parent_matrix = parent.matrix
        pose_matrix = parent_matrix.inverted() @ pose_matrix

    # Create a Quaternion directly from Euler angles
    rotation_quaternion = Quaternion(rotation)

    # Convert quaternion rotation to Matrix
    rotation_matrix = rotation_quaternion.to_matrix().to_4x4()

    # Multiply pose matrix by rotation matrix
    transformed_matrix = pose_matrix.inverted() @ rotation_matrix

    # Extract quaternion from the result
    transformed_quaternion = transformed_matrix.to_quaternion()

    return transformed_quaternion
    
def calculate_transformed_scale(pose_bone, scale):
    parent = pose_bone.parent
    while parent and not parent.bone.use_deform:
        parent = parent.parent

    pose_matrix = pose_bone.matrix
    if parent:
        parent_matrix = parent.matrix
        pose_matrix = parent_matrix.inverted() @ pose_matrix

    # Create scale matrices for each axis
    scale_matrix_x = Matrix.Scale(scale[0], 4, (1, 0, 0))
    scale_matrix_y = Matrix.Scale(scale[1], 4, (0, 1, 0))
    scale_matrix_z = Matrix.Scale(scale[2], 4, (0, 0, 1))

    # Multiply pose matrix by scale matrices
    transformed_matrix = pose_matrix.inverted() @ (scale_matrix_x @ scale_matrix_y @ scale_matrix_z)

    # Extract scales from the result
    transformed_scale = transformed_matrix.to_scale()

    return transformed_scale

def create_animation(animation, armature_obj):
    scene = bpy.context.scene
    armature = armature_obj.data
    
    # Switch to Pose Mode
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='POSE')
    
    if armature_obj.animation_data:
        armature_obj.animation_data_clear()
        
    scene.frame_start = 0
    scene.frame_end = animation.FrameCount
    
    bpy.context.scene.frame_set(0)
    bpy.ops.pose.select_all(action='SELECT')
    bpy.ops.pose.transforms_clear()
    
    # Create an action for the animation
    action = bpy.data.actions.new(name=animation.AnimationName)
    
    # Loop through each track in animdata
    for track in animation.Tracks:
        for node in track.Nodes:
            if track.Name.startswith("Bone") and not track.Name == "BoneBool":
                bone = find_bone_by_crc32(armature, node.Name)
                if bone is None:
                    continue
        
                pose_bone = armature_obj.pose.bones.get(bone.name)
                if not pose_bone:
                    print(f"Pose bone {bone.name} not found.")
                    continue
                
                # Determine the transformation channel
                if track.Name == "BoneLocation":
                    data_path = f'pose.bones["{pose_bone.name}"].location'
                    indices = [0, 1, 2]  # X, Y, Z location
                elif track.Name == "BoneRotation":
                    data_path = f'pose.bones["{pose_bone.name}"].rotation_quaternion'
                    indices = [0, 1, 2, 3]  # W, X, Y, Z quaternion
                elif track.Name == "BoneScale":
                    data_path = f'pose.bones["{pose_bone.name}"].scale'
                    indices = [0, 1, 2]  # X, Y, Z scale
                else:
                    continue
                
                # Add fcurves and keyframes
                for index in indices:
                    fcurve = action.fcurves.find(data_path=data_path, index=index)
                    if not fcurve:
                        fcurve = action.fcurves.new(data_path=data_path, index=index)
                    for frame in node.Frames:
                        frame_num = frame.Key
                        value = frame.Value
                        
                        if track.Name == "BoneLocation":
                            transformation = calculate_transformed_location(pose_bone, Vector([value.X, value.Y, value.Z]))
                            fcurve.keyframe_points.insert(frame=frame_num, value=transformation[index])
                        elif track.Name == "BoneRotation":
                            transformation = calculate_transformed_rotation(pose_bone, Vector([value.W, value.X, value.Y, value.Z]))
                            fcurve.keyframe_points.insert(frame=frame_num, value=transformation[index])
                        elif track.Name == "BoneScale":
                            transformation = calculate_transformed_scale(pose_bone, Vector([value.X, value.Y, value.Z]))
                            fcurve.keyframe_points.insert(frame=frame_num, value=transformation[index])
            
            #elif track.Name == "MaterialTransparency":
            #    bpy.ops.object.mode_set(mode='OBJECT')
            
            #elif track.Name.startswith("UV"):
            #    nodeName = resData[res.RESType.Textproj][node.Name]
            #    
            #    bpy.ops.object.mode_set(mode='OBJECT')
            #    
            #    for mesh in bpy.data.meshes:
            #        for obj in bpy.data.objects:
            #            if obj.data == mesh:
            #                modifier = obj.modifiers.get(nodeName)
            #                if modifier:
            #                    for frame in node.Frames:
            #                        frame_num = frame.Key
            #                        value = frame.Value
            #                        
            #                        if track.Name == "UVMove":
            #                            modifier.offset[0] = value.X
            #                            modifier.offset[1] = value.Y
            #                            modifier.keyframe_insert(data_path="offset", index=0, frame=frame_num)
            #                            modifier.keyframe_insert(data_path="offset", index=1, frame=frame_num)
            #                        if track.Name == "UVScale":
            #                            modifier.scale[0] = value.X
            #                            modifier.scale[1] = value.Y
            #                            modifier.keyframe_insert(data_path="scale", index=0, frame=frame_num)
            #                            modifier.keyframe_insert(data_path="scale", index=1, frame=frame_num)
            #                        if track.Name == "UVRotate":
            #                            modifier.rotation[0] = value.X
            #                            modifier.keyframe_insert(data_path="rotation", index=0, frame=frame_num)
            else:
                pass

    # Assign the created action to the armature object
    armature_obj.animation_data_create()
    armature_obj.animation_data.action = action
                
def fileio_open_xmtn(operator, context, filepath):
    animation_name = ""
    frame_count = 0
    bone_name_hashes = []
    animation = None
        
    file_name = os.path.splitext(os.path.basename(filepath))[0]
    file_extension = os.path.splitext(filepath)[1]
    
    # Check if there is an active object and if it's an armature
    active_obj = bpy.context.active_object
    if not active_obj or active_obj.type != 'ARMATURE':
        operator.report({'ERROR'}, 'No armature selected or active.')
        return {'CANCELLED'}

    armature_obj = bpy.context.active_object    
    
    if file_extension == ".mtn2" or file_extension == ".mtn3":
        with open(filepath, 'rb') as file:
            animation = animation_manager.AnimationManager(reader=io.BytesIO(file.read()))
    else:
        operator.report({'ERROR'}, f"Unsupported file format '{file_extension}'. Please use .mtn2 or .mtn3.")
        return {'FINISHED'}

    create_animation(animation, armature_obj)
    
    return {'FINISHED'}

def fileio_write_xmtn(context, armature_name, animation_name, animation_format):   
    scene = context.scene
    
    armature = bpy.data.objects[armature_name]
    armature.data.pose_position = 'POSE'
    bpy.context.view_layer.objects.active = armature
    
    bpy.ops.object.mode_set(mode='POSE')

    # Create tracks
    tracks = []
    tracks.append(animation_manager.Track('BoneLocation', 0, []))
    tracks.append(animation_manager.Track('BoneRotation', 1, []))
    tracks.append(animation_manager.Track('BoneScale', 2, []))
    
    # Checks if the armature has an animation
    if armature.animation_data and armature.animation_data.action:
        action = armature.animation_data.action
        
        keyframes_data = {}

        for fcurve in action.fcurves:
            data_path = fcurve.data_path
            bone_name = data_path.split('"')[1] if '"' in data_path else None

            if bone_name:
                # Determine the type of transformation
                if 'location' in data_path:
                    transformation_type = 'location'
                elif 'rotation' in data_path:
                    transformation_type = 'rotation'
                elif 'scale' in data_path:
                    transformation_type = 'scale'
                else:
                    continue

                # Retrieve the sorted key points
                sorted_keyframes = sorted(fcurve.keyframe_points, key=lambda kf: kf.co.x)

                for keyframe in sorted_keyframes:
                    frame = int(keyframe.co.x)

                    # Ensure that the frame key exists in the dictionary
                    if frame not in keyframes_data:
                        keyframes_data[frame] = {}

                    # Ensure that the bone name exists in the dictionary for this frame
                    if bone_name not in keyframes_data[frame]:
                        keyframes_data[frame][bone_name] = []

                    # Add the transformation to the corresponding list only if it does not already exist
                    if transformation_type not in keyframes_data[frame][bone_name]:
                        keyframes_data[frame][bone_name].append(transformation_type)

        for frame, bones in keyframes_data.items():
            scene.frame_set(frame)

            for bone_name, transformations in bones.items():
                # Check that the bone is indeed present in the armature
                if bone_name in armature.pose.bones:
                    pose_bone = armature.pose.bones[bone_name]
                    
                    # Check if the bone is deformable
                    if not pose_bone.bone.use_deform:
                        continue
                        
                    # Loop to find the first deformable parent bone
                    parent = pose_bone.parent	
                    while parent:
                        if parent.bone.use_deform:
                            break
                        parent = parent.parent   
                    
                    # Get the transformation matrix of the current pose bone
                    pose_matrix = pose_bone.matrix
                    name_crc32 = zlib.crc32(pose_bone.name.encode())
                    
                    # Merge parent matrix and bone matrix
                    if parent:
                        parent_matrix = parent.matrix
                        pose_matrix = parent_matrix.inverted() @ pose_matrix                

                    # If a location transformation is detected
                    if 'location' in transformations:
                        # Check if the node doesn't exist
                        if not tracks[0].NodeExists(name_crc32):
                            # Create it
                            tracks[0].Nodes.append(animation_manager.Node(name_crc32, True, []))
                        
                        # Transform matrix to location                
                        location = pose_matrix.to_translation()
                        location = BoneLocation(float(location[0]), float(location[1]), float(location[2]))
                        
                        # Insert location transformation data
                        node = tracks[0].GetNodeByName(name_crc32)
                        node.add_frame(frame, location)

                    # If a rotation transformation is detected            
                    if 'rotation' in transformations:
                        # Check if the node doesn't exist
                        if not tracks[1].NodeExists(name_crc32):
                            # Create it
                            tracks[1].Nodes.append(animation_manager.Node(name_crc32, True, []))
                        
                        # Transform matrix to rotation
                        rotation = pose_matrix.to_euler()
                        rotation = BoneRotation(float(rotation[0]), float(rotation[1]), float(rotation[2]))
                        rotation.ToQuaternion()
                        
                        # Insert rotation transformation data
                        node = tracks[1].GetNodeByName(name_crc32)
                        node.add_frame(frame, rotation)

                    # If a scale transformation is detected
                    if 'scale' in transformations:
                        # Check if the node doesn't exist
                        if not tracks[2].NodeExists(name_crc32):
                            # Create it
                            tracks[2].Nodes.append(animation_manager.Node(name_crc32, True, []))
                        
                        # Transform matrix to scale
                        scale = pose_matrix.to_scale()
                        scale = BoneLocation(float(scale[0]), float(scale[1]), float(scale[2]))
                        
                        # Insert scale transformation data
                        node = tracks[2].GetNodeByName(name_crc32)
                        node.add_frame(frame, scale)

    # Create animation manager object
    animation = animation_manager.AnimationManager(Format='XMTN', Version='V2', AnimationName=animation_name, FrameCount=scene.frame_end, Tracks=tracks)
    
    # Save
    return animation.Save();
        
##########################################
# Register class
##########################################

class ImportXMTN(bpy.types.Operator, ImportHelper):
    bl_idname = "import.xmtn"
    bl_label = "Import a MTN"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".mtn*"
    filter_glob: StringProperty(default="*.mtn*", options={'HIDDEN'})
    
    def execute(self, context):
            return fileio_open_xmtn(self, context, self.filepath)

class ExportXMTN(bpy.types.Operator, ExportHelper):
    bl_idname = "export.xmtn"
    bl_label = "Export to XMTN"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ""
    filter_glob: StringProperty(default="*.mtn2;*.mtn3", options={'HIDDEN'})
    
    def update_extension(self, context):
        ExportXMTN.filename_ext = f"{self.extension}"
        params  = context.space_data.params
        
        for k in dir(params):
            print(k, getattr(params, k))
            
        params.filename = f"{os.path.splitext(self.filepath)[0]}{self.extension}"

    def item_callback(self, context):
        items = []
        for o in bpy.context.scene.objects:
            if o.type == "ARMATURE":
                items.append((o.name, o.name, ""))
        return items
        
    armature_name: EnumProperty(
        name="Animation Armature",
        description="Choose animation armature",
        items=item_callback,
        default=0,
    )

    animation_name: StringProperty(
        name="Animation Name",
        description="Set your animation name",
        default='my_animation',
        maxlen=40,
    )

    extension: bpy.props.EnumProperty(
        name="Animation Format",
        #items=[(".mtn2", "MTN2", "Export as MTN2"),
               #(".mtn3", "MTN3", "Export as MTN3")],
        items=[(".mtn2", "MTN2", "Export as MTN2")],
        default=".mtn2",
    )

    def check(self, context): 
        changed = False
 
        filepath = self.filepath
        if os.path.basename(filepath):
            filepath = bpy.path.ensure_ext(
                os.path.splitext(self.filepath)[0],
                '.mtn2' if self.extension == '.mtn2' else '.mtn3',
            )
            changed = (filepath != self.filepath)
            self.filepath = filepath
 
        return changed

    def execute(self, context):
        if (self.armature_name == ""):
            self.report({'ERROR'}, "No animation found in the armature")
            return {'FINISHED'}
        else:
            with open(self.filepath, "wb") as f:
                f.write(fileio_write_xmtn(context, self.armature_name, self.animation_name, self.extension))
                return {'FINISHED'} 

