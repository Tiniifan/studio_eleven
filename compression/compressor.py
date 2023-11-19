from ..compression import *

def decompress(data):
    size_method_buffer = data[:4]
    size = (size_method_buffer[0] >> 3) | (size_method_buffer[1] << 5) | \
           (size_method_buffer[2] << 13) | (size_method_buffer[3] << 21)

    method = size_method_buffer[0] & 0x7
    
    if method == 0:
        return data[4:]
    elif method == 1:
        return lzss_decompress(data)
    elif method == 2:
        return huffman.decompress(data, 4)
    elif method == 3:
        return huffman.decompress(data, 8)
    elif method == 4:
        return rle.decompress(data)
    elif method == 5:        
        return zlib_level5.zlib_decompress(data)
    else:
        return None      
    