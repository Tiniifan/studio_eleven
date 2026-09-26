import bpy
from bpy.props import StringProperty, BoolProperty, FloatProperty, IntProperty, EnumProperty, CollectionProperty, PointerProperty

##########################################
# CONST
##########################################

ANIMATION_TYPES = ['armature', 'uv', 'material']

##########################################
# Register class
##########################################

# The export menu edits these properties, what the import fills or the user changes stays saved in the .blend

class Level5CheckItem(bpy.types.PropertyGroup):
    name: StringProperty()
    enabled: BoolProperty(name="Enabled", default=True)

class Level5SplitAnimation(bpy.types.PropertyGroup):
    name: StringProperty()
    speed: FloatProperty(default=1.0)
    frame_start: IntProperty(default=1)
    frame_end: IntProperty(default=250)
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

class Level5Animation(bpy.types.PropertyGroup):
    name: StringProperty(
        name="Animation Name",
        default="animation",
        description="Name of the animation, the mtn2, imm2 and mtm2 files of an animation share it"
    )
    action: PointerProperty(
        type=bpy.types.Action,
        name="Action",
        description="Action of the armature, the UV Warp modifiers of its meshes play it too"
    )
    material_actions: CollectionProperty(type=Level5MaterialAction)
    frame_count: IntProperty(
        name="Frame Count",
        default=0,
        min=0,
        description="Last frame of the animation, 0 uses the end frame of the scene"
    )

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
    thickness: FloatProperty(default=0.0025, min=0.0000, max=0.9999, precision=4)
    visibility: FloatProperty(default=0.5, min=0.0, max=1.0, precision=4)
    private_index: IntProperty()
    meshes: CollectionProperty(type=Level5OutlineMesh)

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

def get_material_actions(armature):
    """Actions the materials of the armature meshes play now."""
    material_actions = {}

    for mesh in get_armature_meshes(armature):
        for material in mesh.data.materials:
            if material and material.animation_data and material.animation_data.action:
                material_actions[material.name] = material.animation_data.action

    return material_actions

def add_animation(settings, name, action=None, material_actions=None, frame_count=0):
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
    animation.frame_count = frame_count
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
    bl_description = "Add an animation to the archive, it takes the actions the armature and its materials play now"
    bl_options = {'INTERNAL', 'UNDO'}

    object_name: StringProperty()

    def execute(self, context):
        armature = bpy.data.objects.get(self.object_name)
        if armature is None or armature.type != 'ARMATURE':
            return {'CANCELLED'}

        action = None
        name = "animation"

        if armature.animation_data and armature.animation_data.action:
            action = armature.animation_data.action
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

        set_actions(get_animation_assignments(armature, animation))

        if animation.frame_count > 0:
            context.scene.frame_end = animation.frame_count

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

def unregister_settings():
    del bpy.types.Object.level5_camera
    del bpy.types.Object.level5_archive

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
