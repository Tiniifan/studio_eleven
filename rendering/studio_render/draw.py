"""Turns evaluated Blender meshes into GPU batches.

The depsgraph already applies the armature, so the batches hold deformed positions and StudioRender
never re-implements the skinning the game vertex stage does.
"""

import bpy

TINT_LAYER = "Tint"
SILHOUETTE_LAYER = "Col"

_smooth_requests = set()


def _enable_auto_smooth():
    for name in _smooth_requests:
        mesh = bpy.data.meshes.get(name)
        if mesh is not None and mesh.has_custom_normals:
            mesh.use_auto_smooth = True

    _smooth_requests.clear()


def request_auto_smooth(name):
    """The viewport draw may not write to blend data, the flag is set right after it."""
    if not _smooth_requests:
        bpy.app.timers.register(_enable_auto_smooth, first_interval=0.0)
    _smooth_requests.add(name)


# The Col layer of the importer is the atr_pr2 attribute (per vertex silhouette weights), only Tint is atr_clr
STATUS = "atr_clr is the Tint layer of operators/fileio_xmpr.py, white when the mesh has none"


class Geometry:
    """Loop attributes of one evaluated mesh plus the triangles of each material slot."""

    def __init__(self, attributes, triangles, uv_count, has_silhouette=False):
        self.attributes = attributes
        self.triangles = triangles
        self.uv_count = uv_count
        self.has_silhouette = has_silhouette


def _uv_arrays(mesh, loop_count):
    arrays = []

    for index in range(3):
        if index < len(mesh.uv_layers):
            data = mesh.uv_layers[index].data
            arrays.append([tuple(data[loop].uv) for loop in range(loop_count)])
        else:
            arrays.append([(0.0, 0.0)] * loop_count)

    return arrays


def _tint_array(mesh, loop_count):
    layers = mesh.vertex_colors if hasattr(mesh, "vertex_colors") else None
    tints = layers.get(TINT_LAYER) if layers else None

    if tints is None:
        return [(1.0, 1.0, 1.0, 1.0)] * loop_count

    return [tuple(tints.data[loop].color) for loop in range(loop_count)]


def _silhouette_array(mesh, loop_count):
    layers = mesh.vertex_colors if hasattr(mesh, "vertex_colors") else None
    flags = layers.get(SILHOUETTE_LAYER) if layers else None

    if flags is None:
        return [(0.0, 0.0, 0.0, 0.0)] * loop_count, False

    return [tuple(flags.data[loop].color) for loop in range(loop_count)], True


def extract(obj, depsgraph):
    """Returns the Geometry of an evaluated object, or None when it has no triangle."""
    evaluated = obj.evaluated_get(depsgraph)

    try:
        mesh = evaluated.to_mesh()
    except RuntimeError:
        return None

    if mesh is None:
        return None

    try:
        mesh.calc_loop_triangles()
        try:
            # Blender 3.4 only reads custom normals with auto smooth on, the importer leaves it off
            if mesh.has_custom_normals and not mesh.use_auto_smooth:
                try:
                    mesh.use_auto_smooth = True
                except AttributeError:
                    request_auto_smooth(obj.data.name)
            mesh.calc_normals_split()
            normals = [tuple(loop.normal) for loop in mesh.loops]
        except (RuntimeError, AttributeError):
            normals = [tuple(mesh.vertices[loop.vertex_index].normal) for loop in mesh.loops]

        loop_count = len(mesh.loops)
        positions = [tuple(mesh.vertices[loop.vertex_index].co) for loop in mesh.loops]
        uvs = _uv_arrays(mesh, loop_count)
        silhouette, has_silhouette = _silhouette_array(mesh, loop_count)

        attributes = {
            "atr_pos": positions,
            "atr_nrm": normals,
            "atr_clr": _tint_array(mesh, loop_count),
            "atr_tx0": uvs[0],
            "atr_tx1": uvs[1],
            "atr_tx2": uvs[2],
            "atr_pr2": silhouette,
        }

        triangles = {}
        for triangle in mesh.loop_triangles:
            triangles.setdefault(triangle.material_index, []).append(tuple(triangle.loops))

        return Geometry(attributes, triangles, len(mesh.uv_layers), has_silhouette)
    finally:
        evaluated.to_mesh_clear()


def make_batch(shader, geometry, material_index):
    """Only the attributes the shader kept are uploaded, an unused one is optimised out of the format."""
    from gpu_extras.batch import batch_for_shader

    indices = geometry.triangles.get(material_index)
    if not indices:
        return None

    names = {name for name, _ in shader.attrs_info_get()}
    content = {name: values for name, values in geometry.attributes.items() if name in names}

    return batch_for_shader(shader, 'TRIS', content, indices=indices)


def attribute_signature(shader):
    return tuple(sorted(name for name, _ in shader.attrs_info_get()))
