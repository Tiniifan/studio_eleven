"""Studio X side panel (3D view > sidebar > Studio X): import choices that can be changed once a move is imported.

    Camera Zoom        rewrites the lens of every camera made by studio_x (cameras.apply_zoom), exactly as if
                       the move had been imported with that zoom
    Swap Ally/Opponent gives every 3DS player armature the archive and animation names of the other side
                       (eleven.set_sides): _aa1 <-> _ad1, _ba1 <-> _bd1...

The values live on the scene; the import sets them to its own options, so the panel always shows what the
scene holds.
"""

import bpy
from bpy.props import BoolProperty, FloatProperty, PointerProperty

from . import cameras, eleven

# Changing a value from the import itself must not rewrite what the import just built
_applying = {"busy": False}


def _zoom_changed(settings, context):
    if _applying["busy"]:
        return
    for obj in context.scene.objects:
        if obj.type == "CAMERA" and cameras.is_studio_x_camera(obj) and obj[cameras.ZOOM_PROPERTY] != settings.camera_zoom:
            cameras.apply_zoom(obj, settings.camera_zoom)


def _swap_changed(settings, context):
    if _applying["busy"]:
        return
    for obj in context.scene.objects:
        if obj.type == "ARMATURE" and eleven.has_side(obj) and bool(obj[eleven.SWAP_PROPERTY]) != settings.swap_sides:
            eleven.set_sides(obj, settings.swap_sides)


def store_import_options(scene, options):
    """Show the options of the last import in the panel without rewriting anything."""
    _applying["busy"] = True
    try:
        scene.studio_x.camera_zoom = options.camera_zoom
        scene.studio_x.swap_sides = options.swap_sides
    finally:
        _applying["busy"] = False


class StudioXSceneSettings(bpy.types.PropertyGroup):
    camera_zoom: FloatProperty(
        name="Camera Zoom", default=1.0, min=0.1, max=5.0, step=5, precision=2, update=_zoom_changed,
        description="How much larger everything is on screen than with the imported field of view. The game "
                    "wants no single framing for every move (Flame Dance: 1, Ocean Birth: about 0.7)")
    swap_sides: BoolProperty(
        name="Swap Ally / Opponent", default=False, update=_swap_changed,
        description="Defence move: the Unity \"Ally\" players get the defender archives (_ad1...) and the "
                    "\"Opponent\" ones the attacker archives (_aa1...), else the game plays each animation on "
                    "the other player")


class STUDIOX_PT_scene(bpy.types.Panel):
    bl_label = "Studio X"
    bl_idname = "STUDIOX_PT_scene"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Studio X"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.studio_x
        scene_objects = context.scene.objects

        box = layout.box()
        box.label(text="Camera", icon="OUTLINER_OB_CAMERA")
        row = box.row()
        row.enabled = any(o.type == "CAMERA" and cameras.is_studio_x_camera(o) for o in scene_objects)
        row.prop(settings, "camera_zoom")

        box = layout.box()
        box.label(text="Players", icon="OUTLINER_OB_ARMATURE")
        row = box.row()
        row.enabled = any(o.type == "ARMATURE" and eleven.has_side(o) for o in scene_objects)
        row.prop(settings, "swap_sides")


classes = (StudioXSceneSettings, STUDIOX_PT_scene)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.studio_x = PointerProperty(type=StudioXSceneSettings)


def unregister():
    del bpy.types.Scene.studio_x
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
