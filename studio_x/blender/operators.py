"""Import operators.

File > Import > Studio X opens the file browser with the import options. Once the files are read,
a dialog lists the models/cameras (all ticked); a ticked one is imported with all of its animations.
"""

import json
import os

import addon_utils
import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from . import animations, cameras, eleven, models, retarget
from .textures import TextureCache
from ..unity import Environment
from ..unity.catalog import KIND_CAMERA, build_catalog

# Files read by the import operator, used by the selection dialog that follows
_session = {"environment": None, "catalog": [], "options": None}


def studio_eleven_enabled():
    return addon_utils.check("studio_eleven")[1]


def studio_render_available():
    """True when Studio Eleven's StudioRender render engine is actually registered.

    A Studio Eleven version older than the one that introduced StudioRender has no rendering
    module at all (ImportError): checking the Blender registration works for any version instead
    of comparing version numbers. Render engines aren't exposed on bpy.types like operators or
    panels are, so the class itself has to be asked whether bpy.utils.register_class succeeded on it.
    """
    if not studio_eleven_enabled():
        return False
    try:
        from studio_eleven.rendering.studio_render.engine import StudioRenderEngine
    except ImportError:
        return False
    return bool(getattr(StudioRenderEngine, "is_registered", False))


RENDER_ENGINE_STUDIO = "STUDIO_RENDER"
RENDER_ENGINE_EEVEE = "BLENDER_EEVEE"


def render_engine_items(self, context):
    items = [(RENDER_ENGINE_EEVEE, "Eevee", "Blender's built-in real time engine")]
    if studio_render_available():
        items.insert(0, (RENDER_ENGINE_STUDIO, "StudioRender", "Studio Eleven's Level-5 render engine"))
    return items


def default_render_engine():
    return RENDER_ENGINE_STUDIO if studio_render_available() else RENDER_ENGINE_EEVEE


def configure_render_engine(context, choice):
    """Set the scene render engine (and game, for StudioRender) before the import: StudioRender reads them while drawing."""
    scene = context.scene
    if choice == RENDER_ENGINE_STUDIO and studio_render_available():
        scene.render.engine = RENDER_ENGINE_STUDIO
        # Filmic (Blender's default view transform) makes StudioRender's output darker and less
        # saturated than the game; Studio Eleven's own scene builder sets Standard for this reason
        scene.view_settings.view_transform = "Standard"
        from studio_eleven.rendering import engines, game_manager
        engine_id = "IE4" if game_manager.is_usable("IE4") else engines.DEFAULT_ENGINE_V1.id
        if hasattr(scene, "level5_game_engine"):
            scene.level5_game_engine = engine_id
    else:
        scene.render.engine = RENDER_ENGINE_EEVEE


# Platform -> screen format it imposes (Custom lets the user pick one)
PLATFORM_FORMATS = {"ORIGINAL": "9:16", "3DS": "5:3"}
# Platform -> frame rate it imposes: Unity samples at 60 fps, the 3DS games at 30 fps
PLATFORM_FPS = {"ORIGINAL": 60, "3DS": 30}
SCREEN_FORMATS = ("16:9", "9:16", "5:3")


def screen_aspect(operator):
    """Width / height of the target screen chosen in the import options."""
    name = PLATFORM_FORMATS.get(operator.platform, operator.screen_format)
    if name == "CUSTOM":
        return operator.custom_width / operator.custom_height
    width, height = name.split(":")
    return float(width) / float(height)


class ImportOptions:
    def __init__(self, operator):
        self.fps = PLATFORM_FPS.get(operator.platform, operator.fps)
        self.frame_offset = operator.frame_offset
        self.camera_frame_offset = operator.camera_frame_offset
        self.scale = operator.scale
        self.adapt_textures = operator.adapt_textures
        self.camera_target_distance = operator.camera_target_distance
        self.split_camera = operator.split_camera
        self.camera_distance_factor = cameras.screen_distance_factor(screen_aspect(operator))
        # The 3DS bodies and the move names only exist on the 3DS platform
        is_3ds = operator.platform == "3DS"
        self.use_3ds_models = is_3ds and operator.use_3ds_models
        self.reduce_textures = is_3ds and getattr(operator, "reduce_textures", True)
        self.waza_name = operator.waza_name.strip() if is_3ds else ""


# Import options kept between Blender sessions (everything but the waza name)
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "import_settings.json")
SAVED_OPTIONS = ("fps", "frame_offset", "scale", "adapt_textures", "camera_frame_offset", "camera_target_distance",
                 "split_camera", "platform", "screen_format", "custom_width", "custom_height", "use_3ds_models",
                 "reduce_textures", "render_engine")


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as stream:
            settings = json.load(stream)
    except (OSError, ValueError):
        return {}
    return settings if isinstance(settings, dict) else {}


def save_settings(operator):
    settings = {name: getattr(operator, name) for name in SAVED_OPTIONS}
    # The format and frame rate imposed by Original / 3DS must not replace the ones chosen in Custom
    if operator.platform in PLATFORM_FORMATS:
        saved = load_settings()
        settings["screen_format"] = saved.get("screen_format", "16:9")
        settings["fps"] = _saved_fps(saved)
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
    except OSError:
        pass


def _saved_fps(settings):
    # Files written before the frame rate became a number held "30", "60" or "CUSTOM"
    value = settings.get("fps")
    return value if isinstance(value, int) and 0 <= value <= 144 else 30


def _option_changed(operator, context):
    save_settings(operator)


def _platform_changed(operator, context):
    # Back to Custom: restore the format and frame rate chosen there
    saved = load_settings()
    operator.screen_format = PLATFORM_FORMATS.get(operator.platform) or saved.get("screen_format", "16:9")
    operator.fps = PLATFORM_FPS.get(operator.platform) or _saved_fps(saved)
    save_settings(operator)


DIALOG_WIDTH = 600
# Nodes that only hold the player node listed on its own
HIDDEN_PREFIXES = ("Ally Root", "Opponent Root")


def listed_entries(catalog):
    """Entries shown in the content dialog."""
    return [entry for entry in catalog if not entry.name.startswith(HIDDEN_PREFIXES)]


def _center_dialog(context, row_count):
    """invoke_props_dialog opens the dialog around the mouse: move the cursor to the window center first.

    Blender centers the dialog horizontally on the mouse and puts its top at the mouse (wm_block_dialog_create),
    so the cursor goes half a dialog height above the center. Measured in Blender 3.4: a dialog with N rows is
    (N + 3) rows high (title, rows, OK button and paddings).
    """
    window = context.window
    if window is None:
        return
    preferences = context.preferences
    ui_scale = getattr(preferences.system, "ui_scale", 0.0) or preferences.view.ui_scale
    unit = 20.0 * ui_scale
    # Title, rows and the OK button
    height = (row_count + 3) * unit
    y = window.height / 2.0 + height / 2.0
    window.cursor_warp(int(window.width / 2), int(min(max(y, 0), window.height - 1)))


class StudioXModelItem(bpy.types.PropertyGroup):
    name: StringProperty()
    key: StringProperty()
    path: StringProperty()
    kind: StringProperty()
    summary: StringProperty()
    selected: BoolProperty(name="Import", default=True)


class STUDIOX_OT_import(bpy.types.Operator, ImportHelper):
    """Import Unity asset bundles / .assets files (requires Studio Eleven)"""
    bl_idname = "import_scene.studio_x"
    bl_label = "Import Studio X"
    bl_options = {"REGISTER"}

    filter_glob: StringProperty(default="*", options={"HIDDEN"})
    files: CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN", "SKIP_SAVE"})
    directory: StringProperty(subtype="DIR_PATH", options={"HIDDEN", "SKIP_SAVE"})

    fps: IntProperty(
        name="Frame Rate", default=30, min=0, max=144, update=_option_changed,
        description="Frames per second of the imported animations and cameras. "
                    "Locked to 30 on the 3DS platform and to 60 on the Original one")
    frame_offset: IntProperty(
        name="Unity Frame Offset", default=1, min=-60, max=60, update=_option_changed,
        description="Unity frames (1/60 s) added when sampling. 1 matches the 3DS timing of the converted moves")
    scale: FloatProperty(
        name="Scale", default=10.0, min=0.0001, update=_option_changed,
        description="Unit conversion. 10 converts Unity meters to Studio Eleven / 3DS units")
    adapt_textures: BoolProperty(
        name="Adapt Textures", default=True, update=_option_changed,
        description="Bake masks, gradations, occlusion and specular into a single texture per material")

    camera_frame_offset: IntProperty(
        name="Camera Frame Offset", default=0, min=-60, max=60, update=_option_changed,
        description="Unity frames (1/60 s) added when sampling cameras. 0 matches the 3DS camera timing")
    camera_target_distance: FloatProperty(
        name="Camera Target Distance", default=2.5, min=0.01, update=_option_changed,
        description="Distance (Unity units) of the CameraEleven target in front of the camera. On a screen wider "
                    "than the Unity one, the camera moves toward this target to keep the framing")
    split_camera: BoolProperty(
        name="Split Camera", default=True, update=_option_changed,
        description="Create one Studio Eleven camera per timeline clip instead of a single merged camera")

    platform: EnumProperty(
        name="Platform",
        items=[("ORIGINAL", "Original", "Keep the Unity cameras as they are (portrait 9:16 screen of Inazuma Eleven Cross)"),
               ("3DS", "3DS", "Adapt the cameras to the 3DS top screen (5:3) and show the 3DS options"),
               ("CUSTOM", "Custom", "Adapt the cameras to the chosen screen format")],
        default="3DS", update=_platform_changed)
    screen_format: EnumProperty(
        name="Screen Format",
        items=[(name, name, "Screen of %s (width:height)" % name) for name in SCREEN_FORMATS]
        + [("CUSTOM", "Custom", "Choose the width:height ratio")],
        default="5:3", update=_option_changed,
        description="Screen the cameras are adapted to (the Unity moves are framed for a 9:16 portrait screen)")
    custom_width: FloatProperty(name="Width", default=16.0, min=0.01, update=_option_changed)
    custom_height: FloatProperty(name="Height", default=9.0, min=0.01, update=_option_changed)
    use_3ds_models: BoolProperty(
        name="Use 3DS Bodies and Ball", default=False, update=_option_changed,
        description="Replace \"Ally\" and \"Opponent\" models by the 3DS bodies (fat, normal, small, tall) and "
                    "\"Ball\" models by the 3DS ball, with their animations retargeted")
    reduce_textures: BoolProperty(
        name="Reduce 512 Textures", default=True, update=_option_changed,
        description="Halve the width and the height of every texture 512 texels wide or high "
                    "(512x512 -> 256x256, 512x256 -> 256x128), lighter for the 3DS")
    waza_name: StringProperty(
        name="Waza Name", default="", options={"SKIP_SAVE"},
        description="Name of the 3DS move (whs0001...). When set, the Studio Eleven export settings get the "
                    "archive and animation names of the move: <waza>_aa1.xc for the first ally on a normal "
                    "body, _ba1/_sa1/_ta1 for the other bodies, _ad1... for the opponents, _bl1.xc for the "
                    "ball and _cam.xv for the cameras")
    render_engine: EnumProperty(
        name="Render Engine",
        items=render_engine_items, update=_option_changed,
        description="Render engine used to preview the import. Locked to Eevee when Studio Eleven's "
                    "StudioRender isn't available")

    @classmethod
    def poll(cls, context):
        return studio_eleven_enabled()

    def invoke(self, context, event):
        # Restore the options of the previous imports, even from another Blender session
        for name, value in load_settings().items():
            if name in SAVED_OPTIONS:
                try:
                    setattr(self, name, value)
                except (TypeError, ValueError):
                    pass
        if self.platform in PLATFORM_FORMATS:
            self.screen_format = PLATFORM_FORMATS[self.platform]
            self.fps = PLATFORM_FPS[self.platform]
        if self.render_engine not in (item[0] for item in render_engine_items(self, context)):
            self.render_engine = default_render_engine()
        return ImportHelper.invoke(self, context, event)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "frame_offset")
        layout.prop(self, "scale")

        box = layout.box()
        box.label(text="Camera Properties", icon="OUTLINER_OB_CAMERA")
        box.prop(self, "camera_frame_offset")
        box.prop(self, "camera_target_distance")
        box.prop(self, "split_camera")

        layout.prop(self, "adapt_textures")

        box = layout.box()
        box.label(text="Scene Properties", icon="SCENE_DATA")
        row = box.row()
        row.enabled = studio_render_available()
        row.prop(self, "render_engine")
        box.prop(self, "platform")
        row = box.row()
        # Original and 3DS impose their screen and frame rate
        row.enabled = self.platform == "CUSTOM"
        row.prop(self, "screen_format")
        if self.platform == "CUSTOM" and self.screen_format == "CUSTOM":
            row = box.row(align=True)
            row.prop(self, "custom_width")
            row.prop(self, "custom_height")
        row = box.row()
        row.enabled = self.platform == "CUSTOM"
        row.prop(self, "fps")
        if self.platform == "3DS":
            box.prop(self, "use_3ds_models")
            box.prop(self, "reduce_textures")
            box.prop(self, "waza_name")

    def execute(self, context):
        if ImportOptions(self).fps <= 0:
            self.report({"ERROR"}, "The frame rate must be above 0")
            return {"CANCELLED"}
        configure_render_engine(context, self.render_engine)
        paths = [os.path.join(self.directory, f.name) for f in self.files if f.name] or [self.filepath]
        try:
            environment = Environment()
            for path in paths:
                environment.load(path)
            catalog = build_catalog(environment)
        except Exception as error:
            self.report({"ERROR"}, "Cannot read Unity files: %s" % error)
            return {"CANCELLED"}
        if not catalog:
            self.report({"WARNING"}, "No model or camera found in the selected files")
            return {"CANCELLED"}

        save_settings(self)
        _session.update(environment=environment, catalog=catalog, options=ImportOptions(self))
        bpy.ops.studio_x.choose_content("INVOKE_DEFAULT")
        return {"FINISHED"}


class STUDIOX_OT_choose_content(bpy.types.Operator):
    """Choose the models and cameras to import"""
    bl_idname = "studio_x.choose_content"
    bl_label = "Studio X - Choose Content"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    models: CollectionProperty(type=StudioXModelItem)

    def invoke(self, context, event):
        self.models.clear()
        for entry in listed_entries(_session["catalog"]):
            tracks, clips = entry.import_sources()
            item = self.models.add()
            item.key = entry.key
            item.name = entry.name
            item.path = entry.node.path
            item.kind = entry.kind
            parts = []
            if tracks:
                parts.append("%d timeline%s" % (len(tracks), "s" if len(tracks) > 1 else ""))
            if clips:
                parts.append("%d clip%s" % (len(clips), "s" if len(clips) > 1 else ""))
            item.summary = ", ".join(parts)
            item.selected = True
        _center_dialog(context, len(self.models))
        return context.window_manager.invoke_props_dialog(self, width=DIALOG_WIDTH)

    def draw(self, context):
        column = self.layout.column(align=True)
        for item in self.models:
            row = column.row()
            row.prop(item, "selected", text=item.path,
                     icon="OUTLINER_OB_CAMERA" if item.kind == KIND_CAMERA else "OUTLINER_OB_ARMATURE")
            if item.summary:
                row.label(text=item.summary)

    def execute(self, context):
        options = _session["options"]
        environment = _session["environment"]
        if options is None or environment is None:
            self.report({"ERROR"}, "Use File > Import > Studio X first")
            return {"CANCELLED"}
        if not studio_eleven_enabled():
            self.report({"ERROR"}, "The Studio Eleven addon must be enabled")
            return {"CANCELLED"}
        if context.object and context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        entries = {entry.key: entry for entry in _session["catalog"]}
        cache = TextureCache(environment, self.report, reduce_512=options.reduce_textures)
        last_frame = 0
        imported = 0
        effects = 0

        for item in self.models:
            entry = entries.get(item.key)
            if not item.selected or entry is None:
                continue
            imported += 1
            # A selected node brings all of its animations, timelines first
            tracks, clips = entry.import_sources()
            sources = [animations.Source.from_track(track) for track in tracks]
            sources += [animations.Source.from_clip(clip) for clip in clips]

            if entry.kind == KIND_CAMERA:
                for source in sources or [None]:
                    cameras.build_cameras(context, entry, source, options)
            else:
                # Effect models ("ev...") are the <waza>_ef1.xc, _ef2.xc... archives of the move
                archive = None
                if entry.name.startswith("ev"):
                    archive = eleven.effect_archive_name(options.waza_name, effects)
                    effects += 1
                self._import_model(context, entry, environment, sources, options, cache, archive)

            # The scene range follows the main animation (the timeline when there is one)
            if sources:
                last_frame = max(last_frame, sources[0].frame_count(options.fps))

        if not imported:
            self.report({"WARNING"}, "Nothing selected")
            return {"CANCELLED"}
        context.scene.render.fps = options.fps
        context.scene.render.fps_base = 1.0
        if last_frame:
            context.scene.frame_start = 0
            context.scene.frame_end = last_frame
        context.scene.frame_set(0)
        return {"FINISHED"}

    def _import_model(self, context, entry, environment, sources, options, cache, archive=None):
        kind = retarget.replacement(entry) if options.use_3ds_models else None
        if kind is not None:
            retarget.import_replacement(context, entry, kind, sources, options, self.report)
            return
        # A ball kept as the Unity model still animates the ball archive of the move (<waza>_bl1.xc)
        if archive is None and retarget.role_of(entry) == "ball":
            archive = eleven.model_archive_name(options.waza_name, "ball", retarget.index_of(entry))
        result = models.build_armature(context, entry, environment, options, cache, self.report)
        first_assignments = []
        for index, source in enumerate(sources):
            # Timelines drive several models: the model name keeps the animation names unique
            name = "%s_%s" % (source.name, entry.name) if source.is_timeline else source.name
            sampler = animations.Sampler(source, options)
            action = bpy.data.actions.new(name)
            result.armature.animation_data_create()
            result.armature.animation_data.action = action
            animations.bake_bones(action, result, sampler, options)
            created = [(result.armature, action)] + animations.bake_renderers(result, sampler, action, options)
            if len(sources) > 1:
                for _, created_action in created:
                    created_action.use_fake_user = True

            if index == 0:
                first_assignments = created
                splits = eleven.split_animations(source, options.fps)
                animation_types = {"armature"}
                material_actions = {}
                for id_data, created_action in created[1:]:
                    if isinstance(id_data, bpy.types.Material):
                        animation_types.add("material")
                        material_actions[id_data.name] = created_action
                    else:
                        animation_types.add("uv")
                eleven.store_armature_animation(result.armature, action, splits, animation_types, archive,
                                                material_actions)
        # Keep the first selected animation active when several were imported
        for id_data, action in first_assignments:
            id_data.animation_data.action = action


def menu_import(self, context):
    self.layout.operator(STUDIOX_OT_import.bl_idname, text="Studio X (Unity bundle / assets)")


classes = (
    StudioXModelItem,
    STUDIOX_OT_import,
    STUDIOX_OT_choose_content,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
