import numpy as np

from .color import get_luminance

class L8:
    name = "L8"
    size = 1
    bit_depth = 8
    type = 0x0C
    has_alpha = False

    def encode(self, pixels):
        return get_luminance(pixels).astype(np.uint8).tobytes()
