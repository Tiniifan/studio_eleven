import numpy as np

class RBGR888:
    name = "RBGR888"
    size = 3
    bit_depth = 24
    type = 3
    has_alpha = False

    def encode(self, pixels):
        # Stored b, g, r
        return np.ascontiguousarray(pixels[:, 2::-1]).tobytes()
