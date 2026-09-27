"""Unity AssetBundle container (UnityFS / UnityWeb / UnityRaw).

Layout and flag handling ported from UnityPy's BundleFile
(https://github.com/K0lb3/UnityPy/blob/master/UnityPy/files/BundleFile.py)
and AssetStudio's BundleFile.cs (https://github.com/aelurum/AssetStudioMod).
"""

import re

from .binary_reader import BinaryReader
from . import compression

# ArchiveFlags
FLAG_COMPRESSION_MASK = 0x3F
FLAG_BLOCKS_AND_DIRECTORY_COMBINED = 0x40
FLAG_BLOCKS_INFO_AT_END = 0x80
FLAG_OLD_WEB_PLUGIN_COMPAT = 0x100
FLAG_BLOCK_INFO_PADDING_AT_START = 0x200
FLAG_ENCRYPTION_OLD = 0x200
FLAG_ENCRYPTION_NEW = 0x1400


class BundleEntry:
    """A file stored inside the bundle (a SerializedFile, a .resS resource, ...)."""

    __slots__ = ("path", "offset", "size", "flags")

    def __init__(self, path, offset, size, flags=0):
        self.path = path
        self.offset = offset
        self.size = size
        self.flags = flags

    def __repr__(self):
        return "BundleEntry(%r, size=%d)" % (self.path, self.size)


def _parse_engine_version(text):
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in match.groups()) if match else (0, 0, 0)


class BundleFile:
    def __init__(self, data):
        reader = BinaryReader(data, ">")
        self.signature = reader.read_cstring()
        self.format_version = reader.read_u32()
        self.player_version = reader.read_cstring()
        self.engine_version = reader.read_cstring()
        self.entries = []
        self._data = b""

        if self.signature == "UnityFS" or (self.signature in ("UnityWeb", "UnityRaw") and self.format_version == 6):
            self._read_fs(reader)
        elif self.signature in ("UnityWeb", "UnityRaw"):
            self._read_web_raw(reader)
        else:
            raise ValueError("Unknown bundle signature: %r" % self.signature)

    @staticmethod
    def is_bundle(data):
        head = bytes(data[:8])
        return head.startswith(b"UnityFS\x00") or head.startswith(b"UnityWeb") or head.startswith(b"UnityRaw")

    def _read_web_raw(self, reader):
        if self.format_version >= 4:
            reader.skip(16 + 4)  # hash + crc
        reader.read_u32()  # minimum streamed bytes
        header_size = reader.read_u32()
        reader.read_u32()  # levels to download before streaming
        level_count = reader.read_i32()
        reader.skip(4 * 2 * (level_count - 1))
        compressed_size = reader.read_u32()
        reader.read_u32()  # uncompressed size
        if self.format_version >= 2:
            reader.read_u32()
        if self.format_version >= 3:
            reader.read_u32()

        reader.seek(header_size)
        payload = reader.read_bytes(compressed_size)
        if self.signature == "UnityWeb":
            payload = compression.decompress_lzma(payload, True)

        blocks = BinaryReader(payload, ">")
        count = blocks.read_i32()
        for _ in range(count):
            path = blocks.read_cstring()
            offset = blocks.read_u32()
            size = blocks.read_u32()
            self.entries.append(BundleEntry(path, offset, size))
        self._data = payload

    def _read_fs(self, reader):
        reader.read_i64()  # total bundle size
        compressed_size = reader.read_u32()
        uncompressed_size = reader.read_u32()
        flags = reader.read_u32()
        if self.signature != "UnityFS":
            reader.read_u8()

        # Before these versions the 0x200 bit meant UnityCN encryption instead of padding
        version = _parse_engine_version(self.engine_version)
        old_flags = (
            version < (2020,)
            or (version[0] == 2020 and version < (2020, 3, 34))
            or (version[0] == 2021 and version < (2021, 3, 2))
            or (version[0] == 2022 and version < (2022, 1, 1))
        )
        encryption_mask = FLAG_ENCRYPTION_OLD if old_flags else FLAG_ENCRYPTION_NEW
        if flags & encryption_mask:
            raise NotImplementedError("Encrypted (UnityCN) bundles are not supported")

        if self.format_version >= 7 or (version[0] == 2019 and version >= (2019, 4, 15)):
            reader.align(16)

        if flags & FLAG_BLOCKS_INFO_AT_END:
            saved = reader.position
            reader.seek(len(reader) - compressed_size)
            info_bytes = reader.read_view(compressed_size)
            reader.seek(saved)
        else:
            info_bytes = reader.read_view(compressed_size)

        info = BinaryReader(
            compression.decompress(info_bytes, uncompressed_size, flags & FLAG_COMPRESSION_MASK), ">"
        )
        info.skip(16)  # uncompressed data hash
        block_count = info.read_i32()
        blocks = []
        for _ in range(block_count):
            block_uncompressed = info.read_u32()
            block_compressed = info.read_u32()
            block_flags = info.read_u16()
            blocks.append((block_uncompressed, block_compressed, block_flags))

        node_count = info.read_i32()
        for _ in range(node_count):
            offset = info.read_i64()
            size = info.read_i64()
            node_flags = info.read_u32()
            path = info.read_cstring()
            self.entries.append(BundleEntry(path, offset, size, node_flags))

        if not old_flags and flags & FLAG_BLOCK_INFO_PADDING_AT_START:
            reader.align(16)

        chunks = []
        for block_uncompressed, block_compressed, block_flags in blocks:
            raw = reader.read_view(block_compressed)
            chunks.append(compression.decompress(raw, block_uncompressed, block_flags & FLAG_COMPRESSION_MASK))
        self._data = b"".join(chunks)

    def read_entry(self, entry):
        return memoryview(self._data)[entry.offset:entry.offset + entry.size]
