import struct

from typing import List
from ..utils.img_format import RGB

modifiers = [
    [2, 8, -2, -8],
    [5, 17, -5, -17],
    [9, 29, -9, -29],
    [13, 42, -13, -42],
    [18, 60, -18, -60],
    [24, 80, -24, -80],
    [33, 106, -33, -106],
    [47, 183, -47, -183]
]

pixel_order = [0, 4, 1, 5, 8, 12, 9, 13, 2, 6, 3, 7, 10, 14, 11, 15]

# ETC1 class for compressing and decompressing ETC1 image data
class ETC1:
    def __init__(self, has_alpha_channel, width, height):
        self.has_alpha_channel = has_alpha_channel
        self.Width = width
        self.Height = height

    # Method for compressing data (Not Implemented)
    def compress(self, data):
        return None

    # Method for decompressing ETC1a4 data
    def decompress(self, data):
        return ETC1Decoder.decompress_etc1a4(data, self.Width, self.Height, self.has_alpha_channel)

class ETC1Decoder:
    @staticmethod
    def decompress_etc1a4(data, width, height, has_alpha_channel):
        result = bytearray(width * height * (4 if has_alpha_channel else 3))
        offset = 0
        write_offset = 0

        for block_y in range(0, height, 4):
            for block_x in range(0, width, 4):
                alphas = ETC1Decoder.decode_block_alphas(data[offset:offset + 8]) if has_alpha_channel else None
                offset += 8 if has_alpha_channel else 0

                colors = ETC1Decoder.decode_block_colors(data[offset:offset + 8])
                offset += 8

                block = bytearray(64 if has_alpha_channel else 48)
                for i in range(16):
                    idx = i * 4 if has_alpha_channel else i * 3
                    block[idx:idx + 3] = colors[i * 3:i * 3 + 3]
                    if has_alpha_channel:
                        block[idx + 3] = alphas[i]

                result[write_offset:write_offset + len(block)] = block
                write_offset += len(block)

        return bytes(result)

    @staticmethod
    def decode_block_colors(data):
        result = bytearray(48)  # Allocate memory for decoded colors

        lsb = struct.unpack('<H', data[:2])[0]
        msb = struct.unpack('<H', data[2:4])[0]
        flags = data[4]
        B = data[5]
        G = data[6]
        R = data[7]

        flip_bit = (flags & 1) == 1
        diff_bit = (flags & 2) == 2
        color_depth = 32 if diff_bit else 16
        table0 = (flags >> 5) & 7
        table1 = (flags >> 2) & 7

        # Decode color0 based on color depth
        color0 = RGB(R * color_depth // 256, G * color_depth // 256, B * color_depth // 256)

        # Decode color1 based on diff_bit
        colors1 = RGB(0, 0, 0)
        if not diff_bit:
            colors1 = RGB(R % 16, G % 16, B % 16)
        else:
            c0 = color0
            rd = RGB.sign3(R % 8)
            gd = RGB.sign3(G % 8)
            bd = RGB.sign3(B % 8)
            colors1 = RGB(c0.R + rd, c0.G + gd, c0.B + bd)

        # Scale color0 and color1 based on color depth
        color0 = color0.scale(color_depth)
        colors1 = colors1.scale(color_depth)

        flip_bit_mask = 2 if flip_bit else 8
        t = 0

        # Iterate over pixel order and apply modifiers to get final colors
        for i in pixel_order:
            basec = color0 if (i & flip_bit_mask) == 0 else colors1
            mod = modifiers[table0] if (i & flip_bit_mask) == 0 else modifiers[table1]
            c = basec + mod[(msb >> i) % 2 * 2 + (lsb >> i) % 2]
            result[t] = c.R
            result[t + 1] = c.G
            result[t + 2] = c.B
            t += 3

        return bytes(result)

    @staticmethod
    def decode_block_alphas(block_data):
        # Unpack alpha data from block
        canal_alpha = struct.unpack('<Q', block_data)[0] if True else 0xFFFFFFFFFFFFFFFF

        alphas = bytearray(16)  # Allocate memory for decoded alphas

        t = 0

        # Iterate over pixel order and extract alpha values
        for i in pixel_order:
            alphas[t] = (canal_alpha >> (4 * i)) % 16 * 17
            t += 1

        return bytes(alphas)

