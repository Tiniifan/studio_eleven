import bpy

from bpy.app.handlers import persistent
from bpy.props import EnumProperty, StringProperty

from .engines import engine_items, get_engine, is_default_engine, DEFAULT_ENGINE_ID, GAME_ENGINES, ALL_ENGINES
from . import render_defaults, game_manager

ADDON_ID = __package__.split(".")[0]

SCENE_ENGINE_PROPERTY = "level5_game_engine"
SCENE_LAST_ENGINE_PROPERTY = "level5_last_engine"
SCENE_INSTALLED_PROPERTY = "level5_installed_engine"

##########################################
# Preferences
##########################################

class StudioElevenPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    default_game_engine: EnumProperty(
        name="Default Game Engine",
        description="Game engine given to new projects, existing projects keep their own",
        items=engine_items(),
        default=DEFAULT_ENGINE_ID,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "default_game_engine")

        box = layout.box()
        box.label(text="Game engines")
        for engine in GAME_ENGINES:
            row = box.row()
            row.label(text=game_manager.describe(engine.id))

            state = game_manager.status(engine.id)
            if state in ("not installed", "update available"):
                operator = row.operator("studio_eleven.install_game_engine", text="Install" if state == "not installed" else "Update")
                operator.engine_id = engine.id

        layout.operator("studio_eleven.setup", text="Run the setup")


def get_default_engine_id():
    addon = bpy.context.preferences.addons.get(ADDON_ID)
    engine_id = addon.preferences.default_game_engine if addon else DEFAULT_ENGINE_ID
    return engine_id if game_manager.is_usable(engine_id) else DEFAULT_ENGINE_ID

##########################################
# Project game engine
##########################################

def get_scene_engine_id(scene=None):
    scene = scene or bpy.context.scene
    return getattr(scene, SCENE_ENGINE_PROPERTY, DEFAULT_ENGINE_ID)


def get_scene_engine(scene=None):
    return get_engine(get_scene_engine_id(scene))


_installed_items = {}


def installed_engine_items(self=None, context=None):
    """Enum items of the engines that can be used right now, one list per set so blender keeps a valid reference."""
    engines = tuple(engine.id for engine in ALL_ENGINES if game_manager.is_usable(engine.id))
    if engines not in _installed_items:
        _installed_items[engines] = [(engine_id, get_engine(engine_id).name, "") for engine_id in engines]
    return _installed_items[engines]


def get_installed_choice(self):
    ids = [item[0] for item in installed_engine_items()]
    engine_id = get_scene_engine_id(self)
    return ids.index(engine_id) if engine_id in ids else 0


def set_installed_choice(self, value):
    setattr(self, SCENE_ENGINE_PROPERTY, installed_engine_items()[value][0])


def is_scene_engine_usable(scene=None):
    return game_manager.is_usable(get_scene_engine_id(scene))


_items_cache = {}


def render_default_items(scene=None):
    """Enum items of the render defaults of the scene engine, blender keeps a reference to the returned list."""
    key = game_manager.data_engine_id(get_scene_engine_id(scene))
    if key not in _items_cache:
        _items_cache[key] = [
            (render_default.name, render_default.name, f"Vertex program {render_default.data['vertex_program']}, combiner {render_default.data['combiner']}")
            for render_default in render_defaults.get_render_defaults(key)
        ]
    return _items_cache[key]


def scene_meshes(scene):
    return {obj.data for obj in scene.objects if obj.type == 'MESH'}


def assign_render_default(mesh, engine_id):
    """Give the mesh a render default of the engine, returns True when its value changed."""
    properties = mesh.level5_properties
    resolved = render_defaults.resolve_render_default(engine_id, properties.render_default)

    if properties.render_default == resolved.name:
        return False

    previous = properties.render_default
    properties.render_default = resolved.name

    if previous:
        print(f"[Studio Eleven] {mesh.name}: render default {previous} is not available in {engine_id}, using {resolved.name}")

    return True


def assign_imported_render_program(mesh, render_program_hash, engine_id=None):
    engine_id = engine_id or get_scene_engine_id()
    found = render_defaults.find_render_default_by_hash(engine_id, render_program_hash)

    if found is None:
        print(f"[Studio Eleven] {mesh.name}: render program {render_program_hash:08X} is not part of {engine_id}")
        assign_render_default(mesh, engine_id)
    else:
        mesh.level5_properties.render_default = found.name


def get_mesh_render_default(mesh, engine_id=None):
    return render_defaults.resolve_render_default(engine_id or get_scene_engine_id(), mesh.level5_properties.render_default)


def sync_scene_render_defaults(scene):
    # The meshes keep their render defaults while the engine isn't installed, the default game would replace them
    if not is_scene_engine_usable(scene):
        return 0

    engine_id = get_scene_engine_id(scene)
    return sum(assign_render_default(mesh, engine_id) for mesh in scene_meshes(scene))


def run_later(function, *args):
    bpy.app.timers.register(lambda: function(*args), first_interval=0.05)


def call_operator(idname, **kwargs):
    # A dialog needs a window, there is none when blender runs in the background
    if bpy.app.background:
        return

    group, name = idname.split(".")
    try:
        getattr(getattr(bpy.ops, group), name)('INVOKE_DEFAULT', **kwargs)
    except RuntimeError as error:
        print(f"[Studio Eleven] {idname} couldn't open: {error}")


def propose_update(engine_id):
    if game_manager.pending_update(engine_id):
        # Asked once per session, an ignored update keeps the installed version
        game_manager.ignore_update(engine_id)
        call_operator("studio_eleven.install_game_engine", engine_id=engine_id)


def refuse_engine(scene_name, engine_id):
    scene = bpy.data.scenes.get(scene_name)
    if scene is None:
        return

    last = getattr(scene, SCENE_LAST_ENGINE_PROPERTY, "") or DEFAULT_ENGINE_ID
    setattr(scene, SCENE_ENGINE_PROPERTY, last if game_manager.is_usable(last) else DEFAULT_ENGINE_ID)
    call_operator("studio_eleven.install_game_engine", engine_id=engine_id, select=True)


def update_scene_engine(self, context):
    engine_id = get_scene_engine_id(self)

    if not game_manager.is_usable(engine_id):
        # The engine can't be used before it is installed, the scene goes back to the previous one
        run_later(refuse_engine, self.name, engine_id)
        return

    setattr(self, SCENE_LAST_ENGINE_PROPERTY, engine_id)
    sync_scene_render_defaults(self)
    run_later(propose_update, engine_id)


def init_scene_engine(scene):
    # The property is absent from the scene until it has been written once
    if SCENE_ENGINE_PROPERTY not in scene.keys():
        engine_id = get_default_engine_id()
        setattr(scene, SCENE_LAST_ENGINE_PROPERTY, engine_id)
        setattr(scene, SCENE_ENGINE_PROPERTY, engine_id)

##########################################
# Handlers
##########################################

@persistent
def on_load_post(_dummy=None):
    for scene in bpy.data.scenes:
        init_scene_engine(scene)
        sync_scene_render_defaults(scene)

        if is_scene_engine_usable(scene):
            propose_update(get_scene_engine_id(scene))

    # Called as a timer, a None return runs it only once
    return None


@persistent
def on_depsgraph_update(scene, depsgraph):
    for update in depsgraph.updates:
        obj = update.id
        if isinstance(obj, bpy.types.Object) and obj.type == 'MESH' and not obj.data.level5_properties.render_default:
            assign_render_default(obj.data, get_scene_engine_id(scene))


def run_setup():
    if not game_manager.is_setup_done():
        call_operator("studio_eleven.setup")

##########################################
# Register
##########################################

def register():
    bpy.utils.register_class(StudioElevenPreferences)

    setattr(bpy.types.Scene, SCENE_ENGINE_PROPERTY, EnumProperty(
        name="Game Engine",
        description="Game engine of the project, it decides the render defaults and the file versions written by the export",
        items=engine_items(),
        default=DEFAULT_ENGINE_ID,
        update=update_scene_engine,
    ))
    setattr(bpy.types.Scene, SCENE_LAST_ENGINE_PROPERTY, StringProperty(default=DEFAULT_ENGINE_ID))
    setattr(bpy.types.Scene, SCENE_INSTALLED_PROPERTY, EnumProperty(
        name="Game",
        description="Game engine of the project, only the ones that are installed are listed",
        items=installed_engine_items,
        get=get_installed_choice,
        set=set_installed_choice,
    ))

    bpy.app.handlers.load_post.append(on_load_post)
    bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)

    # bpy.data is restricted while the addon registers, and load_post has already run when it is enabled later
    bpy.app.timers.register(on_load_post, first_interval=0.0)
    bpy.app.timers.register(run_setup, first_interval=1.0)


def unregister():
    for timer in (on_load_post, run_setup):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)

    bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
    bpy.app.handlers.load_post.remove(on_load_post)

    delattr(bpy.types.Scene, SCENE_INSTALLED_PROPERTY)
    delattr(bpy.types.Scene, SCENE_LAST_ENGINE_PROPERTY)
    delattr(bpy.types.Scene, SCENE_ENGINE_PROPERTY)

    bpy.utils.unregister_class(StudioElevenPreferences)
