import io
import zlib
import struct

def write(name, value):
    out = bytes()

    if name == "HEIGHT" or name == "COLLISION_CHARA":
        out += int(0).to_bytes(4, 'little')
        out += zlib.crc32(name.encode("utf-8")).to_bytes(4, 'little')
        out += int(5).to_bytes(2, 'little')
        out += int(1).to_bytes(2, 'little')
        out += bytearray(struct.pack("f", value))
        out += int(0).to_bytes(4, 'little')
    else:      
        if name == "mesh_sort" or name == "scale_base_one":
            out += int(value).to_bytes(4, 'little')
        else:
            out += bytearray(struct.pack("f", value))
            
        out += zlib.crc32(name.encode("utf-8")).to_bytes(4, 'little')
        out += int(0).to_bytes(4, 'little')
    
    return out