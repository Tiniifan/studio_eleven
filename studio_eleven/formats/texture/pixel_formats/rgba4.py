from .color import quantize, pack_shorts

class RGBA4:
    name = "RGBA4"
    size = 2
    bit_depth = 16
    type = 1
    has_alpha = True

    def encode(self, pixels):
        r = quantize(pixels[:, 0], 4)
        g = quantize(pixels[:, 1], 4)
        b = quantize(pixels[:, 2], 4)
        a = quantize(pixels[:, 3], 4)

        return pack_shorts((r << 12) | (g << 8) | (b << 4) | a)
