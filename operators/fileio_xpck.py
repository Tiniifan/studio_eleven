import io
import os
import copy
import traceback

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, EnumProperty, BoolProperty, CollectionProperty, IntProperty

import bmesh

from math import radians
from mathutils import Matrix, Quaternion, Vector

from ..formats import xmpr, xpck, mbn, imgc, res, minf, xcsl, xcma, xcmt, cmn, txp, atr, animation_manager, animation_support
from .fileio_xmpr import *
from .fileio_animation_manager import *
from .fileio_xcma import *
from .xpck_settings import *
from ..formats.texture import pixel_formats
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

##########################################
# XPCK Import
##########################################

SPLIT_EXTENSIONS = {
    'armature': ('.mtninf', '.mtninf2'),
    'uv': ('.imminf', '.imminf2'),
    'material': ('.mtminf', '.mtminf2'),
}

# Track type of an animation (bone, uv, material) -> settings type (armature, uv, material)
TRACK_TYPE_TO_ANIMATION_TYPE = {
    'bone': 'armature',
    'uv': 'uv',
    'material': 'material',
}

class ArchiveContent:
    """Files read from one archive (nested archives are read into children)."""

    def __init__(self, name):
        self.name = name
        self.children = []
        self.bones_data = []
        self.meshes_data = []
        self.textures_data = []
        self.camera_data = {}
        self.camera_hashes = []
        self.animations_data = []
        self.animations_split_data = {animation_type: [] for animation_type in SPLIT_EXTENSIONS}
        self.txp_data = []
        self.atr_data = []
        self.res_data = None

class AnimationGroup:
    """Files of one animation (mtn2, imm2, mtm2 sharing the same name) inside an archive."""

    def __init__(self, name, archive_name, armature_name):
        self.name = name
        self.archive_name = archive_name
        self.armature_name = armature_name
        self.animations = []
        self.splits = {animation_type: [] for animation_type in SPLIT_EXTENSIONS}

    @property
    def track_types(self):
        track_types = set()
        for animation in self.animations:
            track_types.update(get_animation_track_types(animation))
        return track_types

    @property
    def node_hashes(self):
        node_hashes = set()
        for animation in self.animations:
            node_hashes.update(get_animation_node_hashes(animation))
        return node_hashes

    @property
    def frame_count(self):
        return max([animation.FrameCount for animation in self.animations], default=0)

class XpckImportSession:
    def __init__(self, report=None):
        self.report = report
        self.animation_groups = []
        self.created_armatures = []
        self.cameras = []
        self.max_frame = 0

    def warning(self, message):
        traceback.print_exc()
        if self.report:
            self.report({'WARNING'}, message)

def read_archive(data, archive_name, session):
    content = ArchiveContent(archive_name)
    archive = xpck.open_file(data)

    for file_name in archive:
        if file_name.endswith('.xc') or file_name.endswith('.xv'):
            try:
                content.children.append(read_archive(archive[file_name], file_name, session))
            except Exception as e:
                session.warning(f"{archive_name}/{file_name} can't be read: {e}")
        elif file_name.endswith('.prm'):
            content.meshes_data.append(xmpr.open_xmpr(io.BytesIO(archive[file_name])))
        elif file_name.endswith('.mbn'):
            content.bones_data.append(mbn.open(archive[file_name]))
        elif file_name.endswith('.xi'):
            content.textures_data.append(imgc.open(archive[file_name]))
        elif file_name.endswith('.cmr2'):
            camera = xcma.read(archive[file_name])
            content.camera_data[camera['hash']] = camera
        elif file_name.endswith('.mtn2') or file_name.endswith('.imm2') or file_name.endswith('.mtm2'):
            content.animations_data.append(animation_manager.AnimationManager(reader=io.BytesIO(archive[file_name])))
        elif file_name == 'RES.bin':
            content.res_data = res.open_res(data=archive[file_name])
        elif file_name == 'CMR.bin':
            content.camera_hashes = xcmt.open(data=archive[file_name])
        elif file_name.endswith('.txp'):
            content.txp_data.append(txp.read_txp(io.BytesIO(archive[file_name])))
        elif file_name.endswith('.atr'):
            try:
                content.atr_data.append(atr.read_atr(archive[file_name]))
            except Exception as e:
                session.warning(f"{archive_name}/{file_name} can't be read: {e}")
                content.atr_data.append(None)
        else:
            for animation_type, extensions in SPLIT_EXTENSIONS.items():
                if file_name.endswith(extensions[1]):
                    content.animations_split_data[animation_type].extend(minf.open_minf2(archive[file_name]))
                elif file_name.endswith(extensions[0]):
                    split_anim_crc32, split_anim_name, anim_crc32, frame_start, frame_end, speed = minf.open_minf1(archive[file_name])
                    content.animations_split_data[animation_type].append({
                        'split_anim_crc32': split_anim_crc32,
                        'split_anim_name': split_anim_name,
                        'anim_crc32': anim_crc32,
                        'frame_start': frame_start,
                        'frame_end': frame_end,
                        'speed': speed,
                    })

    return content

def build_archive(context, content, session):
    scene = context.scene
    archive_name = os.path.splitext(content.name)[0]

    for child in content.children:
        try:
            build_archive(context, child, session)
        except Exception as e:
            session.warning(f"{child.name} can't be imported: {e}")

    res_data = content.res_data
    armature = None
    libs = {}

    # Make amature
    if len(content.bones_data) > 0 and res_data is not None:
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

        for i in range(len(content.bones_data)):
            bones_data = content.bones_data

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

        # Remember the archive to export it back
        armature.level5_archive.archive_name = content.name
        armature.level5_archive.export_mode = 'ARMATURE'

        session.created_armatures.append(armature.name)

    # Make libs
    if res_data is not None:
        images = {}

        # Make images
        if len(content.textures_data) > 0:
            res_textures_key = list(res_data[res.RESType.TEXTURE_DATA])
            for i in range(len(content.textures_data)):
                if content.textures_data[i] != None:
                    texture_data, width, height, has_alpha = content.textures_data[i]
                    texture_crc32 = res_textures_key[i]
                    texture_name = res_data[res.RESType.TEXTURE_DATA][texture_crc32]['name']

                    # Create a new image
                    image = bpy.data.images.new(name=texture_name, width=width, height=height, alpha=has_alpha)
                    if has_alpha == False:
                        image.alpha_mode = 'NONE'

                    if hasattr(image, "level5_texture"):
                        res.sampler_to_properties(res_data[res.RESType.TEXTURE_DATA][texture_crc32]['sampler'], image.level5_texture)

                    # Assign pixel data to the image
                    image.pixels.foreach_set(texture_data)

                    images[texture_crc32] = image

        # Make materials
        if res.RESType.MATERIAL_DATA in res_data:
            for material_crc32, material_value in res_data[res.RESType.MATERIAL_DATA].items():
                material_name = material_value['name']
                material_textures_crc32 = material_value['textures']

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

    # Make render states
    atr_states = {}
    if res_data is not None and res.RESType.MATERIAL_DATA in res_data:
        # The .atr files are numbered like the materials, not like the meshes
        materials_data = res_data[res.RESType.MATERIAL_DATA]
        res_materials_key = list(materials_data)

        for i in range(min(len(content.atr_data), len(res_materials_key))):
            atr_states[materials_data[res_materials_key[i]]['name']] = content.atr_data[i]

    # Make txps
    txps = []
    if res_data is not None:
        for i in range(len(content.txp_data)):
            texproj_crc32 = content.txp_data[i][0]
            material_crc32 = content.txp_data[i][1]
            uv_map_index = content.txp_data[i][2]

            if texproj_crc32 in res_data[res.RESType.TEXPROJ]:
                if material_crc32 in res_data[res.RESType.MATERIAL_DATA]:
                    textproj_name = res_data[res.RESType.TEXPROJ][texproj_crc32]
                    material_name = res_data[res.RESType.MATERIAL_DATA][material_crc32]['name']
                    txps.append([textproj_name, material_name, uv_map_index])

    # Make meshes
    if len(content.meshes_data) > 0 and res_data is not None:
        for i in range(len(content.meshes_data)):
            # Get mesh
            mesh_data = content.meshes_data[i]

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

            # Get render state
            atr_state = atr_states.get(mesh_data['material_name'])

            # Create the mesh using the mesh data
            make_mesh(mesh_data, armature=armature, bones=bones, lib=lib, txp_data=txps, atr_state=atr_state)

    # Group the animations by name, the imported animations are applied from the animation menu
    groups = {}
    for animation_data in content.animations_data:
        name = animation_data.AnimationName

        if name not in groups:
            group = AnimationGroup(name, content.name, armature.name if armature else None)

            animation_crc32 = zlib.crc32(name.encode("shift-jis"))
            for animation_type, splits_data in content.animations_split_data.items():
                for split_data in splits_data:
                    if split_data['anim_crc32'] == animation_crc32:
                        group.splits[animation_type].append({
                            'name': split_data['split_anim_name'],
                            'speed': split_data.get('speed', 1.0),
                            'frame_start': split_data['frame_start'],
                            'frame_end': split_data['frame_end'],
                        })

            groups[name] = group
            session.animation_groups.append(group)

        groups[name].animations.append(animation_data)

    # Make camera
    if len(content.camera_data) > 0 and len(content.camera_hashes):
        frame = 0
        index = 0
        for camera_hash in content.camera_hashes:
            if camera_hash in content.camera_data:
                camera = content.camera_data[camera_hash]
                camera_name = archive_name.split('_')[0] + "_" + str(index).rjust(3, '0')
                level5_camera = create_camera(frame, camera_name, camera['values'])
                set_camera_settings(level5_camera, camera, content.name)

                # Switch to this camera when the timeline reaches it
                marker = scene.timeline_markers.new(level5_camera.camera_obj.name, frame=frame)
                marker.camera = level5_camera.camera_obj
                session.cameras.append(level5_camera.camera_obj.name)

                frame += get_last_frame(camera['values'])
                index += 1

        session.max_frame = max(session.max_frame, frame)

def fileio_open_xpck(context, filepath, report=None):
    """Import the meshes, armatures and cameras of an archive and return the session with its animations."""
    session = XpckImportSession(report)

    if context.object and context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    content = read_archive(filepath, os.path.basename(filepath), session)
    build_archive(context, content, session)

    scene = context.scene

    if session.cameras:
        scene.camera = bpy.data.objects.get(session.cameras[0])
        scene.frame_set(0)

    if session.max_frame > 0:
        scene.frame_end = max(1, session.max_frame)

    return session

def find_best_armature(context, group, used_armatures=()):
    """Armature which matches the most animated nodes (bones, single bind bones, texprojs, materials).

    On a tie, an armature which isn't in used_armatures is preferred (characters sharing the same skeleton).
    """
    if group.armature_name and group.armature_name in bpy.data.objects:
        return group.armature_name

    node_hashes = group.node_hashes
    best_name = 'NONE'
    best_score = (0, False)

    for obj in context.scene.objects:
        if obj.type == 'ARMATURE':
            count = count_matching_nodes(node_hashes, obj)
            score = (count, obj.name not in used_armatures)
            if count > 0 and score > best_score:
                best_name = obj.name
                best_score = score

    return best_name

def apply_animation_group(context, group, armature, track_types):
    """Create the actions of an animation group on an armature and return (actions, assignments)."""
    action = None
    material_actions = {}

    for animation in group.animations:
        action = create_animation(animation, armature, action=action, track_types=track_types, material_actions=material_actions)

    # Split animations
    if 'bone' in track_types:
        for split_animation in group.splits['armature']:
            new_animation = bpy.data.actions.new(name=group.name + '_' + split_animation['name'])

            # Specify the start and end of the new animation
            start_frame = split_animation['frame_start']
            end_frame = split_animation['frame_end']

            # Copy the keyframes of the existing action into the new action
            for fcurve in action.fcurves:
                new_fcurve = new_animation.fcurves.new(data_path=fcurve.data_path, index=fcurve.array_index)
                for keyframe in fcurve.keyframe_points:
                    if start_frame <= keyframe.co.x <= end_frame:
                        new_keyframe = new_fcurve.keyframe_points.insert(keyframe.co.x - start_frame, keyframe.co.y)
                        new_keyframe.interpolation = keyframe.interpolation

    # Remember which datablocks use the new actions
    assignments = [(armature, action)]
    for child in armature.children:
        if child.type == 'MESH' and child.animation_data and child.animation_data.action == action:
            assignments.append((child, action))
    for material_name, material_action in material_actions.items():
        assignments.append((bpy.data.materials[material_name], material_action))

    return [action] + list(material_actions.values()), assignments

def apply_animation_imports(context, session, choices):
    """choices: list of (group, armature name, track types) chosen in the animation menu."""
    scene = context.scene
    first_assignments = {}
    actions_by_armature = {}
    max_frame = session.max_frame

    for group, armature_name, track_types in choices:
        armature = bpy.data.objects.get(armature_name)
        track_types = set(track_types) & group.track_types

        if armature is None or armature.type != 'ARMATURE' or not track_types:
            continue

        actions, assignments = apply_animation_group(context, group, armature, track_types)
        max_frame = max(max_frame, group.frame_count)

        actions_by_armature.setdefault(armature.name, []).extend(actions)

        # The first animation of an armature stays active and fills the export settings
        if armature.name in first_assignments:
            continue

        first_assignments[armature.name] = assignments

        settings = armature.level5_archive
        for track_type, animation_type in TRACK_TYPE_TO_ANIMATION_TYPE.items():
            if track_type in track_types:
                set_animation_settings(settings.get_animation(animation_type), group.name, group.splits[animation_type])
            else:
                settings.get_animation(animation_type).include = False

        if group.armature_name != armature.name:
            # Animation of another archive: export it back as an animation archive
            settings.archive_name = group.archive_name
            settings.export_mode = 'ANIMATION'

        sync_archive_settings(armature)

    # Several animations on the same armature: keep them all but play the first one
    for armature_name, actions in actions_by_armature.items():
        first_actions = {action for id_data, action in first_assignments[armature_name]}
        if any(action not in first_actions for action in actions):
            for action in actions:
                action.use_fake_user = True

        for id_data, action in first_assignments[armature_name]:
            if id_data.animation_data is None:
                id_data.animation_data_create()
            id_data.animation_data.action = action

    if max_frame > 0:
        scene.frame_end = max_frame

    scene.frame_set(scene.frame_current)

# Animation groups of the last read archive, used by the animation menu
_import_session = None
_armature_enum_items = []

def import_armature_items(self, context):
    global _armature_enum_items

    _armature_enum_items = [('NONE', "None", "Don't import this animation")]
    _armature_enum_items += [(obj.name, obj.name, "") for obj in context.scene.objects if obj.type == 'ARMATURE']

    return _armature_enum_items

class ImportAnimationChoice(bpy.types.PropertyGroup):
    name: StringProperty()
    archive_name: StringProperty()
    group_index: IntProperty()
    has_bone: BoolProperty()
    has_uv: BoolProperty()
    has_material: BoolProperty()
    import_bone: BoolProperty(name="Bone", default=True, description="Import the bone animation")
    import_uv: BoolProperty(name="UV", default=True, description="Import the UV animation")
    import_material: BoolProperty(name="Material", default=True, description="Import the material animation")
    armature: EnumProperty(name="Armature", description="Armature which receives the animation", items=import_armature_items)

class ImportXC_ChooseAnimations(bpy.types.Operator):
    """Choose the armature of each animation found in the archive"""
    bl_idname = "import_xc.choose_animations"
    bl_label = "Studio Eleven - Import Animations"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    animations: CollectionProperty(type=ImportAnimationChoice)

    def invoke(self, context, event):
        self.animations.clear()

        if _import_session is None:
            return {'CANCELLED'}

        used_armatures = set()

        for index, group in enumerate(_import_session.animation_groups):
            track_types = group.track_types

            item = self.animations.add()
            item.name = group.name
            item.archive_name = group.archive_name
            item.group_index = index
            item.has_bone = 'bone' in track_types
            item.has_uv = 'uv' in track_types
            item.has_material = 'material' in track_types
            item.armature = find_best_armature(context, group, used_armatures)
            used_armatures.add(item.armature)

        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        layout = self.layout

        if not self.animations:
            layout.label(text="No animation found")

        for item in self.animations:
            box = layout.box()
            box.label(text=f"{item.name} ({item.archive_name})", icon='ACTION')

            row = box.row()

            checkboxes = row.row(align=True)
            for track_type in ('bone', 'uv', 'material'):
                sub = checkboxes.row(align=True)
                sub.enabled = getattr(item, "has_" + track_type)
                sub.prop(item, "import_" + track_type)

            row.prop(item, "armature", text="")

    def execute(self, context):
        if _import_session is None:
            return {'CANCELLED'}

        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        choices = []
        for item in self.animations:
            if item.armature == 'NONE':
                continue

            track_types = [track_type for track_type in ('bone', 'uv', 'material') if getattr(item, "has_" + track_type) and getattr(item, "import_" + track_type)]
            choices.append((_import_session.animation_groups[item.group_index], item.armature, track_types))

        apply_animation_imports(context, _import_session, choices)

        return {'FINISHED'}

##########################################
# XPCK Export
##########################################

class XpckExportError(Exception):
    pass

def make_atr(material_name, template):
    material = bpy.data.materials.get(material_name)
    properties = getattr(material, "level5_atr", None) if material else None
    state = atr.default_state() if properties is None else atr.state_from_properties(properties)

    return atr.write_atr(state, template[0].file_version)

def make_xpck_files(operator, context, template, mode, meshes = [], armature = None, textures = {}, animations = {}, outlines = [], cameras=[], properties=[], texprojs=[], attach_bone=False):
    """Return the files ({name: bytes}) of an archive."""
    xmprs = []
    atrs = []
    mtrs = []

    if meshes:
        for mesh in meshes:
            xmprs.append(fileio_write_xmpr(context, mesh.name, mesh.material_name, template[0].modes[template[1]]))
            atrs.append(make_atr(mesh.material_name, template))
            mtrs.append(bytes.fromhex(template[0].mtr))

    # Make bones
    mbns = []
    if armature:
        for bone in armature.pose.bones:
            mbns.append(mbn.write(armature, bone))

    # Make images
    imgcs = []
    for texture_name, texture_data in textures.items():
        get_image_format = getattr(pixel_formats, texture_data['format'], None)

        if get_image_format:
            imgcs.append(imgc.write(bpy.data.images.get(texture_name), get_image_format()))
        else:
            raise XpckExportError(f"Class {texture_data['format']} not found in pixel_formats.")

    # Make animations
    mtns = []
    imms = []
    mtms = []
    mtninfs = []
    imminfs = []
    mtminfs = []

    anim_version = "V1" if template[0].file_version == 1 else "V2"
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

    # Make cameras (Inazuma Eleven Go uses the first camera format)
    xcmas = []
    cameras_sorted = []
    camera_version = "V1" if template[0].file_version == 1 else "V2"
    if cameras:
        # Sort camera by frame start
        cameras_sorted = sorted(cameras, key=lambda cam_object: get_first_frame(cam_object[2]))
        for cam_object in cameras_sorted:
            animation_name = cam_object[0]
            speed = cam_object[1]
            camera = cam_object[2]
            target = cam_object[3]
            xcmas.append(fileio_write_xcma(context, animation_name, speed, camera, target, camera_version))

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

        if template[0].file_version == 1:
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

        if template[0].file_version == 1:
            files["RES.bin"] = res.write_xres(b"XRES", items, string_table)
        else:
            files["RES.bin"] = res.write_res(b"CHRC00\x00\x00", items, string_table)
    elif mode == "MESH":
        pass
        # Not implemented
    elif mode == "CAMERA":
        if len(cameras_sorted) > 0:
            files["CMR.bin"] = xcmt.write(cameras_sorted)

    return files

def fileio_write_xpck(operator, context, filepath, template, mode, **kwargs):
    xpck.pack_archive(make_xpck_files(operator, context, template, mode, **kwargs), filepath)

    return {'FINISHED'}

##########################################
# Register class
##########################################

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
    wrap_s: bpy.props.EnumProperty(name="Wrap X", items=res.WRAP_ITEMS, default='REPEAT')
    wrap_t: bpy.props.EnumProperty(name="Wrap Y", items=res.WRAP_ITEMS, default='REPEAT')
    mag_filter: bpy.props.EnumProperty(name="Magnification", items=res.FILTER_ITEMS, default='LINEAR')
    min_filter: bpy.props.EnumProperty(name="Minification", items=res.FILTER_ITEMS, default='LINEAR')
    mip_filter: bpy.props.EnumProperty(name="Mipmap", items=res.FILTER_ITEMS, default='NEAREST')
    mesh_name: bpy.props.StringProperty()

def fill_texture_sampler(item):
    image = bpy.data.images.get(item.name)

    if image is None or not hasattr(image, "level5_texture"):
        return

    for name, _, _ in res.SAMPLER_FIELDS:
        setattr(item, name, getattr(image.level5_texture, name))

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

class ArchivePropertyGroup(bpy.types.PropertyGroup):
    checked: bpy.props.BoolProperty(default=False, description="Property name")
    name: bpy.props.StringProperty()
    value: bpy.props.FloatProperty(default=0.0, description="Property value")

def get_scene_cameras(context):
    return [obj for obj in context.scene.objects if CameraElevenObject.is_camera_eleven(obj)]

def get_scene_armatures(context):
    return [obj for obj in context.scene.objects if obj.type == 'ARMATURE']

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
            ('SCENE', "Scene", "Export every armature and camera of the scene in one archive"),
        ],
        default='ARMATURE'
    )

    mesh_properties: bpy.props.CollectionProperty(type=MeshPropertyGroup)
    texproj_properties: bpy.props.CollectionProperty(type=TexprojPropertyGroup)
    texture_properties: bpy.props.CollectionProperty(type=TexturePropertyGroup)
    archive_properties: bpy.props.CollectionProperty(type=ArchivePropertyGroup)

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

    armature_enum: EnumProperty(
        name="Armatures",
        items=armature_items_callback,
        default=0,
    )

    settings_armature_enum: EnumProperty(
        name="Armature",
        description="Armature to configure",
        items=armature_items_callback,
        default=0,
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

    def get_settings_armature(self):
        """Armature whose animations and outlines are configured in the current mode."""
        armature = None

        if self.export_option == 'ARMATURE':
            armature = bpy.data.objects.get(self.armature_enum)
        elif self.export_option == 'ANIMATION':
            armature = find_armature_by_animation(self.animation_enum)
        elif self.export_option == 'SCENE':
            armature = bpy.data.objects.get(self.settings_armature_enum)

        if armature and armature.type == 'ARMATURE':
            return armature

        return None

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

    def draw_armature_meshes(self, layout, armature):
        mesh_group = layout.box()
        for child in armature.children:
            if child.type == 'MESH' and child.name in self.mesh_properties:
                row = mesh_group.row(align=True)
                row.prop(self.mesh_properties[child.name], "checked", text=child.name)
                row.label(text=self.mesh_properties[child.name].material_name)

                txp_group = mesh_group.box()
                for texproj in self.texproj_properties:
                    if texproj.mesh_name == child.name:
                        row = txp_group.row(align=True)
                        row.prop(texproj, "checked", text=texproj.name)

    def draw_cameras(self, context, layout, show_archive=False):
        camera_group = layout.box()
        cameras = get_scene_cameras(context)

        if not cameras:
            camera_group.label(text="No camera found")

        for camera in cameras:
            settings = camera.level5_camera
            row = camera_group.row(align=True)
            row.prop(settings, "export", text=camera.name)
            row.prop(settings, "animation_name", text="Name")
            row.prop(settings, "speed", text="Speed")

            if show_archive:
                row.prop(settings, "archive_name", text="Archive")

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
                self.draw_armature_meshes(options_box, armature)
        elif self.export_option == 'ANIMATION':
            options_box.prop(self, "animation_enum", text="Available animations")

            armature = self.get_settings_armature()
            if armature:
                options_box.prop(armature.level5_archive, "attach_bone", text="Attach armature")
        elif self.export_option == 'CAMERA':
            self.draw_cameras(context, options_box)
        elif self.export_option == 'SCENE':
            options_box.label(text="Armatures:")
            armature_group = options_box.box()
            armatures = get_scene_armatures(context)

            if not armatures:
                armature_group.label(text="No armature found")

            for armature in armatures:
                settings = armature.level5_archive

                row = armature_group.row(align=True)
                row.prop(settings, "export", text=armature.name)
                row.prop(settings, "export_mode", text="")
                row.prop(settings, "archive_name", text="Archive")

                if settings.export_mode == 'ANIMATION':
                    row.prop(settings, "attach_bone", text="Attach armature")

            options_box.label(text="Cameras:")
            self.draw_cameras(context, options_box, show_archive=True)

    def get_exported_meshes_names(self, context):
        meshes_names = []
        armatures = []

        if self.export_option == 'ARMATURE':
            armature = bpy.data.objects.get(self.armature_enum)
            if armature and armature.type == 'ARMATURE':
                armatures.append(armature)
        elif self.export_option == 'SCENE':
            armatures = [armature for armature in get_scene_armatures(context) if armature.level5_archive.export and armature.level5_archive.export_mode == 'ARMATURE']

        for armature in armatures:
            armature_meshes = [child for child in armature.children if child.type == 'MESH']
            for mesh_prop in self.mesh_properties:
                if mesh_prop.checked:
                    mesh = bpy.data.objects.get(mesh_prop.name)
                    if mesh and mesh in armature_meshes:
                        meshes_names.append(mesh_prop.name)

        return meshes_names

    def draw_texture(self, context, layout):
        if self.export_option == 'CAMERA' or self.export_option == 'ANIMATION':
            texture_box = layout.box()

            if self.export_option == 'ANIMATION':
                texture_box.label(text="Not available on animation mode")
            elif self.export_option == 'CAMERA':
                texture_box.label(text="Not available on camera mode")
        else:
            meshes_props = []
            same_texture = []

            if self.export_option == 'MESH':
                meshes_props = [mesh_prop.name for mesh_prop in self.mesh_properties if mesh_prop.checked]
            else:
                meshes_props = self.get_exported_meshes_names(context)

            groupbox = layout.box()
            box = groupbox.box()

            for texture_prop in self.texture_properties:
                if texture_prop.mesh_name in meshes_props:
                    if texture_prop.name not in same_texture:
                        row = box.row(align=True)
                        row.label(text=texture_prop.name)
                        row.prop(texture_prop, "format", text="")

                        row = box.row(align=True)
                        row.prop(texture_prop, "wrap_s", text="")
                        row.prop(texture_prop, "wrap_t", text="")

                        row = box.row(align=True)
                        row.prop(texture_prop, "mag_filter", text="")
                        row.prop(texture_prop, "min_filter", text="")
                        row.prop(texture_prop, "mip_filter", text="")

                        same_texture.append(texture_prop.name)

    def draw_settings_armature(self, context, layout):
        """Armature selector of the scene mode, return the armature to configure."""
        if self.export_option == 'SCENE':
            layout.prop(self, "settings_armature_enum", text="Armature")

        armature = self.get_settings_armature()

        if armature is None:
            layout.label(text="No armature found")

        return armature

    def draw_animation(self, context, layout):
        anim_box = layout.box()

        if self.export_option in ('ARMATURE', 'ANIMATION', 'SCENE'):
            armature = self.draw_settings_armature(context, anim_box)
            if armature is None:
                return

            row = anim_box.row(align=True)
            row.prop(self, "export_tab_animation_control", expand=True)

            # Check the selected tab
            if self.export_tab_animation_control == 'ARMATURE_ANIMATION':
                self.draw_animation_settings(context, anim_box, armature, 'armature')
            elif self.export_tab_animation_control == 'UV_ANIMATION':
                self.draw_animation_settings(context, anim_box, armature, 'uv')
            elif self.export_tab_animation_control == 'MATERIAL_ANIMATION':
                self.draw_animation_settings(context, anim_box, armature, 'material')
        else:
            if self.export_option == 'MESH':
                anim_box.label(text="Not available on mesh mode")
            elif self.export_option == 'CAMERA':
                anim_box.label(text="Not available on camera mode")

    def draw_animation_settings(self, context, anim_box, armature, animation_type):
        settings = armature.level5_archive
        animation = settings.get_animation(animation_type)

        # Checkbox for including animation
        anim_box.prop(animation, "include", text="Includes Animation")

        if not animation.include:
            return

        # Group for animation settings
        animation_box = anim_box.box()

        # Text field for animation name
        animation_box.prop(animation, "name", text="Animation Name", icon='ANIM')
        animation_box.prop(self, "animation_format_" + animation_type, text="Animations Format")
        animation_box.prop(self, "split_animation_format_" + animation_type, text="Split Animations Format")

        if animation_type != 'armature':
            animation_box.prop(animation, "mode", text="Mode")

        # Group for manual item addition/removal
        items_box = animation_box.box()

        # List of items with name, frame start, and frame end
        for index, item in enumerate(animation.splits):
            row = items_box.row(align=True)
            row.prop(item, "name", text="Name")
            row.prop(item, "speed", text="Speed")
            row.prop(item, "frame_start", text="Start Frame")
            row.prop(item, "frame_end", text="End Frame")

            # Button to remove selected item
            remove_button = row.operator("export_xc.remove_animation_item", text="", icon='REMOVE')
            remove_button.object_name = armature.name
            remove_button.animation_type = animation_type
            remove_button.index = index

        # Button to add an item
        add_button = items_box.operator("export_xc.add_animation_item", text="Add Item", icon='ADD')
        add_button.object_name = armature.name
        add_button.animation_type = animation_type

        # Draw the transformation checkboxes
        box = animation_box.box()
        box.label(text="Transformations:")

        if animation_type == 'armature':
            box.prop(animation, "transform_location")
            box.prop(animation, "transform_rotation")
            box.prop(animation, "transform_scale")
            box.prop(animation, "transform_bool")
            items, view_property, label = settings.bones, "view_bones", "Bones"
        elif animation_type == 'uv':
            box.prop(animation, "transform_location")
            box.prop(animation, "transform_rotation")
            box.prop(animation, "transform_scale")
            items, view_property, label = settings.texprojs, "view_texprojs", "Texprojs"
        else:
            box.prop(animation, "transform_transparency")
            box.prop(animation, "transform_attribute")
            items, view_property, label = settings.materials, "view_materials", "Materials"

        animation_box.prop(settings, view_property, text="View " + label)

        if getattr(settings, view_property):
            box = animation_box.box()
            box.label(text=label + ":")
            for item in items:
                box.prop(item, "enabled", text=item.name)

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

        if self.export_option not in ('ARMATURE', 'SCENE'):
            outline_box.label(text="Only available on armature and scene modes")
            return

        armature = self.draw_settings_armature(context, outline_box)
        if armature is None:
            return

        settings = armature.level5_archive

        # List existing outline items
        for index, outline_item in enumerate(settings.outlines):
            item_box = outline_box.box()

            # Outline properties
            row = item_box.row(align=True)
            row.prop(outline_item, "name", text="Name")

            # Remove button
            remove_button = row.operator("export_xc.remove_outline_item", text="", icon='REMOVE')
            remove_button.object_name = armature.name
            remove_button.index = index

            # Properties
            item_box.prop(outline_item, "thickness", text="Thickness")
            item_box.prop(outline_item, "visibility", text="Visibility")

            # Mesh selection for this outline
            mesh_box = item_box.box()
            mesh_box.label(text="Meshes:")

            # Meshes already assigned to another outline are hidden
            assigned_elsewhere = {
                mesh.name
                for other_index, other_outline in enumerate(settings.outlines) if other_index != index
                for mesh in other_outline.meshes if mesh.assigned
            }

            for mesh in outline_item.meshes:
                if mesh.name not in assigned_elsewhere:
                    mesh_box.prop(mesh, "assigned", text=mesh.name)

        # Add new outline button
        add_button = outline_box.operator("export_xc.add_outline_item", text="Add Outline", icon='ADD')
        add_button.object_name = armature.name

    def invoke(self, context, event):
        wm = context.window_manager

        self.mesh_properties.clear()
        self.texproj_properties.clear()
        self.texture_properties.clear()

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

            if mesh.data.materials and len(mesh.data.materials) > 0 and mesh.data.materials[0]:
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
                if material is None:
                    continue

                if material.use_nodes:
                    # If material uses nodes, iterate over the material nodes
                    for node in material.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            texture_name = node.image.name
                            item = self.texture_properties.add()
                            item.name = texture_name
                            item.mesh_name = mesh.name
                            fill_texture_sampler(item)
                else:
                    # If material doesn't use nodes, try to access the texture from the diffuse shader
                    if hasattr(material, 'texture_slots'):
                        if material.texture_slots and material.texture_slots[0] and material.texture_slots[0].texture:
                            texture = material.texture_slots[0].texture
                            texture_name = texture.name
                            item = self.texture_properties.add()
                            item.name = texture_name
                            item.mesh_name = mesh.name
                            fill_texture_sampler(item)
                    elif hasattr(material, 'brres'):
                        # Enter in berry bush situation
                        for texture_berry_bush in material.brres.textures:
                            texture_name = texture_berry_bush.name
                            for image in texture_berry_bush.imgs:
                                item = self.texture_properties.add()
                                item.name = texture_name
                                item.mesh_name = mesh.name
                                fill_texture_sampler(item)

        # Refresh the bones, texprojs, materials and outline meshes saved on the armatures
        for obj in bpy.data.objects:
            if obj.type == 'ARMATURE':
                sync_archive_settings(obj)

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

    def get_armature_content(self, armature):
        """Return the checked meshes of an armature, their textures and texprojs."""
        meshes = []
        textures = {}
        texprojs = []

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
                            textures[texture.name]['sampler'] = res.properties_to_sampler(texture)
                            textures[texture.name]['linked_material'] = []

                        textures[texture.name]['linked_material'].append(mesh_prop.material_name)

                    meshes.append(mesh_prop)

        return meshes, textures, texprojs

    def get_animations(self, armature):
        """Animations to export from the settings saved on the armature."""
        settings = armature.level5_archive
        animations = {}

        for animation_type in ANIMATION_TYPES:
            animation = settings.get_animation(animation_type)

            if not animation.include:
                continue

            if not animation.name:
                raise XpckExportError(f"The {animation_type} animation of {armature.name} doesn't have name")

            for sub_animation in animation.splits:
                if not sub_animation.name:
                    raise XpckExportError(f"splitted_animation_'{sub_animation.private_index}' of {armature.name} doesn't have a name!")

            transformations = []
            animation_data = {}

            if animation_type == 'armature':
                if animation.transform_location:
                    transformations.append('location')
                if animation.transform_rotation:
                    transformations.append('rotation')
                if animation.transform_scale:
                    transformations.append('scale')
                if animation.transform_bool:
                    transformations.append('bool')

                animation_data['bones'] = [bone.name for bone in settings.bones if bone.enabled]
            elif animation_type == 'uv':
                if animation.transform_location:
                    transformations.append('offset')
                if animation.transform_rotation:
                    transformations.append('rotation')
                if animation.transform_scale:
                    transformations.append('scale')

                animation_data['mode'] = animation.mode
                animation_data['texprojs'] = [texproj.name for texproj in settings.texprojs if texproj.enabled]
            elif animation_type == 'material':
                if animation.transform_transparency:
                    transformations.append('transparency')
                if animation.transform_attribute:
                    transformations.append('attribute')

                animation_data['mode'] = animation.mode
                animation_data['materials'] = [material.name for material in settings.materials if material.enabled]

            animation_data['name'] = animation.name
            animation_data['format'] = getattr(self, "animation_format_" + animation_type)
            animation_data['transformations'] = transformations
            animation_data['split_animation'] = {
                'format': getattr(self, "split_animation_format_" + animation_type),
                'split': list(animation.splits),
            }

            animations[animation_type] = animation_data

        return animations

    def get_outlines(self, armature):
        outlines = []

        for outline_item in armature.level5_archive.outlines:
            outlines.append({
                "name": outline_item.name,
                "thickness": outline_item.thickness,
                "visibility": outline_item.visibility,
                "meshes": [mesh.name for mesh in outline_item.meshes if mesh.assigned]
            })

        return outlines

    def get_cameras(self, camera_objects):
        cameras = []
        camera_animation_names = []

        for camera_eleven in camera_objects:
            settings = camera_eleven.level5_camera

            if not settings.export:
                continue

            # Check if the camera has a animation name
            if settings.animation_name == "":
                raise XpckExportError(f"{camera_eleven.name}' is checked but doesn't have a animation name!")

            camera, target = CameraElevenObject.get_camera_and_target(camera_eleven)
            cameras.append([settings.animation_name, settings.speed, camera, target])
            camera_animation_names.append(settings.animation_name)

        if len(set(camera_animation_names)) != len(camera_animation_names):
            raise XpckExportError(f"Several cameras have the same animation name")

        return cameras

    def get_properties(self):
        return [[archive_prop.name, archive_prop.value] for archive_prop in self.archive_properties if archive_prop.checked]

    def make_mode_files(self, context, template):
        armature = None
        meshes = []
        textures = {}
        texprojs = []
        cameras = []
        properties = []
        animations = {}
        outlines = []
        attach_bone = False

        if self.export_option == 'MESH':
            raise XpckExportError("Mesh export not yet available!")
        elif self.export_option == 'ARMATURE':
            armature = self.get_settings_armature()

            if armature is None:
                raise XpckExportError("No armature selected")

            meshes, textures, texprojs = self.get_armature_content(armature)
            outlines = self.get_outlines(armature)
        elif self.export_option == 'ANIMATION':
            armature = self.get_settings_armature()

            if armature is None:
                raise XpckExportError("The armature attached to the animation hasn't been found")

            attach_bone = armature.level5_archive.attach_bone
        elif self.export_option == 'CAMERA':
            cameras = self.get_cameras(get_scene_cameras(context))

        if self.export_option != 'CAMERA':
            properties = self.get_properties()
            animations = self.get_animations(armature)

        return make_xpck_files(
            self, context,
            template,
            self.export_option,
            armature=armature,
            meshes=meshes,
            textures=textures,
            animations=animations,
            outlines=outlines,
            cameras=cameras,
            properties=properties,
            texprojs=texprojs,
            attach_bone=attach_bone,
        )

    def make_scene_files(self, context, template):
        """One archive per armature and per camera archive name, packed in a single archive."""
        files = {}
        base_name = os.path.splitext(os.path.basename(self.filepath))[0]
        properties = self.get_properties()

        for armature in get_scene_armatures(context):
            settings = armature.level5_archive

            if not settings.export:
                continue

            archive_name = settings.archive_name or f"{armature.name}.xc"
            if archive_name in files:
                raise XpckExportError(f"Several objects use the archive name {archive_name}")

            meshes, textures, texprojs, outlines = [], {}, [], []
            if settings.export_mode == 'ARMATURE':
                meshes, textures, texprojs = self.get_armature_content(armature)
                outlines = self.get_outlines(armature)

            archive_files = make_xpck_files(
                self, context,
                template,
                settings.export_mode,
                armature=armature,
                meshes=meshes,
                textures=textures,
                animations=self.get_animations(armature),
                outlines=outlines,
                properties=properties,
                texprojs=texprojs,
                attach_bone=settings.attach_bone,
            )

            files[archive_name] = xpck.pack_archive_bytes(archive_files)

        # Group the cameras by archive
        camera_archives = {}
        for camera_eleven in get_scene_cameras(context):
            if camera_eleven.level5_camera.export:
                archive_name = camera_eleven.level5_camera.archive_name or f"{base_name}_cam.xv"
                camera_archives.setdefault(archive_name, []).append(camera_eleven)

        for archive_name, camera_objects in camera_archives.items():
            if archive_name in files:
                raise XpckExportError(f"Several objects use the archive name {archive_name}")

            archive_files = make_xpck_files(self, context, template, 'CAMERA', cameras=self.get_cameras(camera_objects))
            files[archive_name] = xpck.pack_archive_bytes(archive_files)

        if not files:
            raise XpckExportError("Nothing to export")

        return files

    def execute(self, context):
        template = [get_template_by_name(self.template_name), self.template_mode_name]

        try:
            if self.export_option == 'SCENE':
                files = self.make_scene_files(context, template)
            else:
                files = self.make_mode_files(context, template)
        except XpckExportError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        xpck.pack_archive(files, self.filepath)

        return {'FINISHED'}

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
        global _import_session

        _import_session = fileio_open_xpck(context, self.filepath, self.report)

        # Let the user choose the armature of each animation
        if _import_session.animation_groups:
            bpy.ops.import_xc.choose_animations('INVOKE_DEFAULT')

        return {'FINISHED'}
