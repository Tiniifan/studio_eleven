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

##########################################
# ETC1 Encode Function
##########################################

# The encoder of etcpak is fast but loses about 2 dB more than a search encoder (Kuriimu2): the export uses the search
# below, etcpak is only used to measure an ETC1 texture quickly (best_pixel_format).
# Block layout: Khronos, OES_compressed_ETC1_RGB8_texture, https://registry.khronos.org/OpenGL/extensions/OES/OES_compressed_ETC1_RGB8_texture.txt

# Modifiers of the 8 tables, the pixel index 0 to 3 gives +a, +b, -a, -b
ETC1_TABLES = np.array([[2, 8], [5, 17], [9, 29], [13, 42], [18, 60], [24, 80], [33, 106], [47, 183]], dtype=np.int32)
ETC1_MODIFIERS = np.stack([ETC1_TABLES[:, 0], ETC1_TABLES[:, 1], -ETC1_TABLES[:, 0], -ETC1_TABLES[:, 1]], axis=1)

# Tables tried for a half block (the ones closest to how far its pixels are from their average), and the base colors
# tried around the fitted one
TABLE_COUNT = 4
BASE_WINDOW = np.arange(-2, 3)

# Blocks encoded together, it bounds the memory of the search
CHUNK_SIZE = 4096

def expand_base(q, bits):
    if bits == 4:
        return q * 17

    return (q << 3) | (q >> 2)

def quantize_base(values, bits):
    maximum = (1 << bits) - 1

    return np.clip(np.rint(values * maximum / 255), 0, maximum).astype(np.int32)

def get_half_block(flip, half):
    # ETC1 pixels (x * 4 + y) of a half block: the 2 columns left / right, or with flip the 2 rows top / bottom
    indexes = []

    for x in range(4):
        for y in range(4):
            if (flip == 0 and x // 2 == half) or (flip == 1 and y // 2 == half):
                indexes.append(x * 4 + y)

    return np.array(indexes)

def get_best_indexes(pixels, bases, modifiers):
    # For every pixel the modifier that lands closest, and the error of the half block
    colors = np.clip(bases[:, :, None, None, :] + modifiers[:, :, None, :, None], 0, 255)
    errors = ((pixels[:, None, :, None, :] - colors) ** 2).sum(-1)
    indexes = errors.argmin(-1)

    return indexes, np.take_along_axis(errors, indexes[..., None], -1)[..., 0].sum(-1)

def fit_bases(pixels, indexes, q, bits, modifiers):
    # Per channel, the base color around q that fits the chosen modifiers best (the modifier is the same on the 3
    # channels, the error splits by channel)
    chosen = np.take_along_axis(modifiers, indexes, -1)
    candidates = np.clip(q[..., None] + BASE_WINDOW, 0, (1 << bits) - 1)
    colors = np.clip(expand_base(candidates, bits)[:, :, None, :, :] + chosen[:, :, :, None, None], 0, 255)
    errors = ((pixels[:, None, :, :, None] - colors) ** 2).sum(2)

    return np.take_along_axis(candidates, errors.argmin(-1)[..., None], -1)[..., 0]

def pick_tables(pixels):
    luminance = pixels.mean(-1)
    spread = np.abs(luminance - luminance.mean(1, keepdims=True)).mean(1)
    sizes = ETC1_TABLES.mean(1) / 2 + 1

    return np.argsort(np.abs(np.log1p(spread)[:, None] - np.log1p(sizes)[None]), axis=1)[:, :TABLE_COUNT]

def search_half_blocks(pixels, bits):
    count = len(pixels)
    rows = np.arange(count)

    tables = pick_tables(pixels)
    modifiers = ETC1_MODIFIERS[tables]

    # The average color, then the base color that fits the modifiers it gets
    q = np.repeat(quantize_base(pixels.mean(1), bits)[:, None, :], TABLE_COUNT, axis=1)
    indexes, errors = get_best_indexes(pixels, expand_base(q, bits), modifiers)
    q = fit_bases(pixels, indexes, q, bits, modifiers)
    indexes, errors = get_best_indexes(pixels, expand_base(q, bits), modifiers)

    best = errors.argmin(1)

    return errors[rows, best], q[rows, best], tables[rows, best], indexes[rows, best]

def search_fixed_base(pixels, q, bits):
    # Best table and indexes for a base color that can't move (the second color of the differential mode)
    count = len(pixels)
    rows = np.arange(count)

    bases = np.repeat(expand_base(q, bits)[:, None, :], 8, axis=1)
    modifiers = np.repeat(ETC1_MODIFIERS[None], count, axis=0)
    indexes, errors = get_best_indexes(pixels, bases, modifiers)

    best = errors.argmin(1)

    return errors[rows, best], q, best, indexes[rows, best]

def pack_blocks(differential, flip, q0, q1, table0, table1, indexes0, indexes1):
    q0 = q0.astype(np.uint64)
    q1 = q1.astype(np.uint64)
    words = np.zeros(len(q0), dtype=np.uint64)

    for channel in range(3):
        shift = 60 - channel * 8

        if differential:
            # 5 bits of the first color, 3 bits of the difference to the second one
            delta = (q1[:, channel].astype(np.int64) - q0[:, channel].astype(np.int64)) & 7
            words |= (q0[:, channel] << np.uint64(shift - 1)) | (delta.astype(np.uint64) << np.uint64(shift - 4))
        else:
            words |= (q0[:, channel] << np.uint64(shift)) | (q1[:, channel] << np.uint64(shift - 4))

    words |= (table0.astype(np.uint64) << np.uint64(37)) | (table1.astype(np.uint64) << np.uint64(34))
    words |= np.uint64(differential << 33) | np.uint64(flip << 32)

    # The high bit of every pixel index in the bits 16 to 31, the low bit in the bits 0 to 15
    indexes = np.zeros((len(q0), 16), dtype=np.int64)
    indexes[:, get_half_block(flip, 0)] = indexes0
    indexes[:, get_half_block(flip, 1)] = indexes1

    high = ((indexes >> 1) << np.arange(16)).sum(1)
    low = ((indexes & 1) << np.arange(16)).sum(1)

    return words | (high.astype(np.uint64) << np.uint64(16)) | low.astype(np.uint64)

def encode_blocks(pixels):
    # pixels: the rgb of each block, ETC1 pixel order (x * 4 + y). Every flip and mode is tried, the smallest error wins.
    count = len(pixels)
    best_errors = np.full(count, np.inf)
    best_words = np.zeros(count, dtype=np.uint64)

    for flip in (0, 1):
        halves = [pixels[:, get_half_block(flip, 0)], pixels[:, get_half_block(flip, 1)]]
        individual = [search_half_blocks(halves[0], 4), search_half_blocks(halves[1], 4)]
        differential = [search_half_blocks(halves[0], 5), search_half_blocks(halves[1], 5)]

        # Individual mode: two colors of 4 bits
        options = [(0, individual[0], individual[1])]

        # Differential mode: two colors of 5 bits, the second one at -4 to +3 of the first one. One half keeps its color,
        # the other one is moved in range when it has to.
        first = differential[0]
        second_q = np.clip(np.clip(differential[1][1], first[1] - 4, first[1] + 3), 0, 31)
        options.append((1, first, get_moved_half(halves[1], differential[1], second_q)))

        second = differential[1]
        first_q = np.clip(np.clip(differential[0][1], second[1] - 3, second[1] + 4), 0, 31)
        options.append((1, get_moved_half(halves[0], differential[0], first_q), second))

        for mode, half0, half1 in options:
            errors = half0[0] + half1[0]
            better = errors < best_errors

            if better.any():
                words = pack_blocks(mode, flip, half0[1], half1[1], half0[2], half1[2], half0[3], half1[3])
                best_words = np.where(better, words, best_words)
                best_errors = np.where(better, errors, best_errors)

    return best_words

def get_moved_half(pixels, searched, q):
    # The searched result when the color did not move, else the best table for the moved color
    moved = search_fixed_base(pixels, q, 5)
    same = (q == searched[1]).all(1)

    errors = np.where(same, searched[0], moved[0])
    tables = np.where(same, searched[2], moved[2])
    indexes = np.where(same[:, None], searched[3], moved[3])

    return errors, q, tables, indexes

def compress_colors(blocks):
    # Same blocks are encoded once
    pixels = np.zeros((len(blocks), 16, 3), dtype=np.int32)
    pixels[:, PIXEL_ORDER] = blocks[:, :, :3]

    unique, inverse = np.unique(pixels.reshape(len(blocks), 48), axis=0, return_inverse=True)
    unique = unique.reshape(-1, 16, 3)
    words = np.zeros(len(unique), dtype=np.uint64)

    for start in range(0, len(unique), CHUNK_SIZE):
        words[start:start + CHUNK_SIZE] = encode_blocks(unique[start:start + CHUNK_SIZE])

    # The 3DS stores the 64 bit word little endian
    return words[inverse.reshape(-1)].astype('<u8').view(np.uint8).reshape(len(blocks), 8)

def compress_colors_fast(blocks):
    # Given to etcpak as a single column of blocks, block k covers the rows 4k to 4k + 3
    block_count = len(blocks)
    column = np.zeros((block_count, 4, 4, 4), dtype=np.uint8)
    column[:, PIXEL_ORDER % 4, PIXEL_ORDER // 4, :] = blocks
    column[:, :, :, 3] = 255

    color_blocks = np.frombuffer(get_etcpak().compress_etc1_rgb(column.tobytes(), 4, block_count * 4), dtype=np.uint8)

    return color_blocks.reshape(block_count, 8)[:, ::-1]

def compress(pixels, has_alpha, fast = False):
    # 16 pixels of the file make a block, pixel k of a block is the ETC1 pixel PIXEL_ORDER[k]
    block_count = len(pixels) // 16
    blocks = pixels[:block_count * 16].reshape(block_count, 16, 4)

    if fast:
        color_blocks = compress_colors_fast(blocks)
    else:
        color_blocks = compress_colors(blocks)

    if not has_alpha:
        return np.ascontiguousarray(color_blocks).tobytes()

    # 4 bits of alpha per ETC1 pixel before the color block, pixel p in the nibble p & 1 of the byte p // 2
    alpha = (blocks[:, :, 3].astype(np.int32) * 15 + 127) // 255
    alpha_blocks = np.zeros((block_count, 8), dtype=np.int32)

    for k in range(16):
        alpha_blocks[:, PIXEL_ORDER[k] // 2] |= alpha[:, k] << ((PIXEL_ORDER[k] & 1) * 4)

    return np.concatenate((alpha_blocks.astype(np.uint8), color_blocks), axis=1).tobytes()

class ETC1:
    name = "ETC1"
    size = 3
    bit_depth = 4
    type = 27
    has_alpha = False

    def encode(self, pixels):
        return compress(pixels, False)

    def encode_fast(self, pixels):
        return compress(pixels, False, True)

    def decompress(self, data, width, height):
        return decompress(data, width, height, False)

    def decode(self, data, index):
        r, g, b = data[0], data[1], data[2]
        return Color([r, g, b, 255])
