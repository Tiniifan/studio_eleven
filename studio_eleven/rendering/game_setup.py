import bpy

from bpy.props import BoolProperty, StringProperty

from .engines import GAME_ENGINES, get_engine
from . import game_manager, project


class InstallGameEngine(bpy.types.Operator):
    bl_idname = "studio_eleven.install_game_engine"
    bl_label = "Install Game Engine"
    bl_options = {'INTERNAL'}

    engine_id: StringProperty()
    select: BoolProperty(default=False, options={'HIDDEN'})

    def draw(self, context):
        layout = self.layout
        name = get_engine(self.engine_id).name

        if game_manager.is_installed(self.engine_id):
            layout.label(text=f"An update of {name} is downloaded but not installed.")
            layout.label(text=f"v{game_manager.installed_version(self.engine_id)} -> v{game_manager.bundled_version(self.engine_id)}")
            layout.label(text="Cancel to keep the installed version.")
        else:
            layout.label(text=f"{name} is downloaded in the Studio Eleven data but is not installed.")
            layout.label(text="Install it to use this game engine, without it the project can't use it.")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=460)

    def execute(self, context):
        try:
            version = game_manager.install(self.engine_id)
        except (OSError, ValueError) as error:
            self.report({'ERROR'}, f"Couldn't install {get_engine(self.engine_id).name}: {error}")
            return {'CANCELLED'}

        if self.select:
            setattr(context.scene, project.SCENE_ENGINE_PROPERTY, self.engine_id)

        project.sync_all_scenes()
        self.report({'INFO'}, f"{get_engine(self.engine_id).name} v{version} installed")
        return {'FINISHED'}


class InstallAllGameEngines(bpy.types.Operator):
    bl_idname = "studio_eleven.install_all_game_engines"
    bl_label = "Install Every Game Engine"
    bl_description = "Install the game engines whose zip is in the Studio Eleven data"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        try:
            installed = game_manager.install_all()
        except (OSError, ValueError) as error:
            self.report({'ERROR'}, f"Couldn't install the game engines: {error}")
            return {'CANCELLED'}

        project.sync_all_scenes()
        self.report({'INFO'}, f"{len(installed)} game engine(s) installed")
        return {'FINISHED'}


def draw_game_engines(layout):
    """The game engines of the preferences, the ones whose zip is shipped can be installed."""
    box = layout.box()
    box.label(text="Game engines")

    for engine in GAME_ENGINES:
        row = box.row()
        row.label(text=game_manager.describe(engine.id))

        state = game_manager.status(engine.id)

        if state == "not installed":
            row.operator("studio_eleven.install_game_engine", text="Install").engine_id = engine.id
        elif state == "update available":
            row.operator("studio_eleven.install_game_engine", text="Update").engine_id = engine.id

    box.operator("studio_eleven.install_all_game_engines")


classes = (InstallGameEngine, InstallAllGameEngines)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
