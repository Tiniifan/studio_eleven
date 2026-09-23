from .color import Color

class ETC1:
    name = "ETC1"
    size = 3
    type = 27
    has_alpha = False

    def decode(self, data, index):
        r, g, b = data[0], data[1], data[2]
        return Color([r, g, b, 255])
