"""Mesh decoding (vertex channels, index buffer, sub-meshes, skinning, compressed meshes).

Ported from UnityPy's helpers/MeshHelper.py and helpers/PackedBitVector.py
(https://github.com/K0lb3/UnityPy) and AssetStudio's Mesh.cs (https://github.com/aelurum/AssetStudioMod).
"""

import math
import struct

# Unity 2018+ shader channels
CHANNEL_POSITION = 0
CHANNEL_NORMAL = 1
CHANNEL_TANGENT = 2
CHANNEL_COLOR = 3
CHANNEL_UV0 = 4
CHANNEL_BLEND_WEIGHT = 12
CHANNEL_BLEND_INDICES = 13

# (struct format, normalization divisor or None)
VERTEX_FORMAT_2019 = {0: ("f", None), 1: ("e", None), 2: ("B", 255.0), 3: ("b", 127.0), 4: ("H", 65535.0),
                      5: ("h", 32767.0), 6: ("B", None), 7: ("b", None), 8: ("H", None), 9: ("h", None),
                      10: ("I", None), 11: ("i", None)}
VERTEX_FORMAT_2017 = {0: ("f", None), 1: ("e", None), 2: ("B", 255.0), 3: ("B", 255.0), 4: ("b", 127.0),
                      5: ("H", 65535.0), 6: ("h", 32767.0), 7: ("B", None), 8: ("b", None), 9: ("H", None),
                      10: ("h", None), 11: ("I", None), 12: ("i", None)}
VERTEX_FORMAT_OLD = {0: ("f", None), 1: ("e", None), 2: ("B", 255.0), 3: ("B", None), 4: ("I", None)}

TOPOLOGY_TRIANGLES = 0
TOPOLOGY_TRIANGLE_STRIP = 1
TOPOLOGY_QUADS = 2


class MeshData:
    def __init__(self, name):
        self.name = name
        self.positions = []
        self.normals = []
        self.tangents = []
        self.colors = []
        self.uvs = {}
        self.bone_indices = []
        self.bone_weights = []
        # list of triangle lists, one per sub-mesh (= material slot)
        self.submeshes = []
        self.bind_poses = []
        self.bone_name_hashes = []
        self.root_bone_name_hash = 0
        self.blend_shapes = []

    @property
    def vertex_count(self):
        return len(self.positions)


def _unpack_ints(packed, start=0, count=None):
    bit_size = packed["m_BitSize"]
    data = packed["m_Data"]
    if count is None:
        count = packed["m_NumItems"]
    if bit_size == 0:
        return [0] * count
    bit_pos = bit_size * start
    index = bit_pos // 8
    bit_pos %= 8
    mask = (1 << bit_size) - 1
    out = [0] * count
    for i in range(count):
        bits = 0
        value = 0
        while bits < bit_size:
            value |= (data[index] >> bit_pos) << bits
            num = min(bit_size - bits, 8 - bit_pos)
            bit_pos += num
            bits += num
            if bit_pos == 8:
                index += 1
                bit_pos = 0
        out[i] = value & mask
    return out


def _unpack_floats(packed, start=0, count=None):
    if count is None:
        count = packed["m_NumItems"]
    if packed["m_BitSize"] == 0:
        return [packed["m_Start"]] * count
    scale = packed["m_Range"] / ((1 << packed["m_BitSize"]) - 1)
    return [x * scale + packed["m_Start"] for x in _unpack_ints(packed, start, count)]


def _chunks(values, size):
    return [tuple(values[i:i + size]) for i in range(0, len(values), size)]


def _format_table(version):
    if version[0] >= 2019:
        return VERTEX_FORMAT_2019
    if version[0] >= 2017:
        return VERTEX_FORMAT_2017
    return VERTEX_FORMAT_OLD


def _read_vertex_data(mesh, data, vertex_data, version, endian):
    channels = vertex_data.get("m_Channels") or []
    vertex_count = vertex_data["m_VertexCount"]
    if not channels or not vertex_count or not data:
        return
    formats = _format_table(version)

    if version[0] >= 5:
        # Stream layout is not serialized anymore: rebuild it from the channels
        stream_count = 1 + max(c["stream"] for c in channels)
        streams = []
        offset = 0
        for s in range(stream_count):
            stride = 0
            for channel in channels:
                if channel["stream"] == s and channel["dimension"]:
                    stride += (channel["dimension"] & 0xF) * struct.calcsize(formats[channel["format"]][0])
            streams.append((offset, stride))
            offset += vertex_count * stride
            offset = (offset + 15) & ~15
    else:
        streams = [(s["offset"], s["stride"]) for s in vertex_data["m_Streams"]]

    for index, channel in enumerate(channels):
        dimension = channel["dimension"] & 0xF
        if not dimension:
            continue
        fmt, divisor = formats[channel["format"]]
        # Old versions store colors as 4 bytes regardless of the declared dimension
        if version[0] < 2018 and index == 2 and channel["format"] == 2:
            dimension = 4
        stream_offset, stride = streams[channel["stream"]]
        item = struct.Struct("%s%d%s" % (endian, dimension, fmt))
        start = stream_offset + channel["offset"]
        values = [item.unpack_from(data, start + i * stride) for i in range(vertex_count)]
        if divisor:
            values = [tuple(v / divisor for v in value) for value in values]
        _assign_channel(mesh, index, values, version)


def _assign_channel(mesh, index, values, version):
    if version[0] >= 2018:
        if index == CHANNEL_POSITION:
            mesh.positions = [v[:3] for v in values]
        elif index == CHANNEL_NORMAL:
            mesh.normals = [v[:3] for v in values]
        elif index == CHANNEL_TANGENT:
            mesh.tangents = values
        elif index == CHANNEL_COLOR:
            mesh.colors = values
        elif CHANNEL_UV0 <= index < CHANNEL_UV0 + 8:
            mesh.uvs[index - CHANNEL_UV0] = [v[:2] for v in values]
        elif index == CHANNEL_BLEND_WEIGHT:
            mesh.bone_weights = values
        elif index == CHANNEL_BLEND_INDICES:
            mesh.bone_indices = values
        return
    # Pre-2018 channel order: vertex, normal, color, uv0, uv1, (uv2|tangent), uv3, tangent
    if index == 0:
        mesh.positions = [v[:3] for v in values]
    elif index == 1:
        mesh.normals = [v[:3] for v in values]
    elif index == 2:
        mesh.colors = values
    elif index in (3, 4):
        mesh.uvs[index - 3] = [v[:2] for v in values]
    elif index == 5:
        if version[0] >= 5:
            mesh.uvs[2] = [v[:2] for v in values]
        else:
            mesh.tangents = values
    elif index == 6:
        mesh.uvs[3] = [v[:2] for v in values]
    elif index == 7:
        mesh.tangents = values


def _decompress_compressed_mesh(mesh, compressed, version):
    vertices = compressed["m_Vertices"]
    if vertices["m_NumItems"] <= 0:
        return None
    vertex_count = vertices["m_NumItems"] // 3
    mesh.positions = _chunks(_unpack_floats(vertices), 3)

    uv = compressed["m_UV"]
    if uv["m_NumItems"] > 0:
        uv_info = compressed.get("m_UVInfo", 0)
        if uv_info:
            offset = 0
            for channel in range(8):
                bits = (uv_info >> (channel * 4)) & 0xF
                if bits & 4:
                    dimension = 1 + (bits & 3)
                    mesh.uvs[channel] = [v[:2] for v in _chunks(_unpack_floats(uv, offset, vertex_count * dimension), dimension)]
                    offset += dimension * vertex_count
        else:
            mesh.uvs[0] = _chunks(_unpack_floats(uv, 0, vertex_count * 2), 2)
            if uv["m_NumItems"] >= vertex_count * 4:
                mesh.uvs[1] = _chunks(_unpack_floats(uv, vertex_count * 2, vertex_count * 2), 2)

    normals = compressed["m_Normals"]
    if normals["m_NumItems"] > 0:
        data = _chunks(_unpack_floats(normals), 2)
        signs = _unpack_ints(compressed["m_NormalSigns"])
        mesh.normals = []
        for (x, y), sign in zip(data, signs):
            z_sqr = 1.0 - x * x - y * y
            if z_sqr >= 0:
                z = math.sqrt(z_sqr)
            else:
                length = math.sqrt(x * x + y * y) or 1.0
                x, y, z = x / length, y / length, 0.0
            mesh.normals.append((x, y, z if sign else -z))

    weights = compressed["m_Weights"]
    if weights["m_NumItems"] > 0:
        weight_data = _unpack_ints(weights)
        index_data = iter(_unpack_ints(compressed["m_BoneIndices"]))
        mesh.bone_weights = [[0.0] * 4 for _ in range(vertex_count)]
        mesh.bone_indices = [[0] * 4 for _ in range(vertex_count)]
        vertex = j = total = 0
        for weight, bone in zip(weight_data, index_data):
            mesh.bone_weights[vertex][j] = weight / 31.0
            mesh.bone_indices[vertex][j] = bone
            j += 1
            total += weight
            if total >= 31:
                vertex += 1
                j = total = 0
            elif j == 3:
                # The fourth weight is implicit
                mesh.bone_weights[vertex][3] = (31 - total) / 31.0
                mesh.bone_indices[vertex][3] = next(index_data)
                vertex += 1
                j = total = 0

    colors = compressed.get("m_Colors")
    if colors and colors["m_NumItems"] > 0:
        mesh.colors = [((c >> 24 & 0xFF) / 255.0, (c >> 16 & 0xFF) / 255.0, (c >> 8 & 0xFF) / 255.0, (c & 0xFF) / 255.0)
                       for c in _unpack_ints(colors)]

    triangles = compressed["m_Triangles"]
    if triangles["m_NumItems"] > 0:
        return _unpack_ints(triangles)
    return None


def _build_submeshes(mesh, submeshes, indices, use_16bit):
    for submesh in submeshes:
        first = submesh["firstByte"] // (2 if use_16bit else 4)
        count = submesh["indexCount"]
        base = submesh.get("baseVertex", 0)
        topology = submesh.get("topology", 0)
        chunk = [i + base for i in indices[first:first + count]]
        triangles = []
        if topology == TOPOLOGY_TRIANGLES:
            triangles = [tuple(chunk[i:i + 3]) for i in range(0, len(chunk) - 2, 3)]
        elif topology == TOPOLOGY_TRIANGLE_STRIP:
            for i in range(len(chunk) - 2):
                a, b, c = chunk[i:i + 3]
                if a == b or b == c or a == c:
                    continue
                triangles.append((b, a, c) if i & 1 else (a, b, c))
        elif topology == TOPOLOGY_QUADS:
            for i in range(0, len(chunk) - 3, 4):
                a, b, c, d = chunk[i:i + 4]
                triangles.append((a, b, c))
                triangles.append((a, c, d))
        mesh.submeshes.append(triangles)


def decode_mesh(mesh_dict, environment, version, endian="<"):
    """Convert a deserialized Mesh dict into MeshData (Unity space, no axis conversion)."""
    mesh = MeshData(mesh_dict.get("m_Name", ""))
    vertex_data = mesh_dict.get("m_VertexData") or {}

    data = vertex_data.get("m_DataSize") or b""
    stream = mesh_dict.get("m_StreamData") or {}
    if stream.get("path") and stream.get("size"):
        data = environment.get_resource(stream["path"], stream["offset"], stream["size"])
    _read_vertex_data(mesh, data, vertex_data, version, endian)

    raw_indices = mesh_dict.get("m_IndexBuffer") or b""
    if "m_Use16BitIndices" in mesh_dict:
        use_16bit = bool(mesh_dict["m_Use16BitIndices"])
    else:
        use_16bit = mesh_dict.get("m_IndexFormat", 0) == 0
    size = 2 if use_16bit else 4
    indices = list(struct.unpack("%s%d%s" % (endian, len(raw_indices) // size, "H" if use_16bit else "I"),
                                 bytes(raw_indices[:len(raw_indices) // size * size])))

    compressed = mesh_dict.get("m_CompressedMesh")
    if not mesh.positions and compressed:
        compressed_indices = _decompress_compressed_mesh(mesh, compressed, version)
        if compressed_indices:
            indices = compressed_indices

    if not mesh.bone_weights and mesh_dict.get("m_Skin"):
        skin = mesh_dict["m_Skin"]
        mesh.bone_weights = [(s["weight[0]"], s["weight[1]"], s["weight[2]"], s["weight[3]"]) for s in skin]
        mesh.bone_indices = [(s["boneIndex[0]"], s["boneIndex[1]"], s["boneIndex[2]"], s["boneIndex[3]"]) for s in skin]

    _build_submeshes(mesh, mesh_dict.get("m_SubMeshes", []), indices, use_16bit)

    for pose in mesh_dict.get("m_BindPose", []):
        mesh.bind_poses.append([[pose["e%d%d" % (row, col)] for col in range(4)] for row in range(4)])
    mesh.bone_name_hashes = list(mesh_dict.get("m_BoneNameHashes", []))
    mesh.root_bone_name_hash = mesh_dict.get("m_RootBoneNameHash", 0)

    shapes = mesh_dict.get("m_Shapes") or {}
    if shapes.get("vertices"):
        for channel in shapes.get("channels", []):
            # The last frame of a channel holds the full-weight deltas
            shape = shapes["shapes"][channel["frameIndex"] + channel["frameCount"] - 1]
            first = shape["firstVertex"]
            deltas = {}
            for vertex in shapes["vertices"][first:first + shape["vertexCount"]]:
                v = vertex["vertex"]
                deltas[vertex["index"]] = (v["x"], v["y"], v["z"])
            mesh.blend_shapes.append((channel["name"], deltas))
    return mesh
