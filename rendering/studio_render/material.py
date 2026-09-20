"""Binds Blender data to the render data of a game engine: render default, combiner, ATR, textures."""

from ...formats import atr
from .. import game_material, project, render_defaults
from . import combiner, resources, state

STATUS = "the texture order follows what operators/fileio_xmpr.py builds at import"

MAX_TEXTURES = 4


def scene_engine_id(scene):
    return project.get_scene_engine_id(scene)


def render_default_of(engine_id, mesh):
    return project.get_mesh_render_default(mesh, engine_id)


def material_images(material):
    """The image nodes in the order the importer created them, which is the order of the texture list."""
    if material is None or not material.use_nodes or material.node_tree is None:
        return []

    return [node.image for node in material.node_tree.nodes
            if node.type == 'TEX_IMAGE' and node.image is not None][:MAX_TEXTURES]


# Pixels of the mask texture that hold the colors of the character, seen from the top left of the image
PALETTE_PIXELS = {"r": (0, 0), "g": (1, 0), "b": (0, 1)}

# The last mask stage multiplies by 4, the constants of the stages are a quarter of the colors of the character
PALETTE_SCALE = 0.25

_palettes = {}


def palette_of(image):
    """Color of each mask channel of a character texture (hair, eyes, skin), read from its first pixels."""
    key = (image.name_full, tuple(image.size))
    if key not in _palettes:
        width, height = image.size
        colors = {}
        for channel, (x, y) in PALETTE_PIXELS.items():
            start = ((height - 1 - y) * width + x) * 4
            pixel = image.pixels[start:start + 4]
            colors[channel] = (pixel[0] * PALETTE_SCALE, pixel[1] * PALETTE_SCALE, pixel[2] * PALETTE_SCALE, 1.0)
        _palettes[key] = colors

    return _palettes[key]


def clear_palettes():
    _palettes.clear()


def material_state(material, file_version):
    properties = getattr(material, "level5_atr", None) if material is not None else None
    atr_state = atr.state_from_properties(properties) if properties is not None else atr.default_state(file_version)
    atr_state.file_version = file_version

    return state.resolve(atr_state)


class MaterialRender:
    """Everything one draw of one material needs, built once and cached."""

    def __init__(self, engine_id, render_default, program, resolved_state, images, lighting):
        self.engine_id = engine_id
        self.lighting = lighting
        self.render_default = render_default
        self.program = program
        self.state = resolved_state
        self.images = images
        self.program_key = (engine_id, render_default.name if render_default else None)

    @property
    def texture_units(self):
        if self.program is None:
            return ()
        return tuple(unit for unit in sorted(self.program.texture_units) if unit < len(self.images))

    @property
    def fragment_lighting(self):
        return bool(self.program and self.program.uses_fragment_lighting)

    @property
    def skinned(self):
        return bool(self.render_default and self.render_default.data.get("skinned"))


_programs = {}


def clear_cache():
    _programs.clear()


def _stages_of(engine_id, render_default):
    stages = resources.load_combiner(engine_id, render_default.data["combiner"])
    if stages is not None:
        return stages

    # A few shipped render programs point at a combiner their own library doesn't hold
    fallback = render_defaults.get_default_render_default(engine_id)
    print(f"[Studio Eleven] {render_default.name}: combiner {render_default.data['combiner']} is missing from "
          f"{engine_id}, drawing with {fallback.name}")

    return resources.load_combiner(engine_id, fallback.data["combiner"])


def program_of(engine_id, render_default):
    if render_default is None:
        return None

    key = (engine_id, render_default.name)
    if key not in _programs:
        stages = _stages_of(engine_id, render_default)
        _programs[key] = combiner.build_program(stages) if stages else None

    return _programs[key]


def build(engine_id, mesh, material, file_version):
    render_default = render_default_of(engine_id, mesh)

    return MaterialRender(engine_id, render_default, program_of(engine_id, render_default),
                          material_state(material, file_version), material_images(material),
                          game_material.material_of(material, engine_id))
