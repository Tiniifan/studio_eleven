from struct import pack, unpack
from .color import Color

def convert8to5(col):
    table = [ 0x00,0x08,0x10,0x18,0x20,0x29,0x31,0x39,
                    0x41,0x4A,0x52,0x5A,0x62,0x6A,0x73,0x7B,
                    0x83,0x8B,0x94,0x9C,0xA4,0xAC,0xB4,0xBD,
                    0xC5,0xCD,0xD5,0xDE,0xE6,0xEE,0xF6,0xFF ]
    i = 0
    while col > table[i]:
        i += 1
        
    return i

class RGBA5551:
    name = "RGBA5551"
    size = 2
    has_alpha = True
    type = 2
    
    def encode(self, color):
        val = (((c >> 24) & 0xFF) > 0x80 or 0)
        val += convert8to5(((c >> 16) & 0xFF)) << 11
        val += convert8to5(((c >> 8) & 0xFF)) << 6
        val += convert8to5(((c) & 0xFF)) << 1
        v = pack('H', val)
        return bytes([(val & 0xFF), (byte)(val >> 8)])
    
    def decode(self, data, index):
        b1, b2 = unpack('2B', data)
        
        r = ((b1 >> 3) & 0x1F)
        g = (b1 & 0x07) | ((b2 >> 6) & 0x03)
        b = (b2 >> 1) & 0x1F
        a = (b2 & 0x01) * 255
        return Color([r, g, b, a])
