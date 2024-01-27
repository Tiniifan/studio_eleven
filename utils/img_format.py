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

class RGB:
    def __init__(self, r, g, b):
        self.R = r
        self.G = g
        self.B = b
        self.padding = 0  # Padding for speed reasons

    # Operator overloading for addition
    def __add__(self, mod):
        return RGB(self._clamp(self.R + mod), self._clamp(self.G + mod), self._clamp(self.B + mod))

    # Operator overloading for subtraction
    def __sub__(self, other):
        return self._error_rgb(self.R - other.R, self.G - other.G, self.B - other.B)

    # Static method to calculate the average color from a list of colors
    @staticmethod
    def average(src):
        return RGB(
            int(sum(c.R for c in src) / len(src)),
            int(sum(c.G for c in src) / len(src)),
            int(sum(c.B for c in src) / len(src))
        )

    # Method to scale the RGB values
    def scale(self, limit):
        return RGB(self.R * 17, self.G * 17, self.B * 17) if limit == 16 else RGB(
            (self.R << 3) | (self.R >> 2),
            (self.G << 3) | (self.G >> 2),
            (self.B << 3) | (self.B >> 2)
        )

    # Method to unscale the RGB values
    def unscale(self, limit):
        return RGB(self.R * limit // 256, self.G * limit // 256, self.B * limit // 256)

    # Method to calculate the hash value of the RGB instance
    def __hash__(self):
        return self.R | (self.G << 8) | (self.B << 16)

    # Method to check equality of two RGB instances
    def __eq__(self, other):
        return isinstance(other, RGB) and self.__hash__() == other.__hash__()

    # Method to check inequality of two RGB instances
    def __ne__(self, other):
        return not self.__eq__(other)

    # Static method to clamp a value between 0 and 255
    @staticmethod
    def _clamp(n):
        return max(0, min(n, 255))

    # Static method to calculate a signed value between -4 and 3
    @staticmethod
    def sign3(n):
        return (n + 4) % 8 - 4

    # Static method to calculate error in RGB values based on human perception
    @staticmethod
    def _error_rgb(r, g, b):
        return 2 * r * r + 4 * g * g + 3 * b * b  # human perception
    
class RGBA4:
    name = "RGBA4"
    size = 2
    type = 1
    
    def encode(self, color):
        r = color.r >> 4
        g = color.g >> 4
        b = color.b >> 4
        a = color.a >> 4

        rgba4 = (r << 12) | (g << 8) | (b << 4) | a

        data = bytearray([rgba4 & 0xFF, rgba4 >> 8])

        return data

    def decode(self, data):
        rgba4 = (data[1] << 8) | data[0]

        r = (rgba4 >> 12) & 0xF
        g = (rgba4 >> 8) & 0xF
        b = (rgba4 >> 4) & 0xF
        a = rgba4 & 0xF

        r *= 16
        g *= 16
        b *= 16
        a *= 16

        return Color([r, g, b, a])    

class RGBA8:
    name = "RGBA8"
    size = 4
    type = 0
    has_alpha = True
    
    def encode(self, color):
        argb = (color.a << 24) | (color.r << 16) | (color.g << 8) | color.b
        return bytes([(argb >> 24) & 0xFF, argb & 0xFF, (argb >> 8) & 0xFF, (argb >> 16) & 0xFF])       
       
    def decode(self, data):
        if len(data) < 4:
            return Color([0, 0, 0, 0])

        argb = (data[0] << 24) | (data[3] << 16) | (data[2] << 8) | data[1]
        return Color([(argb >> 16) & 0xFF, (argb >> 8) & 0xFF, argb & 0xFF, (argb >> 24) & 0xFF])      

class RBGR888:
    name = "RBGR888"
    size = 3
    type = 3
    has_alpha = False

    def encode(self, color):
        return bytes([(color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF])

    def decode(self, data):
        if len(data) < 3:
            return Color([0, 0, 0])

        rgb = (data[2] << 16) | (data[1] << 8) | data[0]
        return Color([(rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF, 255])

class RGB8:
    name = "RGB8"
    
    def encode(self, color):
        return bytes([((color) & 0xFF), ((color >> 8) & 0xFF), ((color >> 16) & 0xFF)])

class RGBA4444:
    name = "RGBA4444"
    has_alpha = True
    
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
    size = 2
    type = 4
    has_alpha = False
    
    def encode(self, color):
        r = int(color.r >> 3)
        g = int(color.g >> 2)
        b = int(color.b >> 3)
        val = (r << 11) | (g << 5) | b
        return pack('H', val);
        
    def decode(self, data):
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
    size = 1
    type = 14
    has_alpha = True
    
    def encode(self, color_a, color_b):
        return bytes([(L8().encode(color_a)[0] / 0x11) & 0xF  | (L8().encode(color_b)[0] / 0x11) << 4])
        
    def decode(self, data):
        if len(data) < 1:
            return Color(0, 0, 0, 0)

        color_a = (data[0] & 0xF) * 0x11
        color_b = (data[0] >> 4) * 0x11
        return Color([color_a, color_a, color_a, color_b])        

class A4:
    name = "A4"
    
    def encode(self, color_a, color_b):
        return bytes([(A8().encode(color_a)[0] / 0x11) & 0xF  | (A8().encode(color_b)[0] / 0x11) << 4])

class ETC1:
    name = "ETC1"
    size = 3
    type = 27
    has_alpha = False

    def decode(self, data):
        r, g, b = data[0], data[1], data[2]
        return Color([r, g, b, 255]) 
        
class ETC1A4:
    name = "ETC1A4"
    size = 4
    type = 28
    has_alpha = True

    def decode(self, data):
        r, g, b, a = data[0], data[1], data[2], data[3]
        return Color([r, g, b, a])
        