import bpy
from bpy.props import StringProperty, BoolProperty, FloatProperty, FloatVectorProperty, IntProperty, EnumProperty, CollectionProperty, PointerProperty

##########################################
# CONST
##########################################

ANIMATION_TYPES = ['armature', 'uv', 'material']

ANIMATION_TYPE_NAMES = {
    'armature': "Armature",
    'uv': "UV",
    'material': "Material",
}

SPLIT_PROPERTIES = ["name", "speed", "frame_start", "frame_end", "private_index"]

TRACK_NAME = "[Studio Eleven] Second Track"

SOLO_TRACK_NAME = "[Studio Eleven] Solo"

##########################################
# Register class
##########################################

# The export menu edits these properties, what the import fills or the user changes stays saved in the .blend

class Level5CheckItem(bpy.types.PropertyGroup):
    name: StringProperty()
    enabled: BoolProperty(name="Enabled", default=True)

def update_split(self, context):
    if self.id_data.type == 'ARMATURE':
        sync_armature_splits(self.id_data)

class Level5SplitAnimation(bpy.types.PropertyGroup):
    name: StringProperty(name="Name", update=update_split)
    speed: FloatProperty(name="Speed", default=1.0, update=update_split)
    frame_start: IntProperty(name="Start Frame", default=1, update=update_split)
    frame_end: IntProperty(name="End Frame", default=250, update=update_split)
    private_index: IntProperty()

class Level5AnimationSettings(bpy.types.PropertyGroup):
    include: BoolProperty(
        name="Include Animation",
        default=False,
        description="Include animation in the export"
    )
    name: StringProperty(
        name="Animation Name",
        default="animation",
        description="Name of the animation"
    )
    splits: CollectionProperty(type=Level5SplitAnimation)

    transform_location: BoolProperty(name="Location", default=True, description="Include location in the export")
    transform_rotation: BoolProperty(name="Rotation", default=True, description="Include rotation in the export")
    transform_scale: BoolProperty(name="Scale", default=True, description="Include scale in the export")
    transform_bool: BoolProperty(name="Bool", default=True, description="Include bool in the export")
    transform_transparency: BoolProperty(name="Transparency", default=True, description="Include transparency in the export")
    transform_attribute: BoolProperty(name="Attribute", default=True, description="Include attribute in the export")

    mode: EnumProperty(
        name="Mode",
        description="Choose a mode for UV or Material animations",
        items=[
            ("STUDIO_ELEVEN", "Studio Eleven", "Studio Eleven mode"),
            ("BERRY_BUSH", "Berry Bush", "Berry Bush mode")
        ],
        default="STUDIO_ELEVEN"
    )

class Level5MaterialAction(bpy.types.PropertyGroup):
    name: StringProperty()
    action: PointerProperty(type=bpy.types.Action)

def poll_armature_action(self, action):
    armature = self.id_data

    if armature.type != 'ARMATURE':
        return True

    return is_armature_action(armature, action)

class Level5Animation(bpy.types.PropertyGroup):
    name: StringProperty(
        name="Animation Name",
        default="animation",
        description="Name of the animation, the mtn2, imm2 and mtm2 files of an animation share it"
    )
    action: PointerProperty(
        type=bpy.types.Action,
        name="Action",
        description="Action of the armature, the UV Warp modifiers of its meshes play it too. Only the actions of the armature are listed",
        poll=poll_armature_action
    )
    # The actions the materials play in this animation, filled by the import and the add button
    material_actions: CollectionProperty(type=Level5MaterialAction)

    armature_animation: PointerProperty(type=Level5AnimationSettings)
    uv_animation: PointerProperty(type=Level5AnimationSettings)
    material_animation: PointerProperty(type=Level5AnimationSettings)

    def get_animation(self, animation_type):
        return getattr(self, animation_type + "_animation")

def update_outline_mesh_assignment(self, context):
    """A mesh can only be assigned to one outline of the armature."""
    if not self.assigned:
        return

    settings = self.id_data.level5_archive

    for outline in settings.outlines:
        for mesh in outline.meshes:
            if mesh.name == self.name and mesh.assigned and mesh.as_pointer() != self.as_pointer():
                mesh.assigned = False

class Level5OutlineMesh(bpy.types.PropertyGroup):
    name: StringProperty()
    assigned: BoolProperty(default=False, update=update_outline_mesh_assignment)

class Level5Outline(bpy.types.PropertyGroup):
    name: StringProperty()
    thickness: FloatProperty(name="Width", description="Width of the outline: a share of the screen height when Constant Screen Width is on (0.002 in the game), a distance in game units otherwise (0.15)", default=0.0025, min=0.0000, max=0.9999, precision=4)
    visibility: FloatProperty(name="Color Factor", description="The vertex colors of the outline are multiplied by this value, lower is darker", default=0.5, min=0.0, max=1.0, precision=4)
    scale: FloatProperty(name="Marked Color Factor", description="Same as Color Factor for the vertices the model marks in its second silhouette weight", default=0.4, min=0.01, max=10.0, precision=3)
    depth_min: FloatProperty(name="Depth Min", description="Closest distance of the depth range the width is kept inside when Constant Screen Width is off (the game reads 10)", default=10.0, min=0.0, precision=2)
    depth_max: FloatProperty(name="Depth Max", description="Farthest distance of the depth range the width is kept inside when Constant Screen Width is off (the game reads 60)", default=60.0, min=0.0, precision=2)
    open_width: BoolProperty(name="Constant Screen Width", description="Keep the outline the same size on the screen whatever the distance, otherwise the width is a distance kept inside the depth range", default=True)
    color: FloatVectorProperty(name="Color", description="Color of the outline, multiplied by the vertex colors of the mesh", subtype='COLOR', size=4, default=(1.0, 1.0, 1.0, 1.0), min=0.0, max=1.0)
    private_index: IntProperty()
    meshes: CollectionProperty(type=Level5OutlineMesh)

# A second track of the timeline plays another animation with the main one, it is only played, never edited
class Level5TimelineTrack(bpy.types.PropertyGroup):
    animation_name: StringProperty(
        name="Animation",
        default="",
        description="Animation this track plays"
    )
    split_index: IntProperty(default=0)

class Level5TimelineSolo(bpy.types.PropertyGroup):
    armature_name: StringProperty()
    use_preview_range: BoolProperty()
    frame_preview_start: IntProperty()
    frame_preview_end: IntProperty()

class Level5ArchiveSettings(bpy.types.PropertyGroup):
    archive_name: StringProperty(
        name="Archive Name",
        default="",
        description="File name of this armature archive inside a scene archive"
    )
    export: BoolProperty(
        name="Export",
        default=True,
        description="Export this armature in scene mode"
    )
    export_mode: EnumProperty(
        name="Mode",
        items=[
            ('ARMATURE', "Armature", "Export the armature, its meshes and its animations"),
            ('ANIMATION', "Animation", "Export only the animations"),
        ],
        default='ARMATURE'
    )
    attach_bone: BoolProperty(
        name="Attach armature",
        description="Whether to attach armature or not",
        default=False
    )

    animations: CollectionProperty(type=Level5Animation)
    animation_index: IntProperty(default=0)

    # The main track of the timeline plays the active animation
    timeline_split_index: IntProperty(default=0)
    timeline_tracks: CollectionProperty(type=Level5TimelineTrack)

    # One animation per type before the animation list, sync_archive_settings moves them to animations
    armature_animation: PointerProperty(type=Level5AnimationSettings)
    uv_animation: PointerProperty(type=Level5AnimationSettings)
    material_animation: PointerProperty(type=Level5AnimationSettings)

    bones: CollectionProperty(type=Level5CheckItem)
    texprojs: CollectionProperty(type=Level5CheckItem)
    materials: CollectionProperty(type=Level5CheckItem)
    outlines: CollectionProperty(type=Level5Outline)

    view_bones: BoolProperty(name="View Bones", default=False)
    view_texprojs: BoolProperty(name="View Texproj", default=False)
    view_materials: BoolProperty(name="View Material", default=False)

    def get_animation(self, animation_type):
        return getattr(self, animation_type + "_animation")

    def get_active_animation(self):
        if 0 <= self.animation_index < len(self.animations):
            return self.animations[self.animation_index]

        return None

class Level5CameraSettings(bpy.types.PropertyGroup):
    export: BoolProperty(
        name="Export",
        default=True,
        description="Export this camera"
    )
    animation_name: StringProperty(
        name="Animation Name",
        default="",
        description="Name of the camera animation, 0xXXXXXXXX is used as a raw hash (imported cameras)"
    )
    speed: FloatProperty(default=1.0, min=0.1, precision=2)
    archive_name: StringProperty(
        name="Archive Name",
        default="",
        description="File name of the camera archive inside a scene archive"
    )

##########################################
# XPCK Settings Function
##########################################

def get_armature_meshes(armature):
    meshes = []

    for child in armature.children:
        if child.type == 'MESH':
            meshes.append(child)

    return meshes

def get_names(collection):
    names = []

    for item in collection:
        names.append(item.name)

    return names

def sync_check_items(collection, names):
    """Keep the collection equal to names, the existing items keep their enabled state."""
    if get_names(collection) == names:
        return

    states = {}
    for item in collection:
        states[item.name] = item.enabled

    collection.clear()

    for name in names:
        item = collection.add()
        item.name = name
        item.enabled = states.get(name, True)

def sync_archive_settings(armature):
    """Refresh the bones, texprojs, materials and outline meshes of an armature."""
    settings = armature.level5_archive
    meshes = get_armature_meshes(armature)

    sync_check_items(settings.bones, get_names(armature.data.bones))

    texprojs = []
    materials = []
    for mesh in meshes:
        for modifier in mesh.modifiers:
            if modifier.type == 'UV_WARP' and modifier.name not in texprojs:
                texprojs.append(modifier.name)

        for material in mesh.data.materials:
            if material and material.name not in materials:
                materials.append(material.name)

    sync_check_items(settings.texprojs, texprojs)
    sync_check_items(settings.materials, materials)

    for outline in settings.outlines:
        sync_outline_meshes(outline, get_names(meshes))

    move_old_animations(armature)

def move_old_animations(armature):
    """Put the animations of a blend saved before the animation list in the list."""
    settings = armature.level5_archive

    if len(settings.animations) > 0:
        return

    name = None
    for animation_type in ANIMATION_TYPES:
        old_animation = settings.get_animation(animation_type)

        if old_animation.include and name is None:
            name = old_animation.name

    if name is None:
        return

    action = None
    if armature.animation_data:
        action = armature.animation_data.action

    animation = add_animation(settings, name, action, get_material_actions(armature))

    for animation_type in ANIMATION_TYPES:
        old_animation = settings.get_animation(animation_type)
        copy_animation_settings(old_animation, animation.get_animation(animation_type))
        old_animation.include = False

def copy_animation_settings(source, target):
    target.include = source.include
    target.name = source.name
    target.mode = source.mode

    for property_name in ["transform_location", "transform_rotation", "transform_scale", "transform_bool", "transform_transparency", "transform_attribute"]:
        setattr(target, property_name, getattr(source, property_name))

    target.splits.clear()

    for split in source.splits:
        item = target.splits.add()
        item.name = split.name
        item.speed = split.speed
        item.frame_start = split.frame_start
        item.frame_end = split.frame_end
        item.private_index = split.private_index

def get_path_name(data_path, prefix):
    return data_path[len(prefix):data_path.find('"]')]

def uses_action(armature, action):
    """The armature plays the action or has it in its animation list."""
    if armature.animation_data and armature.animation_data.action == action:
        return True

    for animation in armature.level5_archive.animations:
        if animation.action == action:
            return True

    return False

def is_armature_action(armature, action):
    """Action that animates a bone of the armature or a UV Warp modifier of its meshes, and no other armature uses."""
    if uses_action(armature, action):
        return True

    # The characters share their bone names, an action another armature uses is its own
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE' and obj != armature and uses_action(obj, action):
            return False

    meshes = get_armature_meshes(armature)

    for fcurve in action.fcurves:
        data_path = fcurve.data_path

        if data_path.startswith('pose.bones["'):
            if get_path_name(data_path, 'pose.bones["') in armature.data.bones:
                return True
        elif data_path.startswith('modifiers["'):
            modifier_name = get_path_name(data_path, 'modifiers["')

            for mesh in meshes:
                if modifier_name in mesh.modifiers:
                    return True

    return False

def get_default_action(armature):
    """Action a new animation takes: the one the armature plays, or the first action of the armature not used yet."""
    if armature.animation_data and armature.animation_data.action:
        return armature.animation_data.action

    used_actions = []
    for animation in armature.level5_archive.animations:
        used_actions.append(animation.action)

    for action in bpy.data.actions:
        if action not in used_actions and is_armature_action(armature, action):
            return action

    return None

def is_animated_action(action):
    """An action with a curve that changes (Berry Bush gives every material an action with its initial state)."""
    for fcurve in action.fcurves:
        values = set()

        for keyframe in fcurve.keyframe_points:
            values.add(round(keyframe.co.y, 6))

        if len(values) > 1:
            return True

    return False

def get_material_actions(armature):
    """Actions the materials of the armature meshes play now, only the ones that animate something."""
    material_actions = {}

    for mesh in get_armature_meshes(armature):
        for material in mesh.data.materials:
            if material and material.animation_data and material.animation_data.action:
                if is_animated_action(material.animation_data.action):
                    material_actions[material.name] = material.animation_data.action

    return material_actions

def get_animation_frame_count(animation):
    """Last key of the actions of the animation, 0 when they have none."""
    actions = []

    if animation.action:
        actions.append(animation.action)

    for material_action in animation.material_actions:
        if material_action.action:
            actions.append(material_action.action)

    frame_count = 0

    for action in actions:
        for fcurve in action.fcurves:
            for keyframe in fcurve.keyframe_points:
                frame_count = max(frame_count, int(round(keyframe.co.x)))

    return frame_count

def add_animation(settings, name, action=None, material_actions=None):
    """Add an animation to the list, an animation with the same name is replaced (the archive can't have two)."""
    animation = None

    for i, item in enumerate(settings.animations):
        if item.name == name:
            animation = item
            settings.animation_index = i

    if animation is None:
        animation = settings.animations.add()
        settings.animation_index = len(settings.animations) - 1

    animation.name = name
    animation.action = action
    animation.material_actions.clear()

    if material_actions is None:
        material_actions = {}

    for material_name, material_action in material_actions.items():
        item = animation.material_actions.add()
        item.name = material_name
        item.action = material_action

    return animation

def get_animation_assignments(armature, animation):
    """Datablocks and the action they play for this animation, the armature and its meshes share one action."""
    assignments = [(armature, animation.action)]

    for mesh in get_armature_meshes(armature):
        assignments.append((mesh, animation.action))

    for material_action in animation.material_actions:
        material = bpy.data.materials.get(material_action.name)

        if material:
            assignments.append((material, material_action.action))

    return assignments

def set_actions(assignments):
    """Give each datablock its action, return what they played before."""
    previous_assignments = []

    for id_data, action in assignments:
        previous_action = None
        if id_data.animation_data:
            previous_action = id_data.animation_data.action

        previous_assignments.append((id_data, previous_action))

        if id_data.animation_data is None:
            if action is None:
                continue

            id_data.animation_data_create()

        id_data.animation_data.action = action

    return previous_assignments

def sync_outline_meshes(outline, mesh_names):
    if get_names(outline.meshes) == mesh_names:
        return

    states = {}
    for mesh in outline.meshes:
        states[mesh.name] = mesh.assigned

    outline.meshes.clear()

    for mesh_name in mesh_names:
        item = outline.meshes.add()
        item.name = mesh_name
        # Set the raw value, assignments were already exclusive
        item["assigned"] = states.get(mesh_name, False)

def set_animation_settings(animation_settings, name, splits):
    """Fill the animation settings from an imported animation (splits: name, speed, frame_start, frame_end)."""
    animation_settings.include = True
    animation_settings.name = name
    animation_settings.splits.clear()

    for i, split in enumerate(splits):
        item = animation_settings.splits.add()
        item.private_index = i
        item.name = split['name']
        item.speed = split.get('speed', 1.0)
        item.frame_start = split['frame_start']
        item.frame_end = split['frame_end']

def find_unused_index(used_indexes):
    index = 0
    while index in used_indexes:
        index += 1
    return index

def get_archive_animation(object_name, animation_index):
    obj = bpy.data.objects.get(object_name)
    if obj is None:
        return None

    animations = obj.level5_archive.animations
    if animation_index < 0 or animation_index >= len(animations):
        return None

    return animations[animation_index]

def add_default_animation(armature):
    """Animation made from the action the armature plays, used by the export menu and the timeline."""
    action = get_default_action(armature)
    name = "animation"

    if action is not None:
        name = action.name

    # add_animation replaces an animation with the same name
    names = get_names(armature.level5_archive.animations)
    base_name = name
    index = 1

    while name in names:
        name = f"{base_name}.{str(index).rjust(3, '0')}"
        index += 1

    animation = add_animation(armature.level5_archive, name, action, get_material_actions(armature))
    animation.armature_animation.include = action is not None
    animation.material_animation.include = len(animation.material_actions) > 0

    if action is not None:
        for fcurve in action.fcurves:
            if fcurve.data_path.startswith('modifiers["'):
                animation.uv_animation.include = True

    return animation

##########################################
# Timeline Function
##########################################

def get_track_count(armature):
    """The main track and the second tracks."""
    return 1 + len(armature.level5_archive.timeline_tracks)

def get_track_animation(armature, track_index):
    """Animation a track of the timeline plays, the main track (0) plays the active animation."""
    settings = armature.level5_archive

    if track_index == 0:
        return settings.get_active_animation()

    animation_name = settings.timeline_tracks[track_index - 1].animation_name

    for animation in settings.animations:
        if animation.name == animation_name:
            return animation

    return None

def get_track_split_index(armature, track_index):
    settings = armature.level5_archive

    if track_index == 0:
        return settings.timeline_split_index

    return settings.timeline_tracks[track_index - 1].split_index

def set_track_split_index(armature, track_index, index):
    settings = armature.level5_archive

    if track_index == 0:
        settings.timeline_split_index = index
    else:
        settings.timeline_tracks[track_index - 1].split_index = index

def get_source_type(animation):
    """The mtn, imm and mtm of an animation have the same splits, they are edited on the first type it has."""
    for animation_type in ANIMATION_TYPES:
        if animation.get_animation(animation_type).include:
            return animation_type

    return None

def get_track_splits(armature, track_index, animation_type=None):
    """Splits of a type of the track animation, None when the animation doesn't have this type."""
    animation = get_track_animation(armature, track_index)
    if animation is None:
        return None

    if animation_type is None:
        animation_type = get_source_type(animation)

        if animation_type is None:
            return None

    animation_settings = animation.get_animation(animation_type)
    if not animation_settings.include:
        return None

    return animation_settings.splits

def get_track_split(armature, track_index):
    splits = get_track_splits(armature, track_index)
    if splits is None:
        return None

    index = get_track_split_index(armature, track_index)
    if 0 <= index < len(splits):
        return splits[index]

    return None

def copy_splits(source, target):
    """Only the values that differ are written, the update of a split syncs the animation again."""
    while len(target) > len(source):
        target.remove(len(target) - 1)

    while len(target) < len(source):
        target.add()

    for i in range(len(source)):
        for property_name in SPLIT_PROPERTIES:
            value = getattr(source[i], property_name)

            if getattr(target[i], property_name) != value:
                setattr(target[i], property_name, value)

def sync_animation_splits(animation):
    """The other types of the animation get the splits of its first type."""
    source_type = get_source_type(animation)
    if source_type is None:
        return

    source = animation.get_animation(source_type).splits

    for animation_type in ANIMATION_TYPES:
        animation_settings = animation.get_animation(animation_type)

        if animation_type != source_type and animation_settings.include:
            copy_splits(source, animation_settings.splits)

def sync_armature_splits(armature):
    for animation in armature.level5_archive.animations:
        sync_animation_splits(animation)

def setup_timeline(armature):
    """Timeline after an import: the main track plays an animation with bones when there is one."""
    settings = armature.level5_archive
    reference = settings.get_active_animation()

    settings.timeline_split_index = 0

    if reference is not None and not reference.armature_animation.include:
        for i, animation in enumerate(settings.animations):
            if animation.armature_animation.include:
                settings.animation_index = i
                break

    sync_armature_splits(armature)
    apply_track_actions(armature)

def get_timeline_ids(armature):
    """Datablocks the timeline can put a strip on: the armature, its meshes and their materials."""
    ids = [armature]

    for mesh in get_armature_meshes(armature):
        ids.append(mesh)

        for material in mesh.data.materials:
            if material and material not in ids:
                ids.append(material)

    return ids

def clear_timeline_strips(armature):
    for id_data in get_timeline_ids(armature):
        if id_data.animation_data is None:
            continue

        tracks = id_data.animation_data.nla_tracks
        timeline_tracks = [track for track in tracks if track.name in [TRACK_NAME, SOLO_TRACK_NAME]]

        for track in timeline_tracks:
            tracks.remove(track)

def add_timeline_strip(id_data, action, track_name, frame_start, action_start, action_end):
    if id_data.animation_data is None:
        id_data.animation_data_create()

    track = id_data.animation_data.nla_tracks.new()
    track.name = track_name

    strip = track.strips.new(action.name, int(frame_start), action)
    strip.use_sync_length = False

    if action_end <= action_start:
        action_end = action_start + 1

    # The action range can't start after its end, the start is set before and after the end
    strip.action_frame_start = min(action_start, strip.action_frame_end)
    strip.action_frame_end = action_end
    strip.action_frame_start = action_start

    # The game stops the shorter animation, it keeps its last frame while the others play
    strip.extrapolation = 'HOLD'

def apply_track_actions(armature):
    """The main track plays its actions, the second tracks play theirs in NLA strips under it."""
    clear_timeline_strips(armature)

    main_animation = get_track_animation(armature, 0)
    if main_animation is not None:
        set_actions(get_animation_assignments(armature, main_animation))

    for track_index in range(1, get_track_count(armature)):
        animation = get_track_animation(armature, track_index)
        if animation is None:
            continue

        for id_data, action in get_animation_assignments(armature, animation):
            if action is None:
                continue

            action_start = int(action.frame_range[0])
            action_end = int(round(action.frame_range[1]))
            add_timeline_strip(id_data, action, TRACK_NAME, action_start, action_start, action_end)

def get_solo_reference(armature):
    """Split the solo starts from: the one of the main track, or of the first track that has one."""
    for track_index in range(get_track_count(armature)):
        split = get_track_split(armature, track_index)

        if split is not None:
            return split

    return None

def get_solo_offset(scene, armature, track_index):
    """Frames a track is moved by during the solo, its active split starts with the one of the reference."""
    if scene.level5_timeline_solo.armature_name != armature.name:
        return 0

    reference = get_solo_reference(armature)
    split = get_track_split(armature, track_index)

    if reference is None or split is None:
        return 0

    return reference.frame_start - split.frame_start

def start_solo(scene, armature, jump=True):
    """Play the active split of each track together, like the game does, return False when no track has a split."""
    reference = get_solo_reference(armature)
    if reference is None:
        return False

    solo = scene.level5_timeline_solo

    if solo.armature_name != armature.name:
        stop_solo(scene)

        solo.use_preview_range = scene.use_preview_range
        solo.frame_preview_start = scene.frame_preview_start
        solo.frame_preview_end = scene.frame_preview_end

    clear_timeline_strips(armature)

    frame_start = reference.frame_start
    frame_end = frame_start + 1

    # The main track is added last, it plays over the second tracks like out of the solo
    for track_index in reversed(range(get_track_count(armature))):
        split = get_track_split(armature, track_index)
        if split is None:
            continue

        frame_end = max(frame_end, frame_start + split.frame_end - split.frame_start)

        for id_data, action in get_animation_assignments(armature, get_track_animation(armature, track_index)):
            if action is None:
                continue

            # The action of the datablock would play over the strips
            if track_index == 0 and id_data.animation_data is not None:
                id_data.animation_data.action = None

            add_timeline_strip(id_data, action, SOLO_TRACK_NAME, frame_start, split.frame_start, split.frame_end)

    solo.armature_name = armature.name

    scene.use_preview_range = True
    scene.frame_preview_start = frame_start
    scene.frame_preview_end = frame_end

    if jump:
        scene.frame_set(frame_start)
    else:
        scene.frame_set(scene.frame_current)

    return True

def refresh_solo(scene, armature):
    if scene.level5_timeline_solo.armature_name == armature.name:
        if not start_solo(scene, armature, jump=False):
            stop_solo(scene)

def stop_solo(scene):
    solo = scene.level5_timeline_solo
    if solo.armature_name == "":
        return

    armature = bpy.data.objects.get(solo.armature_name)
    if armature is not None:
        apply_track_actions(armature)

    scene.use_preview_range = solo.use_preview_range
    scene.frame_preview_start = solo.frame_preview_start
    scene.frame_preview_end = solo.frame_preview_end

    solo.armature_name = ""
    scene.frame_set(scene.frame_current)

class LEVEL5_UL_animations(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "name", text="", emboss=False, icon='ACTION')

        if item.action:
            row.label(text=item.action.name)
        else:
            row.label(text="No action")

class ExportXC_AddAnimation(bpy.types.Operator):
    bl_idname = "export_xc.add_animation"
    bl_label = "Add Animation"
    bl_description = "Add an animation to the archive, it takes the action of the armature"
    bl_options = {'INTERNAL', 'UNDO'}

    object_name: StringProperty()

    def execute(self, context):
        armature = bpy.data.objects.get(self.object_name)
        if armature is None or armature.type != 'ARMATURE':
            return {'CANCELLED'}

        add_default_animation(armature)

        return {'FINISHED'}

class ExportXC_RemoveAnimation(bpy.types.Operator):
    bl_idname = "export_xc.remove_animation"
    bl_label = "Remove Animation"
    bl_description = "Remove the animation from the archive, its actions are kept"
    bl_options = {'INTERNAL', 'UNDO'}

    object_name: StringProperty()
    index: IntProperty()

    def execute(self, context):
        armature = bpy.data.objects.get(self.object_name)
        if armature is None or self.index >= len(armature.level5_archive.animations):
            return {'CANCELLED'}

        settings = armature.level5_archive
        settings.animations.remove(self.index)
        settings.animation_index = min(settings.animation_index, len(settings.animations) - 1)

        return {'FINISHED'}

class ExportXC_PlayAnimation(bpy.types.Operator):
    bl_idname = "export_xc.play_animation"
    bl_label = "Play Animation"
    bl_description = "Give the actions of this animation to the armature, its meshes and its materials"
    bl_options = {'INTERNAL', 'UNDO'}

    object_name: StringProperty()
    index: IntProperty()

    def execute(self, context):
        armature = bpy.data.objects.get(self.object_name)
        animation = get_archive_animation(self.object_name, self.index)
        if animation is None:
            return {'CANCELLED'}

        # The animation goes on the main track of the timeline, the second tracks keep playing theirs
        if context.scene.level5_timeline_solo.armature_name == armature.name:
            stop_solo(context.scene)

        armature.level5_archive.animation_index = self.index
        armature.level5_archive.timeline_split_index = 0
        apply_track_actions(armature)

        frame_count = get_animation_frame_count(animation)

        if frame_count > 0:
            context.scene.frame_end = frame_count

        context.scene.frame_set(context.scene.frame_current)

        return {'FINISHED'}

class ExportXC_AddAnimationItem(bpy.types.Operator):
    bl_idname = "export_xc.add_animation_item"
    bl_label = "Add Animation Item"
    bl_options = {'INTERNAL', 'UNDO'}

    object_name: StringProperty()
    animation_index: IntProperty()
    animation_type: StringProperty()

    def execute(self, context):
        animation = get_archive_animation(self.object_name, self.animation_index)
        if animation is None or self.animation_type not in ANIMATION_TYPES:
            return {'CANCELLED'}

        collection = animation.get_animation(self.animation_type).splits
        new_item = collection.add()

        used_indexes = []
        for item in collection:
            used_indexes.append(item.private_index)

        # Find the first unused private_index
        new_item.private_index = find_unused_index(used_indexes)

        new_item.name = "splitted_animation_" + str(new_item.private_index)
        new_item.speed = 1
        new_item.frame_start = 1
        new_item.frame_end = 250

        sync_armature_splits(bpy.data.objects[self.object_name])

        return {'FINISHED'}

class ExportXC_RemoveAnimationItem(bpy.types.Operator):
    bl_idname = "export_xc.remove_animation_item"
    bl_label = "Remove Animation Item"
    bl_options = {'INTERNAL', 'UNDO'}

    object_name: StringProperty()
    animation_index: IntProperty()
    animation_type: StringProperty()
    index: IntProperty()

    def execute(self, context):
        animation = get_archive_animation(self.object_name, self.animation_index)
        if animation is None or self.animation_type not in ANIMATION_TYPES:
            return {'CANCELLED'}

        animation.get_animation(self.animation_type).splits.remove(self.index)

        sync_armature_splits(bpy.data.objects[self.object_name])

        return {'FINISHED'}

class ExportXC_AddOutlineItem(bpy.types.Operator):
    bl_idname = "export_xc.add_outline_item"
    bl_label = "Add Outline Item"
    bl_options = {'INTERNAL', 'UNDO'}

    object_name: StringProperty()

    def execute(self, context):
        armature = bpy.data.objects.get(self.object_name)
        if armature is None:
            return {'CANCELLED'}

        collection = armature.level5_archive.outlines
        new_item = collection.add()

        used_indexes = []
        for item in collection:
            used_indexes.append(item.private_index)

        # Find the first unused private_index
        new_item.private_index = find_unused_index(used_indexes)

        new_item.name = "outline_" + str(new_item.private_index)
        new_item.thickness = 0.0025
        new_item.visibility = 0.5

        sync_outline_meshes(new_item, get_names(get_armature_meshes(armature)))

        return {'FINISHED'}

class ExportXC_RemoveOutlineItem(bpy.types.Operator):
    bl_idname = "export_xc.remove_outline_item"
    bl_label = "Remove Outline Item"
    bl_options = {'INTERNAL', 'UNDO'}

    object_name: StringProperty()
    index: IntProperty()

    def execute(self, context):
        armature = bpy.data.objects.get(self.object_name)
        if armature is None:
            return {'CANCELLED'}

        armature.level5_archive.outlines.remove(self.index)
        return {'FINISHED'}

##########################################
# Register
##########################################

classes = (
    Level5CheckItem,
    Level5SplitAnimation,
    Level5AnimationSettings,
    Level5MaterialAction,
    Level5Animation,
    Level5OutlineMesh,
    Level5Outline,
    Level5TimelineTrack,
    Level5TimelineSolo,
    Level5ArchiveSettings,
    Level5CameraSettings,
    LEVEL5_UL_animations,
    ExportXC_AddAnimation,
    ExportXC_RemoveAnimation,
    ExportXC_PlayAnimation,
    ExportXC_AddAnimationItem,
    ExportXC_RemoveAnimationItem,
    ExportXC_AddOutlineItem,
    ExportXC_RemoveOutlineItem,
)

def register_settings():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Object.level5_archive = PointerProperty(type=Level5ArchiveSettings)
    bpy.types.Object.level5_camera = PointerProperty(type=Level5CameraSettings)
    bpy.types.Scene.level5_timeline_solo = PointerProperty(type=Level5TimelineSolo)

def unregister_settings():
    del bpy.types.Scene.level5_timeline_solo
    del bpy.types.Object.level5_camera
    del bpy.types.Object.level5_archive

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
