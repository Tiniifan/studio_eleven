import io
import struct
import zlib
from ..compression import *

def open(data):
    camera_hashes = []

    reader = io.BytesIO(data)
    size = len(reader.getbuffer())
    
    compressed_data = compressor.decompress(reader.read(size))
    data = io.BytesIO(compressed_data)
    
    data.seek(4)
        
    data_pos = struct.unpack("<h", data.read(2))[0]
    item_count = struct.unpack("<h", data.read(2))[0]
    
    for i in range(item_count):
        camera_hashes.append(struct.unpack("<I", data.read(4))[0])
        data.seek(data.tell() + 4)
        
    return camera_hashes
    
def write(cameras):
    out = bytes()  
    
    # header
    out += int("0x544D4358", 16).to_bytes(4, 'little')
    out += int(8).to_bytes(2, 'little')
    out += int(len(cameras)).to_bytes(2, 'little')

    for camera_object in cameras:
        animation_name = camera_object[0]
        out += zlib.crc32(animation_name.encode("utf-8")).to_bytes(4, 'little')
        out += int(0).to_bytes(4, 'little')
        
    return lz10.compress(out)