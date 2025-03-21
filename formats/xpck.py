import os
import math
import zlib
from struct import pack, unpack
from ..compression import *

def file_count_to_hex(file_count):
    for i in range(12):
        var2 = 2 ** i
        if var2 > file_count:
            var2 = i
            break
    return ((var2 << 12) | file_count) & 0xFFFF

def fill(data):
    remainder = len(data) % 16
    
    if remainder != 0:
        missing_bytes = 16 - remainder
        return data + bytes.fromhex("".zfill(missing_bytes*2))
    else:
        return data
        
def fill_to_multiple_of_16(arr, pos):
    remainder = pos % 16
    
    if remainder == 0:
        return arr
    
    padding = 16 - remainder
    padding_bytes = bytes([0] * padding)
    
    return arr[:pos] + padding_bytes        

def open_file(file_item):
    files = {}
    
    if isinstance(file_item, str):
        # If the input is a filename
        with open(file_item, 'rb') as file:
            data = file.read()
    elif isinstance(file_item, (bytearray, bytes)):
        # If the input is a bytearray
        data = bytes(file_item)
    else:
        raise ValueError("Unsupported input type. Please provide a filename or a bytearray.")
    
    files = {}
    
    magic = data[:4]
    if magic == b"XFSP":
        file_count = unpack("<H", data[4:6])[0] & 0xFFF
        file_info_offset = unpack("<H", data[6:8])[0] * 4
        file_table_offset = unpack("<H", data[8:10])[0] * 4
        data_offset = unpack("<H", data[10:12])[0] * 4
        filename_table_size = unpack("<H", data[14:16])[0] * 4
        
        name_table = data[file_table_offset : file_table_offset + filename_table_size]
        name_table = compressor.decompress(name_table)
        
        for i in range(file_count):
            unk = unpack("<H", data[file_info_offset + i * 10 + 0 : file_info_offset + i * 10 + 2])[0]
            name_offset = unpack("<H", data[file_info_offset + i * 10 + 2: file_info_offset + i * 10 + 4])[0]
            offset = unpack("<H", data[file_info_offset + i * 10 + 4 : file_info_offset + i * 10 + 6])[0]
            size = unpack("<H", data[file_info_offset + i * 10 + 6 : file_info_offset + i * 10 + 8])[0]
            offset_ext = unpack("<B", data[file_info_offset + i * 10 + 8 : file_info_offset + i * 10 + 9])[0]
            size_ext =  unpack("<B", data[file_info_offset + i * 10 + 9 : file_info_offset + i * 10 + 10])[0]
            
            offset |= offset_ext << 16
            size |= size_ext << 16
            offset = offset * 4 + data_offset
            
            file_data = data[offset : offset + size]
            
            # Get name
            name_length = name_table.find(b'\x00', name_offset)
            name = name_table[name_offset:name_length].decode("utf-8")
            
            files[name] = file_data
            
        return files
    elif magic == b"XPCK":
        file_count = unpack("<H", data[4:6])[0] & 0xFFF
        file_info_offset = unpack("<H", data[6:8])[0] * 4
        file_table_offset = unpack("<H", data[8:10])[0] * 4
        data_offset = unpack("<H", data[10:12])[0] * 4
        filename_table_size = unpack("<H", data[14:16])[0] * 4
        
        hash_to_data = {}
        for i in range(file_count):
            name_crc = unpack("<I", data[file_info_offset + i * 12 : file_info_offset + i * 12 + 4])[0]
            offset = unpack("<H", data[file_info_offset + i * 12 + 6 : file_info_offset + i * 12 + 8])[0]
            size = unpack("<H", data[file_info_offset + i * 12 + 8 : file_info_offset + i * 12 + 10])[0]
            offset_ext = unpack("<B", data[file_info_offset + i * 12 + 10 : file_info_offset + i * 12 + 11])[0]
            size_ext = unpack("<B", data[file_info_offset + i * 12 + 11 : file_info_offset + i * 12 + 12])[0]
            
            offset |= offset_ext << 16
            size |= size_ext << 16
            offset = offset * 4 + data_offset
            
            file_data = data[offset : offset + size]
            
            hash_to_data[name_crc] = file_data
        
        name_table = data[file_table_offset : file_table_offset + filename_table_size]
        name_table = compressor.decompress(name_table)
        
        pos = 0
        for i in range(file_count):
            name_length = name_table.find(b'\x00', pos)
            name = name_table[pos:name_length].decode("utf-8")
            pos = name_length + 1
            
            crc = zlib.crc32(name.encode("utf-8"))
            if crc in hash_to_data:
                files[name] = hash_to_data[crc]
            else:
                print("Couldn't find", name, hex(crc))
        
        return files
    else:
        raise Exception(f"Unknown xc magic: {magic}")

def pack_archive(files, output_file):
    offset = 0
    name_offset = 0
    
    # Sort filename by alphabetic
    file_names = list(files.keys())
    file_names.sort()
    sorted_files = {i: files[i] for i in file_names}
    files = sorted_files
    
    # Modify the dictionary
    for key, value in files.items():
        files[key] = {"data": fill(value), "offset": offset, "name_offset": name_offset}
        offset += len(fill(value))
        name_offset += len(key) + 1

    # Encodes filenames in UTF-8 and compresses them with zlib
    name_table = b''.join([filename.encode("utf-8") + b'\x00' for filename in list(files.keys())])
    compressed_name_table = lz10.compress(name_table)
    compressed_name_table = fill_to_multiple_of_16(compressed_name_table, 12 * len(file_names) + 20 + len(compressed_name_table))

    # Writes XPCK file header
    with open(output_file, 'wb') as file:
        file.write(pack("4s", "XPCK".encode()))
        file.write(pack("<H", file_count_to_hex(len(files))))
        file.write(pack("<H", 20 // 4))
        file.write(pack("<H", (20 + len(files) * 12) // 4))
        file.write(pack("<H", (20 + len(files) * 12 + len(compressed_name_table)) // 4))
        file.write(pack("<H", len(files) * 12 // 4))
        file.write(pack("<H", len(compressed_name_table) // 4))

        data_size = 0
        for data in files.values():
            data_size += len(data["data"])
            
        file.write(pack("<I", offset // 4))

        # Sort file name by crc32
        key_crc32 = {}
        for filename in list(files.keys()):
            key_crc32[zlib.crc32(filename.encode("utf-8"))] = filename

        # Writes file information for each file
        sorted_by_crc32 = sorted(list(files.keys()), key=lambda x: zlib.crc32(x.encode("utf-8")))
        for filename in sorted_by_crc32:
            name_crc = zlib.crc32(filename.encode("utf-8"))

            shifted_offset = files[filename]["offset"] >> 2
            offset_higher = shifted_offset & 0xFFFF
            offset_lower = shifted_offset >> 16
            
            file_size = len(files[filename]["data"])
            size_higher = file_size & 0xFFFF
            size_lower = file_size >> 16
            
            file.write(pack("<I", name_crc))
            file.write(pack("<H", files[filename]["name_offset"]))
            file.write(pack("<H", offset_higher))
            file.write(pack("<H", size_higher))
            file.write(pack("<B", offset_lower))
            file.write(pack("<B", size_lower))

        # Write name table
        file.write(compressed_name_table)

        # Writes compressed file data
        for filename in list(files.keys()):
            file_data = files[filename]["data"]
            file.write(file_data)
