from .color import Color

class RBGR888:
    name = "RBGR888"
    size = 3
    type = 3
    has_alpha = False

    def encode(self, color):
        return bytes([(color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF])

    def decode(self, data, index):
        if len(data) < 3:
            return Color([0, 0, 0])

        rgb = (data[2] << 16) | (data[1] << 8) | data[0]
        return Color([(rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF, 255])
