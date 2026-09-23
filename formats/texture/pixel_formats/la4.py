from struct import unpack
from .color import Color

class LA4:
    name = "LA4"
    size = 1
    has_alpha = True
    type = 0x0B
    
    def encode(self, color):
        return bytes([((color >> 24) & 0xFF), ((color) & 0xFF), ((color >> 8) & 0xFF), ((color >> 16) & 0xFF)])
    
    def decode(self, data, index):
        la = unpack("B", data)[0]
        r = g = b = ((la >> 4) & 0x0F) * 0x11
        a = (la & 0x0F) * 0x11
        return Color([r, g, b, a])
