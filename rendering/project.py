import bpy
import json
import zlib

from bpy.app.handlers import persistent
from bpy.props import EnumProperty, StringProperty

from .engines import engine_items, get_engine, is_default_engine, DEFAULT_ENGINE_ID, ALL_ENGINES
from . import render_defaults, game_manager
from ..templates import TEMPLATE_ITEMS, DEFAULT_TEMPLATE_ID, get_template
from ..formats import atr, mtr

##########################################
# CONST
##########################################

ADDON_ID = __package__.split(".")[0]

SCENE_TEMPLATE_PROPERTY = "level5_template"
SCENE_ENGINE_PROPERTY = "level5_game_engine"
SCENE_LAST_ENGINE_PROPERTY = "level5_last_engine"
SCENE_INSTALLED_PROPERTY = "level5_installed_engine"

##########################################
# StudioRender
##########################################

def is_studio_render_enabled():
    """StudioRender, the game engines and their install are only there once the preference unlocks them."""
    addon = bpy.context.preferences.addons.get(ADDON_ID)

    if addon is None:
        return False

    preferences = addon.preferences

    return getattr(preferences, "studio_render_unlocked", False) and getattr(preferences, "studio_render_enabled", False)

##########################################
# Project template
##########################################

def get_scene_template(scene=None):
    scene = scene or bpy.context.scene

    return get_template(getattr(scene, SCENE_TEMPLATE_PROPERTY, DEFAULT_TEMPLATE_ID))

def get_template_material(template):
    return mtr.read_mtr(bytes.fromhex(template["mtr"]))

def get_template_state(template):
    state = atr.new_state(get_engine(template["engine"]).file_version)

    for field, value in template["atr"].items():
        state[field] = value

    return state

def get_default_mtr(scene=None):
    """The lighting material a material without its own one exports: the one of the template, or of the game engine with StudioRender."""
    if is_studio_render_enabled():
        return bytes.fromhex(render_defaults.get_engine_data(get_scene_engine_id(scene)).info["default_material"]["mtr"])

    return bytes.fromhex(get_scene_template(scene)["mtr"])

##########################################
# Project game engine
##########################################

def get_scene_engine_id(scene=None):
    scene = scene or bpy.context.scene

    # Without StudioRender the template decides the game engine, the property can't be changed
    if not is_studio_render_enabled():
        return get_scene_template(scene)["engine"]

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

    if engine_id in ids:
        return ids.index(engine_id)

    return 0

def set_installed_choice(self, value):
    setattr(self, SCENE_ENGINE_PROPERTY, installed_engine_items()[value][0])

def is_scene_engine_usable(scene=None):
    return game_manager.is_usable(get_scene_engine_id(scene))

_items_cache = {}

def render_default_items(scene=None):
    """Enum items of the render defaults of the scene engine, blender keeps a reference to the returned list."""
    key = game_manager.data_engine_id(get_scene_engine_id(scene))

    if key not in _items_cache:
        _items_cache[key] = []

        for render_default in render_defaults.get_render_defaults(key):
            description = f"Vertex program {render_default.data['vertex_program']}, combiner {render_default.data['combiner']}"
            _items_cache[key].append((render_default.name, render_default.name, description))

    return _items_cache[key]

def scene_meshes(scene):
    return {obj.data for obj in scene.objects if obj.type == 'MESH'}

def assign_render_default(mesh, engine_id):
    """Give the mesh a render default of the engine, returns True when its value changed."""
    properties = mesh.level5_properties

    kept = None
    if properties.unresolved_render_program:
        kept = render_defaults.find_render_default_by_hash(engine_id, int(properties.unresolved_render_program, 16))

    if kept is not None:
        properties.unresolved_render_program = ""
        resolved = kept
    else:
        resolved = None
        if properties.render_default:
            resolved = render_defaults.find_render_default(engine_id, properties.render_default)

        if resolved is None:
            # A program the engine doesn't have is kept as a hash, the export writes it back
            if properties.render_default and not properties.unresolved_render_program:
                properties.unresolved_render_program = f"{zlib.crc32(properties.render_default.encode('shift-jis')):08X}"

            resolved = render_defaults.get_default_render_default(engine_id)

    if properties.render_default == resolved.name:
        return kept is not None

    properties.render_default = resolved.name

    return True

def assign_render_program(mesh, render_program_hash, engine_id):
    """Give the mesh a render program, the export writes its hash back when the engine doesn't have it."""
    found = render_defaults.find_render_default_by_hash(engine_id, render_program_hash)

    if found is None:
        mesh.level5_properties.unresolved_render_program = f"{render_program_hash:08X}"
        assign_render_default(mesh, engine_id)
    else:
        mesh.level5_properties.unresolved_render_program = ""
        mesh.level5_properties.render_default = found.name

    return found

def assign_imported_render_program(mesh, render_program_hash, engine_id=None):
    engine_id = engine_id or get_scene_engine_id()

    if assign_render_program(mesh, render_program_hash, engine_id) is None:
        print(f"[Studio Eleven] {mesh.name}: render program {render_program_hash:08X} is not part of {engine_id}")

def get_mesh_render_default(mesh, engine_id=None):
    return render_defaults.resolve_render_default(engine_id or get_scene_engine_id(), mesh.level5_properties.render_default)

def get_mesh_render_program_hash(mesh, engine_id=None):
    unresolved = mesh.level5_properties.unresolved_render_program

    if unresolved:
        return int(unresolved, 16)

    return get_mesh_render_default(mesh, engine_id).render_program_hash

def sync_scene_render_defaults(scene):
    # The meshes keep their render defaults while the engine isn't installed, the default game would replace them
    if not is_scene_engine_usable(scene):
        return 0

    engine_id = get_scene_engine_id(scene)
    count = 0

    for mesh in scene_meshes(scene):
        if assign_render_default(mesh, engine_id):
            count += 1

    return count

def sync_all_scenes():
    for scene in bpy.data.scenes:
        sync_scene_render_defaults(scene)

def sync_scene_engines():
    """Without StudioRender every scene goes back to the game engine of its template."""
    for scene in bpy.data.scenes:
        engine_id = get_scene_template(scene)["engine"]

        if not is_studio_render_enabled() and getattr(scene, SCENE_ENGINE_PROPERTY) != engine_id:
            setattr(scene, SCENE_LAST_ENGINE_PROPERTY, engine_id)
            setattr(scene, SCENE_ENGINE_PROPERTY, engine_id)

        sync_scene_render_defaults(scene)

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
    if is_studio_render_enabled() and game_manager.pending_update(engine_id):
        # Asked once per session, an ignored update keeps the installed version
        game_manager.ignore_update(engine_id)
        call_operator("studio_eleven.install_game_engine", engine_id=engine_id)

def refuse_engine(scene_name, engine_id):
    scene = bpy.data.scenes.get(scene_name)

    if scene is None:
        return

    last = getattr(scene, SCENE_LAST_ENGINE_PROPERTY, "") or get_scene_template(scene)["engine"]

    if not game_manager.is_usable(last):
        last = get_scene_template(scene)["engine"]

    setattr(scene, SCENE_ENGINE_PROPERTY, last)
    call_operator("studio_eleven.install_game_engine", engine_id=engine_id, select=True)

def update_scene_engine(self, context):
    engine_id = getattr(self, SCENE_ENGINE_PROPERTY)

    if not game_manager.is_usable(engine_id):
        # The engine can't be used before it is installed, the scene goes back to the previous one
        run_later(refuse_engine, self.name, engine_id)
        return

    setattr(self, SCENE_LAST_ENGINE_PROPERTY, engine_id)
    sync_scene_render_defaults(self)
    run_later(propose_update, engine_id)

def update_scene_template(self, context):
    if is_studio_render_enabled():
        return

    engine_id = get_scene_template(self)["engine"]

    setattr(self, SCENE_LAST_ENGINE_PROPERTY, engine_id)
    setattr(self, SCENE_ENGINE_PROPERTY, engine_id)

def init_scene_engine(scene):
    # The property is absent from the scene until it has been written once
    if SCENE_ENGINE_PROPERTY not in scene.keys():
        engine_id = get_scene_template(scene)["engine"]
        setattr(scene, SCENE_LAST_ENGINE_PROPERTY, engine_id)
        setattr(scene, SCENE_ENGINE_PROPERTY, engine_id)

##########################################
# New meshes and materials
##########################################

def init_new_mesh(mesh, scene):
    engine_id = get_scene_engine_id(scene)

    if is_studio_render_enabled():
        assign_render_default(mesh, engine_id)
    else:
        # A mesh made in Blender gets the render program of the "Object (Transparent)" mode of the template
        assign_render_program(mesh, get_scene_template(scene)["render_program_hash"], engine_id)

def init_new_material(material, scene):
    """A material made in Blender gets the render state and the lighting material of the template."""
    from ..operators.panels.material_render import state_to_properties

    material.level5_mtr.initialized = True

    if is_studio_render_enabled():
        return

    template = get_scene_template(scene)

    state_to_properties(get_template_state(template), material.level5_atr)
    material.level5_mtr.data = json.dumps(get_template_material(template).to_dict())

def keep_materials(materials):
    # The materials of a loaded blend are kept as they are, only the ones made afterwards are initialized
    for material in materials:
        if hasattr(material, "level5_mtr") and not material.level5_mtr.initialized:
            material.level5_mtr.initialized = True

##########################################
# Handlers
##########################################

# Nothing is initialized before the materials of the open blend are kept
loaded = False

@persistent
def on_load_post(dummy=None):
    global loaded

    keep_materials(bpy.data.materials)
    loaded = True

    for scene in bpy.data.scenes:
        init_scene_engine(scene)

    sync_scene_engines()

    for scene in bpy.data.scenes:
        if is_studio_render_enabled() and is_scene_engine_usable(scene):
            propose_update(get_scene_engine_id(scene))

    # Called as a timer, a None return runs it only once
    return None

@persistent
def on_depsgraph_update(scene, depsgraph):
    if not loaded:
        return

    for update in depsgraph.updates:
        data = update.id.original

        if isinstance(data, bpy.types.Object) and data.type == 'MESH' and not data.data.level5_properties.render_default:
            init_new_mesh(data.data, scene)
        elif isinstance(data, bpy.types.Material) and hasattr(data, "level5_mtr") and not data.level5_mtr.initialized:
            init_new_material(data, scene)

##########################################
# Register
##########################################

def register():
    setattr(bpy.types.Scene, SCENE_TEMPLATE_PROPERTY, EnumProperty(
        name="Template",
        description="Games the blend is made for: the version of the exported files and what a new mesh gets",
        items=TEMPLATE_ITEMS,
        default=DEFAULT_TEMPLATE_ID,
        update=update_scene_template,
    ))

    setattr(bpy.types.Scene, SCENE_ENGINE_PROPERTY, EnumProperty(
        name="Game Engine",
        description="Game engine of the project, it decides the render defaults and the file versions written by the export",
        items=engine_items(),
        default=DEFAULT_ENGINE_ID,
        update=update_scene_engine,
        options={'HIDDEN'},
    ))

    setattr(bpy.types.Scene, SCENE_LAST_ENGINE_PROPERTY, StringProperty(default=DEFAULT_ENGINE_ID, options={'HIDDEN'}))

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

def unregister():
    if bpy.app.timers.is_registered(on_load_post):
        bpy.app.timers.unregister(on_load_post)

    bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
    bpy.app.handlers.load_post.remove(on_load_post)

    delattr(bpy.types.Scene, SCENE_INSTALLED_PROPERTY)
    delattr(bpy.types.Scene, SCENE_LAST_ENGINE_PROPERTY)
    delattr(bpy.types.Scene, SCENE_ENGINE_PROPERTY)
    delattr(bpy.types.Scene, SCENE_TEMPLATE_PROPERTY)
