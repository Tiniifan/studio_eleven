import bpy

from bpy.props import BoolProperty, EnumProperty, StringProperty

from .engines import GAME_ENGINES, engine_items, get_engine
from . import game_manager, project


def sync_all_scenes():
    for scene in bpy.data.scenes:
        project.sync_scene_render_defaults(scene)


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

        sync_all_scenes()
        self.report({'INFO'}, f"{get_engine(self.engine_id).name} v{version} installed")
        return {'FINISHED'}


class Setup(bpy.types.Operator):
    bl_idname = "studio_eleven.setup"
    bl_label = "Studio Eleven Setup"
    bl_options = {'INTERNAL'}

    mode: EnumProperty(
        name="Mode",
        items=[
            ('EXPRESS', "Express", "Install one game engine and use it by default"),
            ('FULL', "Complete", "Install every game engine and choose the one used by default"),
            ('SKIP', "Skip", "Install nothing, no game is registered"),
        ],
        default='EXPRESS',
    )

    engine_id: EnumProperty(name="Game Engine", items=engine_items(games_only=True))

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "mode", expand=True)

        if self.mode == 'EXPRESS':
            layout.prop(self, "engine_id", text="Game")
            layout.label(text="This game engine is installed and used by default.")
        elif self.mode == 'FULL':
            layout.label(text="Every game engine is installed.")
            layout.prop(self, "engine_id", text="Used by default")
        else:
            layout.label(text="No game is registered: a configuration that works for every game")
            layout.label(text="is used, it isn't optimized for one. You can register a game later.")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=460)

    def execute(self, context):
        try:
            if self.mode == 'EXPRESS':
                game_manager.install(self.engine_id)
            elif self.mode == 'FULL':
                game_manager.install_all()
        except (OSError, ValueError) as error:
            self.report({'ERROR'}, f"Setup failed: {error}")
            return {'CANCELLED'}

        if self.mode != 'SKIP':
            preferences = context.preferences.addons[project.ADDON_ID].preferences
            preferences.default_game_engine = self.engine_id
            setattr(context.scene, project.SCENE_ENGINE_PROPERTY, self.engine_id)

        game_manager.set_setup_done()
        sync_all_scenes()
        return {'FINISHED'}


classes = (InstallGameEngine, Setup)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
