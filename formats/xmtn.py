import zlib
import struct
from ..animation import *
from ..compression import *

def table_offset(frame_offset, frame_transform):
    out = bytes()
    out += int(frame_offset).to_bytes(4, 'little')
    out += int(frame_offset + 4).to_bytes(4, 'little')
    out += int(frame_offset + 4 + len(frame_transform) * 2).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    return out

def node_modified(node, frames):
    out = bytes()
    out += int(node).to_bytes(2, 'little')
    out += int(len(frames)).to_bytes(1, 'little')
    out += int(32).to_bytes(1, 'little')
    return out

def frame_modified(frame_key):
    return int(frame_key).to_bytes(2, 'little')

def write(name, nodes, frame_location, frame_rotation, frame_scale, frame_end):
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
