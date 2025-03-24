import zlib
import struct
import numpy as np

from ..utils import *
from ..compression import *

##########################################
# IMGC Write Function
##########################################

def flip_vertically(pixels, height, width):
    transposed_pixels = []
    for y in range(height):
        for x in range(width):
            index = y * width + x
            transposed_index = (height - y - 1) * width + x
            transposed_pixels.append(pixels[transposed_index])
    return transposed_pixels
    
def get_pixels(img):
    px = []
    
    img_pixels = list(img.pixels)
    for i in range(0, len(img_pixels), 4):
        px.append([int(img_pixels[i]*255), int(img_pixels[i+1]*255), int(img_pixels[i+2]*255), int(img_pixels[i+3]*255)])
     
    return flip_vertically(px, img.size[1], img.size[0])

def write(img, img_format):
    out = bytes()
    
    height = img.size[1]
    width = img.size[0]
    px = get_pixels(img)

    tile_compress = lz10.compress(image_to_tile(px, height, width))
    image_data_compress = lz10.compress(encode_image(px, height, width, img_format))

    out += bytes.fromhex("494D4743303000003000")
    out += int(img_format.type).to_bytes(1, 'little')
    out += bytes.fromhex("0101108000")
    out += width.to_bytes(2, 'little')
    out += height.to_bytes(2, 'little')
    out += bytes.fromhex("3000000030000100480000000300000000000000000000000000000000000000")
    out += int(len(tile_compress)).to_bytes(4, 'little')
    out += int(len(tile_compress)).to_bytes(4, 'little')
    out += int(len(image_data_compress)).to_bytes(4, 'little')
    out += int(0).to_bytes(8, 'little')
    out += tile_compress
    out += image_data_compress

    missing_bytes = 16 - len(out) % 16
    if missing_bytes > 0:
        out += bytes.fromhex("".zfill(missing_bytes*2))
    
    return out;

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
                0x00: img_format.RGBA8(),
                0x01: img_format.RGBA4(),
                0x02: img_format.RGBA5551(),
                0x03: img_format.RBGR888(),
                0x04: img_format.RGB565(),
                0x0A: img_format.LA8(),
                0x0B: img_format.LA4(),
                0x0C: img_format.L8(),
                0x0D: img_format.L4(),
                0x0E: img_format.A8(),
                0x0F: img_format.A4(),
                0x1B: img_format.ETC1(),
                0x1C: img_format.ETC1A4(),
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
