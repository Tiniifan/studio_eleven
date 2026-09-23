from struct import unpack
from .color import Color

class LA8:
    name = "LA8"
    size = 2
    has_alpha = True
    type = 0x0A
    
    def encode(self, color):
        return bytes([(((0x4CB2 * (color & 0xFF) + 0x9691 * ((color >> 8) & 0xFF) + 0x1D3E * ((color >> 8) & 0xFF)) >> 16) & 0xFF)])
    
    def decode(self, data, index):
        l, a = unpack("2B", data)
        r = g = b = l
        return Color([r, g, b, a])
