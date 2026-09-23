import io
import zlib
import struct

def write(name, value):
    out = bytes()  
        
    if name == "mesh_sort" or name == "scale_base_one":
        out += int(value).to_bytes(4, 'little')
    else:
        out += bytearray(struct.pack("f", value))
        
    out += zlib.crc32(name.encode("utf-8")).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    
    return out