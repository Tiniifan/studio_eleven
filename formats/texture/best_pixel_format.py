import numpy as np

from . import img_tool, pixel_formats
from .pixel_formats.color import quantize, expand, get_luminance
from .pixel_formats.etc1 import decompress as etc1_decompress
from ...compression.best_compression import LEVEL5_COMPRESSIONS, get_best_compression

##########################################
# About this file
##########################################

# find_best_pixel_format(rgba, width, height, methods) tells which pixel format gives the lightest texture file
# (IMGC) that still looks like the image, without writing the file with every pixel format.
#
# The lightest file is not enough: A4 or L4 always win on size and destroy a color image. So a pixel format must first
# keep the image, then the lightest one wins. It is done in 3 steps, the cheap ones first so the costly one (the size,
# which needs the pixels to be encoded and their compression estimated) only runs on a few pixel formats:
#
#   1. Filter by what the image needs (like the automatic modes of tex3ds, auto-etc1 / auto-l8 / auto-l4):
#        - the alpha: an opaque image never takes a pixel format with alpha, an image with alpha only takes one with it;
#        - the colors: an alpha mask (every pixel white) takes A8 / A4, a gray image the luminance formats
#          (L8, L4, LA8, LA4), a color image the RGB ones;
#        - a pixel format that keeps the same information as another one in more bits is dropped (RGBA8 for an opaque
#          image: RBGR888 keeps the same colors in 24 bits).
#      What is left is 2 to 4 pixel formats (CANDIDATES).
#   2. Quality: each pixel format left is simulated (quantized and expanded back like the GPU does, or encoded and
#      decoded by etcpak for ETC1, fast), and its PSNR against the image is measured. A lossless pixel format is always
#      kept, a lossy one only above its threshold. Both thresholds come from the choices of Level-5 in the shipped textures:
#        - ETC1 / ETC1A4 (ETC_QUALITY_THRESHOLD, 32 dB): the textures Level-5 left out of ETC1 lose 27 to 31 dB in
#          etcpak ETC1 (31.3 dB for 90% of them), a new image usually keeps 32 to 38 dB (33.3 dB for the texture of
#          nobuganyan, that Kuriimu2 users put in ETC1A4). The ETC1 error is spread like noise over the 4x4 blocks.
#          etcpak loses about 2 dB more than the search encoder of the export (pixel_formats/etc1.py), so the texture
#          written is better than the one measured. Don't calibrate on shipped ETC1 textures: re-encoding ETC1 blocks
#          gives 38 dB (etcpak) to 47 dB (the export), far above what a new image gets;
#        - the pixel formats with fewer bits per channel (QUANTIZE_QUALITY_THRESHOLD, 50 dB, almost lossless):
#          Level-5 only uses them when they lose nothing. It keeps A8 when A4 would give 42 dB, RBGR888 when RGB565
#          would give 44 dB: cutting the bits makes steps in the gradients (banding), the PSNR hides them.
#      On 120 shipped textures (drawn like the games use the pixel formats), the pixel format of Level-5 comes back for
#      97% of them, the file is the lightest acceptable one every time (checked by writing every pixel format with every
#      compression), and it takes 108 ms per texture instead of 2.4 s for trying everything.
#   3. Size: the pixel formats left are encoded (numpy, and etcpak), their 8x8 tiles deduplicated like the file does,
#      and the size of the compressed tile table and tile data is estimated by best_compression (no compression is
#      run). The lightest file wins, the order of CANDIDATES decides a tie.
#
# Measured on the textures of Inazuma Eleven GO Galaxy, Yo-kai Watch 1 and Yo-kai Watch 3 (see .docs/formats/xi.md).
#
# Sources:
#   - The 3DS texture formats (PICA200) and their layout: 3dbrew, "GPU/Internal Registers" (texture formats),
#     https://www.3dbrew.org/wiki/GPU/Internal_Registers, and the encoders of tex3ds (devkitPro),
#     https://github.com/devkitPro/tex3ds (source/encode.cpp), whose automatic modes pick the format by the alpha.
#   - ETC1, measured with etcpak: https://github.com/wolfpld/etcpak, and its block layout: Khronos,
#     https://registry.khronos.org/OpenGL/extensions/OES/OES_compressed_ETC1_RGB8_texture.txt
#   - PSNR, the quality measure: https://en.wikipedia.org/wiki/Peak_signal-to-noise_ratio
#   - Luma of a color (BT.601), used by the luminance formats: https://en.wikipedia.org/wiki/Luma_(video)

##########################################
# CONST
##########################################

PIXEL_FORMATS = {
    "RGBA8": pixel_formats.RGBA8(),
    "RGBA4": pixel_formats.RGBA4(),
    "RGBA5551": pixel_formats.RGBA5551(),
    "RBGR888": pixel_formats.RBGR888(),
    "RGB565": pixel_formats.RGB565(),
    "LA8": pixel_formats.LA8(),
    "LA4": pixel_formats.LA4(),
    "L8": pixel_formats.L8(),
    "L4": pixel_formats.L4(),
    "A8": pixel_formats.A8(),
    "A4": pixel_formats.A4(),
    "ETC1": pixel_formats.ETC1(),
    "ETC1A4": pixel_formats.ETC1A4(),
}

# The pixel formats worth trying for each kind of image (alpha, colors), the lightest first
CANDIDATES = {
    ("OPAQUE", "GRAY"): ["L4", "ETC1", "L8"],
    ("OPAQUE", "COLOR"): ["ETC1", "RGB565", "RBGR888"],
    ("ALPHA", "MASK"): ["A4", "A8"],
    ("ALPHA", "GRAY"): ["LA4", "ETC1A4", "LA8"],
    ("ALPHA", "COLOR"): ["ETC1A4", "RGBA4", "RGBA5551", "RGBA8"],
}

# Lowest PSNR (dB) a lossy pixel format can have: ETC1 / ETC1A4, and the pixel formats that cut the bits of a channel
ETC_QUALITY_THRESHOLD = 32.0
QUANTIZE_QUALITY_THRESHOLD = 50.0

# PSNR given to a lossless pixel format
LOSSLESS = 99.0

##########################################
# Best Pixel Format Function
##########################################

def get_image_kind(pixels):
    # The alpha: every pixel opaque, or not
    if (pixels[:, 3] == 255).all():
        alpha = "OPAQUE"
    else:
        alpha = "ALPHA"

    # The colors: an alpha mask has only white pixels (the color is not stored at all), a gray image has r = g = b.
    # The pixels that can't be seen (alpha 0) don't count.
    visible = pixels[pixels[:, 3] > 0]
    rgb = visible[:, :3].astype(np.int32)

    if alpha == "ALPHA" and (rgb == 255).all():
        colors = "MASK"
    elif ((rgb[:, 0] == rgb[:, 1]) & (rgb[:, 1] == rgb[:, 2])).all():
        colors = "GRAY"
    else:
        colors = "COLOR"

    return alpha, colors

def simulate(pixels, name):
    # What the GPU reads back from the pixel format: the channels quantized then expanded to 8 bits
    decoded = np.zeros((len(pixels), 4), dtype=np.int32)
    decoded[:, 3] = 255

    if name == "RGBA8":
        decoded[:] = pixels
    elif name == "RBGR888":
        decoded[:, :3] = pixels[:, :3]
    elif name == "RGBA4":
        for i in range(4):
            decoded[:, i] = expand(quantize(pixels[:, i], 4), 4)
    elif name == "RGBA5551":
        for i in range(3):
            decoded[:, i] = expand(quantize(pixels[:, i], 5), 5)

        decoded[:, 3] = quantize(pixels[:, 3], 1) * 255
    elif name == "RGB565":
        decoded[:, 0] = expand(quantize(pixels[:, 0], 5), 5)
        decoded[:, 1] = expand(quantize(pixels[:, 1], 6), 6)
        decoded[:, 2] = expand(quantize(pixels[:, 2], 5), 5)
    elif name in ("L8", "LA8"):
        luminance = get_luminance(pixels)

        for i in range(3):
            decoded[:, i] = luminance

        if name == "LA8":
            decoded[:, 3] = pixels[:, 3]
    elif name in ("L4", "LA4"):
        luminance = expand(quantize(get_luminance(pixels), 4), 4)

        for i in range(3):
            decoded[:, i] = luminance

        if name == "LA4":
            decoded[:, 3] = expand(quantize(pixels[:, 3], 4), 4)
    elif name == "A8":
        decoded[:, :3] = 255
        decoded[:, 3] = pixels[:, 3]
    elif name == "A4":
        decoded[:, :3] = 255
        decoded[:, 3] = expand(quantize(pixels[:, 3], 4), 4)
    elif name in ("ETC1", "ETC1A4"):
        # etcpak encodes then decodes the blocks, the pixels stay in the order of the file
        pixel_format = PIXEL_FORMATS[name]
        data = pixel_format.encode_fast(pixels)
        block_count = len(pixels) // 16
        rgb = np.frombuffer(etc1_decompress(data, 4, block_count * 4, pixel_format.has_alpha), dtype=np.uint8)

        if pixel_format.has_alpha:
            decoded[:] = rgb.reshape(-1, 4)
        else:
            decoded[:, :3] = rgb.reshape(-1, 3)
    else:
        raise Exception(f"Unknown pixel format: {name}")

    return decoded

def get_quality_threshold(name):
    if name in ("ETC1", "ETC1A4"):
        return ETC_QUALITY_THRESHOLD

    return QUANTIZE_QUALITY_THRESHOLD

def get_psnr(pixels, decoded):
    # The color error of a pixel counts as much as the pixel can be seen (its alpha), the alpha error always counts
    pixels = pixels.astype(np.float64)
    decoded = decoded.astype(np.float64)

    visibility = pixels[:, 3:4] / 255
    color_error = np.sum((pixels[:, :3] - decoded[:, :3]) ** 2 * visibility, axis=1)
    alpha_error = (pixels[:, 3] - decoded[:, 3]) ** 2

    mse = np.mean(color_error + alpha_error) / 4

    if mse == 0:
        return LOSSLESS

    return min(10 * np.log10(255 ** 2 / mse), LOSSLESS)

def get_file_size(pixels, name, methods):
    # Header (0x48) + the compressed tile table on 4 bytes + the compressed tile data, the file padded to 16 bytes
    pixel_format = PIXEL_FORMATS[name]
    data = None

    # The ETC1 blocks of etcpak weigh the same as the ones of the export, and they are much faster to get
    if name in ("ETC1", "ETC1A4"):
        data = pixel_format.encode_fast(pixels)

    table, tile_data = img_tool.encode_tiles(pixels, pixel_format, data)

    table_method, table_size = get_best_compression(table, methods, True)
    data_method, data_size = get_best_compression(tile_data, methods, True)

    size = 0x48 + ((table_size + 3) & ~3) + data_size

    return (size + 15) & ~15

def get_pixel_format_scores(rgba, width, height, methods = LEVEL5_COMPRESSIONS):
    # Give the kind of image and, for each candidate pixel format, its PSNR and its file size (None when rejected).
    pixels = img_tool.get_file_pixels(rgba, width, height)
    kind = get_image_kind(pixels)
    scores = {}

    for name in CANDIDATES[kind]:
        # 2. Quality first, it is cheaper than the size
        psnr = get_psnr(pixels, simulate(pixels, name))
        size = None

        # 3. Size of the pixel formats that keep the image
        if psnr >= get_quality_threshold(name):
            size = get_file_size(pixels, name, methods)

        scores[name] = (psnr, size)

    return kind, scores

def find_best_pixel_format(rgba, width, height, methods = LEVEL5_COMPRESSIONS):
    # Give the pixel format that makes the lightest texture file and keeps the image (rows from the top, rgba bytes).
    kind, scores = get_pixel_format_scores(rgba, width, height, methods)

    best_name = None

    for name in CANDIDATES[kind]:
        size = scores[name][1]

        if size is not None:
            if best_name is None or size < scores[best_name][1]:
                best_name = name

    # The last candidate keeps every image losslessly
    if best_name is None:
        best_name = CANDIDATES[kind][-1]

    return best_name
