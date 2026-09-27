"""Endian-aware binary reader working on an in-memory buffer.

Mirrors the EndianBinaryReader found in UnityPy (https://github.com/K0lb3/UnityPy)
and AssetStudio (https://github.com/Perfare/AssetStudio).
"""

import struct


class BinaryReader:
    __slots__ = ("data", "position", "endian")

    def __init__(self, data, endian="<", position=0):
        self.data = memoryview(data) if not isinstance(data, memoryview) else data
        self.endian = endian
        self.position = position

    def __len__(self):
        return len(self.data)

    @property
    def remaining(self):
        return len(self.data) - self.position

    def seek(self, position):
        self.position = position

    def skip(self, count):
        self.position += count

    def align(self, alignment=4):
        self.position = (self.position + alignment - 1) // alignment * alignment

    def read_bytes(self, count):
        start = self.position
        self.position += count
        return bytes(self.data[start:self.position])

    def read_view(self, count):
        start = self.position
        self.position += count
        return self.data[start:self.position]

    def _unpack(self, fmt, size):
        value = struct.unpack_from(self.endian + fmt, self.data, self.position)[0]
        self.position += size
        return value

    def read_bool(self):
        return self._unpack("?", 1)

    def read_i8(self):
        return self._unpack("b", 1)

    def read_u8(self):
        return self._unpack("B", 1)

    def read_i16(self):
        return self._unpack("h", 2)

    def read_u16(self):
        return self._unpack("H", 2)

    def read_i32(self):
        return self._unpack("i", 4)

    def read_u32(self):
        return self._unpack("I", 4)

    def read_i64(self):
        return self._unpack("q", 8)

    def read_u64(self):
        return self._unpack("Q", 8)

    def read_f32(self):
        return self._unpack("f", 4)

    def read_f64(self):
        return self._unpack("d", 8)

    def read_array(self, fmt, count):
        """Read `count` primitives of struct format `fmt` as a tuple."""
        size = struct.calcsize(fmt) * count
        values = struct.unpack_from("%s%d%s" % (self.endian, count, fmt), self.data, self.position)
        self.position += size
        return values

    def read_cstring(self, encoding="utf-8"):
        data = self.data
        end = self.position
        length = len(data)
        # memoryview has no find(), so search on a bytes slice in chunks
        while end < length:
            chunk = bytes(data[end:min(end + 256, length)])
            index = chunk.find(b"\x00")
            if index != -1:
                end += index
                break
            end += len(chunk)
        value = bytes(data[self.position:end]).decode(encoding, "replace")
        self.position = end + 1
        return value

    def read_aligned_string(self):
        length = self.read_i32()
        if 0 < length <= self.remaining:
            value = bytes(self.data[self.position:self.position + length]).decode("utf-8", "surrogateescape")
            self.position += length
        else:
            value = ""
        self.align(4)
        return value
