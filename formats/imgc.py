import numpy as np
import zlib
import struct
from ..utils import *
from ..compression import lz10

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
    out += height.to_bytes(2, 'little')
    out += width.to_bytes(2, 'little')
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
