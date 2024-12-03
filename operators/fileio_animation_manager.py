import re
import io
import os
import zlib

from mathutils import Vector, Euler, Matrix, Quaternion

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, EnumProperty, BoolProperty, CollectionProperty

from ..animation import *
from ..formats import  animation_manager, animation_support, res

##########################################
# XMTN Function
##########################################

def get_real_name(name):
    if name.count('.') > 0 and len(name) > 3:
        if name[len(name)-4] == '.':
            match = re.search(r"^(.*?)(\.\d+)$", name)
            if match:
                return match.group(1)
    return name

def crc32_hash(name):
    return zlib.crc32(name.encode())

def findCrc32(crc32, bones=None, modifier=None, mesh=None):
    if bones:
        for bone in bones.items():
            if crc32_hash(bone[0]) == crc32:
                return bone[0]
    if modifier:
        for uvmap in modifier.items():
            if crc32_hash(uvmap[0]) == crc32 and str(uvmap[0]) != "Armature":
                return str(uvmap[0])
    
    if mesh:
        if mesh.data.materials:
            material_name = get_real_name(mesh.data.materials[0].name)
            if crc32_hash(material_name) == crc32:
                    return mesh
  
    return None

def find_armatures_with_bones(bone_name_hashes):
    armatures = []

    for armature_obj in bpy.data.objects:
        if armature_obj.type == 'ARMATURE' and armature_obj.data:
            contains_any_bone = any(findCrc32(crc32, armature_obj) is not None for crc32 in bone_name_hashes)
            
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

def process_bone_track(track, node, armature, action):
    """Process a track related to bones."""
    bpy.ops.object.mode_set(mode='POSE')
    
    bone_name = findCrc32(node.Name, armature.pose.bones)
    bone = armature.pose.bones.get(bone_name)
    if not bone:
        return

    # Determine the transformation channel
    if track.Name == "BoneLocation":
        data_path = f'pose.bones["{bone_name}"].location'
        indices = [0, 1, 2]  # X, Y, Z location
    elif track.Name == "BoneRotation":
        data_path = f'pose.bones["{bone_name}"].rotation_quaternion'
        indices = [0, 1, 2, 3]  # W, X, Y, Z quaternion
    elif track.Name == "BoneScale":
        data_path = f'pose.bones["{bone_name}"].scale'
        indices = [0, 1, 2]  # X, Y, Z scale
    else:
        # Skip unknown bone tracks
        return

    # Add fcurves and keyframes
    for index in indices:
        fcurve = action.fcurves.find(data_path=data_path, index=index)
        
        if not fcurve:
            fcurve = action.fcurves.new(data_path=data_path, index=index)
            
        for frame in node.Frames:
            frame_num = frame.Key
            value = frame.Value
            
            if track.Name == "BoneLocation":
                transformation = calculate_transformed_location(bone, Vector([value.X, value.Y, value.Z]))
                fcurve.keyframe_points.insert(frame=frame_num, value=transformation[index])
            elif track.Name == "BoneRotation":
                transformation = calculate_transformed_rotation(bone, Vector([value.W, value.X, value.Y, value.Z]))
                fcurve.keyframe_points.insert(frame=frame_num, value=transformation[index])
            elif track.Name == "BoneScale":
                transformation = calculate_transformed_scale(bone, Vector([value.X, value.Y, value.Z]))
                fcurve.keyframe_points.insert(frame=frame_num, value=transformation[index])

def process_uv_track(track, node, action, armature=None, mesh=None):
    """Process a track related to UVs or materials using FCurves."""
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Function to handle UVs for a specific mesh
    def handle_uv_for_mesh(mesh, track, node, action):
        # Ensure the mesh has animation data and an action linked
        if mesh.animation_data is None:
            mesh.animation_data_create()
        if mesh.animation_data.action is None:
            mesh.animation_data.action = action
            
        node_name = findCrc32(node.Name, modifier=mesh.modifiers)
        if not node_name:
            return
        
        modifier = mesh.modifiers.get(node_name)
        if not modifier:
            return
        
        # Define the corresponding data paths
        if track.Name == "UVMove":
            data_path = f'modifiers["{node_name}"].offset'
            indices = [0, 1]  # X, Y offsets
        elif track.Name == "UVScale":
            data_path = f'modifiers["{node_name}"].scale'
            indices = [0, 1]  # X, Y scale
        elif track.Name == "UVRotate":
            data_path = f'modifiers["{node_name}"].rotation'
            indices = [0]  # Rotation (single value)
        else:
            # Skip unknown UV tracks
            return
        
        # Add FCurves and keyframes
        for index in indices:
            fcurve = action.fcurves.find(data_path=data_path, index=index)
            
            if not fcurve:
                fcurve = action.fcurves.new(data_path=data_path, index=index)
            
            for frame in node.Frames:
                frame_num = frame.Key
                value = frame.Value
                
                if track.Name == "UVMove":
                    fcurve.keyframe_points.insert(frame=frame_num, value=(value.X if index == 0 else value.Y))
                elif track.Name == "UVScale":
                    fcurve.keyframe_points.insert(frame=frame_num, value=(value.X if index == 0 else value.Y))
                elif track.Name == "UVRotate":
                    fcurve.keyframe_points.insert(frame=frame_num, value=value.X)

    # Process tracks
    if armature:
        # Based on the armature
        for child in armature.children:
            if child.type == "MESH":
                handle_uv_for_mesh(child, track, node, action)
    elif mesh and mesh.type == "MESH":
        # Based on the mesh
        handle_uv_for_mesh(mesh, track, node, action)

def process_material_track(track, node, action, armature=None, mesh=None):
    """Process a track related to material."""
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Function to handle UVs for a specific mesh
    def handle_material_for_mesh(mesh, track, node, action):
        # Ensure the mesh has animation data and an action linked
        node_name = findCrc32(node.Name, mesh=mesh)
        if not node_name:
            return
        
        material = mesh.data.materials[0]
        
        # Ensure the material has animation data and an action linked
        if material.animation_data is None:
            material.animation_data_create()
        if material.animation_data.action is None:
            material.animation_data.action = bpy.data.actions.new(name="{material.name}.{action_name}")
            action = material.animation_data.action
        
        # Define the corresponding data paths
        if track.Name == "MaterialAttribute":
            data_path = f'node_tree.nodes["Principled BSDF"].inputs[19].default_value'
            indices = [0, 1, 2]
        elif track.Name == "MaterialTransparency":
            # Get texture node
            nodes = material.node_tree.nodes
            texture_node = nodes.get("Image Texture")
            
            # Changes the data_path if the texture has an alpha channel or not
            if texture_node:
                if texture_node.outputs["Alpha"].is_linked:
                    data_path = f'node_tree.nodes["Alpha Multiplier"].inputs[1].default_value'
                else:
                    data_path = f'node_tree.nodes["Principled BSDF"].inputs[21].default_value' 
            
            indices = [0]
        else:
            # Skip unknown material tracks
            return
        
        # Add FCurves and keyframes
        for index in indices:
            fcurve = action.fcurves.find(data_path=data_path, index=index)
            
            if not fcurve:
                fcurve = action.fcurves.new(data_path=data_path, index=index)
            
            for frame in node.Frames:
                frame_num = frame.Key
                material_value = frame.Value
                
                if track.Name == "MaterialAttribute":
                    fcurve.keyframe_points.insert(
                        frame=frame_num, 
                        value=(
                            material_value.hue if index == 0 
                            else material_value.saturation if index == 1 
                            else material_value.value
                        )
                    )
                elif track.Name == "MaterialTransparency":
                    fcurve.keyframe_points.insert(frame=frame_num, value=material_value.transparency)

    # Process tracks
    if armature:
        # Based on the armature
        for child in armature.children:
            if child.type == "MESH":
                handle_material_for_mesh(child, track, node, action)
    elif mesh and mesh.type == "MESH":
        # Based on the mesh
        handle_material_for_mesh(mesh, track, node, action)

def create_animation(animData, active_obj):
    # Define armature or mesh based on the type of the active object
    armature = active_obj if active_obj.type == 'ARMATURE' else None
    mesh = active_obj if active_obj.type == 'MESH' else None
    
    # Ensure the active object is either an armature or a mesh
    if not armature and not mesh:
        operator.report({'ERROR'}, "Active object must be either an armature or a mesh.")
        return {'CANCELLED'}
    
    # Create a new action for the animation
    action = bpy.data.actions.new(name=animData.AnimationName)

    # Assign the action to the armature's animation data
    if armature:
        if armature.animation_data is None:
            armature.animation_data_create()
        armature.animation_data.action = action
    
    # Assign the action to the mesh's animation data  
    if mesh:
        if mesh.animation_data is None:
            mesh.animation_data_create()
        mesh.animation_data.action = action  

    # Loop through each track in animdata
    for track in animData.Tracks:
        # Node refers to a bone or a txtproj
        for node in track.Nodes:
            # Check track type
            if track.Name.startswith("Bone") and not track.Name == "BoneBool":
                if armature:
                    process_bone_track(track, node, armature, action)
            elif track.Name.startswith("UV"):
                    process_uv_track(track, node, action, armature=armature, mesh=mesh)
            elif track.Name.startswith("Material"):
                    process_material_track(track, node, action, armature=armature, mesh=mesh)

def fileio_open_animation(operator, context, filepath):
    # Get file extension
    file_extension = os.path.splitext(filepath)[1].lower()
    
    # Get active object
    active_obj = bpy.context.active_object
    
    if file_extension == ".mtn2":
        # Checks that the active object is an armature
        if not active_obj or active_obj.type != 'ARMATURE':
            operator.report({'ERROR'}, "An armature must be selected for .mtn files.")
            return {'CANCELLED'}
    elif file_extension in {".mtm2", ".imm2"}:
        # Checks that the active object is an armature or mesh
        if not active_obj or active_obj.type not in {'ARMATURE', 'MESH'}:
            operator.report({'ERROR'}, "A mesh or armature must be selected for .mtm or .imm files.")
            return {'CANCELLED'}        
    
    with open(filepath, 'rb') as file:
        # Open file and return AnimationManager object
        animation = animation_manager.AnimationManager(reader=io.BytesIO(file.read()))
        
        # Create an animation from an AnimationManager object and a Blender object
        create_animation(animation, active_obj)
    
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

class ImportAnimation(bpy.types.Operator, ImportHelper):
    bl_idname = "import.level5_animation"
    bl_label = "Import Level 5 Animation"
    bl_options = {'PRESET', 'UNDO'}
    
    filename_ext = ""
    filter_glob: StringProperty(default="*.mtn2;*.mtm2;*.imm2", options={'HIDDEN'})
    
    def execute(self, context):
        allowed_extensions = {".mtn2", ".mtm2", ".imm2"}
        file_extension = os.path.splitext(self.filepath)[1]
        
        if file_extension not in allowed_extensions:
            self.report({'ERROR'}, f"Unsupported file format: {file_extension}. Only .mtn2, .mtm2, and .imm2 are supported.")
            return {'CANCELLED'}
        
        return fileio_open_animation(self, context, self.filepath)

class BoneCheckbox(bpy.types.PropertyGroup):
    """A PropertyGroup for storing a checkbox for each bone."""
    name: StringProperty(name="Bone Name")
    enabled: BoolProperty(name="Enabled", default=False)

class ExportAnimation(bpy.types.Operator, ExportHelper):
    bl_idname = "export.animation"
    bl_label = "Export Animation"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ""
    filter_glob: StringProperty(default="*", options={'HIDDEN'})

    def update_animation_type(self, context):
        """Update available extensions and filter_glob based on animation type."""
        if self.animation_type == "ARMATURE":
            self.filter_glob = "*.mtn2;*.mtn3"
            self.update_armature(context)
        else:
            self.filter_glob = "*.imm2" if self.animation_type == "UV" else "*.mtm2"
            self.update_object(context)

    def update_armature(self, context):
        """Update bone checkboxes when armature is changed."""
        self.bone_checkboxes.clear()
        if self.animation_type == "ARMATURE" and self.armature_name and self.armature_name != "NONE":
            armature = bpy.data.objects.get(self.armature_name)
            if armature and armature.type == "ARMATURE":
                for bone in armature.data.bones:
                    checkbox = self.bone_checkboxes.add()
                    checkbox.name = bone.name
                    checkbox.enabled = True

    def update_object(self, context):
        """Update view object based on UVWarp modifiers or materials."""
        self.view_object_items.clear()
        if self.animation_type == "UV" and self.uv_material_mode == "STUDIO_ELEVEN":
            obj = bpy.data.objects.get(self.object_name)
            if obj and obj.type == "MESH":
                for mod in obj.modifiers:
                    if mod.type == 'UV_WARP':
                        checkbox = self.view_object_items.add()
                        checkbox.name = mod.name
                        checkbox.enabled = True
            elif obj and obj.type == "ARMATURE":
                for child in obj.children:
                    if child.type == "MESH":
                        for mod in child.modifiers:
                            if mod.type == 'UV_WARP':
                                checkbox = self.view_object_items.add()
                                checkbox.name = mod.name
                                checkbox.enabled = True
        elif self.animation_type == "MATERIAL" and self.uv_material_mode == "STUDIO_ELEVEN":
            obj = bpy.data.objects.get(self.object_name)
            if obj and obj.type == "MESH":
                for mat in obj.data.materials:
                    checkbox = self.view_object_items.add()
                    checkbox.name = mat.name
                    checkbox.enabled = True
            elif obj and obj.type == "ARMATURE":
                for child in obj.children:
                    if child.type == "MESH":
                        for mat in child.data.materials:
                            checkbox = self.view_object_items.add()
                            checkbox.name = mat.name
                            checkbox.enabled = True

    animation_type: EnumProperty(
        name="Animation Type",
        description="Select the type of animation",
        items=[
            ("ARMATURE", "Armature (XMTN)", "Export Armature Animation"),
            ("UV", "UV (XIMA)", "Export UV Animation"),
            ("MATERIAL", "Material (XMTM)", "Export Material Animation")
        ],
        default="ARMATURE",
        update=update_animation_type
    )

    view_bones: BoolProperty(
        name="View Bones",
        description="Toggle the visibility of the bones list",
        default=False  # Default to hidden
    )
    
    view_object: BoolProperty(
        name="View Linked Objects",
        description="Toggle the visibility of the linked object list",
        default=False  # Default to hidden
    )    

    def extension_items(self, context):
        """Dynamically generate extension items based on animation type."""
        if self.animation_type == "ARMATURE":
            return [
                (".mtn2", "MTN2", "Export as MTN2"),
                (".mtn3", "MTN3", "Export as MTN3")
            ]
        elif self.animation_type == "UV":
            return [
                (".imm2", "IMM2", "Export as IMM2")
            ]
        elif self.animation_type == "MATERIAL":
            return [
                (".mtm2", "MTM2", "Export as MTM2")
            ]
        return []

    extension: EnumProperty(
        name="Animation Format",
        description="Select the format of the animation file",
        items=extension_items
    )

    def item_callback_armature(self, context):
        """Provide list of armatures."""
        items = []
        for o in bpy.context.scene.objects:
            if o.type == 'ARMATURE':
                items.append((o.name, o.name, ""))
        if not items:  # No armature found
            items.append(("NONE", "No armature available", ""))
        return items

    def item_callback_object(self, context):
        """Provide list of armatures and meshes."""
        items = []
        for o in bpy.context.scene.objects:
            if o.type in {'ARMATURE', 'MESH'}:
                items.append((o.name, o.name, ""))
        if not items:  # No armature or mesh found
            items.append(("NONE", "No object available", ""))
        return items

    armature_name: EnumProperty(
        name="Animation Armature",
        description="Choose animation armature",
        items=item_callback_armature,
        update=update_armature
    )

    object_name: EnumProperty(
        name="Object Name",
        description="Choose object",
        items=item_callback_object,
        update=update_object
    )

    uv_material_mode: EnumProperty(
        name="Mode",
        description="Choose a mode for UV or Material animations",
        items=[
            ("STUDIO_ELEVEN", "Studio Eleven", "Studio Eleven mode"),
            ("BERRY_BUSH", "Berry Bush", "Berry Bush mode")
        ],
        default="STUDIO_ELEVEN"
    )

    animation_name: StringProperty(
        name="Animation Name",
        description="Set your animation name",
        default='my_animation',
        maxlen=40,
    )

    bone_checkboxes: CollectionProperty(type=BoneCheckbox)
    view_object_items: CollectionProperty(type=BoneCheckbox)

    transformation_checkboxes: CollectionProperty(type=BoneCheckbox)

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "animation_type", text="Type")
        layout.prop(self, "extension", text="Format")

        if self.animation_type == "ARMATURE":
            layout.prop(self, "armature_name", text="Armature")
            layout.prop(self, "animation_name", text="Animation Name")
            
            # Draw transformation checkboxes based on animation type
            box = layout.box()
            box.label(text="Transformations:")
            if self.animation_type == "ARMATURE":
                transformations = ["Location", "Rotation", "Scale", "Bool"]
            elif self.animation_type == "UV":
                transformations = ["Location", "Rotation", "Scale"]
            elif self.animation_type == "MATERIAL":
                transformations = ["Transparency", "Attribute"]
            else:
                transformations = []

            for transformation in transformations:
                checkbox = self.transformation_checkboxes.add()
                checkbox.name = transformation
                checkbox.enabled = True
                box.prop(checkbox, "enabled", text=transformation)            
            
            if self.armature_name and self.armature_name != "NONE":
                self.update_armature(context)  # Call update_armature when the menu is drawn
                layout.prop(self, "view_bones", text="View Bones")
                
                if self.view_bones:
                    box = layout.box()
                    box.label(text="Bones:")
                    
                    for bone in self.bone_checkboxes:
                        box.prop(bone, "enabled", text=bone.name)
        elif self.animation_type in {"UV", "MATERIAL"}:
            layout.prop(self, "uv_material_mode", text="Mode")
            layout.prop(self, "object_name", text="Object")
            layout.prop(self, "animation_name", text="Animation Name")

            # Draw transformation checkboxes based on animation type
            box = layout.box()
            box.label(text="Transformations:")
            if self.animation_type == "ARMATURE":
                transformations = ["Location", "Rotation", "Scale", "Bool"]
            elif self.animation_type == "UV":
                transformations = ["Location", "Rotation", "Scale"]
            elif self.animation_type == "MATERIAL":
                transformations = ["Transparency", "Attribute"]
            else:
                transformations = []

            for transformation in transformations:
                checkbox = self.transformation_checkboxes.add()
                checkbox.name = transformation
                checkbox.enabled = True
                box.prop(checkbox, "enabled", text=transformation)
            
            if self.object_name and self.object_name != "NONE":
                self.update_object(context)  # Call update_object when the menu is drawn
                
                if self.uv_material_mode != "BERRY_BUSH":
                    layout.prop(self, "view_object", text="View Object")
                    
                    if self.view_object:
                        box = layout.box()
                        box.label(text="Objects:")
                        
                        for item in self.view_object_items:
                            box.prop(item, "enabled", text=item.name)

    def check(self, context):
        """Ensure the correct file extension is applied."""
        filepath = self.filepath
        if os.path.basename(filepath):
            filepath = bpy.path.ensure_ext(os.path.splitext(filepath)[0], self.filename_ext)
            if filepath != self.filepath:
                self.filepath = filepath
                return True
        return False

    def execute(self, context):
        if self.animation_type == "ARMATURE" and (self.armature_name == "" or self.armature_name == "NONE"):
            self.report({'ERROR'}, "No armature selected for animation.")
            return {'CANCELLED'}

        # Placeholder for export logic
        selected_bones = [bone.name for bone in self.bone_checkboxes if bone.enabled]
        self.report({'INFO'}, f"Exported {self.animation_type} with bones: {', '.join(selected_bones)}")
        return {'FINISHED'}