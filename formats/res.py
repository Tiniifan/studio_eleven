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
    Mesh = 100
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
# RES Open Function
##########################################

def open_res(stream=None, data=None, string_table=None, items=None):
    string_table = string_table or {}
    items = items or {}

    if stream:
        with io.BytesIO(compressor.decompress(stream.read())) as reader:
            _read_data(reader, string_table, items)

    elif data:
        with io.BytesIO(compressor.decompress(data)) as reader:
            _read_data(reader, string_table, items)

    elif string_table and items:
        pass  # Already provided, no need to read data

    return items

def _read_data(reader, string_table, items):
    header = struct.unpack("<qhhhhhh", reader.read(20))
    string_offset = header[1] << 2
    material_table_offset = header[3] << 2
    material_table_count = header[4]
    node_offset = header[5] << 2
    node_count = header[6]

    reader.seek(string_offset)
    text_section = reader.read()

    text_reader = io.BytesIO(text_section)
    while text_reader.tell() < len(text_section):
        name = read_string(text_reader)
        
        if name == '':
            break
        else:
            name_crc = zlib.crc32(name.encode("shift-jis"))
            string_table[name_crc] = name

    _read_section_table(reader, material_table_offset, material_table_count, items, string_table, text_reader)
    _read_section_table(reader, node_offset, node_count, items, string_table, text_reader)
    
def get_object_name(type_reader, text_reader, string_table):
    material_crc32 = struct.unpack("<I", type_reader.read(4))[0]
                
    if material_crc32 in string_table:
        return string_table[material_crc32]
    else:
        text_reader.seek(struct.unpack("<I", type_reader.read(4))[0])
        name = read_string(text_reader)
        return name    

def _read_section_table(reader, table_offset, table_count, items, string_table, text_reader):
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
                

##########################################
# RES Write Function
##########################################

def write(resources):
    out = bytes()
    
    # Generate library data
    library_data, string_table = write_library(resources)
    
    # Header
    out += struct.pack("6s", "CHRC00".encode('utf-8'))
    out += struct.pack("<H", 0)
    out += struct.pack("<H", (len(library_data) + 20) // 4)
    out += struct.pack("<H", 1)
    out += struct.pack("<H", 5)
    out += struct.pack("<H", 4)
    out += struct.pack("<H", 13)
    out += struct.pack("<H", 2)
    out += library_data
    out += string_table

    return lz10.compress(out)
    
def get_string_table(resources):
    string_table = bytes()
    string_table_dict = {}
    
    # Process library names
    for key in resources['libraries'].keys():
        string_table_dict[key] = len(string_table)
        string_table += key.encode("utf-8") + struct.pack("B", 0)
        
    # Process texture names
    for key in resources['textures']:
        string_table_dict[key] = len(string_table)
        string_table += key.encode("utf-8") + struct.pack("B", 0)
        
    # Process mesh names
    for key in resources['meshes']:
        string_table_dict[key] = len(string_table)
        string_table += key.encode("utf-8") + struct.pack("B", 0)
        
    # Process bone names
    for key in resources['bones']:
        string_table_dict[key] = len(string_table)
        string_table += key.encode("utf-8") + struct.pack("B", 0)

    # Return the string table and the dictionary mapping names to string table indices
    return string_table, string_table_dict

def write_library(resources):
    # Initialize header table and data
    header_table = bytes()
    data = bytes()
    string_table, string_table_dict = get_string_table(resources)
    
    data_offset = 68

    # Add libraries header
    header_table += struct.pack("<H", data_offset >> 2)  # Data offset
    header_table += struct.pack("<H", len(resources['libraries'].keys()))  # Number of libraries
    header_table += struct.pack("<H", 220)  # Header type
    header_table += struct.pack("<H", 8)  # Header size
    for library_name in resources['libraries'].keys():
        # Add library data
        data += zlib.crc32(library_name.encode("utf-8")).to_bytes(4, 'little')  # Library name CRC32
        data += int(string_table_dict[library_name]).to_bytes(4, 'little')  # Library name string table index
        data_offset += 8

    # Add another libraries header
    header_table += struct.pack("<H", data_offset >> 2)  # Data offset
    header_table += struct.pack("<H", len(resources['libraries'].keys()))  # Number of libraries
    header_table += struct.pack("<H", 230)  # Header type
    header_table += struct.pack("<H", 8)  # Header size
    for library_name in resources['libraries'].keys():
        # Add library data
        data += zlib.crc32(library_name.encode("utf-8")).to_bytes(4, 'little')  # Library name CRC32
        data += int(string_table_dict[library_name]).to_bytes(4, 'little')  # Library name string table index
        data_offset += 8

    # Add textures header
    header_table += struct.pack("<H", data_offset >> 2)  # Data offset
    header_table += struct.pack("<H", len(resources['textures']))  # Number of textures
    header_table += struct.pack("<H", 240)  # Header type
    header_table += struct.pack("<H", 20)  # Header size
    for texture_name in resources['textures']:
        # Add texture data
        data += zlib.crc32(texture_name.encode("utf-8")).to_bytes(4, 'little')  # Texture name CRC32
        data += int(string_table_dict[texture_name]).to_bytes(4, 'little')  # Texture name string table index
        data += bytes.fromhex("030500000000000000000000")  # Additional data
        data_offset += 20

    # Find the library with the maximum number of elements
    key_max = max(resources['libraries'].keys(), key=lambda k: len(resources['libraries'][k]))
    max_number_element = len(resources['libraries'][key_max])
    data_library_length = 16 + 52 * max_number_element

    # Add libraries data header
    header_table += struct.pack("<H", data_offset >> 2)  # Data offset
    header_table += struct.pack("<H", len(resources['libraries'].items()))  # Number of libraries
    header_table += struct.pack("<H", 290)  # Header type
    header_table += struct.pack("<H", data_library_length)  # Header size
    for key, value in resources['libraries'].items():
        # Add library data
        data += zlib.crc32(key.encode("utf-8")).to_bytes(4, 'little')  # Library name CRC32
        data += int(string_table_dict[key]).to_bytes(4, 'little')  # Library name string table index
        data += zlib.crc32(key.encode("utf-8")).to_bytes(4, 'little')  # Additional CRC32
        data += zlib.crc32(key.encode("utf-8")).to_bytes(4, 'little')  # Additional CRC32
        
        value.reverse()
        for i in range(max_number_element):
            if i < len(value):
                # Add element data
                data += zlib.crc32(value[i].encode("utf-8")).to_bytes(4, 'little')  # Element name CRC32
                data += int(1).to_bytes(4, 'little')  # Element value
            else:
                data += int(0).to_bytes(4, 'little')  # Element name CRC32 (empty)
                data += int(0).to_bytes(4, 'little')  # Element value (empty)
            
            data += bytes.fromhex("0000803F0000803F00000000000000000000803F00000000000000000000803F00000000000000000000803F")  # Additional data
            
        data_offset += data_library_length    

    # Add meshes header
    header_table += struct.pack("<H", data_offset >> 2)  # Data offset
    header_table += struct.pack("<H", len(resources['meshes']))  # Number of meshes
    header_table += struct.pack("<H", 100)  # Header type
    header_table += struct.pack("<H", 8)  # Header size
    for mesh_name in resources['meshes']:
        # Add mesh data
        data += zlib.crc32(mesh_name.encode("utf-8")).to_bytes(4, 'little')  # Mesh name CRC32
        data += int(string_table_dict[mesh_name]).to_bytes(4, 'little')  # Mesh name string table index
        data_offset += 8

    # Add bones header
    header_table += struct.pack("<H", data_offset >> 2)  # Data offset
    header_table += struct.pack("<H", len(resources['bones']))  # Number of bones
    header_table += struct.pack("<H", 110)  # Header type
    header_table += struct.pack("<H", 8)  # Header size
    for bone_name in resources['bones']:
        # Add bone data
        data += zlib.crc32(bone_name.encode("utf-8")).to_bytes(4, 'little')  # Bone name CRC32
        data += int(0).to_bytes(4, 'little')  # Bone name string table index
        data_offset += 8

    # Return the concatenated header table, data, and string table
    return header_table + data, string_table

##########################################
# XRES Open Function
##########################################

