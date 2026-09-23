from struct import pack, unpack
from .color import Color

class RGB565:
    name = "RGB565"
    size = 2
    type = 4
    has_alpha = False
    
    def encode(self, color):
        r = int(color.r >> 3)
        g = int(color.g >> 2)
        b = int(color.b >> 3)
        val = (r << 11) | (g << 5) | b
        return pack('H', val);
        
    def decode(self, data, index):
        if not data:
            return Color((0, 0, 0, 255))

        val = unpack('H', data)[0]
        r = (val >> 11) & 0x1F
        g = (val >> 5) & 0x3F
        b = val & 0x1F

        # Scale the values back to 8-bit range
        r = (r << 3) | (r >> 2)
        g = (g << 2) | (g >> 4)
        b = (b << 3) | (b >> 2)

        return Color((r, g, b, 255))
