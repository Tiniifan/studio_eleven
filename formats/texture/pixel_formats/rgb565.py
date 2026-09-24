from .color import quantize, pack_shorts

class RGB565:
    name = "RGB565"
    size = 2
    bit_depth = 16
    type = 4
    has_alpha = False

    def encode(self, pixels):
        r = quantize(pixels[:, 0], 5)
        g = quantize(pixels[:, 1], 6)
        b = quantize(pixels[:, 2], 5)

        return pack_shorts((r << 11) | (g << 5) | b)
