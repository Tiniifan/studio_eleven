"""AnimationClip decoding (Mecanim muscle clip: streamed, dense and constant curves).

Binary layout of streamed frames and curve/binding indexing follow AssetStudio's
AnimationClip.cs / ModelConverter.cs (https://github.com/aelurum/AssetStudioMod) and
AssetRipper's AnimationClipConverter / StreamedFrame / CustomCurveResolver
(https://github.com/AssetRipper/AssetRipper).

Streamed keys store Hermite segments as cubic coefficients, so curves are evaluated
exactly at any time instead of only at the original key times.
"""

import bisect
import struct
import zlib

# GenericBinding.attribute values for Transform bindings (typeID 4)
TRANSFORM_POSITION = 1
TRANSFORM_ROTATION = 2
TRANSFORM_SCALE = 3
TRANSFORM_EULER = 4

TRANSFORM_DIMENSIONS = {TRANSFORM_POSITION: 3, TRANSFORM_ROTATION: 4, TRANSFORM_SCALE: 3, TRANSFORM_EULER: 3}

CLASS_TRANSFORM = 4
CUSTOM_RENDERER_MATERIAL = 22

MIN_TIME = -3.0e38


class Curve:
    """A single float channel. Keys hold (time, a, b, c, d) with value = a*dt^3 + b*dt^2 + c*dt + d."""

    __slots__ = ("times", "coeffs", "linear")

    def __init__(self):
        self.times = []
        self.coeffs = []
        # Dense clips are sampled data: interpolate linearly between samples
        self.linear = False

    def add_key(self, time, a, b, c, d):
        if self.times and self.times[-1] == time:
            self.coeffs[-1] = (a, b, c, d)
        else:
            self.times.append(time)
            self.coeffs.append((a, b, c, d))

    def evaluate(self, time):
        times = self.times
        if not times:
            return 0.0
        index = bisect.bisect_right(times, time) - 1
        if index < 0:
            return self.coeffs[0][3]
        a, b, c, d = self.coeffs[index]
        dt = time - times[index]
        if self.linear:
            if index + 1 < len(times):
                span = times[index + 1] - times[index]
                if span > 0:
                    return d + (self.coeffs[index + 1][3] - d) * min(dt / span, 1.0)
            return d
        return ((a * dt + b) * dt + c) * dt + d


class Binding:
    """A group of curves driving one property (e.g. the 4 quaternion channels of a bone)."""

    __slots__ = ("path_hash", "type_id", "custom_type", "attribute", "script",
                 "is_pptr", "curves")

    def __init__(self, generic_binding):
        self.path_hash = generic_binding["path"]
        self.type_id = generic_binding["typeID"]
        self.custom_type = generic_binding["customType"]
        self.attribute = generic_binding["attribute"]
        self.script = generic_binding.get("script")
        self.is_pptr = bool(generic_binding.get("isPPtrCurve", 0))
        self.curves = [Curve() for _ in range(self.dimension)]

    @property
    def dimension(self):
        if self.type_id == CLASS_TRANSFORM:
            return TRANSFORM_DIMENSIONS.get(self.attribute, 1)
        return 1

    def evaluate(self, time):
        return [curve.evaluate(time) for curve in self.curves]

    def __repr__(self):
        return "Binding(path=%d, type=%d, custom=%d, attribute=%d)" % (
            self.path_hash, self.type_id, self.custom_type, self.attribute)


class AnimationClipData:
    def __init__(self, name, sample_rate, start_time, stop_time, bindings, loop=False):
        self.name = name
        self.sample_rate = sample_rate
        self.start_time = start_time
        self.stop_time = stop_time
        self.bindings = bindings
        self.loop = loop

    @property
    def duration(self):
        return self.stop_time - self.start_time


def _read_streamed_frames(data, endian):
    raw = struct.pack("%s%dI" % (endian, len(data)), *data)
    frames = []
    position = 0
    size = len(raw)
    while position + 8 <= size:
        time, count = struct.unpack_from(endian + "fi", raw, position)
        position += 8
        keys = [struct.unpack_from(endian + "iffff", raw, position + i * 20) for i in range(count)]
        position += count * 20
        frames.append((time, keys))
    return frames


def decode_clip(clip, endian="<"):
    """Convert a deserialized AnimationClip dict into AnimationClipData."""
    muscle = clip["m_MuscleClip"]
    clip_data = muscle["m_Clip"]["data"]
    bindings = [Binding(b) for b in clip["m_ClipBindingConstant"]["genericBindings"]]

    # Global curve index -> (binding, channel)
    channel_map = []
    for binding in bindings:
        for channel in range(binding.dimension):
            channel_map.append((binding, channel))

    def curve_at(index):
        if 0 <= index < len(channel_map):
            binding, channel = channel_map[index]
            return binding.curves[channel]
        return None

    streamed = clip_data.get("m_StreamedClip") or {"data": [], "curveCount": 0}
    streamed_count = streamed.get("curveCount", 0)
    initial_values = {}
    for time, keys in _read_streamed_frames(streamed["data"], endian):
        for index, a, b, c, d in keys:
            curve = curve_at(index)
            if curve is None:
                continue
            if time < MIN_TIME:
                # Leading frame at -FLT_MAX only carries the initial value
                initial_values[index] = d
            else:
                curve.add_key(max(time, 0.0), a, b, c, d)
    for index, value in initial_values.items():
        curve = curve_at(index)
        if curve is not None and not curve.times:
            curve.add_key(0.0, 0.0, 0.0, 0.0, value)

    dense = clip_data.get("m_DenseClip") or {}
    dense_count = dense.get("m_CurveCount", 0)
    if dense_count:
        samples = dense["m_SampleArray"]
        frame_count = dense["m_FrameCount"]
        rate = dense["m_SampleRate"] or 1.0
        begin = dense["m_BeginTime"]
        for curve_index in range(dense_count):
            curve = curve_at(streamed_count + curve_index)
            if curve is None:
                continue
            curve.linear = True
            for frame in range(frame_count):
                value = samples[frame * dense_count + curve_index]
                curve.add_key(begin + frame / rate, 0.0, 0.0, 0.0, value)

    constant = (clip_data.get("m_ConstantClip") or {}).get("data", [])
    for curve_index, value in enumerate(constant):
        curve = curve_at(streamed_count + dense_count + curve_index)
        if curve is not None:
            curve.add_key(0.0, 0.0, 0.0, 0.0, value)

    return AnimationClipData(
        clip.get("m_Name", ""), clip.get("m_SampleRate", 60.0),
        muscle.get("m_StartTime", 0.0), muscle.get("m_StopTime", 0.0), bindings,
        bool(muscle.get("m_LoopTime", False)))


def path_hash(path):
    return zlib.crc32(path.encode("utf-8"))


def build_path_table(transform_paths):
    """Map crc32(path) -> path for every suffix of every transform path (AssetStudio CreateBonePathHash)."""
    table = {0: ""}
    for path in transform_paths:
        parts = path.split("/")
        for i in range(len(parts)):
            sub = "/".join(parts[i:])
            table[path_hash(sub)] = sub
    return table


def material_attribute_name(attribute, property_names):
    """Resolve a RendererMaterial binding attribute to "_Prop" or "_Prop.x" (AssetRipper CustomCurveResolver).

    Returns (property_name, component) where component is None, or one of x/y/z/w/r/g/b/a.
    """
    crc28 = attribute & 0x0FFFFFFF
    for name in property_names:
        if zlib.crc32(name.encode("utf-8")) & 0x0FFFFFFF == crc28:
            if attribute & 0x80000000:
                return name, None
            index = (attribute >> 28) & 3
            is_color = bool(attribute & 0x40000000)
            return name, ("rgba" if is_color else "xyzw")[index]
    return None, None

