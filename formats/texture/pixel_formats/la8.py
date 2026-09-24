import numpy as np

from .color import get_luminance

class LA8:
    name = "LA8"
    size = 2
    bit_depth = 16
    type = 0x0A
    has_alpha = True

    def encode(self, pixels):
        # The alpha is the low byte, stored first
        out = np.zeros((len(pixels), 2), dtype=np.uint8)
        out[:, 0] = pixels[:, 3]
        out[:, 1] = get_luminance(pixels)

        return out.tobytes()
