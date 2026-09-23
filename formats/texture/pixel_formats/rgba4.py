from .color import Color

class RGBA4:
    name = "RGBA4"
    size = 2
    type = 1
    has_alpha = True
    
    def encode(self, color):
        r = color.r >> 4
        g = color.g >> 4
        b = color.b >> 4
        a = color.a >> 4

        rgba4 = (r << 12) | (g << 8) | (b << 4) | a

        data = bytearray([rgba4 & 0xFF, rgba4 >> 8])

        return data

    def decode(self, data, index):
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
