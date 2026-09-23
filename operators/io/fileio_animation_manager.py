import re
import io
import os
import zlib

from mathutils import Vector, Euler, Matrix, Quaternion

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, EnumProperty, BoolProperty, CollectionProperty

from ...formats.animation.tracks import *
from ...formats import  animation_manager, animation_support, res

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
            material_name = mesh.data.materials[0].name
            if crc32_hash(material_name) == crc32:
                    return mesh
                    
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

def get_rest_matrix(pose_bone):
    """Rest matrix relative to the first deforming parent, the pose used before any animation is applied."""
    parent = pose_bone.parent
    while parent and not parent.bone.use_deform:
        parent = parent.parent

    rest_matrix = pose_bone.bone.matrix_local
    if parent:
        rest_matrix = parent.bone.matrix_local.inverted() @ rest_matrix

    return rest_matrix

def calculate_transformed_location(rest_matrix, location):
    return rest_matrix.inverted() @ location

def calculate_transformed_rotation(rest_matrix, rotation):
    # Create a Quaternion directly from Euler angles
    rotation_quaternion = Quaternion(rotation)

    # Convert quaternion rotation to Matrix
    rotation_matrix = rotation_quaternion.to_matrix().to_4x4()

    # Multiply rest matrix by rotation matrix
    transformed_matrix = rest_matrix.inverted() @ rotation_matrix

    # Extract quaternion from the result
    transformed_quaternion = transformed_matrix.to_quaternion()

    return transformed_quaternion

def calculate_transformed_scale(rest_matrix, scale):
    # Create scale matrices for each axis
    scale_matrix_x = Matrix.Scale(scale[0], 4, (1, 0, 0))
    scale_matrix_y = Matrix.Scale(scale[1], 4, (0, 1, 0))
    scale_matrix_z = Matrix.Scale(scale[2], 4, (0, 0, 1))

    # Multiply rest matrix by scale matrices
    transformed_matrix = rest_matrix.inverted() @ (scale_matrix_x @ scale_matrix_y @ scale_matrix_z)

    # Extract scales from the result
    transformed_scale = transformed_matrix.to_scale()

    return transformed_scale

def get_track_type(track_name):
    if track_name.startswith("Bone") and track_name != "BoneBool":
        return 'bone'
    elif track_name.startswith("UV"):
        return 'uv'
    elif track_name.startswith("Material"):
        return 'material'

    return None

def get_animation_track_types(animData):
    track_types = set()

    for track in animData.Tracks:
        track_type = get_track_type(track.Name)

        if track.Nodes and track_type:
            track_types.add(track_type)

    return track_types

def get_animation_node_hashes(animData):
    node_hashes = set()

    for track in animData.Tracks:
        for node in track.Nodes:
            node_hashes.add(node.Name)

    return node_hashes

def get_object_hashes(obj):
    """Hashes an animation can move on an object: bones, single bind bones, UV modifiers and materials."""
    names = []
    meshes = []

    if obj.type == 'ARMATURE':
        for bone in obj.data.bones:
            names.append(bone.name)

        for child in obj.children:
            if child.type == 'MESH':
                meshes.append(child)
    elif obj.type == 'MESH':
        meshes.append(obj)

    for mesh in meshes:
        if mesh.parent_type == 'BONE' and mesh.parent_bone:
            names.append(mesh.parent_bone)

        for modifier in mesh.modifiers:
            if modifier.type == 'UV_WARP':
                names.append(modifier.name)

        for material in mesh.data.materials:
            if material:
                names.append(material.name)
                names.append(get_real_name(material.name))

    hashes = set()

    for name in names:
        hashes.add(crc32_hash(name))

    return hashes

def count_matching_nodes(node_hashes, obj):
    return len(node_hashes & get_object_hashes(obj))

def process_bone_track(track, node, armature, action, bone_names):
    """Process a track related to bones."""
    bone_name = bone_names.get(node.Name)
    if not bone_name:
        return

    bone = armature.pose.bones.get(bone_name)
    if not bone:
        return

    rest_matrix = get_rest_matrix(bone)

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

    # Compute the transformations once per frame
    transformations = []
    for frame in node.Frames:
        value = frame.Value

        if track.Name == "BoneLocation":
            transformations.append((frame.Key, calculate_transformed_location(rest_matrix, Vector([value.X, value.Y, value.Z]))))
        elif track.Name == "BoneRotation":
            transformations.append((frame.Key, calculate_transformed_rotation(rest_matrix, Vector([value.W, value.X, value.Y, value.Z]))))
        elif track.Name == "BoneScale":
            transformations.append((frame.Key, calculate_transformed_scale(rest_matrix, Vector([value.X, value.Y, value.Z]))))

    # Add fcurves and keyframes
    for index in indices:
        fcurve = action.fcurves.find(data_path=data_path, index=index)

        if not fcurve:
            fcurve = action.fcurves.new(data_path=data_path, index=index)

        for frame_num, transformation in transformations:
            fcurve.keyframe_points.insert(frame=frame_num, value=transformation[index])

def process_uv_track(track, node, action, meshes):
    """Process a track related to UVs using FCurves."""
    for mesh in meshes:
        node_name = findCrc32(node.Name, modifier=mesh.modifiers)
        if not node_name:
            continue

        modifier = mesh.modifiers.get(node_name)
        if not modifier:
            continue

        # The UV action is shared by every mesh (each mesh only resolves its own modifiers)
        if mesh.animation_data is None:
            mesh.animation_data_create()
        mesh.animation_data.action = action

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

def process_material_track(track, node, action_name, meshes, material_actions):
    """Process a track related to material."""
    for mesh in meshes:
        if not findCrc32(node.Name, mesh=mesh):
            continue

        material = mesh.data.materials[0]
        if material is None or not material.use_nodes:
            continue

        # Define the corresponding data paths
        if track.Name == "MaterialAttribute":
            data_path = f'node_tree.nodes["Principled BSDF"].inputs[19].default_value'
            indices = [0, 1, 2]
        elif track.Name == "MaterialTransparency":
            # Get texture node
            nodes = material.node_tree.nodes
            texture_node = nodes.get("Image Texture")

            # Changes the data_path if the texture has an alpha channel or not
            if texture_node and texture_node.outputs["Alpha"].is_linked:
                data_path = f'node_tree.nodes["Alpha Multiplier"].inputs[1].default_value'
            else:
                data_path = f'node_tree.nodes["Principled BSDF"].inputs[21].default_value'

            indices = [0]
        else:
            # Skip unknown material tracks
            return

        # Get or create the action of this material
        action = material_actions.get(material.name)
        if action is None:
            action = bpy.data.actions.new(name=f"{action_name}.{material.name}")
            material_actions[material.name] = action

            if material.animation_data is None:
                material.animation_data_create()
            material.animation_data.action = action

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

def create_animation(animData, active_obj, action=None, track_types=None, material_actions=None):
    """Create the actions of an animation, the files of the same animation share them."""
    armature = None
    mesh = None

    # Define armature or mesh based on the type of the active object
    if active_obj.type == 'ARMATURE':
        armature = active_obj
    elif active_obj.type == 'MESH':
        mesh = active_obj

    # Ensure the active object is either an armature or a mesh
    if not armature and not mesh:
        raise ValueError("Active object must be either an armature or a mesh.")

    if track_types is None:
        track_types = {'bone', 'uv', 'material'}

    if material_actions is None:
        material_actions = {}

    # Create a new action for the animation
    if action is None:
        action = bpy.data.actions.new(name=animData.AnimationName)

    # Assign the action to the object's animation data
    if active_obj.animation_data is None:
        active_obj.animation_data_create()
    active_obj.animation_data.action = action

    meshes = []
    bone_names = {}

    if armature:
        for child in armature.children:
            if child.type == 'MESH':
                meshes.append(child)

        for bone in armature.pose.bones:
            bone_names[crc32_hash(bone.name)] = bone.name
    else:
        meshes.append(mesh)

    # Loop through each track in animdata
    for track in animData.Tracks:
        track_type = get_track_type(track.Name)
        if track_type not in track_types:
            continue

        # Node refers to a bone or a txtproj
        for node in track.Nodes:
            # Check track type
            if track_type == 'bone':
                if armature:
                    process_bone_track(track, node, armature, action, bone_names)
            elif track_type == 'uv':
                process_uv_track(track, node, action, meshes)
            elif track_type == 'material':
                process_material_track(track, node, animData.AnimationName, meshes, material_actions)

    return action

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

def fileio_write_animation(context, armature_name=None, object_name=None, animation_type=None, animation_name=None, selected_items=None, transformations=None, extension=None, uv_material_mode=None):
    if animation_type == "ARMATURE":
        if not armature_name:
            raise ValueError("No armature specified for ARMATURE animation.")
        
        armature = bpy.data.objects.get(armature_name)
        if not armature or armature.type != 'ARMATURE':
            raise ValueError("Specified armature does not exist or is invalid.")

        return fileio_write_xmtn(context, armature, animation_name, transformations, selected_items)
    elif animation_type == "UV":
        if not object_name:
            raise ValueError("No object specified for UV animation.")
            
        obj = bpy.data.objects.get(object_name)
        if not obj or obj.type not in {"MESH", "ARMATURE"}:
            raise ValueError("Specified object doesn't exist or is invalid.")

        is_studio_eleven = uv_material_mode == "STUDIO_ELEVEN"
        
        return fileio_write_imm(context, obj, animation_name, transformations, selected_items, is_studio_eleven)
    elif animation_type == "MATERIAL":
        if not object_name:
            raise ValueError("No object specified for Material animation.")
        
        obj = bpy.data.objects.get(object_name)
        if not obj or obj.type not in {"MESH", "ARMATURE"}:
            raise ValueError("Specified object doesn't exist or is invalid.")
            
        is_studio_eleven = uv_material_mode == "STUDIO_ELEVEN"    

        return fileio_write_mtm(context, obj, animation_name, transformations, selected_items, is_studio_eleven)
    else:
        raise ValueError(f"Unknown animation type: {animation_type}")

def fileio_write_xmtn(context, armature, animation_name, transformations, bones, version="V2"):    
    scene = context.scene
    armature.data.pose_position = 'POSE'
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode='POSE')

    tracks = {
        'location': animation_manager.Track('BoneLocation', 0, []),
        'rotation': animation_manager.Track('BoneRotation', 1, []),
        'scale': animation_manager.Track('BoneScale', 2, []),
    }

    if armature.animation_data and armature.animation_data.action:
        action = armature.animation_data.action
        keyframes_data = {}

        for fcurve in action.fcurves:
            data_path = fcurve.data_path
            bone_name = data_path.split('"')[1] if '"' in data_path else None

            if bone_name and bone_name in bones:
                transformation_type = next((t for t in transformations if t in data_path), None)
                if not transformation_type:
                    continue

                sorted_keyframes = sorted(fcurve.keyframe_points, key=lambda kf: kf.co.x)
                for keyframe in sorted_keyframes:
                    frame = int(keyframe.co.x)
                    keyframes_data.setdefault(frame, {}).setdefault(bone_name, []).append(transformation_type)

        for frame, bones_data in sorted(keyframes_data.items()):
            scene.frame_set(frame)
            for bone_name, bone_transformations in bones_data.items():
                pose_bone = armature.pose.bones.get(bone_name)
                if not pose_bone or not pose_bone.bone.use_deform:
                    continue

                pose_matrix = pose_bone.matrix
                parent = pose_bone.parent
                while parent and not parent.bone.use_deform:
                    parent = parent.parent
                if parent:
                    pose_matrix = parent.matrix.inverted() @ pose_matrix

                name_crc32 = zlib.crc32(bone_name.encode())
                for transformation in bone_transformations:
                    if not tracks[transformation].NodeExists(name_crc32):
                        tracks[transformation].Nodes.append(animation_manager.Node(name_crc32, True, []))

                    if transformation == 'location':
                        location = pose_matrix.to_translation()
                        tracks['location'].GetNodeByName(name_crc32).add_frame(
                            frame, BoneLocation(*map(float, location))
                        )
                    elif transformation == 'rotation':
                        rotation = pose_matrix.to_euler()
                        rotation = BoneRotation(*map(float, rotation))
                        rotation.ToQuaternion()
                        tracks['rotation'].GetNodeByName(name_crc32).add_frame(frame, rotation)
                    elif transformation == 'scale':
                        scale = pose_matrix.to_scale()
                        tracks['scale'].GetNodeByName(name_crc32).add_frame(
                            frame, BoneLocation(*map(float, scale))
                        )

    animation = animation_manager.AnimationManager(
        Format='XMTN', Version=version, AnimationName=animation_name,
        FrameCount=scene.frame_end, Tracks=list(tracks.values())
    )
    
    return animation.Save()
    
def fileio_write_imm(context, focused_object, animation_name, transformations, objects, is_studio_eleven, version="V2"):
    scene = context.scene
    bpy.context.view_layer.objects.active = focused_object
    bpy.ops.object.mode_set(mode='OBJECT')

    meshes_enabled = []
    modifiers_enabled = []

    tracks = {
        'offset': animation_manager.Track('UVMove', 0, []),
        'rotation': animation_manager.Track('UVRotate', 1, []),
        'scale': animation_manager.Track('UVScale', 2, []),
    }

    # Vérifie si l'objet est une armature
    if focused_object.type == 'ARMATURE':
        for obj in context.scene.objects:
            # Vérifie que l'objet est une mesh et qu'il est parenté à l'armature
            if obj.type == 'MESH' and obj.parent == focused_object:
                if is_studio_eleven:
                    for modifier in obj.modifiers:
                        if modifier.type == 'UV_WARP':
                            if modifier.name in objects:
                                if obj.animation_data and obj.animation_data.action:
                                    modifiers_enabled.append(modifier)
                else:
                    meshes_enabled.append(obj)
    elif focused_object.type == 'MESH':
        if is_studio_eleven:
            for modifier in focused_object.modifiers:
                if modifier.type == 'UV_WARP':
                    if modifier.name in objects:
                        if obj.animation_data and obj.animation_data.action:
                            modifiers_enabled.append(modifier)
        else:
            meshes_enabled.append(focused_object)

    # Vérifie quel type d'objets est activé
    if modifiers_enabled and not meshes_enabled:
        print(f"Modifiers activés : {[mod.name for mod in modifiers_enabled]}")
        
        keyframes_data = {}  # Structure pour stocker les données des keyframes
        
        # Parcours des modifiers activés
        for modifier in modifiers_enabled:
            associated_mesh = modifier.id_data  # Récupère la mesh associée au modifier
            if associated_mesh.animation_data and associated_mesh.animation_data.action:
                action = associated_mesh.animation_data.action
                
                for fcurve in action.fcurves:
                    if fcurve.data_path.startswith(f"modifiers[\"{modifier.name}\"]"):
                        data_path = fcurve.data_path
                        modifier_name = data_path.split('"')[1] if '"' in data_path else None

                        transformation_type = next((t for t in transformations if t in data_path), None)
                        if not transformation_type:
                            continue

                        sorted_keyframes = sorted(fcurve.keyframe_points, key=lambda kf: kf.co.x)
                        for keyframe in sorted_keyframes:
                            frame = int(keyframe.co.x)
                            keyframes_data.setdefault(frame, {}).setdefault(modifier_name, []).append(transformation_type)

        for frame, modifiers_data in sorted(keyframes_data.items()):
            scene.frame_set(frame)
            for modifier_name, modifier_transformations in modifiers_data.items():
                # Récupérer le modifier par son nom et l'objet associé
                modifier = next((mod for mod in modifiers_enabled if mod.name == modifier_name), None)
                if not modifier:
                    continue

                name_crc32 = zlib.crc32(modifier_name.encode())
                for transformation in modifier_transformations:
                    if not tracks[transformation].NodeExists(name_crc32):
                        tracks[transformation].Nodes.append(animation_manager.Node(name_crc32, True, []))

                    if transformation == 'offset':
                        location = modifier.offset
                        tracks['offset'].GetNodeByName(name_crc32).add_frame(
                            frame, UVMove(*map(float, location))
                        )
                    elif transformation == 'scale':
                        scale = modifier.scale
                        tracks['scale'].GetNodeByName(name_crc32).add_frame(
                            frame, UVScale(*map(float, scale))
                        )
                    elif transformation == 'rotation':
                        rotation = modifier.rotation
                        tracks['rotation'].GetNodeByName(name_crc32).add_frame(
                            frame, UVRotate(rotation)
                        )                      
    elif meshes_enabled and not modifiers_enabled:
        meshes_material_dict = {}
        for i, obj in enumerate(context.scene.objects):
            if obj.type == 'MESH':
                meshes_material_dict[obj.name] = f"{obj.name}.texproj0"
        
        for frame in range(scene.frame_start, scene.frame_end + 1):
            scene.frame_set(frame)
            
            for mesh in meshes_enabled:
                name_crc32 = zlib.crc32(meshes_material_dict[mesh.name].encode())
                
                if (len(mesh.material_slots) > 0):
                    material = mesh.material_slots[0].material
                    
                    if hasattr(material, "brres"):
                        material_transformation = material.brres.textures.coll_[0].transform
                    
                        for transformation in transformations:
                            if not tracks[transformation].NodeExists(name_crc32):
                                tracks[transformation].Nodes.append(animation_manager.Node(name_crc32, True, []))
                                
                            if transformation == 'offset':
                                location = [material_transformation.translation[0], - material_transformation.translation[1]]
                                tracks['offset'].GetNodeByName(name_crc32).add_frame(
                                    frame, UVMove(*map(float, location))
                                )
                            elif transformation == 'scale':
                                scale = [material_transformation.scale[0], material_transformation.scale[1]]
                                tracks['scale'].GetNodeByName(name_crc32).add_frame(
                                    frame, UVScale(*map(float, scale))
                                )
                            elif transformation == 'rotation':
                                rotation = material_transformation.rotation
                                tracks['rotation'].GetNodeByName(name_crc32).add_frame(
                                    frame, UVRotate(rotation)
                                )    
    elif not modifiers_enabled and not meshes_enabled:
        raise ValueError("Les listes 'modifiers_enabled' et 'meshes_enabled' sont toutes les deux vides. Aucune opération possible.")
    else:
        raise ValueError("Les deux types d'objets sont activés : Studio Eleven et Berry Bush")

    animation = animation_manager.AnimationManager(
        Format='XIMA', Version=version, AnimationName=animation_name,
        FrameCount=scene.frame_end, Tracks=list(tracks.values())
    )

    return animation.Save()

def fileio_write_mtm(context, focused_object, animation_name, transformations, objects, is_studio_eleven, version="V2"):
    scene = context.scene
    bpy.context.view_layer.objects.active = focused_object
    bpy.ops.object.mode_set(mode='OBJECT')

    meshes_enabled = []
    materials_enabled = []

    tracks = {
        'transparency': animation_manager.Track('MaterialTransparency', 0, []),
        'attribute': animation_manager.Track('MaterialAttribute', 1, []),
    }

    # Vérifie si l'objet est une armature
    if focused_object.type == 'ARMATURE':
        for obj in context.scene.objects:
            # Vérifie que l'objet est une mesh et qu'il est parenté à l'armature
            if obj.type == 'MESH' and obj.parent == focused_object:
                if is_studio_eleven:
                    if len(obj.data.materials) > 0:
                        if obj.data.materials[0].name in objects:
                            if obj.data.materials[0].animation_data and obj.data.materials[0].animation_data.action:
                                materials_enabled.append(obj.data.materials[0])
                else:
                    meshes_enabled.append(obj)
    elif focused_object.type == 'MESH':
        if is_studio_eleven:
            if len(focused_object.materials) > 0:
                if focused_object.materials[0].name in objects:
                    if focused_object.materials[0].animation_data and focused_object.materials[0].animation_data.action:
                        materials_enabled.append(focused_object)
        else:
            meshes_enabled.append(focused_object)
    
    # Vérifie quel type d'objets est activé
    if materials_enabled and not meshes_enabled:
        print(f"materials activés : {[mat.name for mat in materials_enabled]}")
        
        keyframes_data = {}  # Structure pour stocker les données des keyframes
        
        # Parcours des modifiers activés
        for material in materials_enabled:
            if material.animation_data and material.animation_data.action:
                action = material.animation_data.action
                
                for fcurve in action.fcurves:
                    data_path = fcurve.data_path
                    
                    if data_path == f'node_tree.nodes["Alpha Multiplier"].inputs[1].default_value' or data_path == f'node_tree.nodes["Principled BSDF"].inputs[21].default_value':
                        # Transparency
                        transformation_type = 'transparency'
                        if not 'transparency' in transformations:
                            continue
                        
                    elif data_path == f'node_tree.nodes["Principled BSDF"].inputs[19].default_value':
                        # Emission
                        transformation_type = 'attribute'
                        if not 'attribute' in transformations:
                            continue
                    else:
                        continue
                        
                    sorted_keyframes = sorted(fcurve.keyframe_points, key=lambda kf: kf.co.x)
                    for keyframe in sorted_keyframes:
                        frame = int(keyframe.co.x)
                        keyframes_data.setdefault(frame, {}).setdefault(material.name, []).append(transformation_type)

        for frame, material_data in sorted(keyframes_data.items()):
            scene.frame_set(frame)
            
            for material_name, material_transformations in material_data.items():
                # Récupérer le material par son nom et l'objet associé
                material = next((mat for mat in materials_enabled if mat.name == material_name), None)
                if not material:
                    continue
                
                nodes = material.node_tree.nodes
                name_crc32 = zlib.crc32(material_name.encode())
                
                for transformation in material_transformations:
                    if not tracks[transformation].NodeExists(name_crc32):
                        tracks[transformation].Nodes.append(animation_manager.Node(name_crc32, True, []))

                    if transformation == 'transparency':
                        texture_node = nodes.get("Image Texture")
                        if texture_node:
                            transparency = 0
                            
                            if texture_node.outputs["Alpha"].is_linked:
                                transparency = nodes["Alpha Multiplier"].inputs[1].default_value
                            else:
                                transparency = nodes["Principled BSDF"].inputs[21].default_value

                            tracks['transparency'].GetNodeByName(name_crc32).add_frame(
                                frame, Transparency(transparency)
                            )
                    elif transformation == 'attribute':
                        emission = nodes["Principled BSDF"].inputs[19].default_value
                        tracks['attribute'].GetNodeByName(name_crc32).add_frame(
                            frame, MaterialAttribute(*map(float, emission))
                        )                    
    elif meshes_enabled and not materials_enabled:
        meshes_material_dict = {}
        for i, obj in enumerate(context.scene.objects):
            if obj.type == 'MESH':
                if obj.data.materials and len(obj.data.materials) > 0:
                    meshes_material_dict[obj.name] = obj.data.materials[0].name
                else:
                    meshes_material_dict[obj.name] = f"DefaultLib.{obj.name}"
        
        for frame in range(scene.frame_start, scene.frame_end + 1):
            scene.frame_set(frame)
            
            for mesh in meshes_enabled:
                name_crc32 = zlib.crc32(meshes_material_dict[mesh.name].encode())
                
                if (len(mesh.material_slots) > 0):
                    material = mesh.material_slots[0].material
                    
                    if hasattr(material, "brres"):
                        light_channel = material.brres.lightChans.coll_[0]
                        color_register = material.brres.colorRegs
                        
                        if light_channel.alphaSettings.difFromReg == True:
                            transparency = light_channel.difColor[3]
                            attribute = (light_channel.difColor[0], light_channel.difColor[1], light_channel.difColor[2])
                        else:
                            transparency = color_register.constant2[3]
                            attribute = (color_register.constant2[0], color_register.constant2[1], color_register.constant2[2])
                    
                        for transformation in transformations:
                            if not tracks[transformation].NodeExists(name_crc32):
                                tracks[transformation].Nodes.append(animation_manager.Node(name_crc32, True, []))
                                
                            if transformation == 'transparency':
                                tracks['transparency'].GetNodeByName(name_crc32).add_frame(
                                    frame, Transparency(transparency)
                                )
                            elif transformation == 'attribute':
                                tracks['attribute'].GetNodeByName(name_crc32).add_frame(
                                    frame, MaterialAttribute(*map(float, attribute))
                                ) 
    elif not materials_enabled and not meshes_enabled:
        raise ValueError("Les listes 'materials_enabled' et 'meshes_enabled' sont toutes les deux vides. Aucune opération possible.")
    else:
        raise ValueError("Les deux types d'objets sont activés : Studio Eleven et Berry Bush")

    animation = animation_manager.AnimationManager(
        Format='XMTM', Version=version, AnimationName=animation_name,
        FrameCount=scene.frame_end, Tracks=list(tracks.values())
    )

    return animation.Save()
    
    
##########################################
# Register class
##########################################

class ImportAnimation(bpy.types.Operator, ImportHelper):
    bl_idname = "import_level5.animation"
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
        else:
            self.filter_glob = "*.imm2" if self.animation_type == "UV" else "*.mtm2"

    def update_armature(self, context):
        """Update bone checkboxes when armature is changed."""
        if self.animation_type == "ARMATURE" and self.armature_name and self.armature_name != "NONE":
            armature = bpy.data.objects.get(self.armature_name)
            if armature and armature.type == "ARMATURE":
                existing_bones = {checkbox.name: checkbox.enabled for checkbox in self.bone_checkboxes}
                self.bone_checkboxes.clear()  # Effacer l'ancienne liste

                for bone in armature.data.bones:
                    checkbox = self.bone_checkboxes.add()
                    checkbox.name = bone.name
                    checkbox.enabled = existing_bones.get(bone.name, True)

    def update_object(self, context):
        """Update view object based on UVWarp modifiers or materials."""
        if self.animation_type in {"UV", "MATERIAL"} and self.object_name and self.object_name != "NONE":
            obj = bpy.data.objects.get(self.object_name)
            if obj:
                existing_items = {checkbox.name: checkbox.enabled for checkbox in self.view_object_items}
                self.view_object_items.clear()  # Effacer l'ancienne liste

                if self.animation_type == "UV":
                    for mod in obj.modifiers:
                        if mod.type == 'UV_WARP':
                            checkbox = self.view_object_items.add()
                            checkbox.name = mod.name
                            checkbox.enabled = existing_items.get(mod.name, True)  # Restaurer l'état ou activer par défaut

                    for child in obj.children:
                        if child.type == "MESH":
                            for mod in child.modifiers:
                                if mod.type == 'UV_WARP':
                                    checkbox = self.view_object_items.add()
                                    checkbox.name = mod.name
                                    checkbox.enabled = existing_items.get(mod.name, True)
                elif self.animation_type == "MATERIAL":
                    if obj.type == "ARMATURE":
                        for child in obj.children:
                            if child.type == "MESH":
                                for mat in child.data.materials:
                                    checkbox = self.view_object_items.add()
                                    checkbox.name = mat.name
                                    checkbox.enabled = existing_items.get(mat.name, True)                       
                    else:
                        for mat in obj.data.materials:
                            checkbox = self.view_object_items.add()
                            checkbox.name = mat.name
                            checkbox.enabled = existing_items.get(mat.name, True)

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
                #(".mtn3", "MTN3", "Export as MTN3")
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

    def update_transformations(self):
        """Update transformation checkboxes."""
        existing_transformations = {checkbox.name: checkbox.enabled for checkbox in self.transformation_checkboxes}
        self.transformation_checkboxes.clear()

        if self.animation_type == "ARMATURE":
            transformations = ["Location", "Rotation", "Scale", "Bool"]
        elif self.animation_type == "UV":
            transformations = ["Offset", "Scale", "Rotation"]
        elif self.animation_type == "MATERIAL":
            transformations = ["Transparency", "Attribute"]
        else:
            transformations = []

        for transformation in transformations:
            checkbox = self.transformation_checkboxes.add()
            checkbox.name = transformation
            checkbox.enabled = existing_transformations.get(transformation, True)

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "animation_type", text="Type")
        layout.prop(self, "extension", text="Format")

        if self.animation_type == "ARMATURE":
            layout.prop(self, "armature_name", text="Armature")
            layout.prop(self, "animation_name", text="Animation Name")

            # Initialiser les transformations
            self.update_transformations()
            
            # Dessiner les cases des transformations
            box = layout.box()
            box.label(text="Transformations:")
            for checkbox in self.transformation_checkboxes:
                box.prop(checkbox, "enabled", text=checkbox.name)
            
            if self.armature_name and self.armature_name != "NONE":
                layout.prop(self, "view_bones", text="View Bones")

                self.update_armature(context)
                if self.view_bones:
                    box = layout.box()
                    box.label(text="Bones:")
                    for bone in self.bone_checkboxes:
                        box.prop(bone, "enabled", text=bone.name)
        elif self.animation_type in {"UV", "MATERIAL"}:
            layout.prop(self, "uv_material_mode", text="Mode")
            layout.prop(self, "object_name", text="Object")
            layout.prop(self, "animation_name", text="Animation Name")

            # Initialiser les transformations
            self.update_transformations()

            # Dessiner les cases des transformations
            box = layout.box()
            box.label(text="Transformations:")
            for checkbox in self.transformation_checkboxes:
                box.prop(checkbox, "enabled", text=checkbox.name)

            if self.object_name and self.object_name != "NONE":
                layout.prop(self, "view_object", text="View Object")

                self.update_object(context)
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
        # Vérifier les transformations sélectionnées
        selected_transformations = list(set(
            transformation.name.lower() for transformation in self.transformation_checkboxes if transformation.enabled
        ))

        if not selected_transformations:
            self.report({'ERROR'}, "No transformations selected for the animation.")
            return {'CANCELLED'}

        # Récupérer les données en fonction du type d'animation
        selected_items = []
        if self.animation_type == "ARMATURE":
            selected_items = [bone.name for bone in self.bone_checkboxes if bone.enabled]

            if not selected_items:
                self.report({'ERROR'}, "No bones selected for armature animation.")
                return {'CANCELLED'}
        elif self.animation_type == "UV":
            selected_items = [uv.name for uv in self.view_object_items if uv.enabled]

            # Ignore the error if uv_material_mode is BERRY_BUSH
            if not selected_items and self.uv_material_mode != "BERRY_BUSH":
                self.report({'ERROR'}, "No UV modifiers selected for UV animation.")
                return {'CANCELLED'}
        elif self.animation_type == "MATERIAL":
            selected_items = [mat.name for mat in self.view_object_items if mat.enabled]

            # Ignore the error if uv_material_mode is BERRY_BUSH
            if not selected_items and self.uv_material_mode != "BERRY_BUSH":
                self.report({'ERROR'}, "No materials selected for material animation.")
                return {'CANCELLED'}

        # Vérifier si une extension est sélectionnée
        if not self.extension:
            self.report({'ERROR'}, "No animation format selected.")
            return {'CANCELLED'}

        # Ajouter une extension au filepath si nécessaire
        if not self.filepath.endswith(self.extension):
            self.filepath += self.extension
            
        with open(self.filepath, "wb") as f:
            f.write(fileio_write_animation(
                    context=context,
                    armature_name=self.armature_name if self.animation_type == "ARMATURE" else None,
                    object_name=self.object_name if self.animation_type in {"UV", "MATERIAL"} else None,
                    animation_type=self.animation_type,
                    animation_name=self.animation_name,
                    selected_items=selected_items,
                    transformations=selected_transformations,
                    extension=self.extension,
                    uv_material_mode=self.uv_material_mode
                )
            )            

        # Appeler la fonction fileio_write_animation avec les données collectées
        try:
            with open(self.filepath, "wb") as f:
                f.write(fileio_write_animation(
                        context=context,
                        armature_name=self.armature_name if self.animation_type == "ARMATURE" else None,
                        object_name=self.object_name if self.animation_type in {"UV", "MATERIAL"} else None,
                        animation_type=self.animation_type,
                        animation_name=self.animation_name,
                        selected_items=selected_items,
                        transformations=selected_transformations,
                        extension=self.extension,
                        uv_material_mode=self.uv_material_mode
                    )
                )
            self.report({'INFO'}, f"Successfully exported {self.animation_type} animation '{self.animation_name}' with format {self.extension}.")
        except Exception as e:
            self.report({'ERROR'}, f"An error occurred during export: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}

##########################################
# Register
##########################################

classes = (
    BoneCheckbox,
    ImportAnimation,
    ExportAnimation,
)

def register_animation_manager():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister_animation_manager():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
