import zlib
import struct
import numpy as np
from io import BytesIO

from . import img_tool, pixel_formats
from ...compression import *

##########################################
# IMGC Write Function
##########################################

def write(rgba, width, height, img_format):
    # rgba holds the rows of the image from the top, 4 bytes per pixel
    out = bytes()

    pixels = img_tool.get_file_pixels(rgba, width, height)
    table, tile_data = img_tool.encode_tiles(pixels, img_format)

    table_compress = compressor.compress(table)
    tile_data_compress = compressor.compress(tile_data)

    # The tile data starts on 4 bytes
    table_length = (len(table_compress) + 3) & ~3

    out += bytes.fromhex("494D4743303000003000")
    out += int(img_format.type).to_bytes(1, 'little')
    out += bytes.fromhex("0101")
    out += int(img_format.bit_depth).to_bytes(1, 'little')
    out += int(64 * img_format.bit_depth // 8).to_bytes(2, 'little')
    out += width.to_bytes(2, 'little')
    out += height.to_bytes(2, 'little')
    out += bytes.fromhex("3000000030000100480000000300000000000000000000000000000000000000")
    out += int(len(table_compress)).to_bytes(4, 'little')
    out += int(table_length).to_bytes(4, 'little')
    out += int(len(tile_data_compress)).to_bytes(4, 'little')
    out += int(0).to_bytes(8, 'little')
    out += table_compress
    out += bytes(table_length - len(table_compress))
    out += tile_data_compress
    out += bytes(-len(out) % 16)

    return out

##########################################
# IMGCSupport
##########################################

class IMGCSupport:
    class Header:
        def __init__(self, header_bytes):
            self.Magic = header_bytes[0]
            self.ImageFormat = header_bytes[1]
            self.CombineFormat = header_bytes[2]
            self.BitDepth = header_bytes[3]
            self.BytesPerTile = header_bytes[4]
            self.Width = header_bytes[5]
            self.Height = header_bytes[6]
            self.TileOffset = header_bytes[7]
            self.TileSize1 = header_bytes[8]
            self.TileSize2 = header_bytes[9]
            self.ImageSize = header_bytes[10]
            self.ImageFormats = {
                0x00: pixel_formats.RGBA8(),
                0x01: pixel_formats.RGBA4(),
                0x02: pixel_formats.RGBA5551(),
                0x03: pixel_formats.RBGR888(),
                0x04: pixel_formats.RGB565(),
                0x0A: pixel_formats.LA8(),
                0x0B: pixel_formats.LA4(),
                0x0C: pixel_formats.L8(),
                0x0D: pixel_formats.L4(),
                0x0E: pixel_formats.A8(),
                0x0F: pixel_formats.A4(),
                0x1B: pixel_formats.ETC1(),
                0x1C: pixel_formats.ETC1A4(),
            }

##########################################
# IMGC Open Function
##########################################

def open(file_content):
    data = BytesIO(file_content)

    # Reading and unpacking the header data
    header_data = data.read(struct.calcsize('I6xbxbbhhh8xi20xiii8x'))
    header = IMGCSupport.Header(struct.unpack('I6xbxbbhhh8xi20xiii8x', header_data))

    # Decompressing tile and image data
    data.seek(header.TileOffset)
    tile_data = compressor.decompress(data.read(header.TileSize1))

    data.seek(header.TileOffset + header.TileSize2)
    image_data = compressor.decompress(data.read(header.ImageSize))

    if header.ImageFormat in header.ImageFormats:
        return img_tool.decode_image(tile_data, image_data, header.ImageFormats[header.ImageFormat], header.Width, header.Height, header.BitDepth)
    else:
        return None

def read_format(file_content):
    header = IMGCSupport.Header(struct.unpack_from('I6xbxbbhhh8xi20xiii8x', file_content))
    image_format = header.ImageFormats.get(header.ImageFormat)

    if image_format is None:
        return None

    return image_format.name
