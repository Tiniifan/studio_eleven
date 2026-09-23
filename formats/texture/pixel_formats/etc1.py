import os
import sys
import platform
import importlib.machinery
import importlib.util
import numpy as np

from .color import Color

ETCPAK_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                             "vendor", "etcpak")
etcpak_module = None

# Pixels of a block are written in this order, the values are ETC1 pixel indexes (x * 4 + y)
PIXEL_ORDER = np.array([0, 4, 1, 5, 8, 12, 9, 13, 2, 6, 3, 7, 10, 14, 11, 15])

def etcpak_path():
    if sys.platform == "win32":
        return os.path.join(ETCPAK_FOLDER, "_etcpak_none.pyd")

    system = "linux"
    if sys.platform == "darwin":
        system = "macos"

    machine = "x86_64"
    if platform.machine().lower() in ["arm64", "aarch64"]:
        machine = "arm64"

    return os.path.join(ETCPAK_FOLDER, f"_etcpak_none_{system}_{machine}.so")

def get_etcpak():
    global etcpak_module

    if etcpak_module is None:
        path = etcpak_path()

        if not os.path.isfile(path):
            raise ImportError(f"No etcpak module for this platform: {path}")

        # Loaded from its path because the etcpak package __init__ needs archspec
        loader = importlib.machinery.ExtensionFileLoader("_etcpak_none", path)
        spec = importlib.util.spec_from_file_location("_etcpak_none", path, loader=loader)
        etcpak_module = importlib.util.module_from_spec(spec)
        loader.exec_module(etcpak_module)

    return etcpak_module

def decompress(data, width, height, has_alpha):
    block_count = ((height + 3) // 4) * ((width + 3) // 4)

    block_length = 8
    if has_alpha:
        block_length = 16

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
