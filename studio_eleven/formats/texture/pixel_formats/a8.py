import numpy as np

class A8:
    name = "A8"
    size = 1
    bit_depth = 8
    type = 0x0E
    has_alpha = True

    def encode(self, pixels):
        return np.ascontiguousarray(pixels[:, 3]).tobytes()
