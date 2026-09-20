import math
from struct import pack, unpack_from

from ..compression import *

LUT_MAGIC = b"LUTC00\x00\x00"
LUT_HEADER_SIZE = 16
LUT_ENTRY_COUNT = 256


def to_float32(value):
    return unpack_from("<f", pack("<f", value))[0]


def shortest_float32(value):
    for digits in range(1, 10):
        text = f"{value:.{digits}g}"
        if to_float32(float(text)) == value:
            return float(text)
    return value


class Lut:
    """256 values and the 256 differences to the next value, the flag is a byte the engine keeps next to the table."""

    def __init__(self, values, deltas, flag=0):
        self.values = list(values)
        self.deltas = list(deltas)
        self.flag = flag

    def __eq__(self, other):
        return isinstance(other, Lut) and (self.values, self.deltas, self.flag) == (other.values, other.deltas, other.flag)

    def to_dict(self, name=None):
        data = {"name": name} if name is not None else {}
        data["flag"] = self.flag
        data["values"] = [shortest_float32(value) for value in self.values]
        data["deltas"] = [shortest_float32(delta) for delta in self.deltas]
        return data

    @classmethod
    def from_dict(cls, data):
        return cls([to_float32(value) for value in data["values"]], [to_float32(delta) for delta in data["deltas"]], data.get("flag", 0))

    def to_table(self):
        """The 256 words of the GPU table: a 12 bit value and a 12 bit difference (sign and magnitude), like the engine builds them."""
        return [quantize_value(value) | (quantize_delta(delta) << 12) for value, delta in zip(self.values, self.deltas)]


def quantize_value(value):
    if not math.isfinite(value) or value <= 0.0:
        return 0

    scaled = to_float32(value * 4096.0)
    return 4095 if scaled >= 4096.0 else int(scaled)


def quantize_delta(delta):
    if not math.isfinite(delta) or delta == 0.0:
        return 0

    scaled = to_float32(delta * 2048.0)
    sign = 0 if scaled >= 0.0 else 2048
    magnitude = abs(scaled)

    return sign | (2047 if magnitude >= 2048.0 else int(magnitude))


def read_lut(data):
    if data[:8] != LUT_MAGIC:
        raise ValueError(f"Unknown LUT magic: {data[:8]!r}")

    flag = unpack_from("<H", data, 8)[0]
    payload_offset = unpack_from("<H", data, 10)[0]

    # Stored blocks keep their alignment padding
    payload = compressor.decompress(data[payload_offset:])[:LUT_ENTRY_COUNT * 8]

    if len(payload) != LUT_ENTRY_COUNT * 8:
        raise ValueError(f"Unexpected LUT payload size: {len(payload)}")

    return Lut(unpack_from(f"<{LUT_ENTRY_COUNT}f", payload, 0), unpack_from(f"<{LUT_ENTRY_COUNT}f", payload, LUT_ENTRY_COUNT * 4), flag)


def write_lut(lut):
    payload = pack(f"<{LUT_ENTRY_COUNT}f", *lut.values) + pack(f"<{LUT_ENTRY_COUNT}f", *lut.deltas)
    return LUT_MAGIC + pack("<HHI", lut.flag, LUT_HEADER_SIZE, 0) + compress(payload)
