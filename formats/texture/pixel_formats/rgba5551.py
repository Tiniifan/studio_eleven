from .color import quantize, pack_shorts

class RGBA5551:
    name = "RGBA5551"
    size = 2
    bit_depth = 16
    type = 2
    has_alpha = True

    def encode(self, pixels):
        r = quantize(pixels[:, 0], 5)
        g = quantize(pixels[:, 1], 5)
        b = quantize(pixels[:, 2], 5)
        a = quantize(pixels[:, 3], 1)

        return pack_shorts((r << 11) | (g << 6) | (b << 1) | a)
