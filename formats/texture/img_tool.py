import struct
import numpy as np
from io import BytesIO

from .img_swizzle import *

##########################################
# IMGC Encode Function
##########################################

def get_file_pixels(rgba, width, height):
    # Give the pixels of an image (rows from the top, rgba bytes) in the order of the file.
    # The image is padded with transparent black to whole 8x8 tiles
    padded_width = (width + 7) & ~7
    padded_height = (height + 7) & ~7

    padded = np.zeros((padded_height, padded_width, 4), dtype=np.uint8)
    padded[:height, :width] = rgba

    x, y = imgc_swizzle_points(padded_width, padded_height, padded_width * padded_height)

    return padded[y, x]

def encode_tiles(pixels, img_format, data = None):
    # Encode the pixels (or take them already encoded), then keep every different 8x8 tile once: give the tile table and the tile data.
    if data is None:
        data = img_format.encode(pixels)

    data = np.frombuffer(data, dtype=np.uint8)

    tile_size = 64 * img_format.bit_depth // 8
    tiles = data.reshape(-1, tile_size)

    # The tiles are numbered in the order they first appear
    unique_tiles, first_indexes, inverse = np.unique(tiles, axis=0, return_index=True, return_inverse=True)
    order = np.argsort(first_indexes)

    ranks = np.zeros(len(order), dtype=np.int64)
    ranks[order] = np.arange(len(order))

    table = ranks[inverse.reshape(-1)].astype('<u2').tobytes()
    tile_data = unique_tiles[order].tobytes()

    return table, tile_data

##########################################
# IMGC Decode Function
##########################################

# Returns the r, g, b and a arrays of every pixel
def decode_pixels(image_format, data, pixel_count):
    name = image_format.name
    size = image_format.size
    
    # 4 bits per pixel formats read the whole stream with a nibble index
    if name in ("L4", "A4"):
        indexes = np.arange(pixel_count)
        nibbles = ((data[indexes // 2].astype(np.int32) >> ((indexes & 1) * 4)) & 0x0F) * 0x11
        full = np.full(pixel_count, 255, dtype=np.int32)
        if name == "L4":
            return nibbles, nibbles, nibbles, full
        return full, full, full, nibbles
    
    px = data[:pixel_count * size].reshape(pixel_count, size).astype(np.int32)
    opaque = np.full(pixel_count, 255, dtype=np.int32)
    
    if name == "RGBA8":
        return px[:, 3], px[:, 2], px[:, 1], px[:, 0]
    elif name == "RGBA4":
        value = (px[:, 1] << 8) | px[:, 0]
        return ((value >> 12) & 0xF) * 17, ((value >> 8) & 0xF) * 17, ((value >> 4) & 0xF) * 17, (value & 0xF) * 17
    elif name == "RGBA5551":
        value = (px[:, 1] << 8) | px[:, 0]
        r = (value >> 11) & 0x1F
        g = (value >> 6) & 0x1F
        b = (value >> 1) & 0x1F
        return (r << 3) | (r >> 2), (g << 3) | (g >> 2), (b << 3) | (b >> 2), (value & 0x01) * 255
    elif name == "RBGR888":
        return px[:, 2], px[:, 1], px[:, 0], opaque
    elif name == "RGB565":
        value = (px[:, 1] << 8) | px[:, 0]
        r = (value >> 11) & 0x1F
        g = (value >> 5) & 0x3F
        b = value & 0x1F
        return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2), opaque
    elif name == "LA8":
        # The alpha is the low byte, stored first
        return px[:, 1], px[:, 1], px[:, 1], px[:, 0]
    elif name == "L8":
        return px[:, 0], px[:, 0], px[:, 0], opaque
    elif name == "A8":
        return opaque, opaque, opaque, px[:, 0]
    elif name == "LA4":
        luminance = ((px[:, 0] >> 4) & 0x0F) * 0x11
        return luminance, luminance, luminance, (px[:, 0] & 0x0F) * 0x11
    elif name == "ETC1":
        return px[:, 0], px[:, 1], px[:, 2], opaque
    elif name == "ETC1A4":
        return px[:, 0], px[:, 1], px[:, 2], px[:, 3]
    
    raise NotImplementedError(f"Image format {name} not implemented")

def imgc_swizzle_points(width, height, point_count):
    # Same as IMGCSwizzle.get_point_sequence() for every point at once: z-order inside 8x8 tiles
    stride_width = (width + 0x7) & ~0x7
    width_in_tiles = (stride_width + 7) // 8
    
    indexes = np.arange(point_count, dtype=np.int64)
    macro_tile = indexes // 64
    
    x = ((macro_tile % width_in_tiles) * 8) ^ (((indexes >> 1) & 1) | (((indexes >> 3) & 1) << 1) | (((indexes >> 5) & 1) << 2))
    y = ((macro_tile // width_in_tiles) * 8) ^ ((indexes & 1) | (((indexes >> 2) & 1) << 1) | (((indexes >> 4) & 1) << 2))
    
    return x, y

def decode_image(tile, image_data, image_format, width, height, bit_depth):
    # The pixels are returned as floats, bottom row first like Blender
    table_value = bytes(tile)
    table_value = table_value[:len(table_value) // 2 * 2]
    
    if struct.unpack('<H', table_value[:2])[0] != 0x453:
        entries = np.frombuffer(table_value, dtype='<u2', count=len(table_value) // 2).astype(np.int64)
    else:
        entries = np.frombuffer(table_value, dtype='<u4', count=len(table_value) // 4).astype(np.int64)
    
    block_size = 64 * bit_depth // 8
    tex_value = np.frombuffer(bytes(image_data), dtype=np.uint8)
    
    # Empty tiles are filled with 0, tiles pointing outside of the data are skipped
    empty = (entries == 0xFFFF) | (entries == 0xFFFFFFFF)
    keep = empty | (entries * block_size < len(tex_value))
    entries = entries[keep]
    empty = empty[keep]
    
    block_count = len(tex_value) // block_size + 1
    blocks = np.zeros(block_count * block_size, dtype=np.uint8)
    blocks[:len(tex_value)] = tex_value
    blocks = blocks.reshape(block_count, block_size)
    
    ms = blocks[np.where(empty, 0, entries)]
    ms[empty] = 0
    ms = ms.reshape(-1)
    
    if image_format.name in ("ETC1", "ETC1A4"):
        ms = np.frombuffer(image_format.decompress(ms, width, height), dtype=np.uint8)
    
    pixel_count = width * height
    
    # Pad the stream so truncated data decodes to black instead of failing
    needed = pixel_count * image_format.size + 1
    if len(ms) < needed:
        padded = np.zeros(needed, dtype=np.uint8)
        padded[:len(ms)] = ms
        ms = padded
    
    r, g, b, a = decode_pixels(image_format, ms, pixel_count)
    
    x, y = imgc_swizzle_points(width, height, pixel_count)
    inverted_y = height - 1 - y
    valid = (x < width) & (inverted_y >= 0) & (inverted_y < height)
    
    pixels = np.zeros((pixel_count, 4), dtype=np.float64)
    target = inverted_y[valid] * width + x[valid]
    pixels[target, 0] = r[valid]
    pixels[target, 1] = g[valid]
    pixels[target, 2] = b[valid]
    pixels[target, 3] = a[valid]
    
    pixels = (pixels / 255.0).astype(np.float32).reshape(-1)
    
    return pixels, width, height, image_format.has_alpha
