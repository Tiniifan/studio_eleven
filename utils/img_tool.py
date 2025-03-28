import struct
import numpy as np
from io import BytesIO

from io import BytesIO
from ..compression import etc1
from .img_format import *
from .img_swizzle import *

zorder = [  0, 2, 8, 10, 32, 34, 40, 42,
            1, 3, 9, 11, 33, 35, 41, 43,
            4, 6, 12, 14, 36, 38, 44, 46,
            5, 7, 13, 15, 37, 39, 45, 47,
            16, 18, 24, 26, 48, 50, 56, 58,
            17, 19, 25, 27, 49, 51, 57, 59,
            20, 22, 28, 30, 52, 54, 60, 62,
            21, 23, 29, 31, 53, 55, 61, 63 ]   

def encode_image(px, height, width, img_format):
    out = bytes()
    tiles = []
    

    for h in range(0, height, 8):
        for w in range(0, width, 8):
            tile = []

            for bh in range(8):
                for bw in range(8):
                    tile.append(px[(w+bw) + (h+bh) * width])

            if tile not in tiles:
                tiles.append(tile)
                
                for bh in range(8):
                    for bw in range(8):
                        pos = bw + bh * 8
                        for i in range(len(zorder)):
                            if zorder[i] == pos:
                                color = Color(tile[i])
                                out += img_format.encode(color)
                                break
    return out

def image_to_tile(px, height, width):
    out = bytes()
    tiles = []
    
    for h in range(0, height, 8):
        for w in range(0, width, 8):
            tile = []

            for bh in range(8):
                for bw in range(8):
                    tile.append(px[(w+bw) + (h+bh) * width])
            
            if tile not in tiles:
                tiles.append(tile)
                out += int(len(tiles)-1).to_bytes(2, 'little')
            else:
                out += int(tiles.index(tile)).to_bytes(2, 'little')          
    return out

def decode_image(tile, image_data, image_format, width, height, bit_depth):
    table_value = BytesIO(tile).getvalue()
    
    table_value_len = len(table_value)

    if table_value_len % 2 != 0 or table_value_len % 4 != 0:
        new_table_value_len = (table_value_len // 2) * 2
        table_value = table_value[:new_table_value_len]   
    
    tex_value = BytesIO(image_data).getvalue()

    table_length = len(table_value)
    entry_length = 2 if struct.unpack('<H', table_value[:2])[0] != 0x453 else 4

    ms = bytearray()
    for i in range(0, table_length, entry_length):
        entry = struct.unpack('<H' if entry_length == 2 else '<I', table_value[i:i+entry_length])[0]
        if entry in (0xFFFF, 0xFFFFFFFF):
            ms.extend(b'\x00' * (64 * bit_depth // 8))
        elif entry * (64 * bit_depth // 8) < len(tex_value):
            ms.extend(tex_value[entry * (64 * bit_depth // 8):(entry + 1) * (64 * bit_depth // 8)])

    imgc_swizzle = IMGCSwizzle(width, height)

    if image_format.name == "ETC1A4":
        image_data_after_swizzle = bytearray(etc1.ETC1(True, width, height).decompress(ms))
    elif image_format.name == "ETC1":
        image_data_after_swizzle = bytearray(etc1.ETC1(False, width, height).decompress(ms))
    else:
        image_data_after_swizzle = ms
    
    pixel_count = width * height
    pixels = [[0.0, 0.0, 0.0, 0.0] for _ in range(width * height)]

    for i, swizzled_point in zip(range(pixel_count), imgc_swizzle.get_point_sequence()):
        dataIndex = i * image_format.size
        group = image_data_after_swizzle[dataIndex:dataIndex + image_format.size]
        color = Color([0, 0, 0, 0])
        if image_format.name == "L4" or image_format.name == "A4":
            color = image_format.decode(image_data_after_swizzle, dataIndex)
        else:
            color = image_format.decode(group, dataIndex)

        # Calculer les indices x, y pour accéder directement à la position dans le tableau pixels
        x, y = swizzled_point.X, swizzled_point.Y

        # Inverser l'indice y
        inverted_y = height - 1 - y

        if 0 <= x < width and 0 <= inverted_y < height:
            pixels[(inverted_y * width) + x] = [color.r, color.g, color.b, color.a]

    # Convertir les valeurs de pixels en float et les aplatir
    pixels = [chan / 255.0 for px in pixels for chan in px]

    return pixels, width, height, image_format.has_alpha

def decode_image_optimized(tile, image_data, image_format, width, height, bit_depth):
    table_value = np.frombuffer(tile, dtype=np.uint8)
    table_value_len = len(table_value)

    # Ensure table_value length is even and divisible by 4
    if table_value_len % 4 != 0:
        table_value = table_value[:table_value_len - (table_value_len % 4)]
    
    tex_value = np.frombuffer(image_data, dtype=np.uint8)
    table_length = len(table_value)
    entry_length = 2 if struct.unpack('<H', table_value[:2].tobytes())[0] != 0x453 else 4
    block_size = 64 * bit_depth // 8

    ms = np.zeros((table_length // entry_length * block_size,), dtype=np.uint8)
    ms_offset = 0

    for i in range(0, table_length, entry_length):
        entry = struct.unpack('<H' if entry_length == 2 else '<I', table_value[i:i+entry_length].tobytes())[0]
        if entry in (0xFFFF, 0xFFFFFFFF):
            ms[ms_offset:ms_offset + block_size] = 0
        else:
            start = entry * block_size
            end = start + block_size
            if start < len(tex_value):
                ms[ms_offset:ms_offset + block_size] = tex_value[start:end]
        ms_offset += block_size

    imgc_swizzle = IMGCSwizzle(width, height)

    if image_format.name == "ETC1A4":
        image_data_after_swizzle = np.frombuffer(etc1.ETC1(True, width, height).decompress(ms.tobytes()), dtype=np.uint8)
    elif image_format.name == "ETC1":
        image_data_after_swizzle = np.frombuffer(etc1.ETC1(False, width, height).decompress(ms.tobytes()), dtype=np.uint8)
    else:
        image_data_after_swizzle = ms
    
    pixel_count = width * height
    pixels = np.zeros((pixel_count, 4), dtype=np.float32)

    for i, swizzled_point in zip(range(pixel_count), imgc_swizzle.get_point_sequence()):
        dataIndex = i * image_format.size
        group = image_data_after_swizzle[dataIndex:dataIndex + image_format.size]
        color = image_format.decode(group)

        # Calculate the indices x, y to directly access the position in the pixels array
        x, y = swizzled_point.X, swizzled_point.Y
        inverted_y = height - 1 - y

        if 0 <= x < width and 0 <= inverted_y < height:
            pixels[(inverted_y * width) + x] = [color.r / 255.0, color.g / 255.0, color.b / 255.0, color.a / 255.0]

    # Flatten the array
    pixels = pixels.flatten()

    return pixels, width, height, image_format.has_alpha
