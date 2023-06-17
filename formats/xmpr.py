import zlib
import struct
from ..utils import *
from ..compression import lz10

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
