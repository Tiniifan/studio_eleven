import numpy as np

class RGBA8:
    name = "RGBA8"
    size = 4
    bit_depth = 32
    type = 0
    has_alpha = True

    def encode(self, pixels):
        # Stored a, b, g, r
        return np.ascontiguousarray(pixels[:, ::-1]).tobytes()
