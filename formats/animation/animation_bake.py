from math import acos, sin

from .tracks import *
from . import animation_support

##########################################
# CONST
##########################################

DEFAULT_TOLERANCE = 0.0001

# Opposite quaternions (dot near 0) keep their sign, it's what decides the path of the game slerp
OPPOSITE_ROTATION_EPSILON = 0.00001

##########################################
# Animation Bake Function
##########################################

def get_components(value):
    if isinstance(value, BoneRotation):
        return (value.X, value.Y, value.Z, value.W)
    elif isinstance(value, (BoneLocation, BoneScale)):
        return (value.X, value.Y, value.Z)
    elif isinstance(value, (UVMove, UVScale)):
        return (value.X, value.Y)
    elif isinstance(value, (UVRotate, BoneBool)):
        return (value.X,)
    elif isinstance(value, Transparency):
        return (value.transparency,)
    elif isinstance(value, MaterialAttribute):
        return (value.hue, value.saturation, value.value)

    raise Exception(f"Unknown animation value: {type(value).__name__}")

def hold(a, b, t):
    return a

def lerp(a, b, t):
    result = []

    for x, y in zip(a, b):
        result.append(x + (y - x) * t)

    return result

def slerp(a, b, t):
    # Same as the game: shortest path, lerp when both quaternions are almost equal
    dot = 0
    for x, y in zip(a, b):
        dot += x * y

    theta = acos(min(abs(dot), 1.0))
    sin_theta = sin(theta)

    if sin_theta < 0.000001:
        return lerp(a, b, t)

    weight_a = sin((1 - t) * theta) / sin_theta
    weight_b = sin(t * theta) / sin_theta

    if dot < 0:
        weight_b = -weight_b

    result = []

    for x, y in zip(a, b):
        result.append(x * weight_a + y * weight_b)

    return result

def get_interpolate_function(track_name, interpolation):
    if interpolation == animation_support.INTERPOLATION_CONSTANT:
        return hold

    if track_name == "BoneRotation":
        return slerp

    return lerp

def align_rotations(frames):
    """Keep consecutive quaternions in the same hemisphere (q and -q are the same rotation)."""
    previous = None

    for frame in frames:
        rotation = frame.Value

        if previous is not None:
            dot = previous.X * rotation.X + previous.Y * rotation.Y + previous.Z * rotation.Z + previous.W * rotation.W

            if dot < -OPPOSITE_ROTATION_EPSILON:
                rotation.X = -rotation.X
                rotation.Y = -rotation.Y
                rotation.Z = -rotation.Z
                rotation.W = -rotation.W

        previous = rotation

def is_close(a, b, tolerance):
    for x, y in zip(a, b):
        if abs(x - y) > tolerance:
            return False

    return True

def is_reproduced(keys, values, start, end, interpolate, tolerance):
    for i in range(start + 1, end):
        t = (keys[i] - keys[start]) / (keys[end] - keys[start])

        if not is_close(interpolate(values[start], values[end], t), values[i], tolerance):
            return False

    return True

def reduce_frames(frames, interpolate, tolerance):
    """Remove the keys which the game interpolation rebuilds from the kept keys."""
    if len(frames) <= 2:
        return frames

    keys = [frame.Key for frame in frames]
    values = [get_components(frame.Value) for frame in frames]

    is_constant = True
    for value in values:
        if not is_close(value, values[0], tolerance):
            is_constant = False

    if is_constant:
        return [frames[0], frames[-1]]

    kept = [0]
    start = 0

    for end in range(2, len(frames)):
        if not is_reproduced(keys, values, start, end, interpolate, tolerance):
            kept.append(end - 1)
            start = end - 1

    kept.append(len(frames) - 1)

    reduced_frames = []
    for i in kept:
        reduced_frames.append(frames[i])

    return reduced_frames

def finalize_track(track, bake, tolerance=DEFAULT_TOLERANCE):
    """Sort the keys of each node, keep the rotations continuous and remove the redundant keys of a baked track."""
    for node in track.Nodes:
        node.Frames.sort(key=lambda frame: frame.Key)

        if track.Name == "BoneRotation":
            align_rotations(node.Frames)

        if bake:
            node.Frames = reduce_frames(node.Frames, get_interpolate_function(track.Name, node.Interpolation), tolerance)
