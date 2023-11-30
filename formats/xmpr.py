import zlib
import struct
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
    
def index_of_geometrie(indices):
    final_indices = []
    
    used_indices = []
    for indice in indices:
        for i in range(3):
            geometrie = []
            
            for j in indice.keys():
                if indice[j] != []:
                    geometrie.append(indice[j][i])
            
            geometrie = tuple(geometrie)
            
            if geometrie not in used_indices:
                used_indices.append(geometrie)
                  
    for indice in indices:
        face = []
        
        for i in range(3):
            geometrie = []
            
            for j in indice.keys():
                if indice[j] != []:
                    geometrie.append(indice[j][i])
            
            geometrie = tuple(geometrie)
            face.append(used_indices.index(geometrie))
            
        face = tuple(face) 
        final_indices.append(face)
     
    return final_indices

def write_geometrie(indices, vertices, uvs, normals, colors, weights):
    out = bytes()
    
    indices = remove_dupe_indices(indices)
    
    for indice in indices:
        for v in vertices[indice['v']]:
            out += bytearray(struct.pack("f", v))
        for n in normals[indice['vn']]:
            out += bytearray(struct.pack("f", n))
        for vt in range(2):
            out += bytearray(struct.pack("f", uvs[indice['vt']][0]))
            out += bytearray(struct.pack("f", 1 - uvs[indice['vt']][1] ))
            
        weight = weights[indice['v']]
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
                out += bytearray(struct.pack("f", colors[indice['vc']][c]))
            else:
                out += int(0).to_bytes(4, 'little')
                
    return out
    
def write_triangle(indices):
    out = bytes()
    
    indices = index_of_geometrie(indices)
    triangle_strip = stripify(indices, True)
    
    for i in range(len(triangle_strip)):
        for j in range(len(triangle_strip[i])):
            out += int(triangle_strip[i][j]).to_bytes(2, 'little')
          
    return out
                
def write(mesh_name, indices, vertices, uvs, normals, colors, weights, bone_names, material_name, template):
    # Get only used bones
    bone_names = used_bones(weights, bone_names)
    weights = used_weights(weights)
    
    # Get content data
    data_geometrie = write_geometrie(indices, vertices, uvs, normals, colors, weights)
    data_triangle = write_triangle(indices)

    # XPVB-------------------------------------------
    compress_geometrie = lz10.compress(data_geometrie) 
    xpvb = bytes()
    xpvb += bytes([int(x,0) for x in ["0x58", "0x50", "0x56", "0x42", "0x10", "0x00", "0x3C", "0x00", "0x48", "0x00", "0x58", "0x00"] ])
    xpvb += int(len(data_geometrie)/88).to_bytes(4, 'little')
    xpvb += bytes([int(x,0) for x in ["0x40", "0x01", "0x00", "0x00", "0x03", "0x00", "0x0C", "0x02", "0x04", "0x00", "0x10", "0x01", "0x03", "0x0C", "0x0C", "0x02", "0x00", "0x00", "0x00", "0x00", "0x02", "0x18", "0x08", "0x02", "0x02", "0x20", "0x08", "0x02", "0x00", "0x00", "0x00", "0x00", "0x04", "0x28", "0x10", "0x02", "0x04", "0x38", "0x10", "0x02", "0x04", "0x48", "0x10", "0x02", "0x81", "0x00", "0x00", "0x00", "0x08", "0x00", "0x00", "0x80", "0x3F", "0x90", "0x03", "0x00"] ])
    xpvb += compress_geometrie

    # XPVI-------------------------------------------
    compress_triangle = lz10.compress(data_triangle) 
    xpvi = bytes()
    xpvi += bytes([int(x,0) for x in ["0x58", "0x50", "0x56", "0x49", "0x02", "0x00", "0x0c", "0x00"] ])
    xpvi += int(len(data_triangle)/2).to_bytes(4, 'little')
    xpvi += compress_triangle

    # Material-------------------------------------------
    material = zlib.crc32(mesh_name.encode("utf-8")).to_bytes(4, 'little')
    material += zlib.crc32(material_name.encode("utf-8")).to_bytes(4, 'little')
    material += bytes.fromhex(template.material)
    material += int(len(bone_names)).to_bytes(4, 'little')

    # Node ------------------------------------------
    node = bytes()
    for name in bone_names:
        name_bytes = name.encode("utf-8")
        node += zlib.crc32(name_bytes).to_bytes(4, 'little')

    # Name ------------------------------------------
    xmpr_name = bytes()
    xmpr_name += mesh_name.encode('utf_8')
    xmpr_name += int(0).to_bytes(4, 'little')
    xmpr_name += material_name.encode('utf_8')
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
    xmpr += int(84 + len(xpvb) + len(xpvi) + len(material) + len(node) + len(mesh_name) + 2).to_bytes(4, 'little')
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

def read_attribute(data, offset, type, count):
    o = (0, 0, 0, 0)
    
    if type == 0:  # nothing
        pass
    elif type == 1:  # Vec3
        pass
    elif type == 2:  # Vec4
        if count > 0 and offset + 4 * count <= len(data):
            o = struct.unpack(f"<{count}f", data[offset:offset + 4 * count])
    else:
        raise Exception(f"Unknown Type 0x{type:02X}")

    return o

def parse_buffer(buffer, node_table):
    vertices = []
    attribute_buffer = bytearray()
    stride = 0
    vertex_count = 0

    offset = 0x4
    att_offset = struct.unpack("<H", buffer[offset:offset + 2])[0]
    offset += 2
    att_something = struct.unpack("<h", buffer[offset:offset + 2])[0]
    offset += 2
    ver_offset = struct.unpack("<H", buffer[offset:offset + 2])[0]
    offset += 2
    stride = struct.unpack("<h", buffer[offset:offset + 2])[0]
    offset += 2
    vertex_count = struct.unpack("<i", buffer[offset:offset + 4])[0]

    attribute_buffer = compressor.decompress(buffer[att_offset:att_offset + att_something])
    buffer = compressor.decompress(buffer[ver_offset:])

    ACount = [0] * 10
    AOffet = [0] * 10
    ASize = [0] * 10
    AType = [0] * 10

    offset = 0
    for i in range(10):
        ACount[i] = struct.unpack("<b", attribute_buffer[offset:offset + 1])[0]
        offset += 1
        AOffet[i] = struct.unpack("<b", attribute_buffer[offset:offset + 1])[0]
        offset += 1
        ASize[i] = struct.unpack("<b", attribute_buffer[offset:offset + 1])[0]
        offset += 1
        AType[i] = struct.unpack("<b", attribute_buffer[offset:offset + 1])[0]
        offset += 1

        if ACount[i] > 0 and i != 0 and i != 1 and i != 2 and i != 4 and i != 7 and i != 8 and i != 9:
            print(f"{i} {ACount[i]} {AOffet[i]} {ASize[i]} {AType[i]}")
            

    for i in range(vertex_count):
        vert = {}
        
        for j in range(10):
            offset = i * stride + AOffet[j]
            if j == 0:  # Position
                vert["positions"] = read_attribute(buffer, offset, AType[j], ACount[j])[:3]
            elif j == 1:  # Tangent
                pass
            elif j == 2:  # Normal
                vert["normals"] = read_attribute(buffer, offset, AType[j], ACount[j])[:3]
            elif j == 4:  # UV0
                uv_data = list(read_attribute(buffer, offset, AType[j], ACount[j])[:2])

                # Effectuer l'opération 1.0 - sur la composante Y des coordonnées UV
                uv_data[1] = 1.0 - uv_data[1]

                vert["uv_data"] = tuple(uv_data)
            elif j == 7:  # Bone Weight
                vert["weights"] = read_attribute(buffer, offset, AType[j], ACount[j])
            elif j == 8:  # Bone Index
                vn = read_attribute(buffer, offset, AType[j], ACount[j])
                if node_table and len(node_table) > 0 and len(node_table) != 1:
                    vert["bone_indices"] = (node_table[int(vn[0])], node_table[int(vn[1])], node_table[int(vn[2])], node_table[int(vn[3])])
            elif j == 9:  # Color
                vert["color_data"] = read_attribute(buffer, offset, AType[j], ACount[j])[:4]

        vertices.append(vert)

    return vertices

def parse_index_buffer(buffer):
    indices = []
    primitive_type = 0
    face_count = 0

    offset = 0x04
    primitive_type = struct.unpack("<h", buffer[offset:offset + 2])[0]
    offset += 2
    face_offset = struct.unpack("<H", buffer[offset:offset + 2])[0]
    offset += 2
    face_count = struct.unpack("<i", buffer[offset:offset + 4])[0]

    buffer = compressor.decompress(buffer[face_offset:])

    if primitive_type != 2 and primitive_type != 0:
        raise NotImplementedError("Primitive Type not implemented")

    if primitive_type == 0:
        offset = 0
        for _ in range(face_count // 2):
            indices.append(struct.unpack("<H", buffer[offset:offset + 2])[0])
            offset += 2
    elif primitive_type == 2:
        # Triangle strip
        offset = 0
        for i in range(face_count):
            indices.append(struct.unpack("<H", buffer[offset:offset + 2])[0])
            offset += 2
        
        indices = triangulate([indices])

    return indices

def open(data):
    offset = 4
    prm_offset = struct.unpack("<I", data[offset:offset + 4])[0]
    
    offset = prm_offset + 4

    # Buffers
    pvb_offset = struct.unpack("<I", data[offset:offset + 4])[0] + prm_offset
    offset += 4
    pvb_size = struct.unpack("<i", data[offset:offset + 4])[0]
    offset += 4

    pvi_offset = struct.unpack("<I", data[offset:offset + 4])[0] + prm_offset
    offset += 4
    pvi_size = struct.unpack("<i", data[offset:offset + 4])[0] 
    offset += 4

    polygon_vertex_buffer = data[pvb_offset : pvb_offset + pvb_size]
    polygon_vertex_index_buffer = data[pvi_offset : pvi_offset + pvi_size]

    # Node Table
    offset = 0x28
    no_offset = struct.unpack("<I", data[offset:offset + 4])[0]
    offset += 4

    no_size = struct.unpack("<i", data[offset:offset + 4])[0] // 4 + 1
    offset += 4

    node_table = []
    offset = no_offset
    for _ in range(no_size):
        node_table.append(struct.unpack("<I", data[offset:offset + 4])[0])
        offset += 4

    # Name and Material
    offset = 0x30
    name_position, name_length = struct.unpack("<II", data[offset:offset + 8])
    offset += 8
    name = data[name_position: name_position + name_length-1].decode('utf-8')

    material_position, material_length = struct.unpack("<II", data[offset:offset + 8])
    offset += 8
    material_name = data[material_position:material_position + material_length-1].decode('utf-8')

    return {
        "vertices": parse_buffer(polygon_vertex_buffer, node_table),
        "triangles": parse_index_buffer(polygon_vertex_index_buffer),
        "node_table": node_table,
        "name": name,
        "material_name": material_name
    }