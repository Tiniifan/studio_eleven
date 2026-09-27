"""Decompression routines used by Unity archives.

LZMA handling follows UnityPy's CompressionHelper (https://github.com/K0lb3/UnityPy).
The LZ4 block decoder is a pure Python implementation of the official LZ4 block
format specification (https://github.com/lz4/lz4/blob/dev/doc/lz4_Block_format.md).
If the optional `lz4` package is importable, it is used instead for speed.
"""

import lzma
import struct

try:
    import lz4.block as _lz4_block
except ImportError:
    _lz4_block = None


COMPRESSION_NONE = 0
COMPRESSION_LZMA = 1
COMPRESSION_LZ4 = 2
COMPRESSION_LZ4HC = 3
COMPRESSION_LZHAM = 4


def decompress_lz4(src, uncompressed_size):
    if _lz4_block is not None:
        return _lz4_block.decompress(bytes(src), uncompressed_size)

    src = bytes(src)
    src_len = len(src)
    dst = bytearray()
    pos = 0
    while pos < src_len:
        token = src[pos]
        pos += 1

        literal_len = token >> 4
        if literal_len == 15:
            while True:
                extra = src[pos]
                pos += 1
                literal_len += extra
                if extra != 255:
                    break
        if literal_len:
            dst += src[pos:pos + literal_len]
            pos += literal_len

        # The last sequence only contains literals
        if pos >= src_len:
            break

        offset = src[pos] | (src[pos + 1] << 8)
        pos += 2
        if offset == 0:
            raise ValueError("LZ4: invalid match offset")

        match_len = token & 0x0F
        if match_len == 15:
            while True:
                extra = src[pos]
                pos += 1
                match_len += extra
                if extra != 255:
                    break
        match_len += 4

        start = len(dst) - offset
        if offset >= match_len:
            dst += dst[start:start + match_len]
        else:
            # Overlapping copy: the match repeats the last `offset` bytes
            pattern = dst[start:]
            repeat = match_len // offset + 1
            dst += (pattern * repeat)[:match_len]

    if len(dst) != uncompressed_size:
        raise ValueError("LZ4: expected %d bytes, got %d" % (uncompressed_size, len(dst)))
    return bytes(dst)


def decompress_lzma(data, read_uncompressed_size=False):
    props, dict_size = struct.unpack_from("<BI", data, 0)
    lc = props % 9
    remainder = props // 9
    pb = remainder // 5
    lp = remainder % 5
    decompressor = lzma.LZMADecompressor(
        format=lzma.FORMAT_RAW,
        filters=[{"id": lzma.FILTER_LZMA1, "dict_size": dict_size, "lc": lc, "lp": lp, "pb": pb}],
    )
    offset = 13 if read_uncompressed_size else 5
    return decompressor.decompress(bytes(data[offset:]))


def decompress(data, uncompressed_size, compression):
    if compression == COMPRESSION_NONE:
        return bytes(data)
    if compression == COMPRESSION_LZMA:
        return decompress_lzma(data)
    if compression in (COMPRESSION_LZ4, COMPRESSION_LZ4HC):
        return decompress_lz4(data, uncompressed_size)
    raise NotImplementedError("Unsupported compression type: %d" % compression)
