"""Soccer/Effect/T3ThresholdF layers with flat colours, baked frame by frame into a texture atlas.

The fire of Flame Dance (the aura around the player, the big fireball of the last cut) is drawn by
T3ThresholdF layers whose three colours are small swatches (16x16 yellow, 64x64 orange and red ramps): everything that
makes the fire, its many small tongues, comes from the masks. The cellular mask 0 and the scrolling
mask 1 are combined by thresholds per texel, both distorted by _FlowTex and mask 0 itself. The
body + foam conversion of mask_shaders.py keeps one mask per texel and the other per vertex, without
the distortion: the fireball became one blurry blob.

The IE4 combiners cannot evaluate thresholds, so the exact shader (fragment program of
data/unity_shaders.zip, see mask_shaders.py for the formula) is evaluated on the CPU at a few frames,
each result in one cell of an atlas, and a stepped UVMove shows the cell of the current frame: the
Level-5 flipbook technique of the 3DS fire effects (who0014_ef1 sparks: stepped UVMove keys over a 4x2
atlas). Layers with textured colours (Ocean Birth's caustics) keep the body + foam conversion: their
colour moves continuously, which a flipbook would turn into steps.

Per texel of a unique UV layout of the mesh, the shader inputs (every UV channel, the vertex alpha) are
interpolated from the triangle under the texel. The colour keeps the (1 + _Luminance) of the shader in
linear space; _Color and the vertex colour stay in the tint, _Transparency in the material animation.
With _VertexAlphaThresholdMode the vertex alpha feeds the threshold instead of the opacity: it is baked
and the tint alpha set to 1.
"""

import math

import bpy
import numpy as np

from . import render_state

CELL_SIZE = 64
GRID = 4
MAX_CELLS = GRID * GRID
# Border of a cell kept free, in cell units
CELL_MARGIN = 1.5 / CELL_SIZE
# smart_project island margins tried in turn until no island reads another one (see _bleed)
ISLAND_MARGINS = (0.03, 0.06, 0.1, 0.15, 0.2)
# Texels around a triangle baked from it: the bilinear filter reads up to one texel past an edge
RASTER_REACH = 1.5
# Share of the UV0 texels drawn by several triangles above which a new layout is made for the bake
OVERLAP_LIMIT = 0.1
# Share of the layout above which a single triangle is taken for one crossing a UV wrap seam
WRAP_SPAN = 0.5
FLAT_DEVIATION = 0.02
SWATCH_SIZE = 64
RENDER_DEFAULT = "#FIX_IMG"
# Texels the layout edges are extended by, within the 1.5 texel margin of a cell
DILATE_PASSES = 2
# Texture levels finer than the footprint of a cell texel that the bake still reads (see _sample_filtered)
LOD_MARGIN = 1.0


def has_flat_colours(colour_pixels):
    """True when no colour texture of the layer carries detail: unassigned, flat, or a tiny swatch
    (Flame Dance's 16x16 yellow / orange / red) whose look all comes from the masks."""
    return all(p is None or max(p.shape[:2]) <= SWATCH_SIZE or float(p[..., :4].std(axis=(0, 1)).max()) < FLAT_DEVIATION
               for p in colour_pixels)


def _texel(coordinate, size, wrap):
    if wrap == "EXTEND":
        return np.clip(coordinate, 0, size - 1)
    if wrap == "MIRROR":
        period = coordinate % (2 * size)
        return np.where(period < size, period, 2 * size - 1 - period)
    return coordinate % size


def _sample(pixels, uv, wrap):
    """Bilinear RGBA sample at UV points (N, 2), bottom-first pixels, wrap per axis."""
    height, width = pixels.shape[:2]
    x = uv[:, 0] * width - 0.5
    y = uv[:, 1] * height - 0.5
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    xa, xb = _texel(x0, width, wrap[0]), _texel(x0 + 1, width, wrap[0])
    ya, yb = _texel(y0, height, wrap[1]), _texel(y0 + 1, height, wrap[1])
    return ((pixels[ya, xa] * (1 - fx) + pixels[ya, xb] * fx) * (1 - fy)
            + (pixels[yb, xa] * (1 - fx) + pixels[yb, xb] * fx) * fy)


def _transform(uv, values, prop):
    """uv' = R(_R) (uv - ST.zw) / ST.xy, the transform of every texture of the effect shaders."""
    st = values.st.get(prop, [1.0, 1.0, 0.0, 0.0])
    angle = math.radians(values.floats.get(prop + "_R", 0.0))
    c, s = math.cos(angle), math.sin(angle)
    d = uv - np.array(st[2:4])
    turned = np.stack([c * d[:, 0] + s * d[:, 1], -s * d[:, 0] + c * d[:, 1]], -1)
    scale = np.array([math.copysign(max(abs(v), 1e-4), v) for v in st[:2]])
    return turned / scale


def _layout(obj, uvs, triangles):
    """Per loop layout of the bake in [0, 1]: the first UV channel whose triangles barely overlap and
    never cross a wrap seam, else a new unwrap.

    A triangle crossing a seam (Flame Dance's _380_inbody_aura_t1m1_a1: u from 0.4 to 1.9 on UV0) spans
    the whole cell: it drew the whole width of the cell squeezed into a line through the fireball, while
    in Unity the thresholds read a channel without seam (UV2) and stay continuous there."""
    loops = np.zeros(len(obj.data.loops), dtype=np.int64)
    obj.data.loops.foreach_get("vertex_index", loops)
    candidates = []
    for channel in sorted(uvs):
        base = np.asarray(uvs[channel], dtype=np.float64)[loops]
        lo, hi = base.min(0), base.max(0)
        if (hi - lo).min() < 1e-6:
            continue
        layout = (base - lo) / (hi - lo)
        corners = layout.reshape(-1, 3, 2)
        wrapped = ((corners.max(1) - corners.min(1)) > WRAP_SPAN).any()
        if not wrapped and _overlap(corners) <= OVERLAP_LIMIT:
            candidates.append((_bleed(layout), len(candidates), layout))
            if not candidates[-1][0]:
                return layout
    # smart_project works on the active object in edit mode
    context = bpy.context
    previous = context.view_layer.objects.active
    for other in context.view_layer.objects:
        other.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    for island_margin in ISLAND_MARGINS:
        layer = obj.data.uv_layers.new(name="flipbook_layout")
        obj.data.uv_layers.active = layer
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(island_margin=island_margin)
        bpy.ops.object.mode_set(mode="OBJECT")
        # Leaving edit mode rebuilds the mesh data: the layer is looked up again
        layer = obj.data.uv_layers["flipbook_layout"]
        values = np.zeros(len(obj.data.loops) * 2, dtype=np.float32)
        layer.data.foreach_get("uv", values)
        obj.data.uv_layers.remove(obj.data.uv_layers["flipbook_layout"])
        layout = values.reshape(-1, 2).astype(np.float64)
        candidates.append((_bleed(layout), len(candidates), layout))
        if not candidates[-1][0]:
            break
    context.view_layer.objects.active = previous
    return min(candidates, key=lambda candidate: candidate[:2])[2]


def _overlap(triangles, size=128):
    counts = np.zeros((size, size), dtype=np.int32)
    for tri in triangles:
        _, cells, _ = _cover(tri * size, size)
        if cells is not None:
            counts[cells[1], cells[0]] += 1
    covered = (counts > 0).sum()
    return float((counts > 1).sum()) / covered if covered else 0.0


def _islands(layout):
    """Island index per triangle of a per loop layout: triangles joined by an edge with the same UVs."""
    count = len(layout) // 3
    parent = np.arange(count)

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    keys = np.round(layout * 1e5).astype(np.int64)
    edges = {}
    for tri in range(count):
        for k in range(3):
            a, b = tuple(keys[tri * 3 + k]), tuple(keys[tri * 3 + (k + 1) % 3])
            edge = (a, b) if a < b else (b, a)
            other = edges.setdefault(edge, tri)
            if other != tri:
                parent[root(tri)] = root(other)
    return np.array([root(tri) for tri in range(count)])


def _bleed(layout, size=CELL_SIZE, margin=CELL_MARGIN):
    """Texels of a cell within one texel of two UV islands, where the bilinear filter of one reads the other.

    smart_project packs its islands about one texel apart at the cell size: the edge of an island read the
    texels of its neighbour, whose layer may be transparent at that frame. The two half domes of Flame
    Dance's _380_inbody_aura_t1m1_a1 touched along a meridian, and a thin transparent line crossed the
    fireball from its top down to its middle."""
    islands = _islands(layout)
    cell = (layout * (1.0 - 2.0 * margin) + margin).reshape(-1, 3, 2) * size
    first = np.full(size * size, -1, dtype=np.int64)
    shared = np.zeros(size * size, dtype=bool)
    for index, tri in enumerate(cell):
        _, cells, _ = _cover(tri, size, 1.0)
        if cells is None:
            continue
        texels = cells[1] * size + cells[0]
        shared[texels[(first[texels] >= 0) & (first[texels] != islands[index])]] = True
        first[texels[first[texels] < 0]] = islands[index]
    return int(shared.sum())


def _cover(tri, size, reach=0.0):
    """Texels of a (3, 2) triangle in texel units, and those within reach texels of it:
    (barycentrics (N, 3), (x, y) indices, distance to the triangle (0 inside))."""
    x, y = tri[:, 0] - 0.5, tri[:, 1] - 0.5
    x0, x1 = max(int(np.floor(x.min() - reach)), 0), min(int(np.ceil(x.max() + reach)), size - 1)
    y0, y1 = max(int(np.floor(y.min() - reach)), 0), min(int(np.ceil(y.max() + reach)), size - 1)
    d = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
    if x1 < x0 or y1 < y0 or abs(d) < 1e-12:
        return None, None, None
    gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
    a = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / d
    b = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / d
    c = 1 - a - b
    distance = np.zeros(gx.shape)
    if reach > 0.0:
        edges = []
        for i in range(3):
            ex, ey = x[(i + 1) % 3] - x[i], y[(i + 1) % 3] - y[i]
            t = np.clip(((gx - x[i]) * ex + (gy - y[i]) * ey) / max(ex * ex + ey * ey, 1e-12), 0.0, 1.0)
            edges.append(np.hypot(gx - x[i] - t * ex, gy - y[i] - t * ey))
        distance = np.where((a >= 0) & (b >= 0) & (c >= 0), 0.0, np.min(edges, 0))
        keep = distance <= reach
    else:
        keep = (a >= 0) & (b >= 0) & (c >= 0)
    return np.stack([a[keep], b[keep], c[keep]], -1), (gx[keep], gy[keep]), distance[keep]


def _raster(layout, loop_vertices, size, margin):
    """For every covered texel of a size x size cell: (texel index, vertex indices (3), barycentrics)."""
    cell = layout * (1.0 - 2.0 * margin) + margin
    owner = np.full(size * size, -1, dtype=np.int64)
    weights = np.zeros((size * size, 3))
    vertices = np.zeros((size * size, 3), dtype=np.int64)
    distance = np.full(size * size, np.inf)
    for index, tri in enumerate(cell.reshape(-1, 3, 2)):
        # The texels the bilinear filter reads past the edges go to the nearest triangle
        bary, cells, outside = _cover(tri * size, size, RASTER_REACH)
        if bary is None:
            continue
        texels = cells[1] * size + cells[0]
        better = outside < distance[texels]
        texels, bary, outside = texels[better], bary[better], outside[better]
        owner[texels] = index
        weights[texels] = np.clip(bary, 0.0, 1.0) / np.clip(bary, 0.0, 1.0).sum(1, keepdims=True).clip(1e-9)
        vertices[texels] = loop_vertices[index * 3:index * 3 + 3]
        distance[texels] = outside
    covered = np.nonzero(owner >= 0)[0]
    return covered, vertices[covered], weights[covered], cell, owner[covered]


def _gradients(uv, cell, size):
    """Per triangle (T, 2, 2) derivatives of a UV channel along the two axes of the cell, per texel of the cell.

    uv, cell: (T, 3, 2) corners in the channel and in the cell ([0, 1] of the cell)."""
    duv = np.stack([uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]], -1)
    dcell = np.stack([cell[:, 1] - cell[:, 0], cell[:, 2] - cell[:, 0]], -1) * size
    det = dcell[:, 0, 0] * dcell[:, 1, 1] - dcell[:, 0, 1] * dcell[:, 1, 0]
    det = np.where(np.abs(det) < 1e-12, 1e-12, det)
    inverse = np.stack([np.stack([dcell[:, 1, 1], -dcell[:, 0, 1]], -1),
                        np.stack([-dcell[:, 1, 0], dcell[:, 0, 0]], -1)], -2) / det[:, None, None]
    return duv @ inverse


_LEVELS = {}


def _levels(pixels):
    """The texture and its 2 x 2 averages down to one texel."""
    cached = _LEVELS.get(id(pixels))
    if cached is not None and cached[0] is pixels:
        return cached[1]
    levels = [pixels]
    while min(levels[-1].shape[:2]) >= 2:
        top = levels[-1]
        height, width = (top.shape[0] // 2) * 2, (top.shape[1] // 2) * 2
        top = top[:height, :width]
        levels.append((top[0::2, 0::2] + top[1::2, 0::2] + top[0::2, 1::2] + top[1::2, 1::2]) * 0.25)
    _LEVELS[id(pixels)] = (pixels, levels)
    return levels


def _sample_filtered(pixels, uv, wrap, gradient):
    """_sample, averaged over the texture footprint of each cell texel (gradient: (N, 2, 2) texture UV per
    cell texel, rows u / v, columns the cell axes).

    Where a cell texel covers many texels of a squeezed mask (the pole of a dome, where UV0 sweeps a whole
    period in one ring of triangles) a point sample picks one of them: a streak of noise ran through Flame
    Dance's fireball. One level of margin keeps the masks as sharp as the cell can hold them."""
    height, width = pixels.shape[:2]
    extent = np.maximum(np.hypot(gradient[:, 0, 0] * width, gradient[:, 1, 0] * height),
                        np.hypot(gradient[:, 0, 1] * width, gradient[:, 1, 1] * height))
    levels = _levels(pixels)
    lod = np.clip(np.log2(np.maximum(extent, 1e-9)) - LOD_MARGIN, 0.0, len(levels) - 1)
    if lod.max() <= 0.0:
        return _sample(pixels, uv, wrap)
    low = np.floor(lod).astype(np.int64)
    result = np.zeros((len(uv), pixels.shape[2]))
    for level in np.unique(low):
        at = np.nonzero(low == level)[0]
        value = _sample(levels[level], uv[at], wrap)
        if level + 1 < len(levels):
            blend = (lod[at] - level)[:, None]
            value = value + blend * (_sample(levels[level + 1], uv[at], wrap) - value)
        result[at] = value
    return result


def _dilate(texels, size, passes=DILATE_PASSES):
    """Per texel of a cell, the index (into texels) of the covered texel it copies, -1 for none.

    The bilinear filter reads one texel past the edge of the layout. Left empty (transparent), those
    texels drew a thin line along every UV seam of the mesh: the vertical cut in the middle of Flame
    Dance's fireball, where UV0 wraps from u = 1 back to 0. Each empty texel copies a covered neighbour.
    """
    source = np.full((size, size), -1, dtype=np.int64)
    source.flat[texels] = np.arange(len(texels))
    for _ in range(passes):
        padded = np.pad(source, 1, constant_values=-1)
        filled = source.copy()
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            neighbour = padded[1 + dy:1 + dy + size, 1 + dx:1 + dx + size]
            take = (filled < 0) & (neighbour >= 0)
            filled[take] = neighbour[take]
        source = filled
    return source.ravel()


def _transform_gradient(gradient, values, prop):
    """UV derivatives carried through the transform of a texture (_transform)."""
    st = values.st.get(prop, [1.0, 1.0, 0.0, 0.0])
    angle = math.radians(values.floats.get(prop + "_R", 0.0))
    c, s = math.cos(angle), math.sin(angle)
    turned = np.stack([c * gradient[:, 0] + s * gradient[:, 1], -s * gradient[:, 0] + c * gradient[:, 1]], 1)
    scale = np.array([math.copysign(max(abs(v), 1e-4), v) for v in st[:2]])
    return turned / scale[None, :, None]


def _shade(values, texture, inputs, vertex_alpha, gradients):
    """Colour and alpha of Soccer/Effect/T3ThresholdF at the given texels (straight, before _Transparency).

    inputs / gradients: per UV channel, the UVs of the texels and their derivatives per cell texel."""
    f, colors = values.floats, values.colors

    def tex(prop, uv, gradient):
        name, pixels, wrap = texture(prop)
        return np.ones((len(uv), 4)) if pixels is None else _sample_filtered(pixels, uv, wrap, gradient)

    def index_of(prop_index):
        index = int(f.get(prop_index, 0))
        return index if index in inputs else min(inputs)

    def channel(prop_index):
        return inputs[index_of(prop_index)]

    def gradient(prop_index, prop):
        return _transform_gradient(gradients[index_of(prop_index)], values, prop)

    second = colors.get("_SecondColor", [1.0, 1.0, 1.0, 1.0])
    flow_scale = second[3] * np.array([f.get("_FlowScale0", 0.0), f.get("_FlowScale1", 0.0), f.get("_FlowScale2", 0.0)])
    flow = tex("_FlowTex", _transform(channel("_FlowTexIndex"), values, "_FlowTex"),
               gradient("_FlowTexIndex", "_FlowTex"))[:, :2] * 2 - 1

    # Mask 0 atlas (_M0PatternX / Y cells, faded from cell n to n + 1 by _M0PatternFadeAnime)
    m0 = _transform(channel("_MaskTex0Index"), values, "_MaskTex0")
    columns, rows = max(int(f.get("_M0PatternX", 1)), 1), max(int(f.get("_M0PatternY", 1)), 1)
    m0_gradient = gradient("_MaskTex0Index", "_MaskTex0") / np.array([columns, rows])[None, :, None]
    fade = f.get("_M0PatternFadeAnime", 0.0)

    def pattern(frame):
        x, y = frame % columns, (frame // columns) % rows
        return m0 / np.array([columns, rows]) + np.array([x / columns, 1.0 - (y + 1) / rows])

    first = int(math.trunc(fade))
    mask0 = tex("_MaskTex0", pattern(first) + flow * flow_scale[1], m0_gradient)
    if fade % 1.0:
        mask0 = mask0 + (math.fabs(fade) % 1.0) * (tex("_MaskTex0", pattern(first + 1) + flow * flow_scale[1],
                                                       m0_gradient) - mask0)
    distortion = mask0[:, :2] * 2 - 1

    m1_uv = channel("_MaskTex1Index") + distortion * f.get("_M0FlowScale2", 0.0) + flow * flow_scale[2]
    m1 = tex("_MaskTex1", _transform(m1_uv, values, "_MaskTex1"), gradient("_MaskTex1Index", "_MaskTex1"))[:, 0]
    colour_uv = channel("_ColorTex0Index") + flow * flow_scale[0] + distortion * f.get("_M0FlowScale0", 0.0)
    colour_uv = _transform(colour_uv, values, "_ColorTex0")
    colour_gradient = gradient("_ColorTex0Index", "_ColorTex0")

    border2 = f.get("_ColorBorderMax2", 0.0)
    if f.get("_VertexAlphaThresholdMode", 0.0) >= 0.5:
        border2 = border2 * vertex_alpha
    k = np.array(second[:3])[None, :] * np.asarray(border2).reshape(-1, 1) * mask0[:, 3:4]

    def width(name):
        return min(max(1.0 - f.get(name, 0.0), 0.01), 1.0)

    s0 = np.clip((m1 - (2.0 - f.get("_ColorBorderMax0", 1.0) - k[:, 0])) / width("_ColorBorderMin0"), 0, 1)[:, None]
    s1 = np.clip((m1 - (2.0 - f.get("_ColorBorderMax1", 1.0) - k[:, 1])) / width("_ColorBorderMin1"), 0, 1)[:, None]
    alpha = np.clip((m1 - (1.0 - k[:, 2])) / width("_ColorBorderMin2"), 0, 1)
    c0, c1, c2 = (tex(prop, colour_uv, colour_gradient) for prop in ("_ColorTex0", "_ColorTex1", "_ColorTex2"))
    colour = c2 + s1 * ((c1 + s0 * (c0 - c1)) - c2)
    return colour[:, :3], alpha * colour[:, 3]


def convert(record, material, unity_material, action, frames, series, visibility, texture, uvs, cache, key,
            write_curve):
    """Bake a flat-colour T3ThresholdF layer into an atlas of CELL_SIZE cells shown by stepped UVMove keys.

    series: mask_shaders.Values at every frame; visibility: > 0 where the layer shows. Returns False when
    the layer is never visible (nothing is changed then).
    """
    from .mask_shaders import _rename_texproj, _set_slots, _uv_warp

    shown = np.nonzero(visibility > 1e-3)[0]
    if not len(shown):
        return False
    first, last = int(shown[0]), int(shown[-1])
    step = max(1, math.ceil((last - first + 1) / MAX_CELLS))
    count = min(MAX_CELLS, math.ceil((last - first + 1) / step))
    samples = [min(first + i * step + step // 2, last) for i in range(count)]

    obj = record.object
    mesh = record.unity_mesh
    loops = np.zeros(len(obj.data.loops), dtype=np.int64)
    obj.data.loops.foreach_get("vertex_index", loops)
    layout = _layout(obj, uvs, None)
    texels, vertices, weights, cell_uv, owners = _raster(layout, loops, CELL_SIZE, CELL_MARGIN)
    inputs = {channel: np.einsum("nk,nkd->nd", weights, np.asarray(values)[vertices]) for channel, values in uvs.items()}
    corners = cell_uv.reshape(-1, 3, 2)
    gradients = {channel: _gradients(np.asarray(values, dtype=np.float64)[loops].reshape(-1, 3, 2), corners,
                                     CELL_SIZE)[owners] for channel, values in uvs.items()}
    colours = np.asarray(mesh.colors, dtype=np.float64) if len(mesh.colors) else np.ones((len(mesh.positions), 4))
    vertex_alpha = np.einsum("nk,nk->n", weights, colours[vertices, 3])

    luminance = 1.0 + series[0].floats.get("_Luminance", 0.0)
    atlas = np.zeros((GRID * CELL_SIZE, GRID * CELL_SIZE, 4))
    source = _dilate(texels, CELL_SIZE)
    filled = source >= 0
    flat_rgb = None
    for index, frame in enumerate(samples):
        rgb, alpha = _shade(series[frame], texture, inputs, vertex_alpha, gradients)
        rgb = render_state.linear_to_srgb(render_state.srgb_to_linear(np.clip(rgb, 0, 1)) * luminance)
        cell = np.zeros((CELL_SIZE * CELL_SIZE, 4))
        # Texels out of reach of the layout keep a mean colour: the filter must not pull black into the edges
        flat_rgb = rgb.mean(0) if flat_rgb is None else flat_rgb
        cell[:, :3] = flat_rgb
        cell[filled, :3] = rgb[source[filled]]
        cell[filled, 3] = alpha[source[filled]]
        x, y = index % GRID, index // GRID
        atlas[y * CELL_SIZE:(y + 1) * CELL_SIZE, x * CELL_SIZE:(x + 1) * CELL_SIZE] = cell.reshape(CELL_SIZE, CELL_SIZE, 4)
    image = cache.image("flipbook_" + key, np.clip(atlas, 0.0, 1.0))

    # --- the mesh: one texproj on the layout of cell 0, UVMove steps to the cell of each frame
    uv_name = material.name + "_texproj0"
    for curve in [c for c in action.fcurves if '"%s"' % record.uv_layer in c.data_path]:
        action.fcurves.remove(curve)
    _rename_texproj(obj, record.uv_layer, uv_name)
    record.uv_layer = uv_name
    for name in [layer.name for layer in obj.data.uv_layers if layer.name != uv_name]:
        obj.data.uv_layers.remove(obj.data.uv_layers[name])
        modifier = obj.modifiers.get(name)
        if modifier is not None:
            obj.modifiers.remove(modifier)
    if uv_name not in obj.data.uv_layers:
        obj.data.uv_layers.new(name=uv_name)
    obj.data.uv_layers[uv_name].data.foreach_set("uv", (cell_uv / GRID).astype(np.float32).ravel())
    _uv_warp(obj, uv_name)
    cells = [min(max((frame - first) // step, 0), count - 1) for frame in range(len(series))]
    # The game computes (u - UVMove.x, v + UVMove.y): cell (x, y) is reached with UVMove (-x, y) / GRID
    base = 'modifiers["%s"].' % uv_name
    for path in ("offset", "scale"):
        for index in range(2):
            curve = action.fcurves.find(base + path, index=index)
            if curve is not None:
                action.fcurves.remove(curve)
    write_curve(action, base + "offset", 0, frames, [-(c % GRID) / GRID for c in cells], 1e-6)
    write_curve(action, base + "offset", 1, frames, [(c // GRID) / GRID for c in cells], 1e-6)

    _set_slots(material, [(image, "EXTEND", "RGBA8")])
    obj.data.level5_properties.render_default = RENDER_DEFAULT
    if series[0].floats.get("_VertexAlphaThresholdMode", 0.0) >= 0.5:
        _opaque_tint(obj)
    record.mask_converted = True
    return True


def _opaque_tint(obj):
    colors = obj.data.vertex_colors.get("Tint")
    if colors is None:
        return
    data = np.zeros(len(colors.data) * 4, dtype=np.float32)
    colors.data.foreach_get("color", data)
    data = data.reshape(-1, 4)
    data[:, 3] = 1.0
    colors.data.foreach_set("color", data.ravel())
