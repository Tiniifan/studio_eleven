from .color import quantize, get_luminance, pack_nibbles

class L4:
    name = "L4"
    size = 1
    bit_depth = 4
    type = 0x0D
    has_alpha = False

    def encode(self, pixels):
        return pack_nibbles(quantize(get_luminance(pixels), 4)).tobytes()
