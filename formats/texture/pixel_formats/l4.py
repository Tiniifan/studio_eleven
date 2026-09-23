from .color import Color
from .l8 import L8

class L4:
    name = "L4"
    size = 1
    type = 14
    has_alpha = True
    
    def encode(self, color_a, color_b):
        return bytes([(L8().encode(color_a)[0] / 0x11) & 0xF  | (L8().encode(color_b)[0] / 0x11) << 4])
        
    def decode(self, data, index):
        l = data[index // 2]
        shift = (index & 1) * 4
        r = g = b = ((l >> shift) & 0x0F) * 0x11
        return Color([r, g, b, 255])
