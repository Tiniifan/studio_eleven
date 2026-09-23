from .color import Color

class ETC1A4:
    name = "ETC1A4"
    size = 4
    type = 28
    has_alpha = True

    def decode(self, data, index):
        r, g, b, a = data[0], data[1], data[2], data[3]
        return Color([r, g, b, a])
