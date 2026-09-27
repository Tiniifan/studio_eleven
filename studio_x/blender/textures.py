"""Texture2D -> Blender image, plus the "adaptation" that bakes Unity multi-texture materials
into the single texture used by Studio Eleven materials.

Rules measured against the 3DS FireTornado textures (whs0001_ef1):
- Effect shaders take their opacity from the mask: alpha = _ColorTex.a * _MaskTex.r
  (Jump_01 + Jump_04 == whs0001_ef_16). Scrolling second masks and extra color layers are not baked.
- Threshold gradation shaders (_Use_ThresholdGradation) have no color texture: the mask is compared
  with the three _BorderMin/_BorderMax thresholds, which cut it into flames and pick their color in
  _GradationTex. There is no 3DS equivalent, so this is an approximation of the shader.
- Character shaders bake occlusion and specular masks into the color (cross_helper open_cross_texture.py).
"""

import bpy
import numpy as np

from ..unity.textures import decode_texture2d

# Main color texture property names, by priority
COLOR_PROPERTIES = ("_ColorTex", "_MainTex", "_BaseMap", "_BaseColorMap", "_ColorTex0", "_Texture2D")
MASK_PROPERTIES = ("_MaskTex", "_MaskTex0")
GRADATION_PROPERTY = "_GradationTex"
OCCLUSION_PROPERTIES = ("_OcclusionTex", "_OcclusionMap")
SPECULAR_MASK_PROPERTIES = ("_SpecularMaskTex",)

# Width of the mask threshold of the gradation shaders when both borders hold the same value
GRADATION_SOFTNESS = 0.05
SHADOW_THRESHOLD = 100.0 / 255.0
SHADOW_FACTOR = 0.7
SPECULAR_MIX = 0.2


class TextureCache:
    """Decode each Texture2D once per import and keep the RGBA arrays for merging."""

    def __init__(self, environment, report=None):
        self.environment = environment
        self.report = report
        self.arrays = {}
        self.images = {}

    def array(self, texture_info):
        key = (texture_info.sfile.name, texture_info.path_id)
        if key not in self.arrays:
            texture = texture_info.read()
            try:
                width, height, rgba = decode_texture2d(texture, self.environment)
            except (NotImplementedError, ImportError, FileNotFoundError) as error:
                if self.report:
                    self.report({"WARNING"}, "%s: %s" % (texture.get("m_Name"), error))
                self.arrays[key] = None
                return None
            # Rows stay bottom first, like Unity UVs and Blender image pixels
            pixels = np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4).astype(np.float32) / 255.0
            self.arrays[key] = (texture.get("m_Name", "texture"), pixels)
        return self.arrays[key]

    def image(self, name, pixels):
        """Create (or reuse) a packed Blender image from a float RGBA array."""
        image = self.images.get(name)
        if image is not None:
            return image
        height, width = pixels.shape[:2]
        image = bpy.data.images.new(name, width, height, alpha=True)
        image.pixels.foreach_set(np.ascontiguousarray(pixels, dtype=np.float32).ravel())
        try:
            image.pack()
        except RuntimeError:
            pass
        self.images[name] = image
        return image


def _floats(material):
    return dict(material["m_SavedProperties"]["m_Floats"])


def _tex_envs(material):
    return material["m_SavedProperties"]["m_TexEnvs"]


def find_texture(material, sfile, names):
    """Return (property, ObjectInfo, env) of the first assigned texture among `names`."""
    for name in names:
        for prop, env in _tex_envs(material):
            if prop == name and env["m_Texture"]["m_PathID"]:
                info = sfile.get_object(env["m_Texture"])
                if info is not None:
                    return prop, info, env
    return None, None, None


def is_gradation(material):
    return _floats(material).get("_Use_ThresholdGradation", 0.0) >= 0.5


def uv_texture_property(material):
    """Texture property whose _ST (tiling/offset) drives the UV_WARP of the baked texture."""
    assigned = [prop for prop, env in _tex_envs(material) if env["m_Texture"]["m_PathID"]]
    if is_gradation(material):
        mask = next((p for p in MASK_PROPERTIES if p in assigned), None)
        if mask:
            return mask
    color = next((p for p in COLOR_PROPERTIES if p in assigned), None)
    if color:
        return color
    names = [prop for prop, _ in _tex_envs(material)]
    return next((p for p in COLOR_PROPERTIES if p in names), None)


def uv_scroll_properties(material):
    """Texture properties whose _ST may drive the UV of the baked texture, the main one first.

    The effect shaders often keep their color texture and first mask still and scroll a second one
    instead (Ocean Birth's closing wave: _ColorTex0 and _MaskTex0 fixed, _MaskTex1 and _FlowTex
    animated). A 3DS mesh has a single UV set, so that second scroll is the only motion left to
    keep: animations.bake_renderers() takes the first of these the clips actually animate.
    """
    main = uv_texture_property(material)
    assigned = [prop for prop, env in _tex_envs(material) if env["m_Texture"]["m_PathID"]]
    return ([main] if main else []) + [prop for prop in assigned if prop != main]


def uv_texture(material, sfile):
    """The Texture2D sampled with the mesh UVs (its wrap/filter apply to the baked texture), or None."""
    prop = uv_texture_property(material)
    _, info, _ = find_texture(material, sfile, (prop,)) if prop else (None, None, None)
    return info.read() if info is not None else None


def _sample(pixels, u, v, wrap=True):
    """Bilinear sampling of an RGBA array at UV coordinates (arrays of the same shape)."""
    height, width = pixels.shape[:2]
    x = u * width - 0.5
    y = v * height - 0.5
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    if wrap:
        x0, x1 = x0 % width, (x0 + 1) % width
        y0, y1 = y0 % height, (y0 + 1) % height
    else:
        x1 = np.clip(x0 + 1, 0, width - 1)
        y1 = np.clip(y0 + 1, 0, height - 1)
        x0 = np.clip(x0, 0, width - 1)
        y0 = np.clip(y0, 0, height - 1)
    top = pixels[y0, x0] * (1.0 - fx) + pixels[y0, x1] * fx
    bottom = pixels[y1, x0] * (1.0 - fx) + pixels[y1, x1] * fx
    return top * (1.0 - fy) + bottom * fy


def _st(env):
    scale = (env["m_Scale"]["x"] or 1e-6, env["m_Scale"]["y"] or 1e-6)
    return scale, (env["m_Offset"]["x"], env["m_Offset"]["y"])


def _resample_into(source, source_env, width, height, target_env):
    """Sample `source` on a width x height grid expressed in the UV space of `target_env`."""
    (tsx, tsy), (tox, toy) = _st(target_env)
    (ssx, ssy), (sox, soy) = _st(source_env)
    u = (np.arange(width, dtype=np.float32) + 0.5) / width
    v = (np.arange(height, dtype=np.float32) + 0.5) / height
    u, v = np.meshgrid(u, v)
    # Target texture UV -> mesh UV -> source texture UV
    mesh_u = (u - tox) / tsx
    mesh_v = (v - toy) / tsy
    return _sample(source, mesh_u * ssx + sox, mesh_v * ssy + soy)


def _gradation_bands(material, values):
    """How deep each texel is inside the three mask thresholds of the gradation shaders.

    _BorderMin0/_BorderMax0 .. _BorderMin2/_BorderMax2 are the three thresholds the shader compares the
    mask with: the first one decides what is drawn at all, the three together shape the flame from its
    edge to its core. Both borders of a pair can hold the same value, which is a hard cut.
    """
    floats = _floats(material)
    bands = []
    for index in range(3):
        low, high = sorted((floats.get("_BorderMin%d" % index, 0.0), floats.get("_BorderMax%d" % index, 1.0)))
        high = max(high, low + GRADATION_SOFTNESS)
        bands.append(np.clip((values - low) / (high - low), 0.0, 1.0))
    return bands


def _gradation_image(material, sfile, cache):
    _, mask_info, _ = find_texture(material, sfile, MASK_PROPERTIES)
    _, gradation_info, _ = find_texture(material, sfile, (GRADATION_PROPERTY,))
    mask = cache.array(mask_info) if mask_info else None
    gradation = cache.array(gradation_info) if gradation_info else None
    if mask is None or gradation is None:
        return None
    values = mask[1][:, :, 0]
    bands = _gradation_bands(material, values)
    # The gradation is read from its far end (the core of the flame) to its near end (the fading edge)
    coordinate = np.clip(1.0 - sum(bands) / len(bands), 0.0, 1.0)
    other = np.full_like(coordinate, 0.5)
    if _floats(material).get("_GradationX", 0.0) >= 0.5:
        colors = _sample(gradation[1], coordinate, other, wrap=False)
    else:
        colors = _sample(gradation[1], other, coordinate, wrap=False)
    # Only what passes the first threshold is drawn: without it the texture is a nearly opaque sheet
    # of pale gradation (mean alpha 0.68 against 0.34 for the ball aura of FireTornado)
    colors[:, :, 3] *= bands[0]
    # Two materials can share the same gradation and mask with different thresholds
    name = "%s_%s_%03d" % (gradation[0], mask[0], round(_floats(material).get("_BorderMin0", 0.0) * 100))
    return cache.image(name, np.clip(colors, 0.0, 1.0))


def build_main_image(material, sfile, cache, adapt):
    """Return the bpy image to use for a Unity material, or None."""
    if adapt and is_gradation(material):
        image = _gradation_image(material, sfile, cache)
        if image is not None:
            return image

    _, info, color_env = find_texture(material, sfile, COLOR_PROPERTIES)
    decoded = cache.array(info) if info else None
    if decoded is None:
        return None
    name, pixels = decoded
    if not adapt:
        return cache.image(name, pixels)

    height, width = pixels.shape[:2]
    result = pixels
    suffixes = []

    _, mask_info, mask_env = find_texture(material, sfile, MASK_PROPERTIES)
    mask = cache.array(mask_info) if mask_info else None
    if mask is not None and _floats(material).get("_MaskTexNum", 1.0) >= 1.0:
        result = result.copy()
        result[:, :, 3] *= _resample_into(mask[1], mask_env, width, height, color_env)[:, :, 0]
        suffixes.append(mask[0])

    _, occlusion_info, _ = find_texture(material, sfile, OCCLUSION_PROPERTIES)
    _, specular_info, _ = find_texture(material, sfile, SPECULAR_MASK_PROPERTIES)
    occlusion = cache.array(occlusion_info) if occlusion_info else None
    specular = cache.array(specular_info) if specular_info else None
    if occlusion or specular:
        result = result.copy()
        rgb = result[:, :, :3]
        if np.all(result[:, :, 3] == 0.0):
            result[:, :, 3] = 1.0
        if occlusion:
            shadow = _resample_into(occlusion[1], color_env, width, height, color_env)[:, :, 0] < SHADOW_THRESHOLD
            rgb[shadow] *= SHADOW_FACTOR
        if specular:
            mix = _resample_into(specular[1], color_env, width, height, color_env)[:, :, :1] * SPECULAR_MIX
            rgb[:] = rgb * (1.0 - mix) + mix
        suffixes.append("merged")

    if not suffixes:
        return cache.image(name, pixels)
    return cache.image("_".join([name] + suffixes), np.clip(result, 0.0, 1.0))
