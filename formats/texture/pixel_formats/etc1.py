import os
import importlib.machinery
import importlib.util
import numpy as np

from .color import Color

ETCPAK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                           "vendor", "etcpak", "_etcpak_none.pyd")
_etcpak = None

# Pixels of a block are written in this order, the values are ETC1 pixel indexes (x * 4 + y)
PIXEL_ORDER = np.array([0, 4, 1, 5, 8, 12, 9, 13, 2, 6, 3, 7, 10, 14, 11, 15])

def get_etcpak():
    global _etcpak
    if _etcpak is None:
        # Loaded from its path because the etcpak package __init__ needs archspec
        loader = importlib.machinery.ExtensionFileLoader("_etcpak_none", ETCPAK_PATH)
        spec = importlib.util.spec_from_file_location("_etcpak_none", ETCPAK_PATH, loader=loader)
        _etcpak = importlib.util.module_from_spec(spec)
        loader.exec_module(_etcpak)
    return _etcpak

def decompress(data, width, height, has_alpha):
    block_count = ((height + 3) // 4) * ((width + 3) // 4)
    block_length = 16 if has_alpha else 8

    source = np.frombuffer(bytes(data), dtype=np.uint8)[:block_count * block_length]
    blocks = np.zeros(block_count * block_length, dtype=np.uint8)
    blocks[:len(source)] = source
    blocks = blocks.reshape(block_count, block_length)

    # The 3DS stores a block as a little endian 64 bit word, etcpak reads it big endian
    color_blocks = np.ascontiguousarray(blocks[:, -8:][:, ::-1])

    # Decoded as a single column of blocks, block k covers the rows 4k to 4k + 3
    rgba = np.frombuffer(get_etcpak().decompress_etc1_rgb(color_blocks.tobytes(), 4, block_count * 4), dtype=np.uint8)
    pixels = rgba.reshape(block_count, 4, 4, 4)[:, PIXEL_ORDER % 4, PIXEL_ORDER // 4, :].copy()

    if not has_alpha:
        return pixels[:, :, :3].tobytes()

    alpha_bytes = blocks[:, :8]
    pixels[:, :, 3] = ((alpha_bytes[:, PIXEL_ORDER // 2] >> ((PIXEL_ORDER & 1) * 4)) & 0x0F) * 17
    return pixels.tobytes()

class ETC1:
    name = "ETC1"
    size = 3
    type = 27
    has_alpha = False

    def decompress(self, data, width, height):
        return decompress(data, width, height, False)

    def decode(self, data, index):
        r, g, b = data[0], data[1], data[2]
        return Color([r, g, b, 255])
