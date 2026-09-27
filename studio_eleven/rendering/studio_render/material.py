"""Binds Blender data to the render data of a game engine: render default, combiner, ATR, textures."""

from ...formats import atr, res
from .. import game_material, project, render_defaults
from . import combiner, resources, state

STATUS = "the texture units follow the texture slots of the material (Material > Level 5 > Textures)"

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


_mip_textures = {}


def is_power_of_two(value):
    return value > 1 and value & (value - 1) == 0


def can_mip(image):
    return is_power_of_two(image.size[0]) and is_power_of_two(image.size[1])


def mip_texture(image):
    """The mip chain of an image in one texture, level 0 on the left and the other levels stacked on its right.

    Blender 3.4 builds no levels for the textures of gpu.texture.from_image, the shader picks a level with the offsets.
    """
    import gpu
    import numpy

    key = image.name_full
    if key not in _mip_textures:
        base = image_texture(image)
        width, height = base.width, base.height
        pixels = numpy.array(base.read().to_list(), dtype=numpy.float32).reshape(height, width, 4)

        # A byte texture is read back as its stored 0..255 values, the sampler of an SRGB8_A8 one gives them scene linear
        if base.format in ('RGBA8', 'SRGB8_A8'):
            pixels /= 255.0

        if base.format == 'SRGB8_A8':
            color = pixels[..., :3]
            pixels[..., :3] = numpy.where(color <= 0.04045, color / 12.92, ((color + 0.055) / 1.055) ** 2.4)

        levels = [pixels]

        while max(levels[-1].shape[:2]) > 1:
            level = levels[-1]
            if level.shape[0] > 1:
                level = level.reshape(level.shape[0] // 2, 2, level.shape[1], 4).mean(axis=1)
            if level.shape[1] > 1:
                level = level.reshape(level.shape[0], level.shape[1] // 2, 2, 4).mean(axis=2)
            levels.append(level)

        rows = max(height, sum(level.shape[0] for level in levels[1:]))
        atlas = numpy.zeros((rows, width + levels[1].shape[1], 4), dtype=numpy.float32)
        atlas[:height, :width] = levels[0]

        row = 0
        for level in levels[1:]:
            atlas[row:row + level.shape[0], width:width + level.shape[1]] = level
            row += level.shape[0]

        buffer = gpu.types.Buffer('FLOAT', atlas.size, atlas.ravel().tolist())
        _mip_textures[key] = gpu.types.GPUTexture((atlas.shape[1], atlas.shape[0]), format='RGBA16F', data=buffer)

    return _mip_textures[key]


def texture_slots(material):
    """The texture slots with an image, in the order of the exported texture list; None when the material has no slots yet."""
    textures = getattr(material, "level5_textures", None) if material is not None else None

    if textures is None or not textures.initialized:
        return None

    return [slot for slot in textures.slots if slot.image is not None][:MAX_TEXTURES]


def material_images(material):
    """The image of each texture unit, None for a disabled slot (the game leaves its unit empty)."""
    slots = texture_slots(material)

    if slots is not None:
        return [slot.image if slot.texture_mode != 'DISABLED' else None for slot in slots]

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
    _mip_textures.clear()


# The value node the importer animates for a MaterialTransparency track (fileio_animation_manager.process_material_track)
FADE_NODE = "Level5 Transparency"
FADE_DATA_PATH = f'node_tree.nodes["{FADE_NODE}"].outputs[0].default_value'


def fade_input_of(material):
    """Name of the node holding the animated transparency of a material, None when it is not animated."""
    animation = material.animation_data if material is not None else None
    if animation is None:
        return None

    # The solo of the timeline plays the action in a NLA strip
    actions = [animation.action] if animation.action is not None else []
    for track in animation.nla_tracks:
        actions.extend(strip.action for strip in track.strips if strip.action is not None)

    for action in actions:
        for fcurve in action.fcurves:
            if fcurve.data_path == FADE_DATA_PATH:
                return FADE_NODE

    return None


def fade_of(material, fade_input):
    """Current value of the transparency track: 1 shows the material, 0 hides it."""
    node = material.node_tree.nodes.get(fade_input) if material.node_tree else None
    return node.outputs[0].default_value if node is not None else 1.0


def sampler_tuple(sampler):
    return (sampler["wrap_s"], sampler["wrap_t"], sampler["mag_filter"] | (sampler["min_filter"] << 1), sampler["mip_filter"])


def samplers_of(material):
    """(wrap S, wrap T, magnification | minification << 1, mipmap) of each texture unit, from the texture slots."""
    from ...operators.panels.material_textures import properties_to_sampler

    slots = texture_slots(material)

    if slots is None:
        return [sampler_tuple(res.DEFAULT_SAMPLER)] * MAX_TEXTURES

    return [sampler_tuple(properties_to_sampler(slot)) for slot in slots]


def material_state(material, file_version):
    from ...operators.panels.material_render import state_from_properties, default_state

    properties = getattr(material, "level5_atr", None) if material is not None else None

    if properties is not None:
        atr_state = state_from_properties(properties)
    else:
        atr_state = default_state(file_version)

    atr_state["version"] = file_version

    return state.resolve(atr_state)


class MaterialRender:
    """Everything one draw of one material needs, built once and cached until Blender reports a change."""

    def __init__(self, engine_id, render_default, program, resolved_state, images, lighting, fade_input=None, samplers=None):
        self.engine_id = engine_id
        self.fade_input = fade_input
        self.samplers = samplers or []
        self.lighting = lighting
        self.render_default = render_default
        self.program = program
        self.state = resolved_state
        self.images = images
        self.program_key = (engine_id, render_default.name if render_default else None)
        self._palette = None
        self._palette_read = False

    def sampler(self, unit):
        return self.samplers[unit] if unit < len(self.samplers) else sampler_tuple(res.DEFAULT_SAMPLER)

    def uses_mip(self, unit):
        return bool(self.sampler(unit)[3]) and can_mip(self.images[unit])

    def texture(self, unit):
        """GPU texture of a texture unit, it needs the GPU so it is created on the first draw."""
        if self.uses_mip(unit):
            return mip_texture(self.images[unit])

        return image_texture(self.images[unit])

    def sampler_uniform(self, unit):
        """The values of unf_frg_smp_N: the last one is the size of the image when the texture holds its mip chain."""
        wrap_s, wrap_t, filters, _ = self.sampler(unit)
        size = self.images[unit].size

        return (wrap_s, wrap_t, filters, (size[0] | (size[1] << 16)) if self.uses_mip(unit) else 0)

    @property
    def palette(self):
        """Colors of the mask channels of the first texture, None for a program without mask stages."""
        if not self._palette_read:
            self._palette_read = True
            program = self.program
            masked = program is not None and (program.palette_channels or (program.base is not None and program.base.palette_channels))
            self._palette = palette_of(self.images[0]) if masked and self.images and self.images[0] is not None else None

        return self._palette

    @property
    def texture_units(self):
        if self.program is None:
            return ()
        return tuple(unit for unit in sorted(self.program.texture_units) if unit < len(self.images) and self.images[unit] is not None)

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
                               game_material.material_of(material, engine_id), fade_input_of(material), samplers_of(material))
        _bound[key] = bound

    # Only a few properties, read on every draw so a change of the sampler shows without rebuilding the material
    bound.samplers = samplers_of(material)

    return bound
