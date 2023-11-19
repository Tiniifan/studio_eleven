import os
import math
import zlib
import struct
from ..compression import *

def calculate_f1_f2(file_count):
    if file_count < 256:
        f1 = file_count
        f2 = 2 ** (int(math.log2(file_count)))
        f2 = int(f2)
    else:
        f1 = file_count & 0xFF
        f2 = (file_count >> 8) & 0xFF
    
    return (f2 << 8) | f1

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
    
    with open(file_item, 'rb') as file:
        data = file.read()
        header = struct.unpack("4s", data[:4])[0].decode()
        if header != "XPCK":
            raise Exception("File header error")

        file_count = struct.unpack("<H", data[4:6])[0] & 0xFFF
        file_info_offset = struct.unpack("<H", data[6:8])[0] * 4
        file_table_offset = struct.unpack("<H", data[8:10])[0] * 4
        data_offset = struct.unpack("<H", data[10:12])[0] * 4
        filename_table_size = struct.unpack("<H", data[14:16])[0] * 4

        hash_to_data = {}
        for i in range(file_count):
            name_crc = struct.unpack("<I", data[file_info_offset + i * 12 : file_info_offset + i * 12 + 4])[0]
            offset = struct.unpack("<H", data[file_info_offset + i * 12 + 6 : file_info_offset + i * 12 + 8])[0]
            size = struct.unpack("<H", data[file_info_offset + i * 12 + 8 : file_info_offset + i * 12 + 10])[0]
            offset_ext = struct.unpack("<B", data[file_info_offset + i * 12 + 10 : file_info_offset + i * 12 + 11])[0]
            size_ext = struct.unpack("<B", data[file_info_offset + i * 12 + 11 : file_info_offset + i * 12 + 12])[0]

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

def pack(files, output_file):
    offset = 0
    name_offset = 0
    
    # Sort filename by alphabetic
    file_names = list(files.keys())
    file_names.sort()
    sorted_files = {i: files[i] for i in file_names}
    files = sorted_files
    
    # Modifie le dictionnaire
    for key, value in files.items():
        files[key] = {"data": fill(value), "offset": offset, "name_offset": name_offset}
        offset += len(fill(value))
        name_offset += len(key) + 1

    # Encode les noms de fichier en UTF-8 et les compresse avec zlib
    name_table = b''.join([filename.encode("utf-8") + b'\x00' for filename in list(files.keys())])
    compressed_name_table = lz10.compress(name_table)
    compressed_name_table = fill_to_multiple_of_16(compressed_name_table, 12 * len(file_names) + 20 + len(compressed_name_table))

    # Écrit l'entête du fichier XPCK
    with open(output_file, 'wb') as file:
        file.write(struct.pack("4s", "XPCK".encode()))
        file.write(struct.pack("<H", calculate_f1_f2(len(files))))
        file.write(struct.pack("<H", 20 // 4))
        file.write(struct.pack("<H", (20 + len(files) * 12) // 4))
        file.write(struct.pack("<H", (20 + len(files) * 12 + len(compressed_name_table)) // 4))
        file.write(struct.pack("<H", len(files) * 12 // 4))
        file.write(struct.pack("<H", len(compressed_name_table) // 4))

        data_size = 0
        for data in files.values():
            data_size += len(data["data"])
            
        file.write(struct.pack("<I", offset // 4))

        # Sort file name by crc32
        key_crc32 = {}
        for filename in list(files.keys()):
            key_crc32[zlib.crc32(filename.encode("utf-8"))] = filename

        # Écrit les informations de fichier pour chaque fichier
        sorted_by_crc32 = sorted(list(files.keys()), key=lambda x: zlib.crc32(x.encode("utf-8")))
        for filename in sorted_by_crc32:
            name_crc = zlib.crc32(filename.encode("utf-8"))

            shifted_offset = files[filename]["offset"] >> 2
            offset_higher = shifted_offset & 0xFFFF
            offset_lower = shifted_offset >> 16
            
            file_size = len(files[filename]["data"])
            size_higher = file_size & 0xFFFF
            size_lower = file_size >> 16
            
            file.write(struct.pack("<I", name_crc))
            file.write(struct.pack("<H", files[filename]["name_offset"]))
            file.write(struct.pack("<H", offset_higher))
            file.write(struct.pack("<H", size_higher))
            file.write(struct.pack("<B", offset_lower))
            file.write(struct.pack("<B", size_lower))

        # Écrit la table de noms
        file.write(compressed_name_table)

        # Écrit les données de fichier compressées
        for filename in list(files.keys()):
            file_data = files[filename]["data"]
            file.write(file_data)
