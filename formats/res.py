import io
import zlib
import struct

from enum import Enum
from ..compression import *

##########################################
# RESType
##########################################

class RESType(Enum):
    Bone = 110
    Textproj = 140
    BoundingBoxParameter = 200
    Shading = 120
    Material1 = 220
    Material2 = 230
    MeshName = 100
    Texture = 240
    MaterialData = 290
    animation_mtn2 = 300
    animation_mtn3 = 301
    Animation2 = 310
    mtninf = 400
    mtninf2 = 401
    AnimationSplit2 = 410
    Null = 9999
    MaterialTypeUnk1 = 0
    MaterialTypeUnk2 = 1
    NodeTypeUnk1 = 2
    NodeTypeUnk2 = 3
    NodeTypeUnk3 = 4
    NodeTypeUnk4 = 460
    NodeTypeUnk5 = 320
    NodeTypeUnk6 = 420
    NodeTypeUnk7 = 20
    
materials_ordered = [
    RESType.MaterialTypeUnk1,
    RESType.Material1,
    RESType.Material2,
    RESType.Texture,
    RESType.MaterialTypeUnk2,
    RESType.MaterialData,
]

nodes_ordered = [
    RESType.MeshName,
    RESType.Bone,
    RESType.animation_mtn2,
    RESType.animation_mtn3,
    RESType.Animation2,
    RESType.NodeTypeUnk1,
    RESType.Shading,
    RESType.NodeTypeUnk2,
    RESType.BoundingBoxParameter,
    RESType.mtninf,
    RESType.mtninf2,
    RESType.AnimationSplit2,
    RESType.NodeTypeUnk3,
    RESType.Textproj,
]

##########################################
# Read String
##########################################
    
def read_string(byte_io):
    bytes_list = []
    
    while True:
        byte = byte_io.read(1)
        if byte == b'\x00':
            break
        bytes_list.append(byte)
    
    name = b''.join(bytes_list).decode('shift-jis')
    return name    

##########################################
# RES
##########################################

def open_res(stream=None, data=None, string_table=None, items=None):
    string_table = string_table or {}
    items = items or {}

    if stream:
        with io.BytesIO(compressor.decompress(stream.read())) as reader:
            read_data(reader, string_table, items)

    elif data:
        with io.BytesIO(compressor.decompress(data)) as reader:
            read_data(reader, string_table, items)

    elif string_table and items:
        pass  # Already provided, no need to read data

    return items

def read_data(reader, string_table, items):
    header = struct.unpack("<qhhhhhh", reader.read(20))
    string_offset = header[1] << 2
    material_table_offset = header[3] << 2
    material_table_count = header[4]
    node_offset = header[5] << 2
    node_count = header[6]

    reader.seek(string_offset)
    text_reader = io.BytesIO(reader.read())
    text_section = text_reader.read().decode("shift-jis").split("\x00")
    for text in text_section:
        if text == "":
            continue
        
        crc32text = zlib.crc32(text.encode("shift-jis"))
        if crc32text not in string_table:
            string_table[crc32text] = text
        
        text_split = text.split(".")
        for t in text_split:
            crc32text_split = zlib.crc32(t.encode("shift-jis"))
            if crc32text_split not in string_table:
                string_table[crc32text_split] = t
        
        text_split = text.split("_")
        for t in text_split:
            crc32text_split = zlib.crc32(t.encode("shift-jis"))
            if crc32text_split not in string_table:
                string_table[crc32text_split] = t
    
    read_section_table(reader, material_table_offset, material_table_count, items, string_table, text_reader)
    read_section_table(reader, node_offset, node_count, items, string_table, text_reader)
    
def get_object_name(type_reader, text_reader, string_table):
    material_crc32 = struct.unpack("<I", type_reader.read(4))[0]
                
    if material_crc32 in string_table:
        return string_table[material_crc32]
    else:
        text_reader.seek(struct.unpack("<I", type_reader.read(4))[0])
        name = read_string(text_reader)
        return name    

def read_section_table(reader, table_offset, table_count, items, string_table, text_reader):
    for i in range(table_count):
        reader.seek(table_offset + i * 8)
        header_table = struct.unpack("<hhhh", reader.read(8))

        data_offset = header_table[0] << 2
        count = header_table[1]
        _type = header_table[2]
        length = header_table[3]
        
        if RESType(_type) == RESType.Null:
            continue

        if RESType(_type) not in items:
            items[RESType(_type)] = {}

        for j in range(count):
            reader.seek(data_offset + j * length)
            type_reader = io.BytesIO(reader.read(length))
            
            object_name = get_object_name(type_reader, text_reader, string_table)
            object_crc32 = zlib.crc32(object_name.encode("shift-jis"))
            
            if length == 8:
                items[RESType(_type)][object_crc32] = object_name
            elif RESType(_type) == RESType.Texture:
                type_reader.seek(8)
                texture_unk = struct.unpack("<b", type_reader.read(1))[0]
                next_facial_expression = struct.unpack("<b", type_reader.read(1))[0]
                
                texture_dict = {}
                texture_dict['name'] = object_name
                texture_dict['texture_unk'] = texture_unk
                texture_dict['next_facial_expression'] = next_facial_expression
                
                items[RESType(_type)][object_crc32] = texture_dict
            elif RESType(_type) == RESType.MaterialData:
                type_reader.seek(16)
                linked_textures = []
                
                max_texture = (length-16) // 52
                for k in range(max_texture):
                    texture_crc32 = struct.unpack("<I", type_reader.read(4))[0]
                    
                    if texture_crc32 != 0:    
                        linked_textures.append(hex(texture_crc32))
                                        
                    type_reader.seek(type_reader.tell() + 48)        
                
                material_dict = {}
                material_dict['name'] = object_name
                material_dict['textures'] = linked_textures
                
                items[RESType(_type)][object_crc32] = material_dict               

def make_library(meshes = [], armature = None, textures = {}, animation = {}, split_animations = [], outline_name = "", properties=[], texprojs=[]):
    items = {}
    string_table = bytes()
        
    if textures:
        lib_names = []
        textures_name = []
        textures_data = []
        
        for key, value in textures.items():
            lib_name = key.encode("shift-jis")
            lib_name_crc32 = zlib.crc32(lib_name).to_bytes(4, 'little')
            
            lib_names.append(lib_name_crc32 + int(len(string_table)).to_bytes(4, 'little'))

            texture_data = lib_name_crc32 + int(len(string_table)).to_bytes(4, 'little') + lib_name_crc32 + lib_name_crc32
            for i in range(4):
                if i < len(value):
                    texture_name = value[i].name.encode("shift-jis")
                    texture_data += zlib.crc32(texture_name).to_bytes(4, 'little') + bytes.fromhex("010000000000803F0000803F00000000000000000000803F00000000000000000000803F00000000000000000000803F")
                else:
                    texture_data += bytes.fromhex("00000000000000000000803F0000803F00000000000000000000803F00000000000000000000803F00000000000000000000803F")
                    
            textures_data.append(texture_data)
            
            string_table += lib_name + int(0).to_bytes(1, 'little')
            
            for texture in value:
                texture_name = texture.name.encode("shift-jis")
                textures_name.append(zlib.crc32(texture_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little') + bytes.fromhex("030A00000000000000000000"))
                string_table += texture_name + int(0).to_bytes(1, 'little')        
            
        items[RESType.Material1] = lib_names
        items[RESType.Material2] = lib_names
        items[RESType.Texture] = textures_name
        items[RESType.MaterialData] = textures_data
        
    if meshes:
        meshes_name = []
        
        for mesh in meshes:
            mesh_name = mesh.name.encode("shift-jis")
            meshes_name.append(zlib.crc32(mesh_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))   
            string_table += mesh_name + int(0).to_bytes(1, 'little')
                
        items[RESType.MeshName] = meshes_name
        
    if armature:
        bones_name = []
        
        for bone in armature.pose.bones:
            bone_name = bone.name.encode("shift-jis")
            bones_name.append(zlib.crc32(bone_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))    
            string_table += bone_name + int(0).to_bytes(1, 'little')

        items[RESType.Bone] = bones_name
        
    if animation:
        animation_name = []
        split_animation_name = []

        name = animation[0].encode("shift-jis")
        animation_name.append(zlib.crc32(name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))
        string_table += name + int(0).to_bytes(1, 'little')
        
        for split_animation in split_animations:
            split_name = split_animation.name.encode("shift-jis")
            split_animation_name.append(zlib.crc32(split_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))   
            string_table += split_name + int(0).to_bytes(1, 'little')
        
        if animation[1] == 'MTN2':
            items[RESType.animation_mtn2] = animation_name
        elif animation[1] == 'MTN3':
            items[RESType.animation_mtn3] = animation_name
        
        if split_animations:
            if animation[2] == 'MTNINF':
                items[RESType.mtninf] = split_animation_name
            elif animation[2] == 'MTNINF2':
                items[RESType.mtninf2] = split_animation_name            

    if outline_name:
        name = outline_name.encode("shift-jis")
        string_table += name + int(0).to_bytes(1, 'little')
        items[RESType.Shading] = [name]
        
    if properties:
        properties_name = []
        
        for archive_property in properties:
            property_name = archive_property[0].encode("shift-jis")
            properties_name.append(zlib.crc32(property_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))
            string_table += property_name + int(0).to_bytes(1, 'little')
            
        items[RESType.BoundingBoxParameter] = properties_name
        
    if texprojs:
        texprojs_name = []
        
        for texproj in texprojs:
            texproj_name = texproj[0].encode("shift-jis")
            texprojs_name.append(zlib.crc32(texproj_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))
            string_table += texproj_name + int(0).to_bytes(1, 'little')
            
        items[RESType.Textproj] = texprojs_name
        
    return items, string_table
                
def write_res(magic, items, string_table):
    materials = {key: value for key, value in items.items() if key in materials_ordered}
    nodes = {key: value for key, value in items.items() if key in nodes_ordered}

    header = {
        'Magic': int.from_bytes(magic, byteorder='little'),
        '_stringOffset': 0,  # Placeholder for string offset
        'Unk1': 1,
        '_materialTableOffset': 0,  # Placeholder for material table offset
        'MaterialTableCount': len(materials),
        '_nodeOffset': 0,  # Placeholder for node offset
        'NodeCount': len(nodes),
    }

    header_pos = 20
    data_pos = header_pos + len(items) * 8

    with io.BytesIO() as writer_res:
        with io.BytesIO() as writer_table:
            with io.BytesIO() as writer_data:
                # Material - Header table
                if materials:
                    header['_materialTableOffset'] = header_pos >> 2

                    for res_type, res_value in materials.items():
                        material_header_table = {
                            '_dataOffset': data_pos >> 2,
                            'Count': len(res_value),
                            'Type': res_type.value,
                            'Length': len(res_value[0]),
                        }

                        header_pos += 8
                        data_pos += sum(len(byte_array) for byte_array in res_value)

                        writer_table.write(struct.pack('<hhhh', *material_header_table.values()))
                        writer_data.write(b''.join(res_value))

                # Node - Header table
                if nodes:
                    header['_nodeOffset'] = header_pos >> 2

                    for res_type, res_value in nodes.items():
                        node_header_table = {
                            '_dataOffset': data_pos >> 2,
                            'Count': len(res_value),
                            'Type': res_type.value,
                            'Length': len(res_value[0]),
                        }

                        header_pos += 8
                        data_pos += sum(len(byte_array) for byte_array in res_value)

                        writer_table.write(struct.pack('<hhhh', *node_header_table.values()))
                        writer_data.write(b''.join(res_value))

                # String table
                header['_stringOffset'] = writer_data.tell() + 20 + len(items) * 8 >> 2
                writer_data.write(string_table)
                        
                # Calculate padding for alignment
                remaining_bytes = 4 - (writer_res.tell() % 4)
                if remaining_bytes != 4:
                    padding = bytes([0] * remaining_bytes)
                    writer_res.write(padding)                        

                writer_res.seek(0)
                writer_res.write(struct.pack('<qhhhhhh', *header.values()))
                writer_res.write(writer_table.getvalue())
                writer_res.write(writer_data.getvalue())
                
                return compress(writer_res.getvalue())

##########################################
# XRES
##########################################

