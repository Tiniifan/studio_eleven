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
                
def write(mesh_name, dimensions, indices, vertices, uvs, normals, colors, weights, bone_names, material_name, mode, single_bind = None, draw_priority = 21):
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
    material += int(0).to_bytes(4, 'little')
    material += int(0).to_bytes(4, 'little')
    material += int(0).to_bytes(4, 'little')
    material += struct.pack("f", dimensions[0]/2)
    material += struct.pack("f", dimensions[1]/2)
    material += struct.pack("f", dimensions[2]/2)
    material += int(draw_priority).to_bytes(4, 'little')
    material += int(mode[1]).to_bytes(4, 'little')
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

def read_vertex(reader, count, aType, size):
    v = (0.0, 0.0, 0.0, 0.0)
    if count != 0x00:
        if aType == 0x02:
            return struct.unpack(f"<{count}f", reader.read(size))
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
    
    reader.seek(vertex_buffer_offset)
    vbuffer = io.BytesIO(compressor.decompress(reader.read()))
    
    for i in range(vertex_count):
        for j in range(10):
            vbuffer.seek(i * stride + aOffset[j])
            
            # Ignore attributes without elements
            if aCount[j] == 0:
                continue
            
            if j == 0:
                vertices["positions"].append(
                    read_vertex(vbuffer, aCount[j], aType[j], aSize[j])[:3]
                )
            elif j == 2:
                vertices["normals"].append(
                    read_vertex(vbuffer, aCount[j], aType[j], aSize[j])[:3]
                )
            elif j == 4:
                uv_data0 = list(read_vertex(vbuffer, aCount[j], aType[j], aSize[j]))[:2]
                uv_data0[1] = 1.0 - uv_data0[1]
                vertices["uv_data0"].append(
                    tuple(uv_data0)
                )
            elif j == 5:
                uv_data1 = list(read_vertex(vbuffer, aCount[j], aType[j], aSize[j]))[:2]
                uv_data1[1] = 1.0 - uv_data1[1]
                vertices["uv_data1"].append(
                    tuple(uv_data1)
                )
            elif j == 7:
                vertices["weights"].append(
                    read_vertex(vbuffer, aCount[j], aType[j], aSize[j])
                )
            elif j == 8:
                bone_indices = read_vertex(vbuffer, aCount[j], aType[j], aSize[j])
                if node_table:
                    vertices["bone_indices"].append((
                        node_table[int(bone_indices[0])],
                        node_table[int(bone_indices[1])],
                        node_table[int(bone_indices[2])],
                        node_table[int(bone_indices[3])],
                    ))
            elif j == 9:
                vertices["color_data"].append(
                    read_vertex(vbuffer, aCount[j], aType[j], aSize[j])
                )
                
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
    unk_type = struct.unpack("<HH", reader.read(4))
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
    }
