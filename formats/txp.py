import io
import zlib
import struct

def read_txp(reader):
    return list(struct.unpack("<III", reader.read(12)))

def write(name, lib_name):
    out = bytes()  
        
    out += zlib.crc32(name.encode("utf-8")).to_bytes(4, 'little')
    out += zlib.crc32(lib_name.encode("utf-8")).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    out += struct.pack('<f', 1)
    out += struct.pack('<f', 1)
    
    return out
