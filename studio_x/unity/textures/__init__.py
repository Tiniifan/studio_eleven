"""Texture2D decoding to RGBA8.

TextureFormat values and raw format layouts come from UnityPy's enums/TextureFormat.py and
export/Texture2DConverter.py (https://github.com/K0lb3/UnityPy).
ETC/EAC/BCn blocks are decoded by etcpak (https://github.com/K0lb3/etcpak, MIT), shipped as a
native module in third_party/etcpak. Version 0.9.13 is used because the decompression
bindings of 0.9.14+ write into an invalid buffer and crash.
Returned pixels keep Unity's row order (bottom row first), which matches Blender images.
"""

import importlib.machinery
import importlib.util
import os
import struct

from . import astc

ETCPAK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "third_party", "etcpak", "_etcpak_none.pyd")
_etcpak = None


def get_etcpak():
    """Load the bundled etcpak extension directly (its package __init__ needs archspec)."""
    global _etcpak
    if _etcpak is None:
        if not os.path.isfile(ETCPAK_PATH):
            raise ImportError("etcpak native module not found: %s" % ETCPAK_PATH)
        loader = importlib.machinery.ExtensionFileLoader("_etcpak_none", ETCPAK_PATH)
        spec = importlib.util.spec_from_file_location("_etcpak_none", ETCPAK_PATH, loader=loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        _etcpak = module
    return _etcpak


ASTC_BLOCKS = {
    48: 4, 49: 5, 50: 6, 51: 8, 52: 10, 53: 12,
    54: 4, 55: 5, 56: 6, 57: 8, 58: 10, 59: 12,
}

# TextureFormat -> (etcpak function name, block size in bytes)
ETCPAK_DECODERS = {
    10: ("decompress_bc1", 8),          # DXT1
    12: ("decompress_bc3", 16),         # DXT5
    25: ("decompress_bc7", 16),
    26: ("decompress_bc4", 8),
    27: ("decompress_bc5", 16),
    34: ("decompress_etc1_rgb", 8),     # ETC_RGB4
    60: ("decompress_etc1_rgb", 8),     # ETC_RGB4_3DS
    41: ("decompress_etc2_r11", 8),     # EAC_R
    43: ("decompress_etc2_rg11", 16),   # EAC_RG
    45: ("decompress_etc2_rgb", 8),
    47: ("decompress_etc2_rgba", 16),
    61: ("decompress_etc2_rgba", 16),   # ETC_RGBA8_3DS
}


def _decode_etcpak(data, width, height, function_name, block_size):
    # etcpak only accepts sizes that are multiples of 4: decode padded then crop
    padded_w = (width + 3) // 4 * 4
    padded_h = (height + 3) // 4 * 4
    length = (padded_w // 4) * (padded_h // 4) * block_size
    pixels = getattr(get_etcpak(), function_name)(bytes(data[:length]), padded_w, padded_h)
    if padded_w == width and padded_h == height:
        return bytes(pixels)
    out = bytearray(width * height * 4)
    for row in range(height):
        src = row * padded_w * 4
        out[row * width * 4:(row + 1) * width * 4] = pixels[src:src + width * 4]
    return bytes(out)


FORMAT_NAMES = {
    1: "Alpha8", 2: "ARGB4444", 3: "RGB24", 4: "RGBA32", 5: "ARGB32", 7: "RGB565", 9: "R16",
    10: "DXT1", 12: "DXT5", 13: "RGBA4444", 14: "BGRA32", 15: "RHalf", 17: "RGBAHalf",
    25: "BC7", 26: "BC4", 27: "BC5", 28: "DXT1Crunched", 29: "DXT5Crunched", 34: "ETC_RGB4",
    41: "EAC_R", 43: "EAC_RG", 45: "ETC2_RGB", 46: "ETC2_RGBA1", 47: "ETC2_RGBA8", 62: "RG16",
    63: "R8", 64: "ETC_RGB4Crunched", 65: "ETC2_RGBA8Crunched",
}
FORMAT_NAMES.update({fmt: "ASTC_%dx%d" % (size, size) for fmt, size in ASTC_BLOCKS.items()})


def _raw_to_rgba(data, width, height, fmt):
    count = width * height
    out = bytearray(count * 4)
    if fmt == 4:  # RGBA32
        return bytes(data[:count * 4])
    if fmt == 3:  # RGB24
        out[0::4] = data[0:count * 3:3]
        out[1::4] = data[1:count * 3:3]
        out[2::4] = data[2:count * 3:3]
        out[3::4] = b"\xff" * count
    elif fmt == 5:  # ARGB32
        out[3::4] = data[0:count * 4:4]
        out[0::4] = data[1:count * 4:4]
        out[1::4] = data[2:count * 4:4]
        out[2::4] = data[3:count * 4:4]
    elif fmt == 14:  # BGRA32
        out[2::4] = data[0:count * 4:4]
        out[1::4] = data[1:count * 4:4]
        out[0::4] = data[2:count * 4:4]
        out[3::4] = data[3:count * 4:4]
    elif fmt == 1:  # Alpha8
        out[0::4] = out[1::4] = out[2::4] = b"\xff" * count
        out[3::4] = data[:count]
    elif fmt == 63:  # R8
        out[0::4] = data[:count]
        out[3::4] = b"\xff" * count
    elif fmt == 62:  # RG16
        out[0::4] = data[0:count * 2:2]
        out[1::4] = data[1:count * 2:2]
        out[3::4] = b"\xff" * count
    elif fmt == 9:  # R16
        values = struct.unpack_from("<%dH" % count, data)
        out[0::4] = bytes(v >> 8 for v in values)
        out[3::4] = b"\xff" * count
    elif fmt in (2, 13, 7):
        values = struct.unpack_from("<%dH" % count, data)
        for i, v in enumerate(values):
            if fmt == 7:  # RGB565
                r, g, b = v >> 11 & 0x1F, v >> 5 & 0x3F, v & 0x1F
                out[i * 4:i * 4 + 4] = bytes((r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2, 255))
            else:
                n = [(v >> shift & 0xF) * 17 for shift in (12, 8, 4, 0)]
                # ARGB4444 stores A,R,G,B from the high nibble, RGBA4444 stores R,G,B,A
                out[i * 4:i * 4 + 4] = bytes(n[1:] + n[:1] if fmt == 2 else n)
    elif fmt in (15, 17):  # RHalf / RGBAHalf
        channels = 1 if fmt == 15 else 4
        values = struct.unpack_from("<%de" % (count * channels), data)
        for i in range(count):
            px = values[i * channels:(i + 1) * channels]
            rgba = (px[0], 0.0, 0.0, 1.0) if channels == 1 else px
            out[i * 4:i * 4 + 4] = bytes(max(0, min(255, int(round(c * 255)))) for c in rgba)
    else:
        raise NotImplementedError("Unsupported texture format %s" % FORMAT_NAMES.get(fmt, fmt))
    return bytes(out)


def get_image_data(texture, environment):
    stream = texture.get("m_StreamData") or {}
    if stream.get("path") and stream.get("size"):
        return environment.get_resource(stream["path"], stream["offset"], stream["size"])
    return texture["image data"]


def decode_texture2d(texture, environment):
    """Return (width, height, rgba_bytes) for a deserialized Texture2D dict (first mip only)."""
    width = texture["m_Width"]
    height = texture["m_Height"]
    fmt = texture["m_TextureFormat"]
    data = get_image_data(texture, environment)

    if fmt in ASTC_BLOCKS:
        size = ASTC_BLOCKS[fmt]
        length = ((width + size - 1) // size) * ((height + size - 1) // size) * 16
        return width, height, astc.decode_astc(data[:length], width, height, size, size)
    if fmt in ETCPAK_DECODERS:
        function_name, block_size = ETCPAK_DECODERS[fmt]
        return width, height, _decode_etcpak(data, width, height, function_name, block_size)
    return width, height, _raw_to_rgba(data, width, height, fmt)
