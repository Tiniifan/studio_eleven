import io
import os
import copy

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, EnumProperty, BoolProperty, CollectionProperty

import bmesh

from math import radians
from mathutils import Matrix, Quaternion, Vector

from ..formats import xmpr, xpck, mbn, imgc, res, minf, xcsl, xcma, xcmt, cmn, txp, animation_manager, animation_support
from .fileio_xmpr import *
from .fileio_animation_manager import *
from .fileio_xcma import *
from ..utils.img_format import *
from ..utils.img_tool import *
from ..utils.properties import *
from ..templates import *
from ..controls import CameraElevenObject

##########################################
# XPCK Function
##########################################

def find_armature_by_animation(animation_name):
    # Get armatures
    armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
    
    # Loop through armatures
    for armature in armatures:
        # Loop through actions/animations
        if armature.animation_data and armature.animation_data.action:
            action = armature.animation_data.action
            if action.name == animation_name:
                return armature
                
    return None

def create_files_dict(extension, data_list):
    output = {}
    
    for i in range(len(data_list)):
        output[str(i).rjust(3,'0') + extension] = data_list[i]
        
    return output

def create_bone(armature, bone_name, parent_name, relative_location, relative_rotation, scale, head, tail):
    # Select amature
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode='EDIT')
        
    # Add a new bone
    bpy.ops.armature.bone_primitive_add()
    new_bone = armature.data.edit_bones[-1]
    new_bone.name = bone_name
    
    new_bone.head = head
    new_bone.tail = tail
    
    # Create a matrix based on the parent matrix if the parent exists
    if parent_name:
        # Get parent bone
        parent_bone = armature.data.edit_bones.get(parent_name)
        if parent_bone:
            new_bone.parent = parent_bone

            # Create a translation matrix
            translation_matrix = Matrix.Translation(relative_location)

            # Create a rotation matrix from the quaternion
            rotation_matrix = relative_rotation.to_matrix().to_4x4()
            
            # Check and adjust scale if necessary
            if scale == (0, 0, 0):
                scale = (0.00001, 0.00001, 0.00001)

            # Create a scaling matrix
            scale_matrix = Matrix.Scale(scale[0], 4, (1, 0, 0))
            scale_matrix *= Matrix.Scale(scale[1], 4, (0, 1, 0))
            scale_matrix *= Matrix.Scale(scale[2], 4, (0, 0, 1))

            # Apply transformations
            new_bone.matrix = parent_bone.matrix @ translation_matrix @ rotation_matrix @ scale_matrix
    else:
        new_bone.matrix = Matrix.Translation(relative_location) @ relative_rotation.to_matrix().to_4x4() @ Matrix.Scale(scale[0], 4)
    
    # Set object mode
    bpy.ops.object.mode_set(mode='OBJECT')

def setup_nla_tracks(mesh=None, armature=None):
    """Create NLA tracks for all animations, playing only the first."""
    if not armature and not mesh:
        print("No mesh or armature provided.")
        return

    scene = bpy.context.scene
    obj = armature if armature else mesh

    if obj.animation_data is None:
        print(f"No animation_data initialized for {obj.name}.")
        return;

    nla_tracks = obj.animation_data.nla_tracks
    while nla_tracks:
        nla_tracks.remove(nla_tracks[0])

    # Collect relevant animations
    print(len(bpy.data.actions), bpy.data.actions[0], bpy.data.actions[0].name)
    print(obj.animation_data.action, obj.animation_data.action.name)
    animations_data = [action for action in bpy.data.actions if obj.animation_data.action.name in action.name]
    print(len(animations_data), animations_data[0].name)

    if not animations_data:
        print(f"No animations found for {obj.name}.")
        return

    max_frame = 0

    # Create NLA tracks for all animations
    for i, action in enumerate(animations_data):
        track = nla_tracks.new()
        track.name = f"{obj.name}_Track_{i}"
        strip = track.strips.new(name=action.name, start=1, action=action)

        # Set the frame range for the strip
        strip.frame_end = action.frame_range[1]
        strip.blend_type = 'REPLACE'

        max_frame = int(max(max_frame, strip.frame_end))

        # Disable playback for all but the first track
        track.mute = i > 0

    # Set the scene's frame range to match the first animation
    scene.frame_start = 1
    scene.frame_end = max_frame

    # Play the animation
    bpy.ops.screen.animation_play()

def fileio_open_xpck(context, filepath, file_name = ""):
    scene = bpy.context.scene
    
    archive = xpck.open_file(filepath)
    
    if file_name == '':
        archive_name = os.path.splitext(os.path.basename(filepath))[0]
    else:
        archive_name = file_name
    
    libs = {}
    armature = None
    res_data = None
    camera_hashes = []
        
    bones_data = []
    meshes_data = []
    textures_data = []
    camera_data = {}
    animations_data = []
    animations_split_data = []
    txp_data = []
    
    for file_name in archive:
        if file_name.endswith('.xc') or file_name.endswith('.xv'):
            try:
                fileio_open_xpck(context, archive[file_name], file_name)
            except Exception as e:
                pass
        elif file_name.endswith('.prm'):
            meshes_data.append(xmpr.open_xmpr(io.BytesIO(archive[file_name])))
        elif file_name.endswith('.mbn'):
            bones_data.append(mbn.open(archive[file_name]))    
        elif file_name.endswith('.xi'):
            textures_data.append(imgc.open(archive[file_name]))
        elif file_name.endswith('.cmr2'):
            hash_name, cam_values = xcma.open(archive[file_name])
            camera_data[hash_name] = cam_values
        elif file_name.endswith('.mtn2') or file_name.endswith('.imm2') or file_name.endswith('.mtm2'):
            print(file_name)
            anim = animation_manager.AnimationManager(reader=io.BytesIO(archive[file_name]))
            animations_data.append(anim)
        elif file_name.endswith('mtninf') and not file_name.endswith('.mtninf2'):
            split_animation_data = {}
            
            split_anim_crc32, split_anim_name, anim_crc32, frame_start, frame_end = minf.open_minf1(archive[file_name])
            split_animation_data['split_anim_crc32'] = split_anim_crc32
            split_animation_data['split_anim_name'] = split_anim_name
            split_animation_data['anim_crc32'] = anim_crc32
            split_animation_data['frame_start'] = frame_start
            split_animation_data['frame_end'] = frame_end
            
            animations_split_data.append(split_animation_data)
        elif file_name.endswith('.mtninf2'):
            animations_split_data.extend(minf.open_minf2(archive[file_name])) 
        elif file_name == 'RES.bin':
            res_data = res.open_res(data=archive[file_name])
        elif file_name == 'CMR.bin':
            camera_hashes = xcmt.open(data=archive[file_name])
        elif file_name.endswith('.txp'):
            txp_data.append(txp.read_txp(io.BytesIO(archive[file_name])))

    if bpy.context.scene.objects:
        bpy.ops.object.mode_set(mode='OBJECT')
    
    # Make amature
    if len(bones_data) > 0 and res_data is not None:
        # Create a new amature
        bpy.ops.object.armature_add(enter_editmode=False, align='WORLD', location=(0, 0, 0))
        armature = bpy.context.active_object
        armature.name = "Armature_" + archive_name
                
        # Remove all existing bones
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.armature.select_all(action='SELECT')
        bpy.ops.armature.delete()

        # Set object mode
        bpy.ops.object.mode_set(mode='OBJECT')           
        
        for i in range(len(bones_data)):
            # Get bone information
            bone_crc32 = bones_data[i]['crc32']
            bone_parent_crc32 = bones_data[i]['parent_crc32']              
            bone_location = bones_data[i]['location']
            bone_rotation = bones_data[i]['quaternion_rotation']
            bone_scale = bones_data[i]['scale']
            bone_head = bones_data[i]['head']
            bone_tail = bones_data[i]['tail']
            
            # Get bone name
            bone_name = "bone_" + str(i)            
            if bone_crc32 in res_data[res.RESType.BONE]:
                bone_name = res_data[res.RESType.BONE][bone_crc32]

            # Get parent name
            parent_name = None            
            if bone_parent_crc32 in res_data[res.RESType.BONE]:
                parent_name = res_data[res.RESType.BONE][bone_parent_crc32]
            
            # Checks if the bone has a parent
            if bone_parent_crc32 == 0:
                create_bone(armature, bone_name, False, bone_location, bone_rotation, bone_scale, bone_head, bone_tail)
            else:
                create_bone(armature, bone_name, parent_name, bone_location, bone_rotation, bone_scale, bone_head, bone_tail)
                
        # Set object mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Apply 90-degree rotation around X axis
        armature.rotation_euler = (radians(90), 0, 0)

    # Make libs
    if len(textures_data) > 0 and res_data is not None:
        images = {}
        res_textures_key = list(res_data[res.RESType.TEXTURE_DATA])
        
        # Make images
        for i in range(len(textures_data)):
            if textures_data[i] != None:
                texture_data, width, height, has_alpha = textures_data[i]
                texture_crc32 = res_textures_key[i]
                texture_name = res_data[res.RESType.TEXTURE_DATA][texture_crc32]['name']

                # Create a new image
                bpy.ops.image.new(name=texture_name, width=width, height=height, alpha=has_alpha)
                image = bpy.data.images[texture_name]
                if has_alpha == False:
                    image.alpha_mode = 'NONE'

                # Assign pixel data to the image
                image.pixels.foreach_set(texture_data)
            
                images[texture_crc32] = image

            # Make materials
            for material_crc32, material_value in res_data[res.RESType.MATERIAL_DATA].items():
                material_name = material_value['name']
                material_textures_crc32 = material_value['textures']
                
                print(material_name, material_textures_crc32)
                
                material_textures = []
                
                for i in range(len(material_textures_crc32)):
                    material_texture_crc32 = material_textures_crc32[i]
                    
                    # Check type and convert if necessary
                    if isinstance(material_texture_crc32, str):
                        # If it's a string, convert from hexadecimal
                        texture_key = int(material_texture_crc32, 16)
                    else:
                        # If it's already an integer, use it directly
                        texture_key = material_texture_crc32
                        
                    if texture_key in images:
                        material_textures.append(images[texture_key])
                                    
                libs[material_name] = material_textures
    
    # Make txps
    txps = []
    for i in range(len(txp_data)):
        texproj_crc32 = txp_data[i][0]
        material_crc32 = txp_data[i][1]
        uv_map_index = txp_data[i][2]
        
        if texproj_crc32 in res_data[res.RESType.TEXPROJ]:
            if material_crc32 in res_data[res.RESType.MATERIAL_DATA]:
                textproj_name = res_data[res.RESType.TEXPROJ][texproj_crc32]
                material_name = res_data[res.RESType.MATERIAL_DATA][material_crc32]['name']
                txps.append([textproj_name, material_name, uv_map_index]) 
    
    # Make meshes
    if len(meshes_data) > 0:
        for i in range(len(meshes_data)):
            # Get mesh
            mesh_data = meshes_data[i]
            
            # Get lib
            lib = None
            if mesh_data['material_name'] in libs:
                lib = libs[mesh_data['material_name']]
            
            # Get bones
            bones = None
            if res.RESType.BONE in res_data:
                bones = res_data[res.RESType.BONE]
            
            # Get single_bind
            if mesh_data["single_bind"] is not None:
                mesh_data["single_bind"] = res_data[res.RESType.BONE][mesh_data["single_bind"]]
                
            # Create the mesh using the mesh data
            make_mesh(mesh_data, armature=armature, bones=bones, lib=lib, txp_data=txps)
    
    # Check if there is an active object and if it's an armature
    if armature == None and len(animations_data) > 0:
        active_obj = bpy.context.active_object
        if not active_obj or active_obj.type != 'ARMATURE':
            operator.report({'ERROR'}, 'No armature selected or active.')
            return {'CANCELLED'}
            
        armature = active_obj

    # Link animation to armature
    if len(animations_data) > 0:
        animations = []
        max_frames = 0
        
        # Iterate over main animations
        for animation_data in animations_data:
            animation = {}
            animation['main'] = animation_data
            animation['split'] = []

            # Find split animations for the current main animation
            for animation_split_data in animations_split_data:
                animation_crc32 = zlib.crc32(animation_data.AnimationName.encode("shift-jis"))
                if animation_crc32 == animation_split_data['anim_crc32']:
                    split_animation = {}
                    
                    split_animation['name'] = animation_data.AnimationName + '_' + animation_split_data['split_anim_name']
                    split_animation['frame_start'] = animation_split_data['frame_start']
                    split_animation['frame_end'] = animation_split_data['frame_end']
                    
                    animation['split'].append(split_animation)

            animations.append(animation)
                        
        # Add all animations to the armature
        for animation in animations:
            # Add main animation           
            name = animation['main'].AnimationName
            frame_count = animation['main'].FrameCount
            data = animation['main']
            
            if frame_count > max_frames:
                max_frames = frame_count
            
            create_animation(data, armature)
            
            # Split animations
            for split_animation in animation['split']:
                new_animation = bpy.data.actions.new(name=split_animation['name'])

                # Specify the start and end of the new animation
                start_frame = split_animation['frame_start']
                end_frame = split_animation['frame_end']

                # Copy the keyframes of the existing action into the new action
                for fcurve in bpy.data.actions.get(name).fcurves:
                    new_fcurve = new_animation.fcurves.new(data_path=fcurve.data_path, index=fcurve.array_index)
                    for keyframe in fcurve.keyframe_points:
                        if start_frame <= keyframe.co.x <= end_frame:
                            new_keyframe = new_fcurve.keyframe_points.insert(keyframe.co.x - start_frame, keyframe.co.y)
                            new_keyframe.interpolation = keyframe.interpolation            
        
        scene.frame_end = max_frames
        
        #setup_nla_tracks(armature)

    # Make camera
    if len(camera_data) > 0 and len(camera_hashes):
        frame = 0
        index = 0
        for camera_hash in camera_hashes:
            if camera_hash in camera_data:
                camera_values = camera_data[camera_hash]
                camera_name = archive_name.split('_')[0] + "_" + str(index).rjust(3, '0')
                create_camera(frame, camera_name, camera_values)
                frame += get_last_frame(camera_values)
                index += 1
            
    return {'FINISHED'}

def fileio_write_xpck(operator, context, filepath, template, mode, meshes = [], armature = None, textures = {}, animations = {}, outlines = [], cameras=[], properties=[], texprojs=[], attach_bone=False):
    xmprs = []
    atrs = []
    mtrs = []
    
    if meshes:
        for mesh in meshes:
            xmprs.append(fileio_write_xmpr(context, mesh.name, mesh.material_name, template[0].modes[template[1]]))
            atrs.append(bytes.fromhex(template[0].atr))
            mtrs.append(bytes.fromhex(template[0].mtr))

    # Make bones
    mbns = []
    if armature:
        for bone in armature.pose.bones:
            mbns.append(mbn.write(armature, bone))
 
    # Make images
    imgcs = []
    for texture_name, texture_data in textures.items():
        get_image_format = globals().get(texture_data['format'])
        
        if get_image_format:
            imgcs.append(imgc.write(bpy.data.images.get(texture_name), get_image_format()))
        else:
            operator.report({'ERROR'}, f"Class {texture.format} not found in img_format.")
            return {'FINISHED'}

    # Make animations
    mtns = []
    imms = []
    mtms = []
    mtninfs = []
    imminfs = []
    mtminfs = []
    
    anim_version = "V1" if template[0].name == "Inazuma Eleven Go" else "V2"
    for animation_type, animation_data in animations.items():
        if animation_type == 'armature':
            mtns.append(fileio_write_xmtn(context, armature, animation_data['name'], animation_data['transformations'], animation_data['bones'], anim_version))
            
            for split_animation in animation_data['split_animation']['split']:
                mtninfs.append(minf.write_minf1(animation_data['name'], split_animation.name, split_animation.speed, split_animation.frame_start, split_animation.frame_end))
        elif animation_type == 'uv':
            is_studio_eleven = animation_data['mode'] == "STUDIO_ELEVEN"
            imms.append(fileio_write_imm(context, armature, animation_data['name'], animation_data['transformations'], animation_data['texprojs'], is_studio_eleven, anim_version))
            
            for split_animation in animation_data['split_animation']['split']:
                imminfs.append(minf.write_minf1(animation_data['name'], split_animation.name, split_animation.speed, split_animation.frame_start, split_animation.frame_end))
        elif animation_type == 'material':
            is_studio_eleven = animation_data['mode'] == "STUDIO_ELEVEN"
            mtms.append(fileio_write_mtm(context, armature, animation_data['name'], animation_data['transformations'], animation_data['materials'], is_studio_eleven, anim_version))
            
            for split_animation in animation_data['split_animation']['split']:
                mtminfs.append(minf.write_minf1(animation_data['name'], split_animation.name, split_animation.speed, split_animation.frame_start, split_animation.frame_end))
    
    # Make outline
    xcsls = []
    if outlines:
        for outline in outlines:
            xcsls.append(xcsl.write(outline['name'], outline['meshes'], outline['thickness'], outline['visibility'], template[0].outline_mesh_data, template[0].cmb1, template[0].cmb2))

    # Make cameras
    xcmas = []
    cameras_sorted = []
    if cameras:
        # Sort camera by frame start
        cameras_sorted = sorted(cameras, key=lambda cam_object: get_first_frame(cam_object[2]))
        for cam_object in cameras_sorted:
            animation_name = cam_object[0]
            speed = cam_object[1]
            camera = cam_object[2]
            target = cam_object[3]
            xcmas.append(fileio_write_xcma(context, animation_name, speed, camera, target))
    
    # Make properties
    cmns = []
    if properties:
        for archive_property in properties:
            cmns.append(cmn.write(archive_property[0], archive_property[1])) 
    
    # Make texprojs
    txps = []
    if texprojs:
        for texproj in texprojs:
            txps.append(txp.write(texproj[0], texproj[1], texproj[2]))
    
    files = {}
    
    if mode == "MESH":
        if xmprs:
            files.update(create_files_dict(".prm", xmprs))
            
        if atrs:
            files.update(create_files_dict(".atr", atrs))

        if mtrs:
            files.update(create_files_dict(".mtr", mtrs))            
                        
        if imgcs:
            files.update(create_files_dict(".xi", imgcs))

        if xcsls:
            files.update(create_files_dict(".sil", xcsls))

        if cmns:
            files.update(create_files_dict(".cmn", cmns)) 
       
        if txps:
            files.update(create_files_dict(".txp", txps))  
    elif mode == "ARMATURE":
        if xmprs:
            files.update(create_files_dict(".prm", xmprs))
            
        if atrs:
            files.update(create_files_dict(".atr", atrs))

        if mtrs:
            files.update(create_files_dict(".mtr", mtrs)) 
            
        if mbns:
            files.update(create_files_dict(".mbn", mbns))
            
        if imgcs:
            files.update(create_files_dict(".xi", imgcs))

        if mtns:
            files.update(create_files_dict(".mtn2", mtns))
            
        if imms:
            files.update(create_files_dict(".imm2", imms))

        if mtms:
            files.update(create_files_dict(".mtm2", mtms))

        if mtninfs:
            files.update(create_files_dict(".mtninf", mtninfs))
 
        if imminfs:
            files.update(create_files_dict(".imminf", imminfs))

        if mtminfs:
            files.update(create_files_dict(".mtminf", mtminfs))

        if xcsls:
            files.update(create_files_dict(".sil", xcsls))
            
        if cmns:
            files.update(create_files_dict(".cmn", cmns))
            
        if txps:
            files.update(create_files_dict(".txp", txps))
    elif mode == "ANIMATION":
        if attach_bone:
            if mbns:
                files.update(create_files_dict(".mbn", mbns))
            
        if mtns:
            files.update(create_files_dict(".mtn2", mtns))
            
        if imms:
            files.update(create_files_dict(".imm2", imms))

        if mtms:
            files.update(create_files_dict(".mtm2", mtms))

        if mtninfs:
            files.update(create_files_dict(".mtninf", mtninfs))
 
        if imminfs:
            files.update(create_files_dict(".imminf", imminfs))

        if mtminfs:
            files.update(create_files_dict(".mtminf", mtminfs))
                
        if cmns:
            files.update(create_files_dict(".cmn", cmns))
    elif mode == "CAMERA":
        if xcmas:
            files.update(create_files_dict(".cmr2", xcmas))
    
    if mode == 'ARMATURE':
        items, string_table = res.make_library(
            meshes = meshes, 
            armature = armature, 
            textures = textures, 
            animations = animations, 
            outlines = outlines, 
            properties=properties, 
            texprojs=texprojs
        )
        
        if template[0].name == "Inazuma Eleven Go":
            files["RES.bin"] = res.write_xres(b"XRES", items, string_table)
        else: 
            files["RES.bin"] = res.write_res(b"CHRC00\x00\x00", items, string_table)
    
    elif mode == "ANIMATION":
        if attach_bone == False:
            armature = None
            
        items, string_table = res.make_library(
            armature = armature, 
            animations = animations,  
            properties=properties,
        )
        
        if template[0].name == "Inazuma Eleven Go":
            files["RES.bin"] = res.write_xres(b"XRES", items, string_table)
        else: 
            files["RES.bin"] = res.write_res(b"CHRC00\x00\x00", items, string_table)
    
    elif mode == "MESH":
        pass
        # Not implemented     
    elif mode == "CAMERA":
        if len(cameras_sorted) > 0:
            files["CMR.bin"] = xcmt.write(cameras_sorted)
    
    # Create xpck
    xpck.pack_archive(files, filepath)
    
    return {'FINISHED'}

##########################################
# Register class
##########################################

class OutlineItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    thickness: bpy.props.FloatProperty(default=0.0025, min=0.0000, max=0.9999, precision=4)
    visibility: bpy.props.FloatProperty(default=0.5, min=0.0, max=1.0, precision=4)
    private_index: bpy.props.IntProperty()

class OutlineMeshAssignment(bpy.types.PropertyGroup):
    outline_index: bpy.props.IntProperty()
    mesh_name: bpy.props.StringProperty()
    assigned: bpy.props.BoolProperty(default=False, update=lambda self, context: OutlineMeshAssignment.update_mesh_assignment(self, context))
    
    @staticmethod
    def update_mesh_assignment(self, context):
        """Update callback when mesh assignment checkbox changes"""
        scene = context.scene
        
        # If this mesh is being assigned to this outline, remove it from others
        if self.assigned:
            for assignment in scene.outline_mesh_assignments:
                if (assignment.mesh_name == self.mesh_name and 
                    assignment.outline_index != self.outline_index):
                    assignment.assigned = False
    
class ExportXC_AddOutlineItem(bpy.types.Operator):
    bl_idname = "export_xc.add_outline_item"
    bl_label = "Add Outline Item"
    
    def execute(self, context):
        collection = context.scene.outline_items
        new_item = collection.add()
        
        # Find the first unused private_index
        used_indexes = [item.private_index for item in collection]
        new_item.private_index = self.find_unused_index(used_indexes)
        
        new_item.name = "outline_" + str(new_item.private_index)
        new_item.thickness = 0.0025
        new_item.visibility = 0.5
        
        # Update mesh assignments when new outline is created
        self.update_mesh_assignments(context)
        
        return {'FINISHED'}
        
    def find_unused_index(self, used_indexes):
        # Find the first unused index
        index = 0
        while index in used_indexes:
            index += 1
        return index
    
    def update_mesh_assignments(self, context):
        scene = context.scene
        available_meshes = [obj.name for obj in bpy.data.objects if obj.type == 'MESH']

        existing_pairs = {(a.outline_index, a.mesh_name) for a in scene.outline_mesh_assignments}

        for outline_index, outline in enumerate(scene.outline_items):
            for mesh_name in available_meshes:
                if (outline_index, mesh_name) not in existing_pairs:
                    assignment = scene.outline_mesh_assignments.add()
                    assignment.outline_index = outline_index
                    assignment.mesh_name = mesh_name
                    assignment.assigned = False

class ExportXC_RemoveOutlineItem(bpy.types.Operator):
    bl_idname = "export_xc.remove_outline_item"
    bl_label = "Remove Outline Item"
    
    index: bpy.props.IntProperty()
    
    def execute(self, context):
        collection = context.scene.outline_items
        
        # Remove mesh assignments for this outline
        assignments = context.scene.outline_mesh_assignments
        to_remove = []
        for i, assignment in enumerate(assignments):
            if assignment.outline_index == self.index:
                to_remove.append(i)
        
        # Remove in reverse order to maintain indices
        for i in reversed(to_remove):
            assignments.remove(i)
        
        # Update indices for remaining assignments
        for assignment in assignments:
            if assignment.outline_index > self.index:
                assignment.outline_index -= 1
        
        collection.remove(self.index)
        return {'FINISHED'}

    def update_mesh_assignment(self, context):
        scene = context.scene

        if self.assigned:
            for assignment in scene.outline_mesh_assignments:
                if (assignment.mesh_name == self.mesh_name and 
                    assignment.outline_index != self.outline_index and
                    assignment.assigned):
                    self.assigned = False
                    break

class Animation(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    checked: bpy.props.BoolProperty(default=False, description="Include animation")

class AnimationItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    speed: bpy.props.FloatProperty(default=1.0)
    frame_start: bpy.props.IntProperty(default=1)
    frame_end: bpy.props.IntProperty(default=250)
    private_index: bpy.props.IntProperty()

class ExportXC_AddAnimationItem(bpy.types.Operator):
    bl_idname = "export_xc.add_animation_item"
    bl_label = "Add Animation Item"
    
    collection_name: bpy.props.StringProperty()
    
    def execute(self, context):
        print(context.scene, self.collection_name, (self.collection_name == ''))
        collection = getattr(context.scene, self.collection_name)
        new_item = collection.add()
        
        # Find the first unused private_index
        used_indexes = [item.private_index for item in collection]
        new_item.private_index = self.find_unused_index(used_indexes)
        
        new_item.name = "splitted_animation_" + str(new_item.private_index)
        new_item.speed = 1
        new_item.frame_start = 1
        new_item.frame_end = 250
        return {'FINISHED'}
        
    def find_unused_index(self, used_indexes):
        # Trouver le premier index non utilisé
        index = 0
        while index in used_indexes:
            index += 1
        return index

class ExportXC_RemoveAnimationItem(bpy.types.Operator):
    bl_idname = "export_xc.remove_animation_item"
    bl_label = "Remove Animation Item"
    
    collection_name: bpy.props.StringProperty()
    index: bpy.props.IntProperty()
    
    def execute(self, context):
        collection = getattr(context.scene, self.collection_name)
        collection.remove(self.index)
        return {'FINISHED'}
    
class TexturePropertyGroup(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    format: bpy.props.EnumProperty(
        items=[
            ('RGBA8', "RGBA8", "Make RGBA8 image"),
            ('RGBA4', "RGBA4", "Make RGBA4 image"),
            ('RBGR888', "RBGR888", "Make RBGR888 image"),
            ('RGB565', "RGB565", "Make RGB565 image"),
            #('L4', "L4", "Make L4 image"),
            #('ETC1', "ETC1", "Make ETC1 image"),
            #('ETC1A4', "ETC1A4", "Make ETC1A4 image"),
        ],
        default='RGBA8'
    )
    mesh_name: bpy.props.StringProperty()

class TexprojPropertyGroup(bpy.types.PropertyGroup):
    checked: bpy.props.BoolProperty(default=False, description="Texproj name")
    name: bpy.props.StringProperty()
    mesh_name: bpy.props.StringProperty()

class LibPropertyGroup(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    textures: bpy.props.CollectionProperty(type=TexturePropertyGroup)

class MeshPropertyGroup(bpy.types.PropertyGroup):
    checked: bpy.props.BoolProperty(default=False, description="Mesh name")
    name: bpy.props.StringProperty()
    material_name: bpy.props.StringProperty()
    
class CameraPropertyGroup(bpy.types.PropertyGroup):
    checked: bpy.props.BoolProperty(default=False, description="Camera name")
    name: bpy.props.StringProperty()
    animation_name: bpy.props.StringProperty()
    speed: bpy.props.FloatProperty(default=1.0, min=0.1, precision=2) 
    
class ArchivePropertyGroup(bpy.types.PropertyGroup):
    checked: bpy.props.BoolProperty(default=False, description="Property name")
    name: bpy.props.StringProperty()
    value: bpy.props.FloatProperty(default=0.0, description="Property value")

class ExportXC(bpy.types.Operator, ExportHelper):
    bl_idname = "export.xc"
    bl_label = "Export to XPCK"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".xc"
    filter_glob: StringProperty(
        default="*.xc;*.xv;*.pck",
        options={'HIDDEN'}
    )
        
    export_tab_control: bpy.props.EnumProperty(
        items=[
            ('MAIN', "Main", "Configure the essentials"),
            ('ANIMATION', "Animations", "Configure animations"),
            ('OUTLINES', "Outlines", "Configure outlines"),
        ],
        default='MAIN'
    )
    main_tab_control: bpy.props.EnumProperty(
        name="Main Tabs",
        description="Tabs for Main settings",
        items=[
            ('GENERAL', "General", "General settings"),
            ('TEXTURES', "Textures", "Configure textures"),
            ('PROPERTIES', "Properties", "Configure properties")
        ],
        default='GENERAL'
    )
    export_tab_animation_control: bpy.props.EnumProperty(
        name="Animation Tabs",
        description="Tabs for Animation settings",
        items=[
            ('ARMATURE_ANIMATION', "Armature", "Settings for Armature animations"),
            ('UV_ANIMATION', "UV", "Settings for UV animations"),
            ('MATERIAL_ANIMATION', "Material", "Settings for Material animations")
        ],
        default='ARMATURE_ANIMATION'
    ) 
    export_option: bpy.props.EnumProperty(
        name="Mode",
        items=[
            #('MESH', "Meshes", "Export multiple meshes"),
            ('ARMATURE', "Armature", "Export one armature"),
            ('ANIMATION', "Animation", "Export one animation"),
            ('CAMERA', "Cameras", "Export multiple camera"),
        ],
        default='ARMATURE'
    ) 

    mesh_properties: bpy.props.CollectionProperty(type=MeshPropertyGroup)
    texproj_properties: bpy.props.CollectionProperty(type=TexprojPropertyGroup)
    texture_properties: bpy.props.CollectionProperty(type=TexturePropertyGroup)
    camera_properties: bpy.props.CollectionProperty(type=CameraPropertyGroup)
    archive_properties: bpy.props.CollectionProperty(type=ArchivePropertyGroup)
    
    include_animation_armature: bpy.props.BoolProperty(
        name="Include Animation",
        default=False,
        description="Include animation in the export"
    )
    include_animation_uv: bpy.props.BoolProperty(
        name="Include Animation",
        default=False,
        description="Include animation in the export"
    )
    include_animation_material: bpy.props.BoolProperty(
        name="Include Animation",
        default=False,
        description="Include animation in the export"
    )

    animation_name_armature: bpy.props.StringProperty(
        name="Animation Name",
        default="animation",
        description="Name of the animation"
    )
    animation_name_uv: bpy.props.StringProperty(
        name="Animation Name",
        default="animation",
        description="Name of the animation"
    )
    animation_name_material: bpy.props.StringProperty(
        name="Animation Name",
        default="animation",
        description="Name of the animation"
    )    
    
    animation_format_armature: bpy.props.EnumProperty(
        name="Format",
        items=[
            ('MTN2', "MTN2", "Make MTN2 Animation"),
            #('MTN3', "MTN3", "Make MTN3 Animation"),
        ],
        default='MTN2'
    )
    animation_format_uv: bpy.props.EnumProperty(
        name="Format",
        items=[
            ('IMM2', "IMM2", "Make IMM2 Animation"),
        ],
        default='IMM2'
    )
    animation_format_material: bpy.props.EnumProperty(
        name="Format",
        items=[
            ('MTM2', "MTM2", "Make MTM2 Animation"),
        ],
        default='MTM2'
    )    

    split_animation_format_armature: bpy.props.EnumProperty(
        name="Format",
        items=[
            ('MTNINF', "MTNINF", "Make MTNINF Split Animation"),
            #('MTNINF2', "MTNINF2", "Make MTNINF2 Split Animation"),
        ],
        default='MTNINF'
    )
    split_animation_format_uv: bpy.props.EnumProperty(
        name="Format",
        items=[
            ('IMMINF', "IMMINF", "Make IMMINF Split Animation"),
        ],
        default='IMMINF'
    )  
    split_animation_format_material: bpy.props.EnumProperty(
        name="Format",
        items=[
            ('MTMINF', "MTMINF", "Make MTMINF Split Animation"),
        ],
        default='MTMINF'
    )      
    
    def armature_items_callback(self, context):
        # Get armatures
        armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
        
        if not armatures:
            # No armatures found, return default or empty list
            return [("None", "None", "No armature found")]
        
        armature_enum_items = [(armature.name, armature.name, "") for armature in armatures]
        return armature_enum_items    

    def update_armature(self, context):
        """Update bone checkboxes when armature is changed."""
        if self.armature_enum and self.armature_enum != "None":
            armature = bpy.data.objects.get(self.armature_enum)
            
            if armature and armature.type == "ARMATURE":
                existing_bones = {checkbox.name: checkbox.enabled for checkbox in self.bone_checkboxes}
                self.bone_checkboxes.clear()  # Effacer l'ancienne liste

                for bone in armature.data.bones:
                    checkbox = self.bone_checkboxes.add()
                    checkbox.name = bone.name
                    checkbox.enabled = existing_bones.get(bone.name, True)
                    
                existing_textjprojs = {checkbox.name: checkbox.enabled for checkbox in self.texjproj_checkboxes}
                self.texjproj_checkboxes.clear()  # Effacer l'ancienne liste

                for texproj in self.texproj_properties:
                    checkbox = self.texjproj_checkboxes.add()
                    checkbox.name = texproj.name
                    checkbox.enabled = existing_textjprojs.get(texproj.name, True)
                    
                existing_materials = {checkbox.name: checkbox.enabled for checkbox in self.material_checkboxes}
                self.material_checkboxes.clear()  # Effacer l'ancienne liste
                
                for child in armature.children:
                    if child.type == "MESH":
                        for mat in child.data.materials:
                            checkbox = self.material_checkboxes.add()
                            checkbox.name = mat.name
                            checkbox.enabled = existing_materials.get(mat.name, True)   

    armature_enum: EnumProperty(
        name="Armatures",
        items=armature_items_callback,
        default=0,
        update=update_armature
    )   
        
    def animation_items_callback(self, context):
        # Get armatures
        armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
        
        animation_names = []
        
        # Loop through armatures
        for armature in armatures:
            if armature.animation_data and armature.animation_data.action:
                action = armature.animation_data.action
                animation_names.append((action.name, action.name, ""))
        
        if not animation_names:
            # No animations found, return default or empty list
            return [("None", "None", "No animations found")]
        
        return animation_names
    
    animation_enum: EnumProperty(
        name="Armatures",
        items=animation_items_callback,
        default=0
    )       

    attach_bone: bpy.props.BoolProperty(
        name="Attach amarture",
        description="Whether to attach armature or not",
        default=False
    )
    attach_texproj: bpy.props.BoolProperty(
        name="Attach texproj",
        description="Whether to attach textproj or not",
        default=False
    )

    def template_items_callback(self, context):
        my_templates = get_templates()
        items = [(template.name, template.name, "") for template in my_templates]
        return items

    template_name: EnumProperty(
        name="Templates",
        description="Choose a template",
        items=template_items_callback,
        default=0,
    )
    
    def template_mode_items_callback(self, context):
        my_template = get_template_by_name(self.template_name)
        items = [(mode, mode, "") for mode in my_template.modes.keys()]
        return items

    template_mode_name: EnumProperty(
        name="Mode",
        description="Choose a mode",
        items=template_mode_items_callback,
        default=0,
    )

    bone_transformation_location: bpy.props.BoolProperty(
        name="Location",
        default=True,
        description="Include bone transformation location in the export"
    )
    bone_transformation_rotation: bpy.props.BoolProperty(
        name="Rotation",
        default=True,
        description="Include bone transformation rotation in the export"
    )
    bone_transformation_scale: bpy.props.BoolProperty(
        name="Scale",
        default=True,
        description="Include bone transformation scale in the export"
    )
    bone_transformation_bool: bpy.props.BoolProperty(
        name="Bool",
        default=True,
        description="Include bone transformation bool in the export"
    )
    uv_transformation_location: bpy.props.BoolProperty(
        name="Location",
        default=True,
        description="Include uv transformation location in the export"
    )
    uv_transformation_rotation: bpy.props.BoolProperty(
        name="Rotation",
        default=True,
        description="Include uv transformation rotation in the export"
    )
    uv_transformation_scale: bpy.props.BoolProperty(
        name="Scale",
        default=True,
        description="Include uv transformation scale in the export"
    )
    material_transformation_transparency: bpy.props.BoolProperty(
        name="Transparency",
        default=True,
        description="Include material transformation transparency in the export"
    )
    material_transformation_attribute: bpy.props.BoolProperty(
        name="Attribute",
        default=True,
        description="Include material transformation attribute in the export"
    )    
    
    view_bones: BoolProperty(
        name="View Bones",
        description="Toggle the visibility of the bones list",
        default=False  # Default to hidden
    )   
    view_textproj: BoolProperty(
        name="View Linked Objects",
        description="Toggle the visibility of the linked object list",
        default=False  # Default to hidden
    )
    view_material: BoolProperty(
        name="View Linked Objects",
        description="Toggle the visibility of the linked object list",
        default=False  # Default to hidden
    )
    
    uv_mode: EnumProperty(
        name="Mode",
        description="Choose a mode for UV animations",
        items=[
            ("STUDIO_ELEVEN", "Studio Eleven", "Studio Eleven mode"),
            ("BERRY_BUSH", "Berry Bush", "Berry Bush mode")
        ],
        default="STUDIO_ELEVEN"
    )
    material_mode: EnumProperty(
        name="Mode",
        description="Choose a mode for Material animations",
        items=[
            ("STUDIO_ELEVEN", "Studio Eleven", "Studio Eleven mode"),
            ("BERRY_BUSH", "Berry Bush", "Berry Bush mode")
        ],
        default="STUDIO_ELEVEN"
    )    

    bone_checkboxes: CollectionProperty(type=BoneCheckbox)
    texjproj_checkboxes: CollectionProperty(type=BoneCheckbox)
    material_checkboxes: CollectionProperty(type=BoneCheckbox)

    outline_items: bpy.props.CollectionProperty(type=OutlineItem)
    outline_mesh_assignments: bpy.props.CollectionProperty(type=OutlineMeshAssignment)

    def get_available_meshes_for_outline(self, context, outline_index):
        """Get meshes that are not assigned to any outline"""
        all_meshes = [obj.name for obj in bpy.data.objects if obj.type == 'MESH']
        assigned_meshes = set()
        
        for assignment in context.scene.outline_mesh_assignments:
            if assignment.assigned and assignment.outline_index != outline_index:
                assigned_meshes.add(assignment.mesh_name)
        
        return [mesh for mesh in all_meshes if mesh not in assigned_meshes]

    def get_assigned_meshes_for_outline(self, context, outline_index):
        """Get meshes assigned to this specific outline"""
        assigned = []
        for assignment in context.scene.outline_mesh_assignments:
            if assignment.assigned and assignment.outline_index == outline_index:
                assigned.append(assignment.mesh_name)
        return assigned

    def draw_main(self, context, layout):
        box = layout.box()
        
        # Add tab control for main sections
        row = box.row(align=True)
        row.prop(self, "main_tab_control", expand=True)
        
        # Display content based on selected tab
        if self.main_tab_control == 'GENERAL':
            self.draw_general(context, box)
        elif self.main_tab_control == 'TEXTURES':
            self.draw_texture(context, box)
        elif self.main_tab_control == 'PROPERTIES':
            self.draw_properties(context, box)

    def draw_general(self, context, layout):
        # Add the template_name property to the general section
        layout.prop(self, "template_name", text="Template")
        layout.prop(self, "template_mode_name", text="Mode")
        
        # Create a box for export option, mesh group, and armature enum
        options_box = layout.box()
        options_box.prop(self, "export_option", text="Export Option")
        
        if self.export_option == 'MESH':
            mesh_group = options_box.box()
            for mesh_prop in self.mesh_properties:
                row = mesh_group.row(align=True)
                row.prop(mesh_prop, "checked", text=mesh_prop.name)
                row.prop(self.libs[mesh_prop.library_index], "name", text="", emboss=False)
        elif self.export_option == 'ARMATURE':
            options_box.prop(self, "armature_enum", text="Available armatures")

            # Display meshes associated with the selected armature
            armature = bpy.data.objects.get(self.armature_enum)
            if armature and armature.type == 'ARMATURE':
                mesh_group = options_box.box()
                for child in armature.children:
                    if child.type == 'MESH':
                        row = mesh_group.row(align=True)
                        row.prop(self.mesh_properties[child.name], "checked", text=child.name)
                        row.label(text=self.mesh_properties[child.name].material_name)
                        
                        txp_group = mesh_group.box()
                        for texproj in self.texproj_properties:
                            if texproj.mesh_name == child.name:
                                row = txp_group.row(align=True)
                                row.prop(texproj, "checked", text=texproj.name)
        elif self.export_option == 'ANIMATION':
            options_box.prop(self, "animation_enum", text="Available animations")
            options_box.prop(self, "attach_bone", text="Attach armature")
            #options_box.prop(self, "attach_texproj", text="Attach texproj")
        elif self.export_option == 'CAMERA':
            camera_group = options_box.box()
            for camera_prop in self.camera_properties:
                row = camera_group.row(align=True)
                row.prop(camera_prop, "checked", text=camera_prop.name)
                row.prop(camera_prop, "animation_name", text="Name")
                row.prop(camera_prop, "speed", text="Speed")

    def draw_texture(self, context, layout):
        if self.export_option == 'CAMERA' or self.export_option == 'ANIMATION':
            texture_box = layout.box()
            
            if self.export_option == 'ANIMATION':
                texture_box.label(text="Not available on animation mode")
            elif self.export_option == 'CAMERA':
                texture_box.label(text="Not available on camera mode")
        else:
            meshes_props =[]
            same_texture = []
            
            if self.export_option == 'MESH':
                meshes_props = [mesh_prop.name for mesh_prop in self.mesh_properties if mesh_prop.checked]
            elif self.export_option == 'ARMATURE':
                if self.armature_enum and self.armature_enum != "None":
                    armature = bpy.data.objects.get(self.armature_enum)
                    armature_meshes = [child for child in armature.children if child.type == 'MESH']
                    for mesh_prop in self.mesh_properties:
                        if mesh_prop.checked:
                            mesh = bpy.data.objects.get(mesh_prop.name)
                            if mesh and mesh in armature_meshes:     
                                meshes_props.append(mesh_prop.name)

            groupbox = layout.box()
            box = groupbox.box()

            for texture_prop in self.texture_properties:
                if texture_prop.mesh_name in meshes_props:
                    if texture_prop.name not in same_texture:
                        row = box.row(align=True)
                        row.label(text=texture_prop.name)
                        row.prop(texture_prop, "format", text="")
                        same_texture.append(texture_prop.name)

    def draw_animation(self, context, layout):
        anim_box = layout.box()

        if self.export_option == 'ARMATURE' or self.export_option == 'ANIMATION':
            row = anim_box.row(align=True)
            row.prop(self, "export_tab_animation_control", expand=True)
            
            # Check the selected tab
            if self.export_tab_animation_control == 'ARMATURE_ANIMATION':
                self.draw_armature_animation(context, anim_box)
            elif self.export_tab_animation_control == 'UV_ANIMATION':
                self.draw_uv_animation(context, anim_box)
            elif self.export_tab_animation_control == 'MATERIAL_ANIMATION':
                self.draw_material_animation(context, anim_box)
        else:
            if self.export_option == 'MESH':
                anim_box.label(text="Not available on mesh mode")
            elif self.export_option == 'CAMERA':
                anim_box.label(text="Not available on camera mode")

    def draw_armature_animation(self, context, anim_box):
        armature_box = anim_box
        
        # Checkbox for including animation
        armature_box.prop(self, "include_animation_armature", text="Includes Animation")

        if self.include_animation_armature:
            # Group for animation settings
            armature_box = anim_box.box()

            # Text field for animation name
            armature_box.prop(self, "animation_name_armature", text="Animation Name", icon='ANIM') 
            armature_box.prop(self, "animation_format_armature", text="Animations Format")
            armature_box.prop(self, "split_animation_format_armature", text="Split Animations Format")

            # Group for manual item addition/removal
            items_box = armature_box.box()
            
            # List of items with name, frame start, and frame end
            for index, item in enumerate(context.scene.animation_items_armature):
                row = items_box.row(align=True)
                row.prop(item, "name", text="Name")
                row.prop(item, "speed", text="Speed")
                row.prop(item, "frame_start", text="Start Frame")
                row.prop(item, "frame_end", text="End Frame")
                
                # Button to remove selected item
                remove_button = row.operator("export_xc.remove_animation_item", text="", icon='REMOVE')
                remove_button.index = index  # Pass the index to the operator
                remove_button.collection_name = "animation_items_armature"
                
            # Button to add an item
            add_button = items_box.operator("export_xc.add_animation_item", text="Add Item", icon='ADD')
            add_button.collection_name = "animation_items_armature"
            
            # Draw the transformation checkboxes
            box = armature_box.box()
            box.label(text="Transformations:")
            box.prop(self, "bone_transformation_location")
            box.prop(self, "bone_transformation_rotation")
            box.prop(self, "bone_transformation_scale")
            box.prop(self, "bone_transformation_bool")
            
            if self.armature_enum and self.armature_enum != "None":
                armature_box.prop(self, "view_bones", text="View Bones")

                self.update_armature(context)
                if self.view_bones:
                    box = armature_box.box()
                    box.label(text="Bones:")
                    for bone in self.bone_checkboxes:
                        box.prop(bone, "enabled", text=bone.name)

    def draw_uv_animation(self, context, anim_box):
        uv_box = anim_box
        
        # Checkbox for including animation
        uv_box.prop(self, "include_animation_uv", text="Includes Animation")

        if self.include_animation_uv:
            # Group for animation settings
            uv_box = anim_box.box()

            # Text field for animation name
            uv_box.prop(self, "animation_name_uv", text="Animation Name", icon='ANIM') 
            uv_box.prop(self, "animation_format_uv", text="Animations Format")
            uv_box.prop(self, "split_animation_format_uv", text="Split Animations Format")
            uv_box.prop(self, "uv_mode", text="Mode")

            # Group for manual item addition/removal
            items_box = uv_box.box()
            
            # List of items with name, frame start, and frame end
            for index, item in enumerate(context.scene.animation_items_uv):
                row = items_box.row(align=True)
                row.prop(item, "name", text="Name")
                row.prop(item, "speed", text="Speed")
                row.prop(item, "frame_start", text="Start Frame")
                row.prop(item, "frame_end", text="End Frame")
                
                # Button to remove selected item
                remove_button = row.operator("export_xc.remove_animation_item", text="", icon='REMOVE')
                remove_button.index = index  # Pass the index to the operator
                remove_button.collection_name = "animation_items_uv"
                
            # Button to add an item
            add_button = items_box.operator("export_xc.add_animation_item", text="Add Item", icon='ADD')
            add_button.collection_name = "animation_items_uv"
            
            # Draw the transformation checkboxes
            box = uv_box.box()
            box.label(text="Transformations:")
            box.prop(self, "uv_transformation_location")
            box.prop(self, "uv_transformation_rotation")
            box.prop(self, "uv_transformation_scale")
            
            if self.armature_enum and self.armature_enum != "None":
                uv_box.prop(self, "view_textproj", text="View Texproj")

                self.update_armature(context)
                if self.view_textproj:
                    box = uv_box.box()
                    box.label(text="Texprojs:")
                    for textproj in self.texjproj_checkboxes:
                        box.prop(textproj, "enabled", text=textproj.name)

    def draw_material_animation(self, context, anim_box):
        material_box = anim_box
        
        # Checkbox for including animation
        material_box.prop(self, "include_animation_material", text="Includes Animation")

        if self.include_animation_material:
            # Group for animation settings
            material_box = anim_box.box()

            # Text field for animation name
            material_box.prop(self, "animation_name_material", text="Animation Name", icon='ANIM') 
            material_box.prop(self, "animation_format_material", text="Animations Format")
            material_box.prop(self, "split_animation_format_material", text="Split Animations Format")
            material_box.prop(self, "material_mode", text="Mode")

            # Group for manual item addition/removal
            items_box = material_box.box()
            
            # List of items with name, frame start, and frame end
            for index, item in enumerate(context.scene.animation_items_material):
                row = items_box.row(align=True)
                row.prop(item, "name", text="Name")
                row.prop(item, "speed", text="Speed")
                row.prop(item, "frame_start", text="Start Frame")
                row.prop(item, "frame_end", text="End Frame")
                
                # Button to remove selected item
                remove_button = row.operator("export_xc.remove_animation_item", text="", icon='REMOVE')
                remove_button.index = index  # Pass the index to the operator
                remove_button.collection_name = "animation_items_material"
                
            # Button to add an item
            add_button = items_box.operator("export_xc.add_animation_item", text="Add Item", icon='ADD')
            add_button.collection_name = "animation_items_material"
            
            # Draw the transformation checkboxes
            box = material_box.box()
            box.label(text="Transformations:")
            box.prop(self, "material_transformation_transparency")
            box.prop(self, "material_transformation_attribute")
            
            if self.armature_enum and self.armature_enum != "None":
                material_box.prop(self, "view_material", text="View Material")

                self.update_armature(context)
                if self.view_material:
                    box = material_box.box()
                    box.label(text="Materials:")
                    for material in self.material_checkboxes:
                        box.prop(material, "enabled", text=material.name)

    def draw_properties(self, context, layout):
        properties_box = layout.box()
        
        if self.export_option != 'CAMERA':
            for archive_prop in self.archive_properties:
                row = properties_box.row(align=True)
                row.prop(archive_prop, "checked", text=archive_prop.name)
                row.prop(archive_prop, "value", text="")
        else:
            properties_box.label(text="Not available on camera mode")

    def draw_outlines(self, context, layout):
        outline_box = layout.box()
        
        # List existing outline items
        for index, outline_item in enumerate(context.scene.outline_items):
            item_box = outline_box.box()
            
            # Outline properties
            row = item_box.row(align=True)
            row.prop(outline_item, "name", text="Name")
            
            # Remove button
            remove_button = row.operator("export_xc.remove_outline_item", text="", icon='REMOVE')
            remove_button.index = index
            
            # Properties
            item_box.prop(outline_item, "thickness", text="Thickness")
            item_box.prop(outline_item, "visibility", text="Visibility")
            
            # Mesh selection for this outline
            mesh_box = item_box.box()
            mesh_box.label(text="Meshes:")
            
            # Get available meshes for this outline
            available_meshes = self.get_available_meshes_for_outline(context, index)
            assigned_meshes = self.get_assigned_meshes_for_outline(context, index)
            
            for mesh_name in available_meshes:
                # Find the assignment
                assignment = None
                for assign in context.scene.outline_mesh_assignments:
                    if (assign.outline_index == index and assign.mesh_name == mesh_name):
                        assignment = assign
                        break
                
                if assignment:
                    mesh_box.prop(assignment, "assigned", text=mesh_name)
        
        # Add new outline button
        outline_box.operator("export_xc.add_outline_item", text="Add Outline", icon='ADD')
        
    def invoke(self, context, event):
        wm = context.window_manager  

        self.mesh_properties.clear()
        self.texproj_properties.clear()
        self.texture_properties.clear()
        self.camera_properties.clear()
        
        self.archive_properties.clear()

        # Get meshes
        meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        
        # Determine if all meshes have the same UV map names
        uv_map_names = [set(mesh.data.uv_layers.keys()) for mesh in meshes]
        common_uv_maps = set.intersection(*uv_map_names) if uv_map_names else set()

        for mesh in meshes:
            # Adding mesh properties
            item = self.mesh_properties.add()
            item.checked = True
            item.name = mesh.name
            
            if mesh.data.materials and len(mesh.data.materials) > 0:
                item.material_name = mesh.data.materials[0].name
            else:
                item.material_name = f"DefaultLib.{mesh.name}"
            
            # Managing UV layers
            for index, uv_layer in enumerate(mesh.data.uv_layers):
                item = self.texproj_properties.add()
                item.mesh_name = mesh.name
                item.checked = True

                if uv_layer.name in common_uv_maps and len(common_uv_maps) > 0:
                    # Specific format if the UV maps are identical between all meshes
                    item.name = f"{mesh.name}.texproj{index}"
                else:
                    # Default name
                    if len(uv_map_names) == 1 and uv_layer.name == 'UVMap':
                        item.name = "UVMap.texproj0"
                    else:
                        item.name = uv_layer.name

            # Get textures from materials
            for material_slot in mesh.material_slots:
                material = material_slot.material
                if material.use_nodes:
                    # If material uses nodes, iterate over the material nodes
                    for node in material.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            texture_name = node.image.name
                            item = self.texture_properties.add()
                            item.name = texture_name
                            item.mesh_name = mesh.name
                else:
                    # If material doesn't use nodes, try to access the texture from the diffuse shader
                    if hasattr(material, 'texture_slots'):
                        if material.texture_slots and material.texture_slots[0] and material.texture_slots[0].texture:
                            texture = material.texture_slots[0].texture
                            texture_name = texture.name
                            item = self.texture_properties.add()
                            item.name = texture_name
                            item.mesh_name = mesh.name
                    else:
                        # Enter in berry bush situation
                        for texture_berry_bush in material.brres.textures:
                            texture_name = texture_berry_bush.name
                            for image in texture_berry_bush.imgs:
                                item = self.texture_properties.add()
                                item.name = texture_name
                                item.mesh_name = mesh.name   

        # Get cameras
        for obj in bpy.context.scene.objects:
            if CameraElevenObject.is_camera_eleven(obj):
                item = self.camera_properties.add()
                item.checked = True
                item.name = obj.name
                item.animation_name = ""
                item.speed = 1.0

        # Get archive properties
        for name, value in properties.items():
            item = self.archive_properties.add()
            item.checked = value[0]
            item.name = name
            item.value = value[1]
            
        wm.fileselect_add(self)    
        return {'RUNNING_MODAL'}

    def draw(self, context):
        layout = self.layout
        
        row = layout.row(align=True)
        row.prop(self, "export_tab_control", expand=True)        
        
        if self.export_tab_control == 'MAIN':
            self.draw_main(context, layout)
        elif self.export_tab_control == 'ANIMATION':
            self.draw_animation(context, layout)
        elif self.export_tab_control == 'OUTLINES':
            self.draw_outlines(context, layout)
            
    def execute(self, context):
        armature = None
        meshes = []
        textures = {}
        cameras = []
        properties = []
        texprojs = []
        outlines = []
        
        animations = {}
        animation_uv = []
        split_animations_uv = []
        animation_material = []
        split_animations_material = []
        
        if self.export_option == 'MESH':
            self.report({'ERROR'}, f"Mesh export not yet available!")
            return {'FINISHED'}
        elif self.export_option == 'ARMATURE':
            # Check that all meshes have a library name
            armature = bpy.data.objects.get(self.armature_enum)
            
            if armature and armature.type == 'ARMATURE':
                # Get the meshes associated with the selected armature
                armature_meshes = [child for child in armature.children if child.type == 'MESH']

                for mesh_prop in self.mesh_properties:
                    if mesh_prop.checked:
                        # Check if the mesh is associated with the armature
                        mesh = bpy.data.objects.get(mesh_prop.name)
                        
                        if mesh and mesh in armature_meshes:
                            linked_texproj = [
                                texproj for texproj in self.texproj_properties
                                if texproj.mesh_name == mesh_prop.name
                            ]
                            
                            for i in range(len(linked_texproj)):
                                name = linked_texproj[i].name
                                texproj = [name, mesh_prop.material_name, i]
                                texprojs.append(texproj)

                            linked_textures = [
                                texture for texture in self.texture_properties
                                if texture.mesh_name == mesh_prop.name
                            ]
                            
                            for texture in linked_textures:
                                if texture.name not in textures:
                                    textures[texture.name] = {}
                                    textures[texture.name]['format'] = texture.format
                                    textures[texture.name]['linked_material'] = []
                                    
                                textures[texture.name]['linked_material'].append(mesh_prop.material_name)  
                        
                            meshes.append(mesh_prop)
        elif self.export_option == 'ANIMATION':
            find_armature = find_armature_by_animation(self.animation_enum)

            if find_armature == None:
                self.report({'ERROR'}, "The armature attached to the animation hasn't been found")
                return {'FINISHED'}
            else:
                armature = find_armature
            
            if self.attach_texproj:
                # To do
                pass
        elif self.export_option == 'CAMERA':
            camera_animation_names = []
            
            for camera_prop in self.camera_properties:
                if camera_prop.checked:
                # Check if the camera has a animation name
                    if camera_prop.animation_name == "":
                        self.report({'ERROR'}, f"{camera_prop.name}' is checked but doesn't have a animation name!")
                        return {'FINISHED'}
                    else:
                        camera_eleven = bpy.data.objects.get(camera_prop.name)
                        camera, target = CameraElevenObject.get_camera_and_target(camera_eleven)
                        cameras.append([camera_prop.animation_name, camera_prop.speed, camera, target])
                        camera_animation_names.append(camera_prop.animation_name)
                        
                if len(set(camera_animation_names)) != len(camera_animation_names):
                    self.report({'ERROR'}, f"Several cameras have the same animation name")
                    return {'FINISHED'}

        # Get archive properties
        if self.export_option != 'CAMERA':
            for archive_prop in self.archive_properties:
                if archive_prop.checked:
                    properties.append([archive_prop.name, archive_prop.value])

        # Get animations
        if self.export_option != 'CAMERA':
            if self.include_animation_armature:
                animation_armature = {}
                split_animations_armature = {}
                transformations = []
                
                if self.bone_transformation_location:
                    transformations.append('location')
                    
                if self.bone_transformation_rotation:
                    transformations.append('rotation')
                    
                if self.bone_transformation_scale:
                    transformations.append('scale')
                    
                if self.bone_transformation_bool:
                    transformations.append('bool')
        
                if not self.animation_name_armature:
                    self.report({'ERROR'}, "The animation doesn't have name")
                    return {'FINISHED'}

                split_animations_armature['format'] = self.split_animation_format_armature
                split_animations_armature['split'] = []
                    
                for sub_animation in context.scene.animation_items_armature:
                    if not sub_animation.name:
                        self.report({'ERROR'}, f"splitted_animation_'{sub_animation.private_index}' doesn't have a a name!")
                        return {'FINISHED'}
                    else:
                        split_animations_armature['split'].append(sub_animation)	
                
                animation_armature['name'] = self.animation_name_armature       
                animation_armature['format'] = self.animation_format_armature
                animation_armature['transformations'] = transformations
                animation_armature['bones'] = [bone.name for bone in self.bone_checkboxes if bone.enabled]
                animation_armature['split_animation'] = split_animations_armature
                animations['armature'] = animation_armature
                
            if self.include_animation_uv:
                animation_uv = {}
                split_animations_uv = {}
                transformations = []
                
                if self.uv_transformation_location:
                    transformations.append('offset')
                    
                if self.uv_transformation_rotation:
                    transformations.append('rotation')
                    
                if self.uv_transformation_scale:
                    transformations.append('scale')
        
                if not self.animation_name_uv:
                    self.report({'ERROR'}, "The animation doesn't have name")
                    return {'FINISHED'}

                split_animations_uv['format'] = self.split_animation_format_uv
                split_animations_uv['split'] = []
                    
                for sub_animation in context.scene.animation_items_uv:
                    if not sub_animation.name:
                        self.report({'ERROR'}, f"splitted_animation_'{sub_animation.private_index}' doesn't have a a name!")
                        return {'FINISHED'}
                    else:
                        split_animations_uv['split'].append(sub_animation)	
                
                animation_uv['name'] = self.animation_name_uv       
                animation_uv['format'] = self.animation_format_uv
                animation_uv['transformations'] = transformations
                animation_uv['mode'] = self.uv_mode
                animation_uv['texprojs'] = [texproj.name for texproj in self.texjproj_checkboxes if texproj.enabled]
                animation_uv['split_animation'] = split_animations_uv
                animations['uv'] = animation_uv
                
            if self.include_animation_material:
                animation_material = {}
                split_animations_material = {}
                transformations = []
                
                if self.material_transformation_transparency:
                    transformations.append('transparency')
                    
                if self.material_transformation_attribute:
                    transformations.append('attribute')
        
                if not self.animation_name_material:
                    self.report({'ERROR'}, "The animation doesn't have name")
                    return {'FINISHED'}

                split_animations_material['format'] = self.split_animation_format_material
                split_animations_material['split'] = []
                    
                for sub_animation in context.scene.animation_items_material:
                    if not sub_animation.name:
                        self.report({'ERROR'}, f"splitted_animation_'{sub_animation.private_index}' doesn't have a a name!")
                        return {'FINISHED'}
                    else:
                        split_animations_material['split'].append(sub_animation)	
                
                animation_material['name'] = self.animation_name_material       
                animation_material['format'] = self.animation_format_material
                animation_material['transformations'] = transformations
                animation_material['mode'] = self.material_mode
                animation_material['materials'] = [material.name for material in self.material_checkboxes if material.enabled]
                animation_material['split_animation'] = split_animations_material
                animations['material'] = animation_material                

        # Get outlines
        for index, outline_item in enumerate(context.scene.outline_items):
            assigned_meshes = [
                assignment.mesh_name
                for assignment in context.scene.outline_mesh_assignments
                if assignment.outline_index == index and assignment.assigned
            ]
            
            outline_dict = {
                "name": outline_item.name,
                "thickness": outline_item.thickness,
                "visibility": outline_item.visibility,
                "meshes": assigned_meshes
            }
            
            outlines.append(outline_dict)

        print(outlines)
    
        return fileio_write_xpck(
            self, context, 
            self.filepath, 
            [get_template_by_name(self.template_name), 
            self.template_mode_name], self.export_option,  
            armature=armature, 
            meshes=meshes, 
            textures=textures, 
            animations=animations, 
            outlines=outlines, 
            cameras=cameras, 
            properties=properties, 
            texprojs=texprojs,
            attach_bone=self.attach_bone,
        )
        
class ImportXC(bpy.types.Operator, ImportHelper):
    bl_idname = "import.xc"
    bl_label = "Import a XPCK"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".xc"
    filter_glob: StringProperty(
        default="*.xc;*.xv;*.pck",
        options={'HIDDEN'}
    )
    
    def execute(self, context):
            return fileio_open_xpck(context, self.filepath)
