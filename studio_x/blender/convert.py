"""Unity <-> Studio Eleven space conversion.

Unity is left-handed Y-up. Studio Eleven works in a right-handed Y-up space (3DS data) and
rotates armatures by 90 degrees on X to display them Z-up in Blender. Measured on the
FireTornado move: Studio Eleven data = Unity data with X mirrored and units x10.
"""

import math

from mathutils import Matrix, Quaternion, Vector

MIRROR_X = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
ARMATURE_ROTATION = (math.radians(90.0), 0.0, 0.0)
# Studio Eleven armature space (Y-up) -> Blender world (Z-up)
Y_UP_TO_Z_UP = Matrix.Rotation(math.radians(90.0), 4, "X")


def position(p, scale):
    return Vector((-p[0] * scale, p[1] * scale, p[2] * scale))


def rotation(q):
    """Unity quaternion (x, y, z, w) -> mathutils Quaternion (w, x, y, z) in mirrored space."""
    return Quaternion((q[3], q[0], -q[1], -q[2]))


def normal(n):
    return Vector((-n[0], n[1], n[2]))


def trs_matrix(location, quaternion, scale):
    return Matrix.Translation(location) @ quaternion.to_matrix().to_4x4() @ Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0))


def local_matrix(p, q, s, scale):
    # A zero scale would make the matrix impossible to decompose back into loc/rot/scale
    s = [v if abs(v) > 1e-6 else 1e-6 for v in s]
    return trs_matrix(position(p, scale), rotation(q).normalized(), s)


def unity_matrix(elements, scale):
    """Convert a Unity 4x4 matrix given as rows [[e00..e03], ...] to the mirrored space."""
    m = Matrix([list(row) for row in elements])
    m = MIRROR_X @ m @ MIRROR_X
    m.translation = m.translation * scale
    return m


def rigid(matrix):
    """Drop scale/shear so the matrix can be used as an edit bone matrix."""
    location, quaternion, _ = matrix.decompose()
    return Matrix.Translation(location) @ quaternion.normalized().to_matrix().to_4x4()


def euler_zxy_to_quaternion(degrees):
    """Unity euler angles (applied Z, then X, then Y) to a Unity-space (x, y, z, w) quaternion."""
    x, y, z = (math.radians(a) * 0.5 for a in degrees)
    cx, sx = math.cos(x), math.sin(x)
    cy, sy = math.cos(y), math.sin(y)
    cz, sz = math.cos(z), math.sin(z)
    qy = Quaternion((cy, 0.0, sy, 0.0))
    qx = Quaternion((cx, sx, 0.0, 0.0))
    qz = Quaternion((cz, 0.0, 0.0, sz))
    q = qy @ qx @ qz
    return (q.x, q.y, q.z, q.w)
