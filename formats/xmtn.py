import io
import struct
import numpy as np
import math
import mathutils
import zlib
from ..animation import *
from ..compression import *

##########################################
# XMTN Function
##########################################

def table_offset(frame_offset, frame_transform):
    out = bytes()
    out += int(frame_offset).to_bytes(4, 'little')
    out += int(frame_offset + 4).to_bytes(4, 'little')
    out += int(frame_offset + 4 + len(frame_transform) * 2).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    return out

def node_modified(node, frames):
    frames_count = len(frames)
    low_frame_count = frames_count & 0xFF
    high_frame_count = (32 + (frames_count >> 8)) & 0xFF

    out = bytes()
    out += int(node).to_bytes(2, 'little')
    out += int(low_frame_count).to_bytes(1, 'little')
    out += int(high_frame_count).to_bytes(1, 'little')
    
    return out

def frame_modified(frame_key):
    return int(frame_key).to_bytes(2, 'little')

def read_string(byte_io):
    bytes_list = []
    
    while True:
        byte = byte_io.read(1)
        if byte == b'\x00':
            break
        bytes_list.append(byte)
    
    name = b''.join(bytes_list).decode('shift-jis')
    return name

def read_frame_data(data, offset, count, data_offset, bone_name_hashes, track, node):
    for i in range(offset, offset + count):
        data.seek(data_offset + 4 * 4 * i)
        flag_offset = struct.unpack("<I", data.read(4))[0]
        key_frame_offset = struct.unpack("<I", data.read(4))[0]
        key_data_offset = struct.unpack("<I", data.read(4))[0]

        data.seek(flag_offset)
        bone_index = struct.unpack("<h", data.read(2))[0]
        low_frame_count = struct.unpack("<B", data.read(1))[0]
        high_frame_count = struct.unpack("<B", data.read(1))[0] - 32

        key_frame_count = (high_frame_count << 8) | low_frame_count

        bone_name_hash = bone_name_hashes[bone_index]
        
        data.seek(key_data_offset)
        for k in range(key_frame_count):
            temp = data.tell()
            data.seek(key_frame_offset + k * 2)
            frame = struct.unpack("<h", data.read(2))[0]
            data.seek(temp)

            anim_data = [0] * track["data_count"]
            for j in range(track["data_count"]):
                if track["data_type"] == 1:
                    anim_data[j] = struct.unpack("<h", data.read(2))[0] / float(0x7FFF)
                elif track["data_type"] == 2:
                    anim_data[j] = struct.unpack("<f", data.read(4))[0]
                elif track["data_type"] == 4:
                    anim_data[j] = struct.unpack("<h", data.read(2))[0]
                else:
                    raise NotImplementedError(f"Data Type {track['data_type']} not implemented")

            if frame not in node:
                node[frame] = {}

            if bone_name_hash not in node[frame]:
                node[frame][bone_name_hash] = {}

            if track["type"] == 1:
                node[frame][bone_name_hash]['location'] = Location(anim_data[0], anim_data[1], anim_data[2])
                location = Location(anim_data[0], anim_data[1], anim_data[2])
            elif track["type"] == 2:
                node[frame][bone_name_hash]['rotation'] = Rotation(anim_data[0], anim_data[1], anim_data[2], anim_data[3])
            elif track["type"] == 3:
                node[frame][bone_name_hash]['scale'] = Scale(anim_data[0], anim_data[1], anim_data[2])

    return node

def read_frame_data2(data, anim_table_offset, bone_name_hashes, track, node):
    for i in range(len(anim_table_offset)):
        data.seek(anim_table_offset[i]['flag_offset'])
        bone_index = struct.unpack('<h', data.read(2))[0]
        low_frame_count = struct.unpack('B', data.read(1))[0]
        high_frame_count = struct.unpack('B', data.read(1))[0] - 32

        key_frame_count = (high_frame_count << 8) | low_frame_count

        bone_name_hash = bone_name_hashes[bone_index]
        
        data.seek(anim_table_offset[i]['key_data_offset'])
        for k in range(key_frame_count):
            temp = data.tell()
            data.seek(anim_table_offset[i]['key_frame_offset'] + k * 2)
            frame = struct.unpack("<h", data.read(2))[0]
            data.seek(temp)

            anim_data = [0] * track["data_count"]
            for j in range(track["data_count"]):
                if track["data_type"] == 1:
                    anim_data[j] = struct.unpack("<h", data.read(2))[0] / float(0x7FFF)
                elif track["data_type"] == 2:
                    anim_data[j] = struct.unpack("<f", data.read(4))[0]
                elif track["data_type"] == 4:
                    anim_data[j] = struct.unpack("<h", data.read(2))[0]
                else:
                    raise NotImplementedError(f"Data Type {track['data_type']} not implemented")

            if frame not in node:
                node[frame] = {}

            if bone_name_hash not in node[frame]:
                node[frame][bone_name_hash] = {}

            if track["type"] == 1:
                node[frame][bone_name_hash]['location'] = Location(anim_data[0], anim_data[1], anim_data[2])
                location = Location(anim_data[0], anim_data[1], anim_data[2])
            elif track["type"] == 2:
                node[frame][bone_name_hash]['rotation'] = Rotation(anim_data[0], anim_data[1], anim_data[2], anim_data[3])
            elif track["type"] == 3:
                node[frame][bone_name_hash]['scale'] = Scale(anim_data[0], anim_data[1], anim_data[2])

##########################################
# XMTN2
##########################################

def open_mtn2(data):
    node = {}
    anim_name = ""
    frame_count = 0
    bone_name_hashes = []

    reader = io.BytesIO(data)
    size = len(reader.getbuffer())
    
    reader.seek(0x08)
    
    decom_size = struct.unpack("<I", reader.read(4))[0]
    name_offset = struct.unpack("<I", reader.read(4))[0]
    comp_data_offset = struct.unpack("<I", reader.read(4))[0]
    position_count = struct.unpack("<I", reader.read(4))[0]
    rotation_count = struct.unpack("<I", reader.read(4))[0]
    scale_count = struct.unpack("<I", reader.read(4))[0]
    unknown_count = struct.unpack("<I", reader.read(4))[0]
    bone_count = struct.unpack("<I", reader.read(4))[0]

    reader.seek(0x54)
    frame_count = struct.unpack("<I", reader.read(4))[0]

    reader.seek(name_offset)
    anim_hash = struct.unpack("<I", reader.read(4))[0]
    anim_name = read_string(reader)

    reader.seek(comp_data_offset)
    compressed_data = compressor.decompress(reader.read(size - comp_data_offset))
    data = io.BytesIO(compressed_data)
        
    bone_hash_table_offset = struct.unpack("<I", data.read(4))[0]
    track_info_offset = struct.unpack("<I", data.read(4))[0]
    data_offset = struct.unpack("<I", data.read(4))[0]

    # Bone Hashes
    data.seek(bone_hash_table_offset)
    while data.tell() < track_info_offset:
        bone_name_hashes.append(struct.unpack("<I", data.read(4))[0])

    # Track Information
    tracks = []
    for i in range(4):
        data.seek(track_info_offset + 2 * i)
        data.seek(struct.unpack("<H", data.read(2))[0])

        track = {}
        track["type"] = struct.unpack("<B", data.read(1))[0]
        track["data_type"] = struct.unpack("<B", data.read(1))[0]
        track["unk"] = struct.unpack("<B", data.read(1))[0]
        track["data_count"] = struct.unpack("<B", data.read(1))[0]
        track["start"] = struct.unpack("<H", data.read(2))[0]
        track["end"] = struct.unpack("<H", data.read(2))[0]
        tracks.append(track)

    offset = 0 
    read_frame_data(data, offset, position_count, data_offset, bone_name_hashes, tracks[0], node)
    offset += position_count
    read_frame_data(data, offset, rotation_count, data_offset, bone_name_hashes, tracks[1], node)
    offset += rotation_count
    read_frame_data(data, offset, scale_count, data_offset, bone_name_hashes, tracks[2],node)
    offset += scale_count
        
    return anim_name, frame_count, bone_name_hashes, node
    
def write_mtn2(name, nodes, frame_location, frame_rotation, frame_scale, frame_end):
    out = bytes()

    # for each node write the crc32 of node name
    table_node = bytes()
    for node in nodes:
        crc32 = zlib.crc32(node.encode("utf-8"))
        table_node += crc32.to_bytes(4, 'little')

    # write [table_node offset, transform offset, frames offset and table_node]
    out += int(12).to_bytes(4, 'little')
    out += int(12 + len(table_node)).to_bytes(4, 'little')
    out += int(52 + len(table_node)).to_bytes(4, 'little')
    out += table_node

    # write location, rotation, size offset
    type_offset = len(out)
    for i in range(1, 5):
        out += (type_offset + 8 * i).to_bytes(2, 'little')

    # write transform specify and the number of frame 
    for i in range(3):
        if i == 0:
            out += int("0x03000201", 16).to_bytes(4, 'little')
        elif i == 1:
            out += int("0x04000102", 16).to_bytes(4, 'little')
        elif i == 2: 
            out += int("0x03000203", 16).to_bytes(4, 'little')            
        out += int(0).to_bytes(2, 'little')
        out += frame_end.to_bytes(2, 'little')
    
    # write empty block
    out += int(0).to_bytes(8, 'little')
    
    # initialise bytes object to save frame data and frame_offset to save each offset of frame
    data_location = bytes()
    data_rotation = bytes()
    data_scale = bytes()
    frame_offset = len(out) + (len(frame_location) + len(frame_rotation) + len(frame_scale)) * 16
    
    # write data_location for each frame
    for node, frames in frame_location.items():
        # table
        out += table_offset(frame_offset, frames)
        frame_offset += len(frames) * 14 + 4;
        # node data
        data_location += node_modified(node, frames)
        # frame edited
        data_transform = bytes()
        for frame_key, frame_transform in frames.items():
            data_location += frame_modified(frame_key)
            data_transform += bytearray(struct.pack("f", frame_transform.location_x))
            data_transform += bytearray(struct.pack("f", frame_transform.location_y))
            data_transform += bytearray(struct.pack("f", frame_transform.location_z))
        data_location += data_transform

    # write data_rotation for each frame
    for node, frames in frame_rotation.items():
        # table
        out += table_offset(frame_offset, frames)
        frame_offset += len(frames) * 10 + 4;
        # node data
        data_rotation += node_modified(node, frames)
        # frame edited
        data_transform = bytes()
        for frame_key, frame_transform in frames.items():
            data_rotation += frame_modified(frame_key)
            quaternion = frame_transform.to_quaternion()
            for i in range(4):
                data_transform += int(quaternion[i] * 32767).to_bytes(2, 'little', signed=True)
        data_rotation += data_transform

    # write data_scale for each frame
    for node, frames in frame_scale.items():
        # table
        out += table_offset(frame_offset, frames)
        frame_offset += len(frames) * 14 + 4;
        # node data
        data_scale += node_modified(node, frames)
        # frame edited
        data_transform = bytes()
        for frame_key, frame_transform in frames.items():
            data_scale += frame_modified(frame_key)
            data_transform += bytearray(struct.pack("f", frame_transform.scale_x))
            data_transform += bytearray(struct.pack("f", frame_transform.scale_y))
            data_transform += bytearray(struct.pack("f", frame_transform.scale_z))
        data_scale += data_transform    

    # compress
    out += data_location + data_rotation + data_scale
    data_uncompress = len(out)
    data_compress = compress(out)    

    # create mtn
    out = int("0x4e544d58", 16).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    out += int(data_uncompress + 8316).to_bytes(4, 'little')
    out += int(40).to_bytes(4, 'little')
    name_bytes = name.encode("utf-8")
    name_bytes = zlib.crc32(name_bytes).to_bytes(4, 'little') + name_bytes
    out += int(88).to_bytes(4, 'little')
    out += int(len(frame_location)).to_bytes(4, 'little')
    out += int(len(frame_rotation)).to_bytes(4, 'little')
    out += int(len(frame_scale)).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    out += int(len(frame_location)).to_bytes(4, 'little')
    out += name_bytes
    out += int(0).to_bytes(40-len(name), 'little')
    out += int(frame_end).to_bytes(4, 'little')
    out += data_compress
    
    return out
    
##########################################
# XMTN3
##########################################

def open_mtn3(data):
    node = {}
    anim_name = ""
    frame_count = 0
    bone_name_hashes = []

    reader = io.BytesIO(data)
    size = len(reader.getbuffer())
    
    reader.seek(0x04)    
    hash_offset = struct.unpack('<H', reader.read(2))[0] - 4
    name_offset = struct.unpack('<H', reader.read(2))[0] - 4
    unk_offset = struct.unpack('<H', reader.read(2))[0]
    reader.seek(reader.tell() + 0x06)
    comp_data_length = struct.unpack('<I', reader.read(4))[0]
    reader.seek(reader.tell() + 0x04)
    position_count = struct.unpack('<I', reader.read(4))[0]
    rotation_count = struct.unpack('<I', reader.read(4))[0]
    scale_count = struct.unpack('<I', reader.read(4))[0]
    unknown_count = struct.unpack('<I', reader.read(4))[0]
    bone_count = struct.unpack('<I', reader.read(4))[0]    
    
    reader.seek(hash_offset)
    hash_value = struct.unpack('<I', reader.read(4))[0]
    anim_name = read_string(reader)

    reader.seek(0x58)
    frame_count = struct.unpack('<I', reader.read(4))[0]
    position_track_offset = struct.unpack('<H', reader.read(2))[0]
    rotation_track_offset = struct.unpack('<H', reader.read(2))[0]
    scale_track_offset = struct.unpack('<H', reader.read(2))[0]
    unknown_track_offset = struct.unpack('<H', reader.read(2))[0]

    anim_table_offsets = []
    for i in range(position_count + rotation_count + scale_count + unknown_count):
        anim_table_offset = {}
        anim_table_offset['flag_offset'] = struct.unpack('<I', reader.read(4))[0]
        anim_table_offset['key_frame_offset'] = struct.unpack('<I', reader.read(4))[0]
        anim_table_offset['key_data_offset'] = struct.unpack('<I', reader.read(4))[0]
        anim_table_offsets.append(anim_table_offset)
        reader.read(0x04)  # Skip 4 bytes

    compressed_data = compressor.decompress(reader.read(size - reader.tell()))
    data = io.BytesIO(compressed_data)
    data_size = len(data.getbuffer())
    
    # Bone Hashes
    bone_name_hashes = []
    for i in range(bone_count):
        bone_name_hashes.append(struct.unpack('<I', data.read(4))[0])

    # Track Information
    tracks = []
    data.seek(position_track_offset)
    for i in range(4):
        track = {}
        track["type"] = struct.unpack("<B", data.read(1))[0]
        track["data_type"] = struct.unpack("<B", data.read(1))[0]
        track["unk"] = struct.unpack("<B", data.read(1))[0]
        track["data_count"] = struct.unpack("<B", data.read(1))[0]
        track["start"] = struct.unpack("<H", data.read(2))[0]
        track["end"] = struct.unpack("<H", data.read(2))[0]
        tracks.append(track)

    anim_data = io.BytesIO(data.read(data_size - data.tell()))
    read_frame_data2(anim_data, anim_table_offsets[:position_count], bone_name_hashes, tracks[0], node)
    read_frame_data2(anim_data, anim_table_offsets[position_count:position_count+rotation_count], bone_name_hashes, tracks[1], node)
    read_frame_data2(anim_data, anim_table_offsets[position_count+rotation_count:position_count+rotation_count+scale_count], bone_name_hashes, tracks[2], node)
    
    return anim_name, frame_count, bone_name_hashes, node
    
def write_mtn3(name, nodes, frame_location, frame_rotation, frame_scale, frame_end):
    data_decomp = bytes()
    header_table = bytes()
    
    # Bone hashes
    for node in nodes:
        crc32 = zlib.crc32(node.encode("shift-jis"))
        data_decomp += crc32.to_bytes(4, 'little')

    # Track information
    position_track_offset = len(data_decomp)
    for i in range(3):
        if i == 0:
            data_decomp += int("0x03000201", 16).to_bytes(4, 'little')
        elif i == 1:
            data_decomp += int("0x04000102", 16).to_bytes(4, 'little')
        elif i == 2: 
            data_decomp += int("0x03000203", 16).to_bytes(4, 'little')            
        data_decomp += int(0).to_bytes(2, 'little')
        data_decomp += frame_end.to_bytes(2, 'little')
    
    # write empty block
    data_decomp += int(0).to_bytes(8, 'little')

    # initialise bytes object to save frame data and frame_offset to save each offset of frame
    data_location = bytes()
    data_rotation = bytes()
    data_scale = bytes()
    frame_offset = 0
    
    # write data_location for each frame
    for node, frames in frame_location.items():
        # table
        header_table += table_offset(frame_offset, frames)
        frame_offset += len(frames) * 14 + 4;
        # node data
        data_location += node_modified(node, frames)
        # frame edited
        data_transform = bytes()
        for frame_key, frame_transform in frames.items():
            data_location += frame_modified(frame_key)
            data_transform += bytearray(struct.pack("f", frame_transform.location_x))
            data_transform += bytearray(struct.pack("f", frame_transform.location_y))
            data_transform += bytearray(struct.pack("f", frame_transform.location_z))
        data_location += data_transform

    # write data_rotation for each frame
    for node, frames in frame_rotation.items():
        # table
        header_table += table_offset(frame_offset, frames)
        frame_offset += len(frames) * 10 + 4;
        # node data
        data_rotation += node_modified(node, frames)
        # frame edited
        data_transform = bytes()
        for frame_key, frame_transform in frames.items():
            data_rotation += frame_modified(frame_key)
            quaternion = frame_transform.to_quaternion()
            for i in range(4):
                data_transform += int(quaternion[i] * 32767).to_bytes(2, 'little', signed=True)
        data_rotation += data_transform

    # write data_scale for each frame
    for node, frames in frame_scale.items():
        # table
        header_table += table_offset(frame_offset, frames)
        frame_offset += len(frames) * 14 + 4;
        # node data
        data_scale += node_modified(node, frames)
        # frame edited
        data_transform = bytes()
        for frame_key, frame_transform in frames.items():
            data_scale += frame_modified(frame_key)
            data_transform += bytearray(struct.pack("f", frame_transform.scale_x))
            data_transform += bytearray(struct.pack("f", frame_transform.scale_y))
            data_transform += bytearray(struct.pack("f", frame_transform.scale_z))
        data_scale += data_transform  

    # compress
    data_decomp += data_location + data_rotation + data_scale
    data_compress = compress(data_decomp)   
            
    out = bytes()
    
    out = int("0x4e544d58", 16).to_bytes(4, 'little')   
    out += int(48).to_bytes(2, 'little')
    out += int(48 + len(name) - 2).to_bytes(2, 'little')
    out += int(104).to_bytes(2, 'little')    
    out += int(0).to_bytes(2, 'little')
    out += int(0).to_bytes(2, 'little')
    out += int(0).to_bytes(2, 'little')
    out += int(len(data_compress)).to_bytes(4, 'little') # comp_data_length
    out += int(0).to_bytes(4, 'little')
    out += int(len(frame_location)).to_bytes(4, 'little')
    out += int(len(frame_rotation)).to_bytes(4, 'little')
    out += int(len(frame_scale)).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    out += int(len(nodes)).to_bytes(4, 'little')
    
    name = name[:40]
    encoded_name = name.encode('shift-jis')
    encoded_name_crc32 = zlib.crc32(encoded_name)
    out += encoded_name_crc32.to_bytes(4, 'little')
    out += encoded_name

    if len(encoded_name) < 40:
        out += b'\x00' * (40 - len(encoded_name))
    
    out += int(frame_end).to_bytes(4, 'little')
    out += int(position_track_offset).to_bytes(2, 'little')
    out += int(position_track_offset + 8 * 1).to_bytes(2, 'little')
    out += int(position_track_offset + 8 * 2).to_bytes(2, 'little')
    out += int(position_track_offset + 8 * 3).to_bytes(2, 'little')
    out += header_table
    out += data_compress
    
    return out