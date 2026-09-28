"""The aura of the ball (Soccer/Ball_Toon _Aura* properties), drawn on the 3DS as a disc facing the camera.

When the ball catches fire (Flame Dance, frames 58-151) Inazuma Eleven Cross animates the aura of the ball's
own shader (ev62_00410_ballanim on the ball renderer b000002_10). Its vertex program takes d = N.V and
splits the ball into three rings (fragment program of data/unity_shaders.zip):
    centre = sat((d - _AuraCenterStart) / _AuraCenterWidth)
    edge   = 1 - sat((d - _AuraEdgeStart) / _AuraEdgeWidth)
    middle = max(1 - centre - edge, 0)
    aura   = centre x _AuraCenterColor + middle x _AuraMiddleColor + edge x _AuraEdgeColor
then adds aura x _AuraAddBlend to the shaded ball (after a hard light blend of the two). The white hot ball
with a glowing rim of the mobile and Victory Road versions is that sum, plus their bloom.

The 3DS ball has no such shader, and a ball archive only animates it (Level-5's whs0001_bl1 holds no mesh;
a mesh put on the ball armature did not show in the game). The aura becomes an effect model instead: the ball
renderer's own node, keyed to follow the centre of the ball, carries a square facing the camera (draw priority
billboard bit) just in front of the ball. On a sphere seen from afar N.V = sqrt(1 - r^2) at r ball radii from
the centre, so the three rings are baked in its texture, added to the ball (SRC_ALPHA / ONE) with the opacity
keyed to _AuraAddBlend. A soft ring past the silhouette, in the edge colour, stands for the bloom glow.
"""

import numpy as np
from mathutils import Matrix

from . import animations, materials, render_state
from ..unity import animation

AURA_PROPERTIES = ("_AuraAddBlend", "_AuraCenterColor", "_AuraMiddleColor", "_AuraEdgeColor",
                   "_AuraCenterStart", "_AuraCenterWidth", "_AuraEdgeStart", "_AuraEdgeWidth")
# Values of the shader before any animation (a ball renderer's material lives in another bundle)
DEFAULTS = {"_AuraCenterStart": 0.6, "_AuraCenterWidth": 0.3, "_AuraEdgeStart": 0.2, "_AuraEdgeWidth": 0.2}
# Half size of the square in ball radii, and where the glow past the silhouette fades out
HALF_SIZE = 1.3
GLOW_END = 1.25
GLOW_ALPHA = 0.6
TEXTURE_SIZE = 64
# Ball radius when the renderer has no bounds (Unity units, the mobile ball: m_AABB extent 0.14, like the 3DS
# ball around its "rot" bone once scaled)
DEFAULT_RADIUS = 0.14
# Drawn after the square covers the ball's front: a bit in front of the tangent plane
FRONT_OFFSET = 1.02
ADDITIVE_MATERIAL = {
    "m_Name": "ball_aura",
    "m_Shader": {"m_FileID": 0, "m_PathID": 0},
    "m_CustomRenderQueue": 3000,
    "m_SavedProperties": {"m_TexEnvs": [], "m_Colors": [],
                          "m_Floats": [("_SrcBlend", 1.0), ("_DstBlend", 1.0), ("_ZWrite", 0.0), ("_Cull", 0.0)]},
}
CLAMPED_TEXTURE = {"m_TextureSettings": {"m_WrapU": 1, "m_WrapV": 1, "m_FilterMode": 1}}


def _renderer_info(entry):
    return entry.node.get_component("SkinnedMeshRenderer") or entry.node.get_component("MeshRenderer")


def _aura_bindings(clip):
    """{(property, component): Binding} of the aura properties a clip animates on its own node."""
    found = {}
    for binding in clip.bindings:
        if binding.path_hash != 0 or binding.custom_type != animation.CUSTOM_RENDERER_MATERIAL:
            continue
        name, component = animation.material_attribute_name(binding.attribute, AURA_PROPERTIES)
        if name:
            found[(name, component)] = binding
    return found


def _aura_track(entry):
    """The timeline track of a renderer node that lights the aura of the ball shader up, None without one.

    Its other tracks may play at the same time (Ocean Birth: track 1 and the aura on track 3)."""
    if _renderer_info(entry) is None:
        return None
    for track in entry.tracks:
        for item in track.clips:
            clip = animation.decode_clip(item.clip_info.read(), item.clip_info.sfile.endian)
            if any(name == "_AuraAddBlend" for name, _ in _aura_bindings(clip)):
                return track
    return None


def has_aura(entry):
    return _aura_track(entry) is not None


def _ball_entry(entry, catalog):
    """The model whose hierarchy holds the ball renderer and animates its bones (Ball 0)."""
    best = None
    for other in catalog:
        if other is entry or other.node is entry.node or other.kind != entry.kind:
            continue
        node = entry.node.parent
        depth = 0
        while node is not None and node is not other.node:
            node, depth = node.parent, depth + 1
        if node is other.node and (best is None or depth < best[0]):
            best = (depth, other)
    return best[1] if best else None


def root_bone(entry):
    """The Unity node at the centre of the ball: the root bone of the ball renderer."""
    renderer = _renderer_info(entry).read()
    pointer = renderer["m_RootBone"]
    return entry.scene.nodes.get(pointer["m_PathID"]) if pointer["m_FileID"] == 0 else None


def _series(sampler):
    """Aura property values on every sampled frame: [{name: float or (r, g, b)}]."""
    per_clip = {id(clip): _aura_bindings(clip) for clip in sampler.source.clips}
    series = []
    for clip, time in sampler.samples:
        bindings = per_clip[id(clip)]
        t = time + animations.STEP_EPSILON
        values = dict(DEFAULTS)
        for name in AURA_PROPERTIES:
            # A float property is bound whole or as its first component depending on the clip
            scalar = bindings.get((name, None)) or bindings.get((name, "x"))
            if scalar is not None:
                values[name] = scalar.curves[0].evaluate(t)
            elif (name, "r") in bindings:
                values[name] = tuple(bindings[(name, c)].curves[0].evaluate(t) if (name, c) in bindings else 1.0
                                     for c in "rgb")
        series.append(values)
    return series


def _texture(values):
    """RGBA pixels (bottom first) of the square: the three rings inside the ball, the glow past it."""
    centres = (np.arange(TEXTURE_SIZE) + 0.5) / TEXTURE_SIZE * 2.0 - 1.0
    x, y = np.meshgrid(centres, centres)
    r = np.hypot(x, y) * HALF_SIZE
    d = np.sqrt(np.clip(1.0 - r * r, 0.0, 1.0))
    centre = np.clip((d - values["_AuraCenterStart"]) / max(values["_AuraCenterWidth"], 1e-4), 0.0, 1.0)
    edge = 1.0 - np.clip((d - values["_AuraEdgeStart"]) / max(values["_AuraEdgeWidth"], 1e-4), 0.0, 1.0)
    middle = np.maximum(1.0 - centre - edge, 0.0)
    colour = lambda name: np.array(values.get(name, (1.0, 1.0, 1.0)))[None, None, :]
    rgb = (centre[..., None] * colour("_AuraCenterColor") + middle[..., None] * colour("_AuraMiddleColor")
           + edge[..., None] * colour("_AuraEdgeColor"))
    # One texel of antialiasing on the silhouette, then the glow
    texel = 2.0 * HALF_SIZE / TEXTURE_SIZE
    inside = np.clip((1.0 - r) / texel + 0.5, 0.0, 1.0)
    glow = GLOW_ALPHA * np.clip((GLOW_END - r) / (GLOW_END - 1.0), 0.0, 1.0) ** 2
    rgb = np.where(r[..., None] < 1.0, rgb, colour("_AuraEdgeColor"))
    alpha = inside + (1.0 - inside) * glow
    return np.concatenate([np.clip(rgb, 0.0, 1.0), alpha[..., None]], -1)


def _radius(entry, options):
    bounds = _renderer_info(entry).read().get("m_AABB", {}).get("m_Extent")
    radius = max(bounds.values()) if bounds else DEFAULT_RADIUS
    return (radius if radius > 0.0 else DEFAULT_RADIUS) * options.scale


def _centre_matrices(entry, ball_entry, frames, options):
    """Matrix of the ball centre (the renderer's root bone) relative to the renderer's parent, per frame.

    Only its place and size: the square faces the camera whatever the spin of the ball."""
    root = root_bone(entry)
    tracks, clips = ball_entry.import_sources()
    if root is None or not (tracks or clips):
        return None
    source = animations.Source.from_track(tracks[0]) if tracks else animations.Source.from_clip(clips[0])
    sampler = animations.Sampler(source, options)
    locals_, _ = animations.sample_local_matrices(ball_entry.node, sampler, options)

    def world(node, index):
        matrix = Matrix.Identity(4)
        while node is not None and node is not ball_entry.node.parent:
            matrix = locals_[id(node)][index] @ matrix
            node = node.parent
        return matrix

    matrices = []
    for frame in frames:
        index = min(frame, len(sampler.frames) - 1)
        relative = world(entry.node.parent, index).inverted() @ world(root, index)
        location, _, scale = relative.decompose()
        matrices.append(Matrix.Translation(location) @ Matrix.Diagonal(scale).to_4x4())
    return matrices


def build(context, result, entry, catalog, sampler, action, options, cache):
    """Add the aura square to the model of the ball renderer (its own effect archive), its node keyed to
    follow the centre of the ball; return its (material, action) pairs."""
    import bpy

    aura_sampler = animations.Sampler(animations.Source.from_track(_aura_track(entry)), options)
    aura_series = _series(aura_sampler)
    series = [aura_series[min(frame, len(aura_series) - 1)] for frame in sampler.frames]
    strength = [max(0.0, min(1.0, values.get("_AuraAddBlend", 0.0))) for values in series]
    ball_entry = _ball_entry(entry, catalog)
    centres = _centre_matrices(entry, ball_entry, sampler.frames, options) if ball_entry else None
    if max(strength) <= 0.0 or centres is None:
        return []

    # The node of the renderer follows the centre of the ball
    bone_name = result.bone_names[id(entry.node)]
    relative_inverse = result.relative[id(entry.node)].inverted()
    animations.write_bone_curves(action, bone_name, sampler.frames, [relative_inverse @ m for m in centres],
                                 options.scale)
    armature = result.armature

    # The colours of the strongest frame (they only ramp up with the strength)
    peak = series[int(np.argmax(strength))]
    image = cache.image("ball_aura_%s" % entry.name, _texture(peak))
    material = materials.build_material("%s_aura" % entry.name, ADDITIVE_MATERIAL, None, None, False,
                                        image=image, sampler_texture=CLAMPED_TEXTURE)

    radius = _radius(entry, options)
    half, front = HALF_SIZE * radius, FRONT_OFFSET * radius
    mesh = bpy.data.meshes.new("%s_aura" % entry.name)
    # The billboard turns the square's +Z towards the camera
    mesh.from_pydata([(-half, -half, front), (half, -half, front), (half, half, front), (-half, half, front)],
                     [], [(0, 1, 2), (0, 2, 3)])
    layer = mesh.uv_layers.new(name="%s_texproj0" % material.name)
    corners = {0: (0.0, 0.0), 1: (1.0, 0.0), 2: (1.0, 1.0), 3: (0.0, 1.0)}
    for loop in mesh.loops:
        layer.data[loop.index].uv = corners[loop.vertex_index]
    mesh.materials.append(material)
    renderer = _renderer_info(entry)
    priority = render_state.draw_priorities(entry.sfile).get(renderer.path_id, render_state.DRAW_PRIORITY_BASE + 1)
    mesh.level5_properties.draw_priority = (priority & 0xFF) | render_state.BILLBOARD_PRIORITY_FLAG
    mesh.level5_properties.mesh_type = "MODEL"
    mesh.level5_properties.render_default = "#FIX_IMG"
    mesh.update()

    obj = bpy.data.objects.new(mesh.name, mesh)
    context.collection.objects.link(obj)
    obj.parent = armature
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    # Blender attaches bone children to the tail: cancel it so the vertices sit in the bone space
    obj.matrix_parent_inverse = Matrix.Translation((0.0, -armature.data.bones[bone_name].length, 0.0))
    render_state.refresh_preview(material)

    data_path = materials.add_transparency_animation(material)
    material.animation_data_create()
    material_action = bpy.data.actions.new("%s.%s" % (action.name, material.name))
    material.animation_data.action = material_action
    animations.write_curve(material_action, data_path, 0, sampler.frames, strength, 1e-3)
    return [(material, material_action)]
