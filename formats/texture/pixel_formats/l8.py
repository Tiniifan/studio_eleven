from struct import unpack
from .color import Color

class L8:
    name = "L8"
    size = 1
    has_alpha = False
    type = 0x0C
    
    def encode(self, color):
        return bytes([(((0x4CB2 * (color & 0xFF) + 0x9691 * ((color >> 8) & 0xFF) + 0x1D3E * ((color >> 8) & 0xFF)) >> 16) & 0xFF)])
    
    def decode(self, data, index):
        r = g = b = unpack("B", data)[0]
        return Color([r, g, b, 255])
