"""Bake Unity AnimationClips into Studio Eleven style Blender actions.

Mapping (measured by comparing FireTornado's Unity clips with the 3DS whs0001 animations):
    bones:     pose bone location / rotation_quaternion / scale (armature action)
    UV:        UV_WARP modifier offset = (_Tex_ST.z, -_Tex_ST.w), scale = (_Tex_ST.x, _Tex_ST.y) (mesh action)
    material:  alpha = Renderer.m_Enabled * GameObject.m_IsActive * (1 - _Transparency) (material action)
    timing:    3DS frame f (30 fps) == Unity time f / 30 + 1 / 60 (cameras: f / 30, see cameras.py)
Curves are sampled on every frame, then keys that linear interpolation already reproduces are dropped.
"""

import zlib

import bpy
import numpy as np
from mathutils import Quaternion

from . import convert, materials
from .textures import uv_scroll_properties
from ..unity import animation

ATTRIBUTE_ENABLED = zlib.crc32(b"m_Enabled")
ATTRIBUTE_IS_ACTIVE = zlib.crc32(b"m_IsActive")
RENDERER_CLASS_IDS = (23, 25, 137)
GAMEOBJECT_CLASS_ID = 1
# Evaluate just after the requested time so 1 frame steps land on the new value
STEP_EPSILON = 1e-4
# Margin keeping an offset sample strictly before the next timeline cut (well above STEP_EPSILON)
CUT_MARGIN = 1e-3


def _frame_index(starts, frame, fps):
    """Index of the last start time at or before a frame, rounded like Source.segment_frames()."""
    current = 0
    for index, start in enumerate(starts):
        if int(round(start * fps)) <= frame:
            current = index
    return current


class Source:
    """A timeline track or a single clip, mapped onto Blender frames."""

    def __init__(self, name, segments, duration, is_timeline=False, cuts=None):
        self.name = name
        self.segments = segments  # list of (AnimationClipData, start, clip_in, time_scale)
        self.duration = duration
        self.is_timeline = is_timeline
        self.cuts = cuts or [segment[1] for segment in segments]

    @classmethod
    def from_clip(cls, clip_info):
        clip = animation.decode_clip(clip_info.read(), clip_info.sfile.endian)
        return cls(clip.name, [(clip, 0.0, 0.0, 1.0)], clip.stop_time)

    @classmethod
    def from_track(cls, track):
        segments = []
        for item in track.clips:
            clip = animation.decode_clip(item.clip_info.read(), item.clip_info.sfile.endian)
            segments.append((clip, item.start, item.clip_in, item.time_scale))
        return cls(track.timeline_name or track.name, segments, track.duration, True, track.cuts)

    @property
    def clips(self):
        return [segment[0] for segment in self.segments]

    def locate(self, frame, fps, offset=0.0):
        """Return (clip, local time) for a Blender frame; clips hold their edge values.

        Both the segment and the sample time come from the frame, and neither reaches the next
        timeline cut: cuts often start on a half frame (Ocean Birth: 62.5, 149.5) which is exactly
        where the +1/60 offset used for bones lands. The step every clip holds at a cut (its whole
        model is placed somewhere else for the next shot) would then be picked up on the last frame
        of the cut, one frame before the split camera switches, and the model would jump away from
        the camera for a single frame (checked against the game: Ocean Birth frames 62 and 149).
        """
        index = _frame_index([segment[1] for segment in self.segments], frame, fps)
        return self.locate_in(index, self.sample_time(frame, fps, offset))

    def sample_time(self, frame, fps, offset):
        """Time a frame is sampled at, kept inside the timeline cut the frame belongs to.

        On the last frame of a cut the offset is dropped: the clips step to the next shot's
        placement right at the cut time, and Unity keys that step on the very frame the offset
        points at (Ocean Birth: keys -16 at 2.0667 then 0 at 2.0833, the cut).
        """
        time = frame / fps + offset
        for cut in self.cuts:
            if int(round(cut * fps)) > frame:
                return frame / fps if time >= cut - CUT_MARGIN else time
        return time

    def locate_in(self, index, time):
        """Like locate() but always inside one segment (used by split cameras)."""
        clip, start, clip_in, time_scale = self.segments[index]
        local = (time - start) * time_scale + clip_in
        return clip, min(max(local, 0.0), clip.stop_time)

    def segment_frames(self, index, fps):
        """Global frames covered by a segment: from its start to the frame before the next one."""
        return self._frames(self.segments[index][1], self.segments[index + 1][1] if index + 1 < len(self.segments) else None, fps)

    def cut_frames(self, index, fps):
        """Global frames covered by a timeline cut (cuts may differ from this track's own clips)."""
        return self._frames(self.cuts[index], self.cuts[index + 1] if index + 1 < len(self.cuts) else None, fps)

    def _frames(self, start, next_start, fps):
        first = int(round(start * fps))
        last = int(round(next_start * fps)) - 1 if next_start is not None else self.frame_count(fps)
        return list(range(first, max(first, last) + 1))

    def frame_count(self, fps):
        return max(1, int(round(self.duration * fps)))


class Sampler:
    def __init__(self, source, options, frame_offset=None):
        self.source = source
        self.fps = options.fps
        self.offset = (options.frame_offset if frame_offset is None else frame_offset) / 60.0
        self.frames = list(range(0, source.frame_count(self.fps) + 1))
        self.samples = [source.locate(frame, self.fps, self.offset) for frame in self.frames]


def _simplify(frames, values, tolerance):
    """Keep the smallest set of keys whose linear interpolation stays within tolerance."""
    values = np.asarray(values, dtype=np.float64)
    count = len(values)
    if count <= 2:
        return list(range(count))
    if np.ptp(values) <= tolerance:
        # First and last keys are kept: studio_eleven reads them to find an animation's range
        return [0, count - 1]
    frames = np.asarray(frames, dtype=np.float64)
    keep = [0]
    anchor = 0
    candidate = 2
    while candidate < count:
        span = slice(anchor + 1, candidate)
        t = (frames[span] - frames[anchor]) / (frames[candidate] - frames[anchor])
        line = values[anchor] + (values[candidate] - values[anchor]) * t
        if np.max(np.abs(line - values[span])) > tolerance:
            anchor = candidate - 1
            keep.append(anchor)
        candidate += 1
    keep.append(count - 1)
    return keep


def write_curve(action, data_path, index, frames, values, tolerance, group=None):
    kept = _simplify(frames, values, tolerance)
    fcurve = action.fcurves.find(data_path, index=index)
    if fcurve is None:
        fcurve = action.fcurves.new(data_path, index=index, action_group=group) if group else \
            action.fcurves.new(data_path, index=index)
    points = fcurve.keyframe_points
    start = len(points)
    points.add(len(kept))
    for offset, key in enumerate(kept):
        point = points[start + offset]
        point.co = (frames[key], values[key])
        point.interpolation = "LINEAR"
    fcurve.update()
    return fcurve


def _node_bindings(clip, model_node):
    """Group a clip's Transform bindings by node: {id(node): (node, {attribute: Binding})}."""
    grouped = {}
    table = animation.build_path_table([n.relative_path(model_node) for n in model_node.walk()])
    for binding in clip.bindings:
        if binding.type_id != animation.CLASS_TRANSFORM:
            continue
        path = table.get(binding.path_hash)
        node = model_node.find(path) if path is not None else None
        if node is None:
            continue
        grouped.setdefault(id(node), (node, {}))[1][binding.attribute] = binding
    return grouped


def _node_local_matrices(node, key, per_clip, sampler, scale):
    """Local matrix (Studio Eleven space) of an animated node on every sampled frame."""
    matrices = []
    for clip, time in sampler.samples:
        bindings = per_clip[id(clip)].get(key, (node, {}))[1]
        t = time + STEP_EPSILON
        position = bindings[animation.TRANSFORM_POSITION].evaluate(t) if animation.TRANSFORM_POSITION in bindings else node.position
        if animation.TRANSFORM_ROTATION in bindings:
            rotation = bindings[animation.TRANSFORM_ROTATION].evaluate(t)
        elif animation.TRANSFORM_EULER in bindings:
            rotation = convert.euler_zxy_to_quaternion(bindings[animation.TRANSFORM_EULER].evaluate(t))
        else:
            rotation = node.rotation
        local_scale = bindings[animation.TRANSFORM_SCALE].evaluate(t) if animation.TRANSFORM_SCALE in bindings else node.scale
        matrices.append(convert.local_matrix(position, rotation, local_scale, scale))
    return matrices


def _animated_nodes(sampler, model_node):
    per_clip = {id(clip): _node_bindings(clip, model_node) for clip in sampler.source.clips}
    animated = {}
    for grouped in per_clip.values():
        for key, (node, _) in grouped.items():
            animated[key] = node
    return per_clip, animated


def sample_local_matrices(model_node, sampler, options):
    """Return ({id(node): [local matrix per frame]} for every node of the model, set of animated ids)."""
    per_clip, animated = _animated_nodes(sampler, model_node)
    matrices = {}
    for node in model_node.walk():
        key = id(node)
        if key in animated:
            matrices[key] = _node_local_matrices(node, key, per_clip, sampler, options.scale)
        else:
            matrices[key] = [convert.local_matrix(node.position, node.rotation, node.scale, options.scale)] * len(sampler.frames)
    return matrices, set(animated)


def write_bone_curves(action, bone_name, frames, bases, scale):
    """Key a pose bone with one basis matrix per frame (quaternions kept on the same hemisphere)."""
    locations, rotations, scales = [], [], []
    previous = None
    for basis in bases:
        location, quaternion, basis_scale = basis.decompose()
        if previous is not None and previous.dot(quaternion) < 0.0:
            quaternion = Quaternion((-quaternion.w, -quaternion.x, -quaternion.y, -quaternion.z))
        previous = quaternion
        locations.append(location)
        rotations.append(quaternion)
        scales.append(basis_scale)

    base = 'pose.bones["%s"].' % bone_name
    for index in range(3):
        write_curve(action, base + "location", index, frames, [v[index] for v in locations], 1e-4 * scale, bone_name)
        write_curve(action, base + "scale", index, frames, [v[index] for v in scales], 1e-5, bone_name)
    for index in range(4):
        write_curve(action, base + "rotation_quaternion", index, frames, [q[index] for q in rotations], 1e-5, bone_name)


def bake_bones(action, model, sampler, options):
    per_clip, animated = _animated_nodes(sampler, model.entry.node)
    for key, node in animated.items():
        bone_name = model.bone_names.get(key)
        if bone_name is None:
            continue
        relative_inverse = model.relative[key].inverted()
        bases = [relative_inverse @ m for m in _node_local_matrices(node, key, per_clip, sampler, options.scale)]
        write_bone_curves(action, bone_name, sampler.frames, bases, options.scale)


def _renderer_bindings(clip, model_node, record):
    """Bindings affecting one renderer: visibility factors and resolved material properties."""
    table = animation.build_path_table([n.relative_path(model_node) for n in model_node.walk()])
    node_path = record.node.relative_path(model_node)
    ancestors = set()
    walker = record.node
    while walker is not None and walker is not model_node.parent:
        ancestors.add(walker.relative_path(model_node))
        walker = walker.parent

    property_names = []
    for _, material in record.unity_materials:
        if material:
            property_names.extend(materials.material_property_names(material))

    visibility = []
    properties = {}
    for binding in clip.bindings:
        path = table.get(binding.path_hash)
        if path is None:
            continue
        if path == node_path and binding.type_id in RENDERER_CLASS_IDS and binding.attribute == ATTRIBUTE_ENABLED:
            visibility.append(binding)
        elif path in ancestors and binding.type_id == GAMEOBJECT_CLASS_ID and binding.attribute == ATTRIBUTE_IS_ACTIVE:
            visibility.append(binding)
        elif path == node_path and binding.custom_type == animation.CUSTOM_RENDERER_MATERIAL:
            name, component = animation.material_attribute_name(binding.attribute, property_names)
            if name:
                properties[(name, component)] = binding
    return visibility, properties


def bake_renderers(model, sampler, action_name, options):
    """Return the list of (id_data, action) created for UV and material animations."""
    created = []
    model_node = model.entry.node
    clips = sampler.source.clips

    for record in model.renderers:
        per_clip = {id(clip): _renderer_bindings(clip, model_node, record) for clip in clips}
        has_visibility = any(v or (("_Transparency", None) in p) for v, p in per_clip.values())
        first_material = next((m for _, m in record.unity_materials if m), None)
        candidates = uv_scroll_properties(first_material) if first_material else []
        # The texture whose _ST the clips animate drives the single UV set of the mesh; when it is
        # not the baked texture itself, only its scrolling is kept (see uv_scroll_properties)
        texture_property = next((p for p in candidates
                                 if any(any(k[0] == p + "_ST" for k in props)
                                        for _, props in per_clip.values())), None)

        if has_visibility:
            created.extend(_bake_alpha(record, per_clip, sampler, action_name))
        if texture_property and record.uv_layer:
            created.append(_bake_uv(record, per_clip, sampler, action_name, texture_property,
                                    texture_property == candidates[0]))
    return created


def _static_st(record, texture_property):
    for _, material in record.unity_materials:
        if material:
            for name, env in material["m_SavedProperties"]["m_TexEnvs"]:
                if name == texture_property:
                    return (env["m_Scale"]["x"], env["m_Scale"]["y"], env["m_Offset"]["x"], env["m_Offset"]["y"])
    return (1.0, 1.0, 0.0, 0.0)


def _bake_uv(record, per_clip, sampler, action_name, texture_property, is_baked_texture):
    obj = record.object
    uv_property = texture_property + "_ST"
    static = _static_st(record, texture_property)
    series = {"x": [], "y": [], "z": [], "w": []}
    for clip, time in sampler.samples:
        properties = per_clip[id(clip)][1]
        for index, component in enumerate("xyzw"):
            binding = properties.get((uv_property, component))
            series[component].append(binding.curves[0].evaluate(time + STEP_EPSILON) if binding else static[index])

    if obj.animation_data is None:
        obj.animation_data_create()
    action = bpy.data.actions.new("%s.%s" % (action_name, obj.name))
    obj.animation_data.action = action
    base = 'modifiers["%s"].' % record.uv_layer
    if is_baked_texture:
        offsets = (series["z"], [-v for v in series["w"]])
    else:
        # Scroll of another texture: its tiling is not in the baked image, so only the motion it
        # adds is kept, brought back to the mesh UV scale (offset / tiling, from its rest offset)
        offsets = ([(v - static[2]) / (static[0] or 1.0) for v in series["z"]],
                   [-(v - static[3]) / (static[1] or 1.0) for v in series["w"]])
    write_curve(action, base + "offset", 0, sampler.frames, offsets[0], 1e-5)
    write_curve(action, base + "offset", 1, sampler.frames, offsets[1], 1e-5)
    # The 3DS files hold no UVScale track when the tiling never changes: don't create curves for it
    if is_baked_texture and any(abs(v - 1.0) > 1e-5 for v in series["x"] + series["y"]):
        write_curve(action, base + "scale", 0, sampler.frames, series["x"], 1e-5)
        write_curve(action, base + "scale", 1, sampler.frames, series["y"], 1e-5)
    return obj, action


def _bake_alpha(record, per_clip, sampler, action_name):
    renderer_data = record.node.get_component("MeshRenderer") or record.node.get_component("SkinnedMeshRenderer")
    static_enabled = 1.0 if renderer_data is None else float(bool(renderer_data.read().get("m_Enabled", 1)))
    static_active = 1.0 if record.node.active else 0.0
    created = []
    for slot, (_, material) in enumerate(record.unity_materials):
        blender_material = record.blender_materials[slot] if slot < len(record.blender_materials) else None
        if material is None or blender_material is None:
            continue
        static_transparency = materials.material_floats(material).get("_Transparency", 0.0)
        values = []
        for clip, time in sampler.samples:
            visibility, properties = per_clip[id(clip)]
            t = time + STEP_EPSILON
            factor = static_enabled * static_active if not visibility else 1.0
            for binding in visibility:
                factor *= 1.0 if binding.curves[0].evaluate(t) >= 0.5 else 0.0
            transparency = properties.get(("_Transparency", None))
            value = transparency.curves[0].evaluate(t) if transparency else static_transparency
            values.append(max(0.0, min(1.0, factor * (1.0 - value))))

        # Material animations are per renderer in Unity: give animated renderers their own copy
        if slot not in record.owned_slots and blender_material.users > 1:
            blender_material = blender_material.copy()
            record.object.data.materials[slot] = blender_material
            record.blender_materials[slot] = blender_material
        record.owned_slots.add(slot)
        if blender_material.animation_data is None:
            blender_material.animation_data_create()
        action = bpy.data.actions.new("%s.%s" % (action_name, blender_material.name))
        blender_material.animation_data.action = action
        write_curve(action, materials.alpha_data_path(blender_material), 0, sampler.frames, values, 1e-3)
        created.append((blender_material, action))
    return created
