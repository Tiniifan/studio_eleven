import zlib
import struct

def zlib_decompress(data):
    if data[4] == 0x78:
        return zlib.decompress(data[4:])
    else:
        return False
        
def zlib_compress(data):
    return struct.pack('<I', len(data) << 3 | 0x1) + zlib.compress(data)