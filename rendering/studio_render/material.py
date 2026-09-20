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


_image_textures = {}


def image_texture(image):
    """GPU texture of an image, uploaded once."""
    import gpu

    key = image.name_full
    if key not in _image_textures:
        _image_textures[key] = gpu.texture.from_image(image)

    return _image_textures[key]


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


def clear_textures():
    _image_textures.clear()


# The inputs the importer animates for a MaterialTransparency track (fileio_animation_manager.process_material_track)
FADE_INPUTS = (
    ('node_tree.nodes["Alpha Multiplier"].inputs[1].default_value', "Alpha Multiplier", 1),
    ('node_tree.nodes["Principled BSDF"].inputs[21].default_value', "Principled BSDF", 21),
)


def fade_input_of(material):
    """(node name, input index) holding the animated transparency of a material, None when it is not animated."""
    animation = material.animation_data if material is not None else None
    if animation is None or animation.action is None:
        return None

    paths = {fcurve.data_path for fcurve in animation.action.fcurves}
    return next(((node, index) for path, node, index in FADE_INPUTS if path in paths), None)


def fade_of(material, fade_input):
    """Current value of the transparency track: 1 shows the material, 0 hides it."""
    node = material.node_tree.nodes.get(fade_input[0]) if material.node_tree else None
    return node.inputs[fade_input[1]].default_value if node is not None else 1.0


def material_state(material, file_version):
    properties = getattr(material, "level5_atr", None) if material is not None else None
    atr_state = atr.state_from_properties(properties) if properties is not None else atr.default_state(file_version)
    atr_state.file_version = file_version

    return state.resolve(atr_state)


class MaterialRender:
    """Everything one draw of one material needs, built once and cached until Blender reports a change."""

    def __init__(self, engine_id, render_default, program, resolved_state, images, lighting, fade_input=None):
        self.engine_id = engine_id
        self.fade_input = fade_input
        self.lighting = lighting
        self.render_default = render_default
        self.program = program
        self.state = resolved_state
        self.images = images
        self.program_key = (engine_id, render_default.name if render_default else None)
        self._textures = {}
        self._palette = None
        self._palette_read = False

    def texture(self, unit):
        """GPU texture of a texture unit, it needs the GPU so it is created on the first draw."""
        if unit not in self._textures:
            self._textures[unit] = image_texture(self.images[unit])

        return self._textures[unit]

    @property
    def palette(self):
        """Colors of the mask channels of the first texture, None for a program without mask stages."""
        if not self._palette_read:
            self._palette_read = True
            program = self.program
            masked = program is not None and (program.palette_channels or (program.base is not None and program.base.palette_channels))
            self._palette = palette_of(self.images[0]) if masked and self.images else None

        return self._palette

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
_bound = {}


def clear_cache():
    _programs.clear()
    _bound.clear()


def invalidate(material_names=(), mesh_names=()):
    """Drops the cached draws of the materials and meshes Blender reports as changed."""
    if not material_names and not mesh_names:
        return

    for key in [key for key in _bound if key[1] in mesh_names or key[2] in material_names]:
        del _bound[key]


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
    key = (engine_id, mesh.name, material.name if material is not None else None, file_version)
    bound = _bound.get(key)

    if bound is None:
        render_default = render_default_of(engine_id, mesh)
        bound = MaterialRender(engine_id, render_default, program_of(engine_id, render_default),
                               material_state(material, file_version), material_images(material),
                               game_material.material_of(material, engine_id), fade_input_of(material))
        _bound[key] = bound

    return bound
