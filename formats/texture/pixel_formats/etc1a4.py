from .color import Color
from .etc1 import decompress, compress

class ETC1A4:
    name = "ETC1A4"
    size = 4
    bit_depth = 8
    type = 28
    has_alpha = True

    def encode(self, pixels):
        return compress(pixels, True)

    def encode_fast(self, pixels):
        return compress(pixels, True, True)

    def decompress(self, data, width, height):
        return decompress(data, width, height, True)

    def decode(self, data, index):
        r, g, b, a = data[0], data[1], data[2], data[3]
        return Color([r, g, b, a])
