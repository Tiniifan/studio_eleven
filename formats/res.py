import zlib
import struct
from ..compression import lz10

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