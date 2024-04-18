import os
import zlib

from mathutils import Vector, Euler, Matrix, Quaternion

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, EnumProperty

from ..animation import *
from ..formats import xmtn

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
  
def create_animation(animation_name, frame_count, armature_obj, animation_data):
    scene = bpy.context.scene
    armature = armature_obj.data
    
    # Switch to Pose Mode
    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode='POSE')
    
    if armature_obj.animation_data:
        armature_obj.animation_data_clear()
        
    scene.frame_start = 0
    scene.frame_end = frame_count
    
    bpy.context.scene.frame_set(0)
    bpy.ops.pose.select_all(action='SELECT')
    bpy.ops.pose.transforms_clear()    
    
    # Create a new action here outside the loop
    action = bpy.data.actions.new(name=animation_name)

    for frame in range(frame_count):
        if frame in animation_data:
            for bone_hash, transformation in animation_data[frame].items():
                bone = find_bone_by_crc32(armature, bone_hash)
                if bone == None:
                    continue
        
                pose_bone = armature_obj.pose.bones.get(bone.name)
                if not pose_bone:
                    print(f"Pose bone {bone.name} not found.")
                    continue
                                     
                if 'location' in transformation:
                    location = calculate_transformed_location(pose_bone, Vector([transformation['location'].location_x, transformation['location'].location_y, transformation['location'].location_z]))
                    
                    for i in range(3):
                        fcurve = action.fcurves.find("pose.bones[\"{}\"].location".format(pose_bone.name), index=i)
                        if not fcurve:
                            fcurve = action.fcurves.new(data_path="pose.bones[\"{}\"].location".format(pose_bone.name), index=i)
                        fcurve.keyframe_points.insert(frame, location[i])
                
                if 'rotation' in transformation:
                    pose_bone.rotation_mode = 'QUATERNION'
                    rotation = calculate_transformed_rotation(pose_bone, Vector([transformation['rotation'].rotation_w, transformation['rotation'].rotation_x, transformation['rotation'].rotation_y, transformation['rotation'].rotation_z]))
                    
                    parent = pose_bone.parent
                    while parent and not parent.bone.use_deform:
                        parent = parent.parent
                        
                    for i in range(4):
                        fcurve = action.fcurves.find("pose.bones[\"{}\"].rotation_quaternion".format(pose_bone.name), index=i)
                        if not fcurve:
                            fcurve = action.fcurves.new(data_path="pose.bones[\"{}\"].rotation_quaternion".format(pose_bone.name), index=i)
                        fcurve.keyframe_points.insert(frame, rotation[i])

                if 'scale' in transformation:
                    scale = calculate_transformed_scale(pose_bone, Vector([transformation['scale'].scale_x, transformation['scale'].scale_y, transformation['scale'].scale_z]))
                    
                    for i in range(3):
                        fcurve = action.fcurves.find("pose.bones[\"{}\"].scale".format(pose_bone.name), index=i)
                        if not fcurve:
                            fcurve = action.fcurves.new(data_path="pose.bones[\"{}\"].scale".format(pose_bone.name), index=i)
                        fcurve.keyframe_points.insert(frame, scale[i])

    # Assign the created action to the armature object
    armature_obj.animation_data_create()
    armature_obj.animation_data.action = action
              
def fileio_open_xmtn(operator, context, filepath):
    animation_name = ""
    frame_count = 0
    bone_name_hashes = []
    animation_data = {}
        
    file_name = os.path.splitext(os.path.basename(filepath))[0]
    file_extension = os.path.splitext(filepath)[1]
    
    # Check if there is an active object and if it's an armature
    active_obj = bpy.context.active_object
    if not active_obj or active_obj.type != 'ARMATURE':
        operator.report({'ERROR'}, 'No armature selected or active.')
        return {'CANCELLED'}

    armature_obj = bpy.context.active_object    
    
    if file_extension == ".mtn2":
        with open(filepath, 'rb') as file:
            animation_name, frame_count, bone_name_hashes, animation_data = xmtn.open_mtn2(file.read())
    elif file_extension == ".mtn3":
        with open(filepath, 'rb') as file:
            animation_name, frame_count, bone_name_hashes, animation_data = xmtn.open_mtn3(file.read())
    else:
        operator.report({'ERROR'}, f"Unsupported file format '{file_extension}'. Please use .mtn2 or .mtn3.")
        return {'FINISHED'}

    create_animation(animation_name, frame_count, armature_obj, animation_data)
    
    return {'FINISHED'}

def fileio_write_xmtn(context, armature_name, animation_name, animation_format):   
    scene = context.scene
    
    armature = bpy.data.objects[armature_name]
    armature.data.pose_position = 'POSE'
    bpy.context.view_layer.objects.active = armature
    
    bpy.ops.object.mode_set(mode='POSE')

    # initialise transform data
    node_name = []
    transform_location = {}
    transform_rotation = {}
    transform_scale = {}
    
    # for each bone
    for bone in armature.pose.bones:
        node_name.append(bone.name)
        
    # for each frame
    for frame in range(scene.frame_end):
        scene.frame_set(frame)
        for bone in armature.pose.bones:
            # get pose_bone matrix relative to bone_parent
            bone_index = armature.pose.bones.values().index(bone)
            pose_bone = armature.pose.bones[bone_index]
            
            if not pose_bone.bone.use_deform: 
                continue
		
            parent = pose_bone.parent	
            while parent:
                if parent.bone.use_deform:
                    break
                parent = parent.parent   
                        
            pose_matrix = pose_bone.matrix
            if parent:
                parent_matrix = parent.matrix
                pose_matrix = parent_matrix.inverted() @ pose_matrix
            
            # append location in transform_location
            location = pose_matrix.to_translation()
            location = Location(float(location[0]), float(location[1]), float(location[2]))
            if bone_index not in transform_location:
                transform_location[bone_index] = {}
            transform_location[bone_index][frame] = location

            # append rotation in transform_rotation
            rotation = pose_matrix.to_euler()
            rotation = Rotation(float(rotation[0]), float(rotation[1]), float(rotation[2]))          
            if bone_index not in transform_rotation:
                transform_rotation[bone_index] = {}
            transform_rotation[bone_index][frame] = rotation

            # append scale in transform_scale
            scale = pose_matrix.to_scale()
            scale = Scale(float(scale[0]), float(scale[1]), float(scale[2]))            
            if bone_index not in transform_scale:
                transform_scale[bone_index] = {}
            transform_scale[bone_index][frame] = scale             

    if animation_format == '.mtn2' or animation_format == 'MTN2':
        return xmtn.write_mtn2(animation_name, node_name, transform_location, transform_rotation, transform_scale, scene.frame_end)  
    elif animation_format == '.mtn3'  or animation_format == 'MTN3':
        return xmtn.write_mtn3(animation_name, node_name, transform_location, transform_rotation, transform_scale, scene.frame_end)
        
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

