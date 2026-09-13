import bpy
from bpy.props import StringProperty, BoolProperty, FloatProperty, IntProperty, EnumProperty, CollectionProperty, PointerProperty

##########################################
# XPCK export settings stored on objects
#
# The xpck export menu edits these properties directly, so what is filled
# by the import (animation names, split animations, cameras) or changed by
# the user stays saved on the object and in the .blend file.
##########################################

ANIMATION_TYPES = ('armature', 'uv', 'material')

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
    """Settings of the archive made from an armature."""
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

class Level5CameraSettings(bpy.types.PropertyGroup):
    """Settings of a CameraEleven object."""
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
# Helpers
##########################################

def get_armature_meshes(armature):
    return [child for child in armature.children if child.type == 'MESH']

def sync_check_items(collection, names):
    """Keep the collection equal to names, preserving the enabled state of existing items."""
    if [item.name for item in collection] == names:
        return

    states = {item.name: item.enabled for item in collection}
    collection.clear()

    for name in names:
        item = collection.add()
        item.name = name
        item.enabled = states.get(name, True)

def sync_archive_settings(armature):
    """Refresh the bones, texprojs, materials and outline meshes lists of an armature."""
    settings = armature.level5_archive
    meshes = get_armature_meshes(armature)

    sync_check_items(settings.bones, [bone.name for bone in armature.data.bones])

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

    mesh_names = [mesh.name for mesh in meshes]
    for outline in settings.outlines:
        sync_outline_meshes(outline, mesh_names)

def sync_outline_meshes(outline, mesh_names):
    if [mesh.name for mesh in outline.meshes] == mesh_names:
        return

    states = {mesh.name: mesh.assigned for mesh in outline.meshes}
    outline.meshes.clear()

    for mesh_name in mesh_names:
        item = outline.meshes.add()
        item.name = mesh_name
        # Set the raw value, assignments were already exclusive
        item["assigned"] = states.get(mesh_name, False)

def set_animation_settings(animation_settings, name, splits):
    """Fill the animation settings from an imported animation.

    splits: list of dicts with name, speed, frame_start, frame_end.
    """
    animation_settings.include = True
    animation_settings.name = name
    animation_settings.splits.clear()

    for index, split in enumerate(splits):
        item = animation_settings.splits.add()
        item.private_index = index
        item.name = split['name']
        item.speed = split.get('speed', 1.0)
        item.frame_start = split['frame_start']
        item.frame_end = split['frame_end']

def find_unused_index(used_indexes):
    index = 0
    while index in used_indexes:
        index += 1
    return index

##########################################
# Operators
##########################################

class ExportXC_AddAnimationItem(bpy.types.Operator):
    bl_idname = "export_xc.add_animation_item"
    bl_label = "Add Animation Item"
    bl_options = {'INTERNAL', 'UNDO'}

    object_name: StringProperty()
    animation_type: StringProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if obj is None or self.animation_type not in ANIMATION_TYPES:
            return {'CANCELLED'}

        collection = obj.level5_archive.get_animation(self.animation_type).splits
        new_item = collection.add()

        # Find the first unused private_index
        new_item.private_index = find_unused_index([item.private_index for item in collection])

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
    animation_type: StringProperty()
    index: IntProperty()

    def execute(self, context):
        obj = bpy.data.objects.get(self.object_name)
        if obj is None or self.animation_type not in ANIMATION_TYPES:
            return {'CANCELLED'}

        obj.level5_archive.get_animation(self.animation_type).splits.remove(self.index)
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

        # Find the first unused private_index
        new_item.private_index = find_unused_index([item.private_index for item in collection])

        new_item.name = "outline_" + str(new_item.private_index)
        new_item.thickness = 0.0025
        new_item.visibility = 0.5

        sync_outline_meshes(new_item, [mesh.name for mesh in get_armature_meshes(armature)])

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

classes = (
    Level5CheckItem,
    Level5SplitAnimation,
    Level5AnimationSettings,
    Level5OutlineMesh,
    Level5Outline,
    Level5ArchiveSettings,
    Level5CameraSettings,
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
