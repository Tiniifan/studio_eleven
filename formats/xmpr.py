import zlib
import struct
import io

from ..utils import *
from ..compression import lz10, compressor

##########################################
# XMPR Write Function
##########################################

def used_bones(weights, bone_names):
    used = {}
    
    for key in list(weights.keys()):
        for sub_key in list(weights[key].keys()):
            if sub_key not in used:
                used[sub_key] = bone_names[sub_key]
     
    return list(used.values())

def used_weights(weights):
    used = {}
    index = 0
    
    for key in list(weights.keys()):
        temp_dict = weights.pop(key)
        weights[key] = {}
        for sub_key in list(temp_dict.keys()):
            if sub_key not in used:
                used[sub_key] = index
                index += 1
                 
            weights[key][used[sub_key]] = temp_dict[sub_key]    
            
    return weights

def remove_dupe_indices(indices):
    used_indices = []
    final_indices = []
    keys = ["v", "vt", "vn", "vc"]
    
    for indice in indices:
        for i in range(3):
            geometrie = []
            for j in indice.keys():
                if indice[j] != []:
                    geometrie.append(indice[j][i])
            
            geometrie = tuple(geometrie)
            
            if geometrie not in used_indices:
                used_indices.append(geometrie)
            
                # Transform geometrie tuple to dict
                geometrie = used_indices[used_indices.index(geometrie)]
                geometrie_dict = {}
                for i, key in enumerate(keys):
                    if i < len(geometrie):
                        geometrie_dict[key] = geometrie[i]
                    else:
                        break
                    
                final_indices.append(geometrie_dict)
     
    return final_indices
    
def flatten_tuple(tuples_list):
    flat = [x for tup in tuples_list for x in tup]
    return list(dict.fromkeys(flat))

def classify_tint(tints):
    if not tints:
        return (1.0, 1.0, 1.0, 1.0), False

    first = tuple(tints[0])

    if any(tuple(tint) != first for tint in tints):
        return (1.0, 1.0, 1.0, 1.0), True

    return first, False

def write_attributes(tint_streamed):
    attributes = [[0, 0, 0, 0] for i in range(10)]
    offset = 0

    def add(slot, count, size):
        nonlocal offset
        attributes[slot] = [count, offset, size, 2]
        offset += size

    add(0, 3, 12)
    if tint_streamed:
        add(1, 4, 16)
    else:
        attributes[1] = [4, 0, 16, 1]
    add(2, 3, 12)
    add(4, 2, 8)
    add(5, 2, 8)
    add(7, 4, 16)
    add(8, 4, 16)
    add(9, 4, 16)

    out = bytes()
    for attribute in attributes:
        out += bytes(attribute)

    return struct.pack("<I", len(out) << 3) + out, offset

def write_fixed_tint(tint):
    # A fixed attribute holds a single value for the whole mesh, always 4 floats
    if tuple(tint) == (1.0, 1.0, 1.0, 1.0):
        return bytes([int(x,0) for x in ["0x81", "0x00", "0x00", "0x00", "0x08", "0x00", "0x00", "0x80", "0x3F", "0x90", "0x03", "0x00"] ])

    return lz10.compress(struct.pack("<4f", *tint))

def write_geometrie(indices, vertices, uvs, normals, colors, weights, tints = None):
    out = bytes()
    
    indices = flatten_tuple(indices)
    
    for indice in indices:
        for v in vertices[indice]:
            out += bytearray(struct.pack("f", v))
        if tints:
            for t in range(4):
                out += bytearray(struct.pack("f", tints[indice][t]))
        for n in normals[indice]:
            out += bytearray(struct.pack("f", n))
        for vt in range(2):
            out += bytearray(struct.pack("f", uvs[indice][0]))
            out += bytearray(struct.pack("f", 1 - uvs[indice][1] ))
            
        weight = weights[indice]
        keys = list(weight.keys())
        for w in range(4):
            if w < len(keys):
                out += bytearray(struct.pack("f", float(weight[keys[w]])))
            else:
                out += int(0).to_bytes(4, 'little')
        for x in range(4):
            if x < len(keys):
                out += bytearray(struct.pack("f", float(keys[x])))
            else:
                out += int(0).to_bytes(4, 'little')
        
        for c in range(4):
            if len(colors) > 0:
                out += bytearray(struct.pack("f", colors[indice][c]))
            else:
                out += int(0).to_bytes(4, 'little')
                
    return out
    
def write_triangle(indices):
    out = bytes()
    
    triangle_strip = stripify(indices, True)
    
    for i in range(len(triangle_strip)):
        for j in range(len(triangle_strip[i])):
            out += int(triangle_strip[i][j]).to_bytes(2, 'little')
          
    return out
                
def write(mesh_name, texspace, indices, vertices, uvs, normals, colors, weights, bone_names, material_name, mode, single_bind = None, draw_priority = 21, mesh_type = 1, tints = None):
    # Get only used bones
    bone_names = used_bones(weights, bone_names)
    weights = used_weights(weights)
    
    # A tint that doesn't change over the mesh is stored once as a fixed attribute
    tint, tint_streamed = classify_tint(tints)
    att_buffer, stride = write_attributes(tint_streamed)
    fixed_buffer = write_fixed_tint(tint)

    # Get content data
    data_geometrie = write_geometrie(indices, vertices, uvs, normals, colors, weights, tints if tint_streamed else None)
    data_triangle = write_triangle(indices)

    # XPVB-------------------------------------------
    compress_geometrie = lz10.compress(data_geometrie) 
    xpvb = bytes()
    xpvb += bytes([int(x,0) for x in ["0x58", "0x50", "0x56", "0x42"] ])
    xpvb += int(16).to_bytes(2, 'little')
    xpvb += int(16 + len(att_buffer)).to_bytes(2, 'little')
    xpvb += int(16 + len(att_buffer) + len(fixed_buffer)).to_bytes(2, 'little')
    xpvb += int(stride).to_bytes(2, 'little')
    xpvb += int(len(data_geometrie)//stride).to_bytes(4, 'little')
    xpvb += att_buffer
    xpvb += fixed_buffer
    xpvb += compress_geometrie

    # XPVI-------------------------------------------
    compress_triangle = lz10.compress(data_triangle) 
    xpvi = bytes()
    xpvi += bytes([int(x,0) for x in ["0x58", "0x50", "0x56", "0x49", "0x02", "0x00", "0x0c", "0x00"] ])
    xpvi += int(len(data_triangle)/2).to_bytes(4, 'little')
    xpvi += compress_triangle

    # Material-------------------------------------------
    material = zlib.crc32(mesh_name.encode("shift-jis")).to_bytes(4, 'little')
    material += zlib.crc32(material_name.encode("shift-jis")).to_bytes(4, 'little')
    
    if single_bind:
        material += bytes([int(x,0) for x in ["0xF1", "0x69", "0x7E", "0x54"] ])
        material += zlib.crc32(single_bind.encode("shift-jis")).to_bytes(4, 'little')
    else:
        material += bytes.fromhex(mode[0])
        material += int(0).to_bytes(4, 'little')
        
    material += int(0).to_bytes(4, 'little')
    material += int(0).to_bytes(4, 'little')
    material += struct.pack("f", texspace[0][0]) # texspace_location x
    material += struct.pack("f", texspace[0][1]) # texspace_location y
    material += struct.pack("f", texspace[0][2]) # texspace_location z
    material += struct.pack("f", texspace[1][0]) # texspace_size x
    material += struct.pack("f", texspace[1][1]) # texspace_size y
    material += struct.pack("f", texspace[1][2]) # texspace_size z
    material += int(draw_priority).to_bytes(4, 'little')
    material += int(mesh_type).to_bytes(4, 'little')
    material += int(len(bone_names)).to_bytes(4, 'little')

    # Node ------------------------------------------
    node = bytes()
    for name in bone_names:
        name_bytes = name.encode("shift-jis")
        node += zlib.crc32(name_bytes).to_bytes(4, 'little')

    # Name ------------------------------------------
    xmpr_name = bytes()
    xmpr_name += mesh_name.encode('shift-jis')
    xmpr_name += int(0).to_bytes(4, 'little')
    xmpr_name += material_name.encode('shift-jis')
    xmpr_name += int(0).to_bytes(4, 'little')

    # XMPR ------------------------------------------
    xmpr = bytes()
    xmpr += bytes([int(x,0) for x in ["0x58", "0x4D", "0x50", "0x52"] ])
    xmpr += int(64).to_bytes(4, 'little')
    xmpr += int(len(xpvb) + len(xpvi) + 20).to_bytes(4, 'little')
    xmpr += int(84 + len(xpvb) + len(xpvi)).to_bytes(4, 'little')
    for i in range(3):
        xmpr += int(84 + len(xpvb) + len(xpvi) + len(material)).to_bytes(4, 'little')
        xmpr += int(0).to_bytes(4, 'little')
    xmpr += int(84 + len(xpvb) + len(xpvi) + len(material)).to_bytes(4, 'little')
    xmpr += int(len(node)).to_bytes(4, 'little')
    xmpr += int(84 + len(xpvb) + len(xpvi) + len(material) + len(node)).to_bytes(4, 'little')
    xmpr += int(len(mesh_name) + 1).to_bytes(4, 'little')
    xmpr += int(84 + len(xpvb) + len(xpvi) + len(material) + len(node) + len(mesh_name) + 4).to_bytes(4, 'little')
    xmpr += int(len(material_name) + 1).to_bytes(4, 'little')
    xmpr += bytes([int(x,0) for x in ["0x58", "0x50", "0x52", "0x4D"] ])
    xmpr += int(20).to_bytes(4, 'little')
    xmpr += int(len(xpvb)).to_bytes(4, 'little')
    xmpr += int(len(xpvb)+20).to_bytes(4, 'little')
    xmpr += int(len(xpvi)).to_bytes(4, 'little')
    xmpr += xpvb
    xmpr += xpvi
    xmpr += material
    xmpr += node
    xmpr += xmpr_name
 
    return xmpr

##########################################
# XMPR Open Function
##########################################

def read_vertex(vbuffer, fbuffer, index, stride, count, offset, size, aType):
    v = (0.0, 0.0, 0.0, 0.0)
    if count != 0x00:
        if aType == 0x01:
            # A fixed attribute is one value for the whole mesh, always 4 floats at a 4 bytes aligned offset
            fbuffer.seek(offset & 0xFC)
            fixed = fbuffer.read(16)
            if len(fixed) == 16:
                return struct.unpack("<4f", fixed)
        elif aType == 0x02:
            vbuffer.seek(index * stride + offset)
            return struct.unpack(f"<{count}f", vbuffer.read(size))
    return v

def parse_buffer(reader, node_table):
    vertices = {
        "positions": [],
        "normals": [],
        "uv_data0": [],
        "uv_data1": [],
        "weights": [],
        "bone_indices": [],
        "color_data": [],
        "tint_data": [],
    }
    
    xpvb_magic = struct.unpack("<4s", reader.read(4))[0]
    att_buffer_offset = struct.unpack("<H", reader.read(2))[0]
    unk_offset = struct.unpack("<H", reader.read(2))[0]
    vertex_buffer_offset = struct.unpack("<H", reader.read(2))[0]
    stride = struct.unpack("<H", reader.read(2))[0]
    vertex_count = struct.unpack("<I", reader.read(4))[0]
    
    reader.seek(att_buffer_offset)
    attbuffer = io.BytesIO(compressor.decompress(reader.read(unk_offset - att_buffer_offset)))
    aCount = [int] * 10
    aOffset = [int] * 10
    aSize = [int] * 10
    aType = [int] * 10
    for i in range(10):
        aCount[i]  = struct.unpack("<B", attbuffer.read(1))[0]
        aOffset[i] = struct.unpack("<B", attbuffer.read(1))[0]
        aSize[i]   = struct.unpack("<B", attbuffer.read(1))[0]
        aType[i]   = struct.unpack("<B", attbuffer.read(1))[0]
    attbuffer.close()
    
    fixed_data = b""
    if vertex_buffer_offset > unk_offset:
        reader.seek(unk_offset)
        fixed_data = compressor.decompress(reader.read(vertex_buffer_offset - unk_offset)) or b""
    fbuffer = io.BytesIO(fixed_data)

    reader.seek(vertex_buffer_offset)
    vbuffer = io.BytesIO(compressor.decompress(reader.read()))
    
    for i in range(vertex_count):
        for j in range(10):
            # Ignore attributes without elements
            if aCount[j] == 0:
                continue
            
            attribute = read_vertex(vbuffer, fbuffer, i, stride, aCount[j], aOffset[j], aSize[j], aType[j])

            if j == 0:
                vertices["positions"].append(
                    attribute[:3]
                )
            elif j == 1:
                vertices["tint_data"].append(
                    attribute
                )
            elif j == 2:
                vertices["normals"].append(
                    attribute[:3]
                )
            elif j == 4:
                uv_data0 = list(attribute)[:2]
                uv_data0[1] = 1.0 - uv_data0[1]
                vertices["uv_data0"].append(
                    tuple(uv_data0)
                )
            elif j == 5:
                uv_data1 = list(attribute)[:2]
                uv_data1[1] = 1.0 - uv_data1[1]
                vertices["uv_data1"].append(
                    tuple(uv_data1)
                )
            elif j == 7:
                vertices["weights"].append(
                    attribute
                )
            elif j == 8:
                bone_indices = attribute
                if node_table:
                    vertices["bone_indices"].append((
                        node_table[int(bone_indices[0])],
                        node_table[int(bone_indices[1])],
                        node_table[int(bone_indices[2])],
                        node_table[int(bone_indices[3])],
                    ))
            elif j == 9:
                vertices["color_data"].append(
                    attribute
                )
                
    fbuffer.close()
    vbuffer.close()
    reader.close()

    return vertices

def parse_index_buffer(reader):
    triangles = []
    
    xpvi_magic = struct.unpack("<4s", reader.read(4))[0]
    primitive_type = struct.unpack("<H", reader.read(2))[0]
    faces_offset = struct.unpack("<H", reader.read(2))[0]
    face_count = struct.unpack("<I", reader.read(4))[0]
    
    reader.seek(faces_offset)
    ibuffer = io.BytesIO(compressor.decompress(reader.read()))
    
    if primitive_type == 0:
        for i in range(0, face_count, 3):
            triangles.append(struct.unpack("<HHH", ibuffer.read(6)))
    elif primitive_type == 2:
        for i in range(face_count):
            triangles.append(struct.unpack("<H", ibuffer.read(2))[0])
        triangles = triangulate([triangles])
    else:
        raise NotImplementedError("Primitive Type not implemented")
    ibuffer.close()
    reader.close()
    
    return triangles

def open_xmpr(reader):
    xmpr_magic = struct.unpack("<4s", reader.read(4))[0]
    xprm_offset = struct.unpack("<I", reader.read(4))[0]
    xprm_lenght = struct.unpack("<I", reader.read(4))[0]
    properties_offset = struct.unpack("<I", reader.read(4))[0]
    unk_offset = struct.unpack("<I", reader.read(4))[0]
    unk_length = struct.unpack("<I", reader.read(4))[0]
    unk1_offset = struct.unpack("<I", reader.read(4))[0]
    unk1_length = struct.unpack("<I", reader.read(4))[0]
    unk2_offset = struct.unpack("<I", reader.read(4))[0]
    unk2_length = struct.unpack("<I", reader.read(4))[0]
    nodes_offset = struct.unpack("<I", reader.read(4))[0]
    nodes_lenght = struct.unpack("<I", reader.read(4))[0]
    mesh_name_offset = struct.unpack("<I", reader.read(4))[0]
    mesh_name_lenght = struct.unpack("<I", reader.read(4))[0]
    material_name_offset = struct.unpack("<I", reader.read(4))[0]
    material_name_length = struct.unpack("<I", reader.read(4))[0]
    
    reader.seek(xprm_offset)
    xprm_magic = struct.unpack("<4s", reader.read(4))[0]
    xpvb_offset = struct.unpack("<I", reader.read(4))[0]
    xpvb_lenght = struct.unpack("<I", reader.read(4))[0]
    xpvi_offset = struct.unpack("<I", reader.read(4))[0]
    xpvi_lenght = struct.unpack("<I", reader.read(4))[0]
    
    reader.seek(xpvb_offset + xprm_offset)
    xpvb = io.BytesIO(reader.read(xpvb_lenght))
    reader.seek(xpvi_offset + xprm_offset)
    xpvi = io.BytesIO(reader.read(xpvi_lenght))
    
    reader.seek(properties_offset)
    mesh_name_hash = struct.unpack("<I", reader.read(4))[0]
    mat_name_hash = struct.unpack("<I", reader.read(4))[0]
    unk_hash = struct.unpack("<I", reader.read(4))[0]
    mesh_name_split_hash = struct.unpack("<I", reader.read(4))[0]
    reader.read(32) # unk
    draw_priority = struct.unpack("<I", reader.read(4))[0]
    mesh_type = struct.unpack("<H", reader.read(2))[0]
    mesh_unk = struct.unpack("<H", reader.read(2))[0]
    nodes_count = struct.unpack("<I", reader.read(4))[0]
    
    reader.seek(nodes_offset)
    node_table = None
    if nodes_lenght != 0:
        node_table = []
        for i in range(nodes_count):
            node_table.append(unpack("<I", reader.read(4))[0])
    
    reader.seek(mesh_name_offset)
    mesh_name = reader.read(mesh_name_lenght).decode("shift-jis").replace("\x00", "")
    
    reader.seek(material_name_offset)
    material_name = reader.read(material_name_length).decode("shift-jis").replace("\x00", "")
    
    single_bind = None
    if nodes_lenght == 0:
        single_bind = mesh_name_split_hash
    
    reader.close()
    
    return {
        "vertices": parse_buffer(xpvb, node_table),
        "triangles": parse_index_buffer(xpvi),
        "node_table": node_table,
        "name": mesh_name,
        "material_name": material_name,
        "single_bind": single_bind,
        "draw_priority": draw_priority,
        "mesh_type": mesh_type,
    }
