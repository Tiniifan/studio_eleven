from struct import unpack
from .color import Color

class A8:
    name = "A8"
    size = 1
    has_alpha = True
    type = 0x0E
    
    def encode(self, color):
        return bytes([((color >> 24) & 0xFF)])
    
    def decode(self, data, index):
        a = unpack("B", data)[0]
        return Color([255, 255, 255, a])
