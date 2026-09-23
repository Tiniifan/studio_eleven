from .color import Color

class RGBA8:
    name = "RGBA8"
    size = 4
    type = 0
    has_alpha = True
    
    def encode(self, color):
        argb = (color.a << 24) | (color.r << 16) | (color.g << 8) | color.b
        return bytes([(argb >> 24) & 0xFF, argb & 0xFF, (argb >> 8) & 0xFF, (argb >> 16) & 0xFF])       
       
    def decode(self, data, index):
        if len(data) < 4:
            return Color([0, 0, 0, 0])

        argb = (data[0] << 24) | (data[3] << 16) | (data[2] << 8) | data[1]
        return Color([(argb >> 16) & 0xFF, (argb >> 8) & 0xFF, argb & 0xFF, (argb >> 24) & 0xFF])
