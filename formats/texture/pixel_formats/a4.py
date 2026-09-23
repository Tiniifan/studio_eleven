from struct import pack
from .color import Color
from .a8 import A8

class A4:
    name = "A4"
    size = 1
    has_alpha = True
    type = 0x0F
    
    def encode(self, color_a, color_b):
        return bytes([(A8().encode(color_a)[0] / 0x11) & 0xF  | (A8().encode(color_b)[0] / 0x11) << 4])
    
    def decode(self, data, index):
        byte = ord(pack("B", data[index // 2]))
        shift = (index & 1) * 4
        a = ((byte >> shift) & 0x0F) * 0x11
        r = g = b = 255
        return Color([r, g, b, a])
