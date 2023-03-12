from struct import *

class Color:
    def __init__(self, color):
        self.r = color[0]
        self.g = color[1]
        self.b = color[2]
        self.a = 0

        if (len(color) == 4):
            self.a = color[3]

def convert8to5(col):
    table = [ 0x00,0x08,0x10,0x18,0x20,0x29,0x31,0x39,
                    0x41,0x4A,0x52,0x5A,0x62,0x6A,0x73,0x7B,
                    0x83,0x8B,0x94,0x9C,0xA4,0xAC,0xB4,0xBD,
                    0xC5,0xCD,0xD5,0xDE,0xE6,0xEE,0xF6,0xFF ]
    i = 0
    while col > table[i]:
        i += 1
        
    return i

class RGBA8:
    name = "RGBA8"
    
    def encode(self, color):
        return bytes([((color >> 24) & 0xFF), ((color) & 0xFF), ((color >> 8) & 0xFF), ((color >> 16) & 0xFF)]);

class RGB8:
    name = "RGB8"
    
    def encode(self, color):
        return bytes([((color) & 0xFF), ((color >> 8) & 0xFF), ((color >> 16) & 0xFF)])

class RGBA4444:
    name = "RGBA4444"
    
    def encode(self, color):
        val = (((color >> 24) & 0xFF) / 0x11)
        val += ((((color) & 0xFF) / 0x11) << 4)
        val += ((((color >> 8) & 0xFF) / 0x11) << 8)
        val += ((((color >> 16) & 0xFF) / 0x11) << 12)
        return bytes([(val & 0xFF), (byte)(val >> 8)])

class RGBA5551:
    name = "RGBA5551"
    
    def encode(self, color):
        val = (((c >> 24) & 0xFF) > 0x80 or 0)
        val += convert8to5(((c >> 16) & 0xFF)) << 11
        val += convert8to5(((c >> 8) & 0xFF)) << 6
        val += convert8to5(((c) & 0xFF)) << 1
        v = pack('H', val);è
        return bytes([(val & 0xFF), (byte)(val >> 8)])

class RGB565:
    name = "RGB565"
    type = 4
    
    def encode(color):
        r = int(color.r >> 3)
        g = int(color.g >> 2)
        b = int(color.b >> 3)
        val = (r << 11) | (g << 5) | b
        return pack('H', val);

class RBGR555:
    name = "RGB565"
    
    def encode(self, color):
        r = int(color.r / 8)
        g = int((color.g /8)) << 5
        b = int((color.b /8)) << 10
        return pack('H', r+g+b);   

class LA8:
    name = "LA8"
    
    def encode(self, color):
        return bytes([(((0x4CB2 * (color & 0xFF) + 0x9691 * ((color >> 8) & 0xFF) + 0x1D3E * ((color >> 8) & 0xFF)) >> 16) & 0xFF)])

class HILO8:
    name = "HILO8"
    
    def encode(self, color):
        bytes([((color) & 0xFF), (byte)((color >> 8) & 0xFF)])

class L8:
    name = "L8"
    
    def encode(self, color):
        return bytes([(((0x4CB2 * (color & 0xFF) + 0x9691 * ((color >> 8) & 0xFF) + 0x1D3E * ((color >> 8) & 0xFF)) >> 16) & 0xFF)])

class A8:
    name = "A8"
    
    def encode(self, color):
        return bytes([((color >> 24) & 0xFF)])

class LA4:
    name = "LA4"
    
    def encode(self, color):
        return bytes([((color >> 24) & 0xFF), ((color) & 0xFF), ((color >> 8) & 0xFF), ((color >> 16) & 0xFF)]);

class L4:
    name = "L4"
    
    def encode(self, color_a, color_b):
        return bytes([(L8().encode(color_a)[0] / 0x11) & 0xF  | (L8().encode(color_b)[0] / 0x11) << 4])

class A4:
    name = "A4"
    
    def encode(self, color_a, color_b):
        return bytes([(A8().encode(color_a)[0] / 0x11) & 0xF  | (A8().encode(color_b)[0] / 0x11) << 4])