import numpy as np

class Color:
    def __init__(self, color):
        self.r = color[0]
        self.g = color[1]
        self.b = color[2]
        self.a = 0

        if (len(color) == 4):
            self.a = color[3]

##########################################
# Color Function
##########################################

# The encoders take the pixels in the order of the file, an array of rgba bytes (one row per pixel)

def quantize(values, bits):
    # Nearest value on bits bits, a value that was expanded from bits bits gets back the same bits
    maximum = (1 << bits) - 1

    return (values.astype(np.int32) * maximum + 127) // 255

def expand(values, bits):
    # Back to 8 bits, the high bits are copied in the low bits like the GPU does
    values = values.astype(np.int32)

    return (values << (8 - bits)) | (values >> (2 * bits - 8))

def get_luminance(pixels):
    # BT.601 luma, a gray pixel keeps its value
    rgb = pixels[:, :3].astype(np.int32)

    return (rgb[:, 0] * 299 + rgb[:, 1] * 587 + rgb[:, 2] * 114 + 500) // 1000

def pack_nibbles(values):
    # 2 pixels per byte, the first one in the low nibble
    values = values.astype(np.uint8)

    return (values[0::2] | (values[1::2] << 4)).astype(np.uint8)

def pack_shorts(values):
    return values.astype('<u2').tobytes()
