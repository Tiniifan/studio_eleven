"""Turns evaluated Blender meshes into GPU batches.

The depsgraph already applies the armature, so the batches hold deformed positions and StudioRender
never re-implements the skinning the game vertex stage does.
"""

import bpy
import numpy as np

TINT_LAYER = "Tint"
SILHOUETTE_LAYER = "Col"

# Component count of every vertex attribute
ATTRIBUTE_SIZES = {"atr_pos": 3, "atr_nrm": 3, "atr_clr": 4, "atr_tx0": 2, "atr_tx1": 2, "atr_tx2": 2, "atr_pr2": 4}

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


class Topology:
    """What only changes with the topology of a mesh: triangles of each material slot, their GPU index buffers, the vertex colors."""

    def __init__(self, counts, loop_vertices, triangle_loops, triangle_materials, tint, silhouette, has_silhouette, uv_count):
        self.counts = counts
        self.loop_vertices = loop_vertices
        self.triangles = {int(index): triangle_loops[triangle_materials == index] for index in np.unique(triangle_materials)}
        self.tint = tint
        self.silhouette = silhouette
        self.has_silhouette = has_silhouette
        self.uv_count = uv_count
        self.elements = {}

    def element(self, material_index):
        import gpu

        if material_index not in self.elements:
            self.elements[material_index] = gpu.types.GPUIndexBuf(type='TRIS', seq=self.triangles[material_index])

        return self.elements[material_index]


class Geometry:
    """Loop attributes of one evaluated mesh (one float array per attribute) plus the triangles of each material slot."""

    def __init__(self, attributes, topology, vertex_positions):
        self.attributes = attributes
        self.topology = topology
        self.vertex_positions = vertex_positions
        self.triangles = topology.triangles
        self.uv_count = topology.uv_count
        self.has_silhouette = topology.has_silhouette
        self.buffers = {}
        self.batches = {}
        self._corners = None

    @property
    def corners(self):
        """The 8 corners of the box around the mesh, one per row in homogeneous coordinates."""
        if self._corners is None:
            points = self.vertex_positions.reshape(-1, 3)
            low, high = points.min(axis=0), points.max(axis=0)
            self._corners = np.array([[x, y, z, 1.0] for x in (low[0], high[0]) for y in (low[1], high[1])
                                      for z in (low[2], high[2])])
        return self._corners


_zeros = {}


def _zero_array(count, size):
    key = (count, size)
    if key not in _zeros:
        if len(_zeros) > 512:
            _zeros.clear()
        _zeros[key] = np.zeros((count, size), dtype=np.float32)

    return _zeros[key]


def _uv_arrays(mesh, loop_count):
    arrays = []

    for index in range(3):
        if index < len(mesh.uv_layers):
            values = np.empty(loop_count * 2, dtype=np.float32)
            mesh.uv_layers[index].data.foreach_get("uv", values)
            arrays.append(values.reshape(-1, 2))
        else:
            arrays.append(_zero_array(loop_count, 2))

    return arrays


def _color_array(mesh, name, loop_count, fallback):
    layers = mesh.vertex_colors if hasattr(mesh, "vertex_colors") else None
    layer = layers.get(name) if layers else None

    if layer is None:
        return np.full((loop_count, 4), fallback, dtype=np.float32), False

    values = np.empty(loop_count * 4, dtype=np.float32)
    layer.data.foreach_get("color", values)
    return values.reshape(-1, 4), True


def _build_topology(mesh, counts):
    mesh.calc_loop_triangles()

    triangle_count = len(mesh.loop_triangles)
    if triangle_count == 0:
        return None

    loop_count = counts[0]
    loop_vertices = np.empty(loop_count, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_vertices)
    triangle_loops = np.empty(triangle_count * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get("loops", triangle_loops)
    triangle_materials = np.empty(triangle_count, dtype=np.int32)
    mesh.loop_triangles.foreach_get("material_index", triangle_materials)

    tint, _ = _color_array(mesh, TINT_LAYER, loop_count, 1.0)
    silhouette, has_silhouette = _color_array(mesh, SILHOUETTE_LAYER, loop_count, 0.0)

    return Topology(counts, loop_vertices, triangle_loops.reshape(-1, 3), triangle_materials, tint, silhouette,
                    has_silhouette, len(mesh.uv_layers))


def _split_normals(mesh, obj, loop_count, loop_vertices):
    try:
        # Blender 3.4 only reads custom normals with auto smooth on, the importer leaves it off
        if mesh.has_custom_normals and not mesh.use_auto_smooth:
            try:
                mesh.use_auto_smooth = True
            except AttributeError:
                request_auto_smooth(obj.data.name)
        mesh.calc_normals_split()
        normals = np.empty(loop_count * 3, dtype=np.float32)
        mesh.loops.foreach_get("normal", normals)
        return normals.reshape(-1, 3)
    except (RuntimeError, AttributeError):
        vertex_normals = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get("normal", vertex_normals)
        return vertex_normals.reshape(-1, 3)[loop_vertices]


def extract(obj, depsgraph, previous=None):
    """Returns the Geometry of an evaluated object, or None when it has no triangle.

    `previous` is the Geometry drawn before. It is given back as it is when the mesh did not move (a mesh fixed on a bone
    is flagged with every pose but never deforms), and its topology is kept while the mesh keeps its size: a change of
    topology goes with an update of the mesh itself, which drops the cache.
    """
    evaluated = obj.evaluated_get(depsgraph)

    try:
        mesh = evaluated.to_mesh()
    except RuntimeError:
        return None

    if mesh is None:
        return None

    try:
        counts = (len(mesh.loops), len(mesh.vertices), len(mesh.polygons))
        topology = previous.topology if previous is not None else None

        if topology is None or topology.counts != counts:
            topology = _build_topology(mesh, counts)
            previous = None
            if topology is None:
                return None

        vertex_positions = np.empty(counts[1] * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", vertex_positions)
        uvs = _uv_arrays(mesh, counts[0])

        if previous is not None and np.array_equal(vertex_positions, previous.vertex_positions) and all(
                np.array_equal(uv, previous.attributes[name]) for uv, name in zip(uvs, ("atr_tx0", "atr_tx1", "atr_tx2"))):
            return previous

        attributes = {
            "atr_pos": vertex_positions.reshape(-1, 3)[topology.loop_vertices],
            "atr_nrm": _split_normals(mesh, obj, counts[0], topology.loop_vertices),
            "atr_clr": topology.tint,
            "atr_tx0": uvs[0],
            "atr_tx1": uvs[1],
            "atr_tx2": uvs[2],
            "atr_pr2": topology.silhouette,
        }

        return Geometry(attributes, topology, vertex_positions)
    finally:
        evaluated.to_mesh_clear()


_formats = {}
_signatures = {}


def clear_cache():
    _formats.clear()
    _signatures.clear()
    _zeros.clear()


def _format_of(names):
    import gpu

    if names not in _formats:
        vertex_format = gpu.types.GPUVertFormat()
        for name in names:
            vertex_format.attr_add(id=name, comp_type='F32', len=ATTRIBUTE_SIZES[name], fetch_mode='FLOAT')
        _formats[names] = vertex_format

    return _formats[names]


def _signature(shader):
    """The attributes the shader kept, an unused one is optimised out of the format."""
    if shader not in _signatures:
        _signatures[shader] = tuple(sorted(name for name, _ in shader.attrs_info_get() if name in ATTRIBUTE_SIZES))

    return _signatures[shader]


def make_batch(shader, geometry, material_index):
    """One vertex buffer per set of attributes and one batch per material slot, kept on the geometry."""
    import gpu

    if material_index not in geometry.triangles:
        return None

    names = _signature(shader)
    key = (names, material_index)
    batch = geometry.batches.get(key)

    if batch is None:
        buffer = geometry.buffers.get(names)
        if buffer is None:
            first = geometry.attributes["atr_pos"]
            buffer = gpu.types.GPUVertBuf(_format_of(names), len=len(first))
            for name in names:
                buffer.attr_fill(id=name, data=geometry.attributes[name])
            geometry.buffers[names] = buffer

        batch = gpu.types.GPUBatch(type='TRIS', buf=buffer, elem=geometry.topology.element(material_index))
        geometry.batches[key] = batch

    return batch


def attribute_signature(shader):
    return _signature(shader)
