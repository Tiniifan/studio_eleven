from ..compression import *

##########################################
# CONST
##########################################

# The addon preferences choose the compression of the exported files, BEST_COMPRESSION lets find_best_compression pick
BEST_COMPRESSION = -1

default_compression = BEST_COMPRESSION

##########################################
# Compressor Function
##########################################

def set_default_compression(method):
    global default_compression
    default_compression = method

def compress_with(data, method):
    data = bytes(data)

    if method == NO_COMPRESSION:
        return int(len(data) << 3).to_bytes(4, 'little') + data
    elif method == LZ10:
        return lz10.compress(data)
    elif method == HUFFMAN_4:
        return huffman.compress(data, 4)
    elif method == HUFFMAN_8:
        return huffman.compress(data, 8)
    elif method == RLE:
        return rle.compress(data)
    elif method == ZLIB:
        return zlib_compress(data)
    else:
        raise Exception(f"Unknown compression method: {method}")

def compress(data, methods = LEVEL5_COMPRESSIONS):
    method = default_compression

    if method == BEST_COMPRESSION:
        method = find_best_compression(data, methods)
    elif method not in methods:
        # The block doesn't accept the chosen compression
        method = LZ10

    try:
        return compress_with(data, method)
    except Exception:
        # A Huffman tree can be too deep for the 6 bit offsets of its nodes
        return compress_with(data, LZ10)

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
        return zlib_decompress(data)
    else:
        return None

