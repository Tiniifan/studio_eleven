import numpy as np

from .color import quantize, get_luminance

class LA4:
    name = "LA4"
    size = 1
    bit_depth = 8
    type = 0x0B
    has_alpha = True

    def encode(self, pixels):
        # The luminance is the high nibble
        return ((quantize(get_luminance(pixels), 4) << 4) | quantize(pixels[:, 3], 4)).astype(np.uint8).tobytes()
