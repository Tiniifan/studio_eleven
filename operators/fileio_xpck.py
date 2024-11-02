import os
import copy

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, EnumProperty, BoolProperty, CollectionProperty

import bmesh

from math import radians
from mathutils import Matrix, Quaternion, Vector
import io

from ..formats import xmpr, xpck, mbn, imgc, res, minf, xcsl, xcma, xcmt, cmn, txp, animationmanager, animationsupport
from .fileio_xmpr import *
from .fileio_xmtn import *
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

def create_bone(armature, bone_name, parent_name, relative_location, relative_rotation, scale):
    # Select amature
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode='EDIT')
        
    # Add a new bone
    bpy.ops.armature.bone_primitive_add()
    new_bone = armature.data.edit_bones[-1]
    new_bone.name = bone_name
    
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

            # Create a resizing matrix
            scale_matrix = Matrix.Scale(scale[0], 4, (1, 0, 0))
            scale_matrix *= Matrix.Scale(scale[1], 4, (0, 1, 0))
            scale_matrix *= Matrix.Scale(scale[2], 4, (0, 0, 1))

            # Applying transformations
            new_bone.matrix = parent_bone.matrix @ translation_matrix @ rotation_matrix @ scale_matrix
    else:
        new_bone.matrix = Matrix.Translation(relative_location) @ relative_rotation.to_matrix().to_4x4() @ Matrix.Scale(scale[0], 4)
    
    # Set object mode
    bpy.ops.object.mode_set(mode='OBJECT')

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
            meshes_data.append(xmpr.open(archive[file_name]))
        elif file_name.endswith('.mbn'):
            bones_data.append(mbn.open(archive[file_name]))    
        elif file_name.endswith('.xi'):
            textures_data.append(imgc.open(archive[file_name]))
        elif file_name.endswith('.cmr2'):
            hash_name, cam_values = xcma.open(archive[file_name])
            camera_data[hash_name] = cam_values
        elif file_name.endswith('.mtn2'):
            #animation_data = {}
            #
            #name, frame_count, bone_name_hashes, data = xmtn.open_mtn2(archive[file_name])
            #animation_data['name'] = name
            #animation_data['frame_count'] = frame_count
            #animation_data['bone_name_hashes'] = bone_name_hashes
            #animation_data['data'] = data
            anim = animationmanager.AnimationManager(reader=io.BytesIO(archive[file_name]))
            animations_data.append(anim)
        elif file_name.endswith('.mtn3'):
            animation_data = {}
            
            name, frame_count, bone_name_hashes, data = xmtn.open_mtn3(archive[file_name])
            animation_data['name'] = name
            animation_data['frame_count'] = frame_count
            animation_data['bone_name_hashes'] = bone_name_hashes
            animation_data['data'] = data
            
            animations_data.append(animation_data)
        elif file_name.endswith('.imm2'):
            anim = animationmanager.AnimationManager(reader=io.BytesIO(archive[file_name]))
            animations_data.append(anim)
        elif file_name.endswith('.mtm2'):
            anim = animationmanager.AnimationManager(reader=io.BytesIO(archive[file_name]))
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
            
            # Get bone name
            bone_name = "bone_" + str(i)            
            if bone_crc32 in res_data[res.RESType.Bone]:
                bone_name = res_data[res.RESType.Bone][bone_crc32]

            # Get parent name
            parent_name = None            
            if bone_parent_crc32 in res_data[res.RESType.Bone]:
                parent_name = res_data[res.RESType.Bone][bone_parent_crc32]
            
            # Checks if the bone has a parent
            if bone_parent_crc32 == 0:
                create_bone(armature, bone_name, False, bone_location, bone_rotation, bone_scale)
            else:
                create_bone(armature, bone_name, parent_name, bone_location, bone_rotation, bone_scale)
                
        # Set object mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Apply 90-degree rotation around X axis
        armature.rotation_euler = (radians(90), 0, 0)

    # Make libs
    if len(textures_data) > 0 and res_data is not None:
        images = {}
        res_textures_key = list(res_data[res.RESType.Texture])
        
        # Make images
        for i in range(len(textures_data)):
            if textures_data[i] != None:
                texture_data, width, height, has_alpha = textures_data[i]
                texture_crc32 = res_textures_key[i]
                texture_name = res_data[res.RESType.Texture][texture_crc32]['name']

                # Create a new image
                bpy.ops.image.new(name=texture_name, width=width, height=height, alpha=has_alpha)
                image = bpy.data.images[texture_name]
                if has_alpha == False:
                    image.alpha_mode = 'NONE'

                # Assign pixel data to the image
                image.pixels = texture_data
            
                images[texture_crc32] = image

        # Make materials
        for material_crc32, material_value in res_data[res.RESType.MaterialData].items():
            material_name = material_value['name']
            material_textures_crc32 = material_value['textures']
            
            material_textures = []
            
            for i in range(len(material_textures_crc32)):
                material_texture_crc32 = material_textures_crc32[i]
                
                if int(material_texture_crc32, 16) in images:
                    material_textures.append(images[int(material_texture_crc32, 16)])
                                
            libs[material_name] = material_textures
    
    # Make txps
    txps = []
    for i in range(len(txp_data)):
        txps.append([
            res_data[res.RESType.Textproj][txp_data[i][0]],
            res_data[res.RESType.MaterialData][txp_data[i][1]]['name'],
        ])
    
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
            if res.RESType.Bone in res_data:
                bones = res_data[res.RESType.Bone]
            
            # Get single_bind
            if mesh_data["single_bind"] is not None:
                mesh_data["single_bind"] = res_data[res.RESType.Bone][mesh_data["single_bind"]]
                
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
            
            create_animation(name, frame_count, armature, data, res_data)
            
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

def fileio_write_xpck(operator, context, filepath, template, mode, meshes = [], armature = None, textures = {}, animation = {}, split_animations = [], outline = [], cameras=[], properties=[], texprojs=[]):    
    # Make meshes
    xmprs = []
    atrs = []
    mtrs = []
    if meshes:
        for mesh in meshes:
            xmprs.append(fileio_write_xmpr(context, mesh.name, mesh.library_name, template[0].modes[template[1]]))
            atrs.append(bytes.fromhex(template[0].atr))
            mtrs.append(bytes.fromhex(template[0].mtr))

    # Make bones
    mbns = []
    if armature:
        for bone in armature.pose.bones:
            mbns.append(mbn.write(armature, bone))
            
    # Make images
    imgcs = []
    if textures:
        linked_textures = []
        
        for texture in textures.values():
            linked_textures.extend(texture)
            
        for texture in linked_textures:
            get_image_format = globals().get(texture.format)
            if get_image_format:
                imgcs.append(imgc.write(bpy.data.images.get(texture.name), get_image_format()))
            else:
                operator.report({'ERROR'}, f"Class {texture.format} not found in img_format.")
                return {'FINISHED'}
                
    # Make animations
    mtns = []
    minfs = []
    if animation:
        animation_name = animation[0]
        animation_format = animation[1]
        
        if armature == None:
            found_armature = find_armature_by_animation(animation[3])
            mtns.append(fileio_write_xmtn(context, found_armature.name, animation_name, animation_format))
        else:
            mtns.append(fileio_write_xmtn(context, armature.name, animation_name, animation_format))
        
        for split_animation in split_animations:
            minfs.append(minf.write_minf1(animation_name, split_animation.name, split_animation.speed, split_animation.frame_start, split_animation.frame_end))
    
    # Make outline
    xcsls = []
    #if outline and meshes:
        #meshes_name = []
        
        #for mesh in meshes:
            #meshes_name.append(mesh.name)
            
        #xcsls.append(xcsl.write("#new_000", meshes_name, outline[0], outline[1], template.outline_mesh_data, template.cmb1, template.cmb2))

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
            txps.append(txp.write(texproj[0], texproj[1])) 
    
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

        #if xcsls:
            #files.update(create_files_dict(".sil", xcsls))

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
            if animation[1] == 'MTN2':
                files.update(create_files_dict(".mtn2", mtns))
            elif animation[1] == 'MTN3':
                files.update(create_files_dict(".mtn3", mtns))

        if minfs:
            if animation[2] == 'MTNINF':
                files.update(create_files_dict(".mtninf", minfs))
            elif animation[2] == 'MTNINF2':
                files.update(create_files_dict(".mtninf2", minfs))

        #if xcsls:
            #files.update(create_files_dict(".sil", xcsls))
            
        if cmns:
            files.update(create_files_dict(".cmn", cmns))
            
        if txps:
            files.update(create_files_dict(".txp", txps))
    elif mode == "ANIMATION":
        if mbns:
            files.update(create_files_dict(".mbn", mbns))
            
        if mtns:
            if animation[1] == 'MTN2':
                files.update(create_files_dict(".mtn2", mtns))
            elif animation[1] == 'MTN3':
                files.update(create_files_dict(".mtn3", mtns))

        if minfs:
            if animation[2] == 'MTNINF':
                files.update(create_files_dict(".mtninf", minfs))
            elif animation[2] == 'MTNINF2':
                files.update(create_files_dict(".mtninf2", minfs))
                
        if cmns:
            files.update(create_files_dict(".cmn", cmns))  
    elif mode == "CAMERA":
        if xcmas:
            files.update(create_files_dict(".cmr2", xcmas))

    if mode != "CAMERA":
        items, string_table = res.make_library(meshes = meshes, armature = armature, textures = textures, animation = animation, split_animations = split_animations, outline_name = "", properties=properties, texprojs=texprojs)
        files["RES.bin"] = res.write_res(bytes.fromhex("4348524330300000"), items, string_table)
    else:
        if len(cameras_sorted) > 0:
            files["CMR.bin"] = xcmt.write(cameras_sorted)
    
    # Create xpck
    xpck.pack(files, filepath)
    
    return {'FINISHED'}

##########################################
# Register class
##########################################

# Operator to add an animation element
class ExportXC_AddAnimationItem(bpy.types.Operator):
    bl_idname = "export_xc.add_animation_item"
    bl_label = "Add Animation Item"
    
    def execute(self, context):
        # Logic to add a new element to the collection
        new_item = context.scene.export_xc_animations_items.add()
        
        # Find the first unused private_index
        used_indexes = [item.private_index for item in context.scene.export_xc_animations_items]
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

# Operator to delete an animation element
class ExportXC_RemoveAnimationItem(bpy.types.Operator):
    bl_idname = "export_xc.remove_animation_item"
    bl_label = "Remove Animation Item"
    
    index: bpy.props.IntProperty()
    
    def execute(self, context):
        # Logic to remove the selected item from the collection
        items = context.scene.export_xc_animations_items
        items.remove(self.index)
        return {'FINISHED'}

class AnimationItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    speed: bpy.props.FloatProperty()
    frame_start: bpy.props.IntProperty()
    frame_end: bpy.props.IntProperty()
    private_index: bpy.props.IntProperty()
    
# Define a Property Group to store texture information
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

class LibPropertyGroup(bpy.types.PropertyGroup):
    texproj_name: bpy.props.StringProperty()
    name: bpy.props.StringProperty()
    textures: bpy.props.CollectionProperty(type=TexturePropertyGroup)

# Define a Property Group to store mesh information
class MeshPropertyGroup(bpy.types.PropertyGroup):
    checked: bpy.props.BoolProperty(default=False, description="Mesh name")
    name: bpy.props.StringProperty()
    library_index: bpy.props.IntProperty()
    library_name: bpy.props.StringProperty()
    
# Define a Property Group to store camera information
class CameraPropertyGroup(bpy.types.PropertyGroup):
    checked: bpy.props.BoolProperty(default=False, description="Camera name")
    name: bpy.props.StringProperty()
    animation_name: bpy.props.StringProperty()
    speed: bpy.props.FloatProperty(default=1.0, min=0.1, precision=2) 
    
# Define a Property Group to store archive information
class ArchivePropertyGroup(bpy.types.PropertyGroup):
    checked: bpy.props.BoolProperty(default=False, description="Property name")
    name: bpy.props.StringProperty()
    value: bpy.props.FloatProperty(default=0.0, description="Property value")

# Define a Property Group to store armature information
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
            ('TEXTURE', "Texture", "Configure textures"),
            ('ANIMATION', "Animation", "Configure animations"),
            ('PROPERTIES', "Properties", "Configure properties"),
        ],
        default='MAIN'
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
    libs: bpy.props.CollectionProperty(type=LibPropertyGroup)
    camera_properties: bpy.props.CollectionProperty(type=CameraPropertyGroup)
    archive_properties: bpy.props.CollectionProperty(type=ArchivePropertyGroup)
    
    include_animation: bpy.props.BoolProperty(
        name="Include Animation",
        default=False,
        description="Include animation in the export"
    )
    
    animation_format: bpy.props.EnumProperty(
        name="Format",
        items=[
            ('MTN2', "MTN2", "Make MTN2 Animation"),
            #('MTN3', "MTN3", "Make MTN3 Animation"),
        ],
        default='MTN2'
    )

    split_animation_format: bpy.props.EnumProperty(
        name="Format",
        items=[
            ('MTNINF', "MTNINF", "Make MTNINF Split Animation"),
            #('MTNINF2', "MTNINF2", "Make MTNINF2 Split Animation"),
        ],
        default='MTNINF'
    )     
    
    def armature_items_callback(self, context):
        # Get armatures
        armatures = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE']
        
        if not armatures:
            # No armatures found, return default or empty list
            return [("None", "None", "No armature found")]
        
        armature_enum_items = [(armature.name, armature.name, "") for armature in armatures]
        return armature_enum_items    

    armature_enum: EnumProperty(
        name="Armatures",
        items=armature_items_callback,
        default=0
    )   
    
    animation_name: bpy.props.StringProperty(
        name="Animation Name",
        default="animation",
        description="Name of the animation"
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
    
    outline_thickness: bpy.props.FloatProperty(
        name="Outline Thickness",
        description="Thickness of the outline",
        default=0.0025,
        min=0.0000,
        max=0.9999,
        precision=4
    )

    outline_visibility: bpy.props.FloatProperty(
        name="Outline Visibility",
        description="Visibility of the outline",
        default=0.5,
        min=0.0,
        max=1.0,
        precision=4
    )

    def update_outline_properties(self, context):
        if self.outline_name == 'TEMPLATE':
            self.outline_thickness = 0.0025
            self.outline_visibility = 0.5
        elif self.outline_name == 'CARTOON':
            self.outline_thickness = 0.0025
            self.outline_visibility = 0.0
        else:
            self.outline_thickness = 0.0
            self.outline_visibility = 1     
    
    outline_name: EnumProperty(
        name="Outlines",
        description="Choose a outline mode",
        items=[
            ('TEMPLATE', "Template", "Same as template"),
            ('CARTOON', "Cartoon", "Cartoon"),
            ('NONE', "None", "None"),
        ],
        default=0,
        update=update_outline_properties
    )
    
    def invoke(self, context, event):
        wm = context.window_manager  

        libs = []
        self.mesh_properties.clear()
        self.libs.clear()
        self.camera_properties.clear()
        context.scene.export_xc_animations_items.clear()
        self.archive_properties.clear()

        # Get meshes
        meshes = [obj for obj in bpy.data.objects if obj.type == 'MESH']
        for mesh in meshes:
            item = self.mesh_properties.add()
            item.checked = True
            item.name = mesh.name

            lib = {}
            lib['texture_name'] = []
            lib['mesh_name'] = [mesh.name]
            used_texture = []

            # Get textures from materials
            for material_slot in mesh.material_slots:
                material = material_slot.material
                if material.use_nodes:
                    # If material uses nodes, iterate over the material nodes
                    for node in material.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            if node.image not in used_texture:
                                texture_name = node.image.name
                                lib['texture_name'].append(texture_name)
                                used_texture.append(node.image)
                else:
                    # If material doesn't use nodes, try to access the texture from the diffuse shader
                    if hasattr(material, 'texture_slots'):
                        if material.texture_slots and material.texture_slots[0] and material.texture_slots[0].texture:
                            if texture not in used_texture:
                                texture = material.texture_slots[0].texture
                                texture_name = texture.name
                                lib['texture_name'].append(texture_name)
                                used_texture.append(texture)
                    else:
                        # Enter in berry bush situation
                        for texture_berry_bush in material.brres.textures:
                            texture_name = texture_berry_bush.name
                            for image in texture_berry_bush.imgs:
                                lib['texture_name'].append(texture_name)
                                used_texture.append(image.img)

            found = False
            for key, value in enumerate(libs):
                if value['texture_name'] == lib['texture_name']:
                    found = True
                    break
            
            if found:
                libs[key]['mesh_name'].append(mesh.name)
            else:
                libs.append(lib)

        for index, value in enumerate(libs):
            item = self.libs.add()
            item.name = 'DefaultLib.' + str(index)
            item.texproj_name =  item.name + "_texproj0"
            
            for texture_name in value['texture_name']:
                texture = item.textures.add()
                texture.name = texture_name           

        for mesh_prop in self.mesh_properties:
            for index, value in enumerate(libs):
                for mesh_name in value['mesh_name']:
                    if mesh_prop.name == mesh_name:
                        mesh_prop.library_index = index
                        break          

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
        
        # Create two tabs: "Main"
        row = layout.row(align=True)
        row.prop(self, "export_tab_control", expand=True)

        if self.export_tab_control == 'MAIN':
            box = layout.box()
            
            # Add the template_name property to the main box
            box.prop(self, "template_name", text="Template")
            
            if self.template_name == 'Inazuma Eleven':
                box.prop(self, "template_mode_name", text="Mode")
            
            # Create a sub-box for outline properties
            #outline_box = box.box()
            #outline_box.prop(self, "outline_name", text="Outline")
            #outline_box.prop(self, "outline_thickness", text="Thickness")
            #outline_box.prop(self, "outline_visibility", text="Visibility")

            # Create a box for export option, mesh group, and armature enum
            options_box = box.box()
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
                            row.prop(self.libs[self.mesh_properties[child.name].library_index], "name", text="", emboss=False)
            elif self.export_option == 'ANIMATION':
                options_box.prop(self, "animation_enum", text="Available animations")
                options_box.prop(self, "attach_bone", text="Attach armature")
            elif self.export_option == 'CAMERA':
                camera_group = options_box.box()
                for camera_prop in self.camera_properties:
                    row = camera_group.row(align=True)
                    row.prop(camera_prop, "checked", text=camera_prop.name)
                    row.prop(camera_prop, "animation_name", text="Name")
                    row.prop(camera_prop, "speed", text="Speed")
        elif self.export_tab_control == 'TEXTURE':
            if self.export_option == 'CAMERA' or self.export_option == 'ANIMATION':
                texture_box = layout.box()
                texture_box.label(text="Not available on camera mode")
            else:
                meshes_props =[]
                lib_indexes = []
                
                if self.export_option == 'MESH':
                    meshes_props = [mesh_prop for mesh_prop in self.mesh_properties if mesh_prop.checked]
                elif self.export_option == 'ARMATURE':
                    armature = bpy.data.objects.get(self.armature_enum)
                    armature_meshes = [child for child in armature.children if child.type == 'MESH']
                    for mesh_prop in self.mesh_properties:
                        if mesh_prop.checked:
                            mesh = bpy.data.objects.get(mesh_prop.name)
                            if mesh and mesh in armature_meshes:     
                                meshes_props.append(mesh_prop)
                                
                for mesh_prop in meshes_props:
                    if mesh_prop.checked:
                        index = mesh_prop.library_index
                        if index not in lib_indexes:
                            lib = self.libs[index]
                            groupbox = layout.box()
                            groupbox.prop(lib, "texproj_name", text="")
                            box = groupbox.box()
                            box.prop(lib, "name", text="")
                                                        
                            for texture in lib.textures:
                                row = box.row(align=True)
                                row.label(text=texture.name)
                                row.prop(texture, "format", text="")
                                
                            lib_indexes.append(index)
        elif self.export_tab_control == 'ANIMATION':
            anim_box = layout.box()

            # Check if ARMATURE is selected and has animation
            if self.export_option == 'ARMATURE':
                armature = bpy.data.objects.get(self.armature_enum)
                if armature and armature.type == 'ARMATURE' and armature.animation_data:
                    # Checkbox for including animation
                    anim_box.prop(self, "include_animation", text="Includes Animation")

                    if self.include_animation:
                        # Group for animation settings
                        anim_settings_box = anim_box.box()

                        # Text field for animation name
                        anim_settings_box.prop(self, "animation_name", text="Animation Name", icon='ANIM') 
                        anim_settings_box.prop(self, "animation_format", text="Animations Format")
                        anim_settings_box.prop(self, "split_animation_format", text="Split Animations Format")

                        # Group for manual item addition/removal
                        items_box = anim_settings_box.box()
                        
                        # List of items with name, frame start, and frame end
                        for index, item in enumerate(context.scene.export_xc_animations_items):
                            row = items_box.row(align=True)
                            row.prop(item, "name", text="Name")
                            row.prop(item, "speed", text="Speed")
                            row.prop(item, "frame_start", text="Start Frame")
                            row.prop(item, "frame_end", text="End Frame")
                            
                            # Button to remove selected item
                            remove_button = row.operator("export_xc.remove_animation_item", text="", icon='REMOVE')
                            remove_button.index = index  # Pass the index to the operator
                            
                        # Button to add an item
                        items_box.operator("export_xc.add_animation_item", text="Add Item", icon='ADD')
                else:
                    anim_box.label(text="No animation")
            elif self.export_option == 'ANIMATION':
                # Group for animation settings
                anim_settings_box = anim_box.box()

                # Text field for animation name
                anim_settings_box.prop(self, "animation_name", text="Animation Name", icon='ANIM')             
                anim_settings_box.prop(self, "animation_format", text="Animations Format")                       
                anim_settings_box.prop(self, "split_animation_format", text="Split Animations Format")

                # Group for manual item addition/removal
                items_box = anim_settings_box.box()
                        
                # List of items with name, frame start, and frame end
                for index, item in enumerate(context.scene.export_xc_animations_items):
                    row = items_box.row(align=True)
                    row.prop(item, "name", text="Name")
                    row.prop(item, "speed", text="Speed")
                    row.prop(item, "frame_start", text="Start Frame")
                    row.prop(item, "frame_end", text="End Frame")
                            
                    # Button to remove selected item
                    remove_button = row.operator("export_xc.remove_animation_item", text="", icon='REMOVE')
                    remove_button.index = index  # Pass the index to the operator
                            
                # Button to add an item
                items_box.operator("export_xc.add_animation_item", text="Add Item", icon='ADD')            
            else:
                if self.export_option == 'MESH':
                    anim_box.label(text="Not available on mesh mode")
                elif self.export_option == 'CAMERA':
                    anim_box.label(text="Not available on camera mode")
        elif self.export_tab_control == 'PROPERTIES':
                properties_box = layout.box()
                
                if self.export_option != 'CAMERA':
                    for archive_prop in self.archive_properties:
                        row = properties_box.row(align=True)
                        row.prop(archive_prop, "checked", text=archive_prop.name)
                        row.prop(archive_prop, "value", text="")
                else:
                    properties_box.label(text="Not available on camera mode")

    def execute(self, context):
        armature = None
        meshes = []
        textures = {}
        animation = []
        cameras = []
        split_animations = []
        properties = []
        texprojs = []
        outline = [self.outline_thickness, self.outline_visibility]
        
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
                            index = mesh_prop.library_index
                            lib = self.libs[index]
                            
                            # Check if the mesh has a library_name
                            if not lib.name:
                                self.report({'ERROR'}, f"Mesh '{mesh_prop.name}' is checked but doesn't have a library_name!")
                                return {'FINISHED'}
                                
                           # Check if the mesh has a texproj_name
                            if not lib.texproj_name:
                                self.report({'ERROR'}, f"Mesh '{mesh_prop.name}' is checked but doesn't have a texproj_name!")
                                return {'FINISHED'}     
                            
                            texprojs.append([lib.texproj_name, lib.name])
                            mesh_prop.library_name = lib.name
                                
                            textures[lib.name] = []                              
                            meshes.append(mesh_prop)
                                
                            # Get texture
                            for texture in lib.textures:
                                textures[lib.name].append(texture)

                if self.include_animation:
                    if not self.animation_name:
                        self.report({'ERROR'}, "The animation doesn't have name")
                        return {'FINISHED'}
                        
                    animation = [self.animation_name, self.animation_format, self.split_animation_format]
                    
                    for sub_animation in context.scene.export_xc_animations_items:
                        if not sub_animation.name:
                            self.report({'ERROR'}, f"splitted_animation_'{sub_animation.private_index}' doesn't have a a name!")
                            return {'FINISHED'}
                        else:
                            split_animations.append(sub_animation)
        elif self.export_option == 'ANIMATION':
            if not self.animation_name:
                self.report({'ERROR'}, "The animation doesn't have name")
                return {'FINISHED'}
                        
            animation = [self.animation_name, self.animation_format, self.split_animation_format, self.animation_enum]
                    
            for sub_animation in context.scene.export_xc_animations_items:
                if not sub_animation.name:
                    self.report({'ERROR'}, f"splitted_animation_'{sub_animation.private_index}' doesn't have a a name!")
                    return {'FINISHED'}
                else:
                    split_animations.append(sub_animation)

            if self.attach_bone:
                find_armature = find_armature_by_animation(self.animation_enum)

                if find_armature == None:
                    self.report({'ERROR'}, "The armature attached to the animation hasn't been found")
                    return {'FINISHED'}
                else:
                    armature = find_armature
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

        return fileio_write_xpck(self, context, self.filepath, [get_template_by_name(self.template_name), self.template_mode_name], self.export_option,  armature=armature, meshes=meshes, textures=textures, animation=animation, split_animations=split_animations, outline=outline, cameras=cameras, properties=properties, texprojs=texprojs)
        
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