import os
import bpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, EnumProperty

from ..animation import *
from ..formats import xmtn

##########################################
# XMTN Class
##########################################

def fileio_write_mtn2(context, filepath, armature_name, animation_name):   
    scene = context.scene
    armature = bpy.data.objects[armature_name]
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
    
    # Save file
    new_xmtn = xmtn.write(animation_name, node_name, transform_location, transform_rotation, transform_scale, scene.frame_end)  
    f = open(filepath, 'wb')
    f.write(new_xmtn)
    f.close()
    
    return {'FINISHED'}

class ExportMTN2(bpy.types.Operator, ExportHelper):
    bl_idname = "export.mtn2"
    bl_label = "Export to mtn2"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".mtn2"
    filter_glob: StringProperty(default="*.mtn2", options={'HIDDEN'})

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

    def execute(self, context):
        if (self.armature_name == ""):
            self.report({'ERROR'}, "No animation armature found")
            return {'FINISHED'}
        else:
            return fileio_write_mtn2(context, self.filepath, self.armature_name, self.animation_name)

