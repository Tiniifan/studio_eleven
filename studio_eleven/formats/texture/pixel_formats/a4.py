from .color import quantize, pack_nibbles

class A4:
    name = "A4"
    size = 1
    bit_depth = 4
    type = 0x0F
    has_alpha = True

    def encode(self, pixels):
        return pack_nibbles(quantize(pixels[:, 3], 4)).tobytes()
