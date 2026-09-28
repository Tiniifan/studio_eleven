"""Masked effect shaders on the 3DS: a colour texture seen through a mask that scrolls on its own.

Soccer/Effect/Basic with one mask (the "Effect_T1M1*" materials): alpha = _ColorTex.a x _MaskTex.r,
rgb = _ColorTex, times the vertex colour (fragment program of Basic, data/unity_shaders.zip). The
colour and the mask have their own UV channel, _ST, rotation (_R) and scroll. That is exactly the IE4
render default #FIX_IMG_T1M1 below: slot 0 = the colour texture, slot 1 = the mask (red copied to the
green the combiner reads), each on its own texproj. Baked into one texture the mask stopped moving
over the colour and the thin white lines of Ocean Birth's rising tube became pale smears. Not kept: the
view dependent rim (_Use_Rim) of the T1M1Rim variants. The T1M1Flow variants are left to the bake (see
shader_kind).

Threshold shaders (Soccer/Effect/T3ThresholdF, Soccer/Effect/Threshold with three colours):

The Unity shader (read in data/unity_shaders.zip):
    m1 = mask 1 (foam, grey 0.5..1), k = _SecondColor.rgb x _ColorBorderMax2 x mask 0 alpha (shape)
    alpha = sat((m1 - (1 - k)) / (1 - _ColorBorderMin2))
    colour = lerp(C2, lerp(C1, C0, s0), s1), s0 / s1 the same test against 2 - _ColorBorderMax0 / 1
Every texture has its UV channel and its own _ST, and the clips scroll the masks and the colour apart.
Baking the whole into one texture (the prototypes of session 7) sampled the colour texture in the space
of a mask tile: moire stripes and a pale water, and the colour stopped flowing.

The game has what it needs: the render default #FIX_IMG_T1M1 (IE4, used by Level-5 in whs0087, whs0084,
whs0121, whs0025) gives rgb = TEXTURE0 and alpha = TEXTURE0.a x TEXTURE1.G, and each texture unit has
its own UV set, texproj and UV animation (whs0087 scrolls its *_t1m1_texproj1 apart). So:
    body: slot 0 = the colour texture (C0) on its channel with its tiling and scroll,
          slot 1 = the alpha of the thresholds, baked over one tile of the mask that scrolls the most,
                   on that mask's channel with its scroll;
    foam: a copy of the mesh (#FIX_IMG) drawn over the body where the thresholds give the border colours
          C1 / C2, on the mask UVs, with their mean colour: white foam in Ocean Birth (ev..._01), the orange
          and red bands around the yellow core of Flame Dance (flat 16x16 textures). Seeing only C0, Flame
          Dance's aura was a pale yellow ball. No copy when the thresholds never reach C1 / C2.
The other mask cannot scroll too: when it is the shape (mask 0), its value at each vertex goes into the
tint alpha; when the shape is the one that scrolls, the foam mask is taken at its mean.
_ColorBorderMax2 (the appearance / dissolve of the layer) scales the animated transparency. Not kept:
_FlowTex distortion, the edge mask (view dependent), soft particles, the colour offsets of Threshold's
bands (_ColorBorderX/Y).

A mesh without the UV channel a mask reads (Ocean Birth's rising tube, _250_Base6 and three others: only
UV0, the masks on channel 1) is shaded as if that channel were UV0: the exact shader rendered that way
forms the tube little by little like the mobile game, from thin streaks to the full body. The shape mask _17 clamps in V (m_WrapV): past its edge it stays opaque, before
it the shape shows, so the baked mask keeps the wrap of its texture. Reading (0, 0) instead gave the whole
tube at once, and ignoring the clamp cut it into strips.

UVs: every texproj holds the rest transform of its texture, R(_R) . (uv - offset) / tiling like the
shaders, and only the scroll from there is keyed (the convention of animations._bake_uv).
"""

import math

import bpy
import numpy as np

from . import flipbook, materials, render_state
from .textures import find_texture

SHADER_T3THRESHOLDF = 2057163477493348147
SHADER_THRESHOLD = 893760763001934368
SHADER_BASIC = 1994188762195017600

# Material property names of each shader: colours (C0, C1, C2), threshold mask (scrolls), shape mask
KINDS = {
    "t3f": {"colours": ("_ColorTex0", "_ColorTex1", "_ColorTex2"), "foam_mask": "_MaskTex1",
            "shape_mask": "_MaskTex0", "shape_component": 3},
    "threshold": {"colours": ("_ColorTex", "_SecondColorTex", "_ThirdColorTex"), "foam_mask": "_SecondMaskTex",
                  "shape_mask": "_MaskTex", "shape_component": 0},
    # Threshold with _Use_ThresholdGradation: same masks and thresholds, the colour read in _GradationTex
    "grd": {"colours": (), "foam_mask": "_SecondMaskTex", "shape_mask": "_MaskTex", "shape_component": 0},
}
# UV channel property of each texture (T3ThresholdF numbers its colour channels differently)
CHANNEL_PROPERTIES = {"_ColorTex0": "_ColorTex0Index", "_ColorTex1": "_Color1TexIndex", "_ColorTex2": "_Color2TexIndex"}

BODY_RENDER_DEFAULT = "#FIX_IMG_T1M1"
FOAM_RENDER_DEFAULT = "#FIX_IMG"
MASK_SIZE_RANGE = (32, 128)


def shader_kind(material):
    """'t1m1' (Basic, one colour and one mask), 't3f', 'threshold' (three colours, two masks) or None."""
    if material is None:
        return None
    path_id = material["m_Shader"]["m_PathID"]
    floats = dict(material["m_SavedProperties"]["m_Floats"])
    if path_id == SHADER_T3THRESHOLDF:
        return "t3f"
    if path_id == SHADER_THRESHOLD and floats.get("_ColorTexNum") == 3 and floats.get("_MaskTexNum") == 2:
        return "threshold"
    if (path_id == SHADER_THRESHOLD and floats.get("_Use_ThresholdGradation", 0.0) >= 0.5
            and floats.get("_MaskTexNum") == 2):
        assigned = {name for name, env in material["m_SavedProperties"]["m_TexEnvs"] if env["m_Texture"]["m_PathID"]}
        if {"_GradationTex", "_MaskTex", "_SecondMaskTex"} <= assigned:
            return "grd"
    # The Flow variants (Ocean Birth's final beams) keep the colour x mask bake: without their _FlowTex
    # distortion the two textures on their own units drew long smooth streaks instead of ragged foam
    if (path_id == SHADER_BASIC and floats.get("_ColorTexNum") == 1 and floats.get("_MaskTexNum") == 1
            and not floats.get("_FlowTexNum", 0)):
        assigned = {name for name, env in material["m_SavedProperties"]["m_TexEnvs"] if env["m_Texture"]["m_PathID"]}
        if {"_ColorTex", "_MaskTex"} <= assigned:
            return "t1m1"
    return None


class Values:
    """Material values at one frame: floats, _ST (tiling u, v, offset u, v) and colours."""

    def __init__(self, material, properties, time):
        saved = material["m_SavedProperties"]
        self.floats = dict(saved["m_Floats"])
        self.st = {name: [env["m_Scale"]["x"], env["m_Scale"]["y"], env["m_Offset"]["x"], env["m_Offset"]["y"]]
                   for name, env in saved["m_TexEnvs"]}
        self.colors = {name: [c["r"], c["g"], c["b"], c["a"]] for name, c in saved["m_Colors"]}
        for (name, component), binding in properties.items():
            value = binding.curves[0].evaluate(time)
            if name.endswith("_ST") and component:
                self.st.setdefault(name[:-3], [1.0, 1.0, 0.0, 0.0])["xyzw".index(component)] = value
            elif component and component in "rgba":
                self.colors.setdefault(name, [1.0, 1.0, 1.0, 1.0])["rgba".index(component)] = value
            elif component is None:
                self.floats[name] = value

    def tiling(self, prop):
        return np.array([_safe(v) for v in self.st.get(prop, [1.0, 1.0, 0.0, 0.0])[:2]])

    def offset(self, prop):
        return np.array(self.st.get(prop, [1.0, 1.0, 0.0, 0.0])[2:], dtype=np.float64)

    def threshold(self, kind):
        return self.floats.get("_ColorBorderMax2" if kind == "t3f" else "_BorderMax2", 1.0)


def _rotation(values, prop):
    """The shaders turn the UVs by _<tex>_R degrees: (c u + s v, -s u + c v) (vertex programs)."""
    angle = math.radians(values.floats.get(prop + "_R", 0.0))
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, s], [-s, c]])


def _texproj_uv(uv, values, prop):
    """UVs of a texproj at rest: R . (uv - offset) / tiling."""
    return ((uv - values.offset(prop)) @ _rotation(values, prop).T) / values.tiling(prop)


def _texproj_scroll(series, rest, prop):
    """UVMove keys that bring the rest UVs to each frame's offset (tiling and rotation at rest)."""
    rotation, tiling, rest_offset = _rotation(rest, prop), rest.tiling(prop), rest.offset(prop)
    moves = []
    for values in series:
        shift = (rotation @ (values.offset(prop) - rest_offset)) / tiling
        moves.append((shift[0], -shift[1]))
    return moves


def _reference_tiling(series, rest, prop, visible_threshold=0.05, degenerate=0.05):
    """Values like rest, with the tiling a texproj is laid out on.

    The material's own tiling can be 0 when the clips animate it (Flame Dance's fire stream: _ColorTex_ST.x
    0 at rest, 0.46 -> 1.41 while the stream grows on a clamped texture). Laid out on it (clamped to 1e-4)
    the UVs reached 10000 and only ever read the transparent edge of the texture: the stream never showed.
    The reference is the median tiling while the layer is visible, ignoring near 0 values; the rest of the
    motion is keyed as UVScale = tiling / reference (_key_scale).
    """
    shown = [v for v in series if 1.0 - v.floats.get("_Transparency", 0.0) > visible_threshold] or series
    base = list(rest.st.get(prop, [1.0, 1.0, 0.0, 0.0]))
    tiling = []
    for axis in range(2):
        values = np.array([v.st.get(prop, base)[axis] for v in shown])
        values = values[np.abs(values) >= degenerate]
        if len(values):
            tiling.append(float(np.median(values)))
        else:
            tiling.append(base[axis] if abs(base[axis]) >= degenerate else 1.0)
    reference = Values.__new__(Values)
    reference.floats, reference.colors = rest.floats, rest.colors
    reference.st = dict(rest.st)
    reference.st[prop] = tiling + base[2:]
    return reference


def _key_scale(action, name, frames, series, reference, prop, write_curve):
    """UVScale keys (tiling / reference tiling) when the clips animate the tiling of a texproj."""
    ref = reference.tiling(prop)
    scales = np.array([[_safe(s) for s in v.st.get(prop, [1.0, 1.0])[:2]] for v in series]) / ref
    scales = np.sign(scales) * np.maximum(np.abs(scales), 1e-3)
    base = 'modifiers["%s"].scale' % name
    for index in range(2):
        curve = action.fcurves.find(base, index=index)
        if curve is not None:
            action.fcurves.remove(curve)
    # The 3DS files hold no UVScale track when the tiling never changes
    if np.abs(scales - 1.0).max() > 1e-4:
        write_curve(action, base, 0, frames, list(scales[:, 0]), 1e-5)
        write_curve(action, base, 1, frames, list(scales[:, 1]), 1e-5)


def _safe(value):
    return float(np.copysign(max(abs(value), 1e-4), value))


def _saturate(x):
    return np.clip(x, 0.0, 1.0)


def _width(values, name):
    # The shaders divide by clamp(1 - _ColorBorderMin, 0.01, 1)
    return min(max(1.0 - values.floats.get(name, 0.0), 0.01), 1.0)


def _resample(pixels, size):
    """One repeat of a texture at another size (bilinear, wrapped); pixels bottom first."""
    height, width = pixels.shape[:2]
    u = (np.arange(size[0]) + 0.5) / size[0] * width - 0.5
    v = (np.arange(size[1]) + 0.5) / size[1] * height - 0.5
    x0, y0 = np.floor(u).astype(int), np.floor(v).astype(int)
    fx, fy = (u - x0)[None, :, None], (v - y0)[:, None, None]
    x0, x1 = x0 % width, (x0 + 1) % width
    y0, y1 = y0 % height, (y0 + 1) % height
    top = pixels[y0][:, x0] * (1 - fx) + pixels[y0][:, x1] * fx
    bottom = pixels[y1][:, x0] * (1 - fx) + pixels[y1][:, x1] * fx
    return top * (1 - fy) + bottom * fy


def _thresholds(kind, values, m1, kterm):
    """(s0, s1, alpha) of the shader for foam mask values m1 and threshold offsets k x shape."""
    if kind == "t3f":
        names = ("_ColorBorderMax0", "_ColorBorderMax1", "_ColorBorderMin0", "_ColorBorderMin1", "_ColorBorderMin2")
    else:
        names = ("_BorderMax0", "_BorderMax1", "_BorderMin0", "_BorderMin1", "_BorderMin2")
    max0, max1, min0, min1, min2 = names
    s0 = _saturate((m1 - (2.0 - values.floats.get(max0, 1.0) - kterm)) / _width(values, min0))
    s1 = _saturate((m1 - (2.0 - values.floats.get(max1, 1.0) - kterm)) / _width(values, min1))
    alpha = _saturate((m1 - (1.0 - kterm)) / _width(values, min2))
    return s0, s1, alpha


def _band_colour(pixels):
    """Mean colour of a border colour texture (C1 / C2): white foam in Ocean Birth, the orange and red
    bands around the yellow core of Flame Dance's fire. An unassigned texture is white."""
    return np.ones(3) if pixels is None else pixels[..., :3].reshape(-1, 3).mean(0)


def _texel_index(coordinate, size, wrap):
    """Texel of a coordinate along one axis for the sampler wrap (Blender enum names)."""
    if wrap == "EXTEND":
        return np.clip(coordinate, 0, size - 1)
    if wrap == "MIRROR":
        period = coordinate % (2 * size)
        return np.where(period < size, period, 2 * size - 1 - period)
    return coordinate % size


def _vertex_values(pixels, uv, component, wrap=("REPEAT", "REPEAT")):
    """A texture component at UV points (already transformed), bilinear, with the wrap of each axis:
    a clamped axis keeps the edge texel however far the scroll goes (Ocean Birth's tube shape mask)."""
    height, width = pixels.shape[:2]
    x = uv[:, 0] * width - 0.5
    y = uv[:, 1] * height - 0.5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    x0m, x1m = _texel_index(x0, width, wrap[0]), _texel_index(x0 + 1, width, wrap[0])
    y0m, y1m = _texel_index(y0, height, wrap[1]), _texel_index(y0 + 1, height, wrap[1])
    channel = pixels[..., component]
    return (channel[y0m, x0m] * (1 - fx) * (1 - fy) + channel[y0m, x1m] * fx * (1 - fy)
            + channel[y1m, x0m] * (1 - fx) * fy + channel[y1m, x1m] * fx * fy)


def _vertex_shape(pixels, uv, triangles, component, wrap=("REPEAT", "REPEAT")):
    """Shape mask per vertex, averaged over the triangles around it: sparse meshes put their vertices on
    the transparent border of the shape while the inside of their triangles is opaque."""
    if not len(triangles):
        return _vertex_values(pixels, uv, component, wrap)
    weights = np.array([[1, 1, 1], [4, 1, 1], [1, 4, 1], [1, 1, 4], [1, 1, 0], [0, 1, 1], [1, 0, 1]], float)
    weights /= weights.sum(1, keepdims=True)
    points = np.einsum("sk,nkd->nsd", weights, uv[triangles]).reshape(-1, 2)
    per_triangle = _vertex_values(pixels, points, component, wrap).reshape(len(triangles), -1).mean(1)
    total = np.zeros(len(uv))
    count = np.zeros(len(uv))
    for corner in range(3):
        np.add.at(total, triangles[:, corner], per_triangle)
        np.add.at(count, triangles[:, corner], 1)
    return np.where(count > 0, total / np.maximum(count, 1), _vertex_values(pixels, uv, component, wrap))


def _set_loop_uvs(obj, name, per_vertex):
    if name not in obj.data.uv_layers:
        obj.data.uv_layers.new(name=name)
    loops = np.zeros(len(obj.data.loops), dtype=np.int64)
    obj.data.loops.foreach_get("vertex_index", loops)
    obj.data.uv_layers[name].data.foreach_set("uv", per_vertex[loops].astype(np.float32).ravel())


def _uv_warp(obj, name):
    warp = obj.modifiers.get(name) or obj.modifiers.new(name=name, type="UV_WARP")
    warp.uv_layer = name
    warp.center = (0.0, 0.0)
    warp.offset, warp.scale = (0.0, 0.0), (1.0, 1.0)
    return warp


def _rename_texproj(obj, old, new):
    if old == new or old not in obj.data.uv_layers:
        return
    obj.data.uv_layers[old].name = new
    warp = obj.modifiers.get(old)
    if warp is not None:
        warp.name = new
        warp.uv_layer = new


def _key_scroll(action, name, frames, offsets, write_curve):
    """UVMove keys of a texproj, in the convention of animations._bake_uv: the game computes
    (u - move.x, v + move.y) on UVs that already hold the rest tiling and offset."""
    base = 'modifiers["%s"].' % name
    for path in ("offset", "scale"):
        for index in range(2):
            curve = action.fcurves.find(base + path, index=index)
            if curve is not None:
                action.fcurves.remove(curve)
    offsets = np.array(offsets)
    write_curve(action, base + "offset", 0, frames, list(offsets[:, 0]), 1e-5)
    write_curve(action, base + "offset", 1, frames, list(offsets[:, 1]), 1e-5)


def _set_slots(material, textures):
    """Texture slots of a material, in texture unit order: [(image, wrap, pixel format)]."""
    from studio_eleven.operators.panels import material_textures

    material_textures.suspend_updates()
    try:
        slots = material.level5_textures.slots
        material.level5_textures.initialized = True
        while len(slots) > len(textures):
            slots.remove(len(slots) - 1)
        while len(slots) < len(textures):
            slots.add()
        for slot, (image, wrap, pixel_format) in zip(slots, textures):
            slot.image = image
            slot.wrap_x, slot.wrap_y = (wrap, wrap) if isinstance(wrap, str) else wrap
            slot.pixel_format = pixel_format
            slot.show_expanded = False
    finally:
        material_textures.resume_updates()
    material_textures.apply_material_textures(material)


def _owned_material(record, slot=0):
    """The renderer's own copy of its material: the mask it gets is baked for this renderer only."""
    material = record.blender_materials[slot]
    if slot not in record.owned_slots and material.users > 1:
        material = material.copy()
        record.object.data.materials[slot] = material
        record.blender_materials[slot] = material
    record.owned_slots.add(slot)
    return material


def convert(model, record, per_clip, sampler, action, material_actions, write_curve):
    """Convert one threshold renderer; return the (id_data, action) of the foam copy it adds.

    per_clip: {id(clip): (visibility, properties)} of animations._renderer_bindings; action: the armature
    action (UV curves); material_actions: the (material, action) the transparency bake made for it.
    """
    unity_material = next((m for _, m in record.unity_materials if m), None)
    kind = shader_kind(unity_material)
    cache = model.cache
    # The mesh plays the armature action, which holds its UV curves (like animations._bake_uv)
    if record.object.animation_data is None:
        record.object.animation_data_create()
    record.object.animation_data.action = action
    sfile = next(info for info, m in record.unity_materials if m).sfile
    uvs = {channel: np.array(values, dtype=np.float64) for channel, values in record.unity_mesh.uvs.items()}
    triangles = np.array([t for sub in record.unity_mesh.submeshes for t in sub], dtype=np.int64).reshape(-1, 3)

    def texture(prop):
        _, info, _ = find_texture(unity_material, sfile, (prop,))
        decoded = cache.array(info) if info is not None else None
        if decoded is None:
            return None, None, ("REPEAT", "REPEAT")
        settings = info.read().get("m_TextureSettings", {})
        modes = {0: "REPEAT", 1: "EXTEND", 2: "MIRROR"}
        wrap = (modes.get(settings.get("m_WrapU", 0), "REPEAT"), modes.get(settings.get("m_WrapV", 0), "REPEAT"))
        return decoded[0], decoded[1], wrap

    def channel(values, prop):
        index = int(values.floats.get(CHANNEL_PROPERTIES.get(prop, prop + "Index"), 0))
        # A channel the mesh does not have is shaded like the first one (see the module docstring)
        return uvs[index] if index in uvs else uvs[min(uvs)]

    series = [Values(unity_material, per_clip[id(clip)][1], time + 1e-5) for clip, time in sampler.samples]
    rest = Values(unity_material, {}, 0.0)
    if kind == "t1m1":
        _convert_t1m1(record, action, sampler.frames, write_curve, cache, texture, channel, series, rest, unity_material)
        return []
    spec = KINDS[kind]
    visibility = np.array([(1.0 - v.floats.get("_Transparency", 0.0)) * v.threshold(kind) for v in series])
    if visibility.max() <= 0:
        return []
    key = "%s_%s" % (unity_material.get("m_Name", "threshold"), record.node.name)
    if kind == "t3f" and flipbook.has_flat_colours([texture(prop)[1] for prop in KINDS[kind]["colours"]]):
        # Flat colours: the whole look is in the masks, baked exactly frame by frame (flipbook.py)
        if flipbook.convert(record, _owned_material(record), unity_material, action, sampler.frames, series,
                            visibility, texture, uvs, cache, key, write_curve):
            return []
    peak = series[int(np.argmax(visibility))]
    k_peak = max(peak.threshold(kind), 1e-3)
    factors = [min(max(v.threshold(kind) / k_peak, 0.0), 1.0) for v in series]
    second = np.array(peak.colors.get("_SecondColor", [1.0, 1.0, 1.0, 1.0])[:3]) if kind == "t3f" else np.ones(3)

    # --- the mask whose scroll is kept: the one that travels the most while the layer is visible
    shown = [v for v, vis in zip(series, visibility) if vis > 0] or [peak]

    def travel(prop):
        offsets = np.array([v.offset(prop) for v in shown])
        return float(((offsets.max(0) - offsets.min(0)) / np.abs(rest.tiling(prop))).max())

    foam_name, foam_pixels, foam_wrap = texture(spec["foam_mask"])
    shape_name, shape_pixels, shape_wrap = texture(spec["shape_mask"])
    shape_driven = shape_pixels is not None and (foam_pixels is None or travel(spec["shape_mask"]) > travel(spec["foam_mask"]))
    driver = spec["shape_mask"] if shape_driven else spec["foam_mask"]
    driver_pixels = shape_pixels if shape_driven else foam_pixels
    # The baked tile covers one repeat of the mask: its sampler keeps the mask's wrap (a clamped edge)
    driver_wrap = shape_wrap if shape_driven else foam_wrap
    size = tuple(int(min(max(n, MASK_SIZE_RANGE[0]), MASK_SIZE_RANGE[1])) for n in driver_pixels.shape[1::-1])
    tile = _resample(driver_pixels, size)
    shape_uv = (channel(peak, spec["shape_mask"]) - peak.offset(spec["shape_mask"])) / peak.tiling(spec["shape_mask"])
    vertex_k = None
    if shape_driven:
        # The shape scrolls: it is the baked mask, the foam mask is taken at its mean
        m1 = float(foam_pixels[..., 0].mean()) if foam_pixels is not None else 1.0
        kterm = k_peak * second.mean() * tile[..., spec["shape_component"]]
    else:
        m1 = tile[..., 0]
        # The shape stays still on the mesh: its value at each vertex goes into the tint alpha, the mask
        # is baked for a reference threshold offset
        vertex_k = k_peak * second.mean() * (_vertex_shape(shape_pixels, shape_uv, triangles, spec["shape_component"], shape_wrap)
                                               if shape_pixels is not None else np.ones(len(shape_uv)))
        shown_k = vertex_k[vertex_k > 0.05]
        kterm = float(np.percentile(shown_k, 75)) if len(shown_k) else k_peak
    s0, s1, alpha = _thresholds(kind, peak, m1, kterm)
    shape = size[::-1]
    alpha = np.broadcast_to(alpha, shape)
    if kind == "grd":
        _convert_gradation(record, action, sampler.frames, write_curve, cache, texture, channel, series, rest, driver,
                           driver_wrap, np.broadcast_to(s0, shape), np.broadcast_to(s1, shape), alpha, key, peak)
        if vertex_k is not None:
            _scale_tint_alpha(record.object, _saturate(vertex_k / max(kterm, 1e-3)))
        _scale_transparency(record.blender_materials[0], material_actions, sampler.frames, factors, write_curve)
        return []
    colour_textures = [texture(prop) for prop in spec["colours"]]
    # Weights of the three colours: C2 outside s1, C1 between the thresholds, C0 (the body) inside s0
    weight2 = np.broadcast_to(1 - s1, shape)
    weight1 = np.broadcast_to(s1 * (1 - s0), shape)
    band_weight = weight1 + weight2
    colour1, colour2 = _band_colour(colour_textures[1][1]), _band_colour(colour_textures[2][1])
    band_rgb = (weight1[..., None] * colour1 + weight2[..., None] * colour2) / np.maximum(band_weight, 1e-6)[..., None]
    # Texels without border colour keep C1: filtered next to a band they must not darken it
    band_rgb = np.where(band_weight[..., None] > 1e-6, band_rgb, colour1)
    band_alpha = _saturate(alpha * band_weight)
    ones = np.ones(shape)
    mask_image = cache.image("mask_" + key, np.stack([alpha, alpha, alpha, ones], -1))

    # --- body: colour texture on texproj0, threshold mask on texproj1
    obj = record.object
    material = _owned_material(record)
    colour_uv_name = material.name + "_texproj0"
    mask_uv_name = material.name + "_texproj1"
    for curve in [c for c in action.fcurves if '"%s"' % record.uv_layer in c.data_path]:
        action.fcurves.remove(curve)
    _rename_texproj(obj, record.uv_layer, colour_uv_name)
    record.uv_layer = colour_uv_name

    colour_prop = spec["colours"][0]
    _set_loop_uvs(obj, colour_uv_name, _texproj_uv(channel(rest, colour_prop), rest, colour_prop))
    _uv_warp(obj, colour_uv_name)
    mask_uv = _texproj_uv(channel(rest, driver), rest, driver)
    _set_loop_uvs(obj, mask_uv_name, mask_uv)
    _uv_warp(obj, mask_uv_name)
    colour_scroll = _texproj_scroll(series, rest, colour_prop)
    mask_scroll = _texproj_scroll(series, rest, driver)
    _key_scroll(action, colour_uv_name, sampler.frames, colour_scroll, write_curve)
    _key_scroll(action, mask_uv_name, sampler.frames, mask_scroll, write_curve)
    if vertex_k is not None:
        _scale_tint_alpha(obj, _saturate(vertex_k / max(kterm, 1e-3)))

    colour_name, colour_pixels, colour_wrap = colour_textures[0]
    opaque = colour_pixels is None or float(colour_pixels[..., 3].min()) > 0.99
    colour_image = cache.image(colour_name, colour_pixels) if colour_pixels is not None else None
    _set_slots(material, [(colour_image, colour_wrap, "ETC1" if opaque else "RGBA4"), (mask_image, driver_wrap, "L8")])
    obj.data.level5_properties.render_default = BODY_RENDER_DEFAULT
    body_action = _scale_transparency(material, material_actions, sampler.frames, factors, write_curve)
    record.mask_converted = True
    if band_alpha.max() < 0.5 / 255.0:
        # The thresholds never reach the border colours: a foam copy would draw nothing
        return []

    # --- foam: a copy of the mesh drawn with the border colours (C1 / C2)
    white = bool(band_rgb[band_alpha > 0].min() > 0.99) if (band_alpha > 0).any() else True
    foam_image = cache.image("foam_" + key, np.dstack([np.clip(band_rgb, 0.0, 1.0), band_alpha]))
    foam_obj = obj.copy()
    foam_obj.data = obj.data.copy()
    foam_obj.name = obj.name + "_foam"
    for collection in obj.users_collection:
        collection.objects.link(foam_obj)
    foam_material = material.copy()
    foam_material.name = material.name + "_foam"
    foam_obj.data.materials[0] = foam_material
    for modifier in [m for m in foam_obj.modifiers if m.type == "UV_WARP"]:
        foam_obj.modifiers.remove(modifier)
    for name in [layer.name for layer in foam_obj.data.uv_layers]:
        foam_obj.data.uv_layers.remove(foam_obj.data.uv_layers[name])
    foam_uv_name = foam_material.name + "_texproj0"
    _set_loop_uvs(foam_obj, foam_uv_name, mask_uv)
    _uv_warp(foam_obj, foam_uv_name)
    foam_obj.animation_data_create()
    foam_obj.animation_data.action = action
    _key_scroll(action, foam_uv_name, sampler.frames, mask_scroll, write_curve)
    record.foam = foam_obj
    # White foam only needs its alpha (A8 reads as white)
    _set_slots(foam_material, [(foam_image, driver_wrap, "A8" if white else "RGBA8")])
    foam_obj.data.level5_properties.render_default = FOAM_RENDER_DEFAULT
    created = []
    if body_action is not None:
        foam_action = body_action.copy()
        foam_action.name = "%s.%s" % (body_action.name.split(".")[0], foam_material.name)
        foam_material.animation_data_create()
        foam_material.animation_data.action = foam_action
        created.append((foam_material, foam_action))
    return created


def _convert_t1m1(record, action, frames, write_curve, cache, texture, channel, series, rest, unity_material):
    """Basic with one mask: the colour texture and the mask on two texture units, each with its own UVs.

    The colour texture carries the (1 + _Luminance) of the shader (render_state.luminance_colour) and, for
    _SrcBlend SrcColor, the remapped alpha of render_state.src_colour_alpha. Each texproj is laid out on
    its reference tiling and keys UVScale when the clips animate the tiling (see _reference_tiling).
    """
    obj = record.object
    material = _owned_material(record)
    colour_uv_name = material.name + "_texproj0"
    mask_uv_name = material.name + "_texproj1"
    for curve in [c for c in action.fcurves if '"%s"' % record.uv_layer in c.data_path]:
        action.fcurves.remove(curve)
    _rename_texproj(obj, record.uv_layer, colour_uv_name)
    record.uv_layer = colour_uv_name
    for uv_name, prop in ((colour_uv_name, "_ColorTex"), (mask_uv_name, "_MaskTex")):
        reference = _reference_tiling(series, rest, prop)
        _set_loop_uvs(obj, uv_name, _texproj_uv(channel(rest, prop), reference, prop))
        _uv_warp(obj, uv_name)
        _key_scroll(action, uv_name, frames, _texproj_scroll(series, reference, prop), write_curve)
        _key_scale(action, uv_name, frames, series, reference, prop, write_curve)

    colour_name, colour_pixels, colour_wrap = texture("_ColorTex")
    mask_name, mask_pixels, mask_wrap = texture("_MaskTex")
    opaque = float(colour_pixels[..., 3].min()) > 0.99
    luminance = dict(unity_material["m_SavedProperties"]["m_Floats"]).get("_Luminance", 0.0)
    if luminance:
        colour_name = "%s_L%03d" % (colour_name, round(luminance * 100))
        colour_pixels = render_state.luminance_colour(unity_material, colour_pixels)
    if render_state.uses_src_colour(unity_material):
        colour_name, colour_pixels = colour_name + "_srccolour", render_state.src_colour_alpha(colour_pixels)
        opaque = False
    red = mask_pixels[..., 0]
    grey = np.stack([red, red, red, np.ones_like(red)], -1)
    _set_slots(material, [(cache.image(colour_name, colour_pixels), colour_wrap, "ETC1" if opaque else "RGBA4"),
                          (cache.image("mask_" + mask_name, grey), mask_wrap, "L8")])
    obj.data.level5_properties.render_default = BODY_RENDER_DEFAULT
    record.mask_converted = True


def _convert_gradation(record, action, frames, write_curve, cache, texture, channel, series, rest, driver, driver_wrap,
                       s0, s1, alpha, key, peak):
    """Threshold with a gradation: one texture baked over a tile of the mask that scrolls (#FIX_IMG).

    Fragment program of Soccer/Effect/Threshold with _Use_ThresholdGradation: the gradation is read at
    t1 x (0.5 + 0.5 t0) (edge 0, core 1), its alpha multiplies the threshold alpha. The former bake
    thresholded _MaskTex alone, a nearly flat texture in Flame Dance (the shape is in _SecondMaskTex):
    the rising fire wave became a flat orange sheet.
    """
    from .textures import _sample

    obj = record.object
    material = _owned_material(record)
    uv_name = material.name + "_texproj0"
    for curve in [c for c in action.fcurves if '"%s"' % record.uv_layer in c.data_path]:
        action.fcurves.remove(curve)
    _rename_texproj(obj, record.uv_layer, uv_name)
    record.uv_layer = uv_name
    _set_loop_uvs(obj, uv_name, _texproj_uv(channel(rest, driver), rest, driver))
    _uv_warp(obj, uv_name)
    _key_scroll(action, uv_name, frames, _texproj_scroll(series, rest, driver), write_curve)

    _, gradation, _ = texture("_GradationTex")
    coordinate = s1 * (0.5 + 0.5 * s0)
    middle = np.full_like(coordinate, 0.5)
    if peak.floats.get("_GradationX", 0.0) >= 0.5:
        colours = _sample(gradation, coordinate, middle, wrap=False)
    else:
        colours = _sample(gradation, middle, coordinate, wrap=False)
    pixels = np.dstack([colours[..., :3], alpha * colours[..., 3]])
    _set_slots(material, [(cache.image("grd_" + key, np.clip(pixels, 0.0, 1.0)), driver_wrap, "RGBA8")])
    obj.data.level5_properties.render_default = FOAM_RENDER_DEFAULT
    record.mask_converted = True


def _transparency_values(material, material_actions, frames):
    """The keyed transparency of a material at every frame, or its static 1 - _Transparency."""
    action = next((a for m, a in material_actions if m == material), None)
    curve = action.fcurves.find(materials.alpha_data_path(material)) if action else None
    if curve is not None:
        return [curve.evaluate(frame) for frame in frames]
    multiplier = material.node_tree.nodes.get(materials.ALPHA_MULTIPLIER)
    return [multiplier.inputs[1].default_value if multiplier is not None else 1.0] * len(frames)


def _key_transparency(material, material_actions, frames, values, write_curve):
    """Key the transparency of a material with these values (the static one is then in the keys)."""
    action = next((a for m, a in material_actions if m == material), None)
    path = materials.add_transparency_animation(material)
    if action is None:
        action = bpy.data.actions.new("%s.%s" % ("threshold", material.name))
        material.animation_data_create()
        material.animation_data.action = action
        material_actions.append((material, action))
    curve = action.fcurves.find(path)
    if curve is not None:
        action.fcurves.remove(curve)
    write_curve(action, path, 0, frames, values, 1e-3)
    return action


def _scale_tint_alpha(obj, per_vertex):
    colors = obj.data.vertex_colors.get("Tint")
    created = colors is None
    if created:
        colors = obj.data.vertex_colors.new(name="Tint")
    loops = np.zeros(len(obj.data.loops), dtype=np.int64)
    obj.data.loops.foreach_get("vertex_index", loops)
    data = np.zeros(len(colors.data) * 4, dtype=np.float32)
    colors.data.foreach_get("color", data)
    data = data.reshape(-1, 4)
    if created:
        data[:] = 1.0
    data[:, 3] *= per_vertex[loops]
    colors.data.foreach_set("color", data.ravel())


def _scale_transparency(material, material_actions, frames, factors, write_curve):
    """Multiply the animated transparency by the appearance of the thresholds (_ColorBorderMax2)."""
    if all(f >= 0.999 for f in factors) and not any(m == material for m, _ in material_actions):
        return None
    base = _transparency_values(material, material_actions, frames)
    return _key_transparency(material, material_actions, frames, [v * f for v, f in zip(base, factors)], write_curve)
