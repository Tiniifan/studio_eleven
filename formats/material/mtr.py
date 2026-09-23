from struct import pack, unpack_from

from ...compression import *
from .lut import Lut, read_lut, write_lut, shortest_float32, to_float32, LUT_ENTRY_COUNT as LUT_VALUE_COUNT

##########################################
# Constants
##########################################

MAGIC = b"MTR"
PLATFORM = b"C"
LEGACY_MAGIC = b"XMTR"
LEGACY_LUT_MAGIC = b"XLUT"

HEADER_SIZE = 24
LEGACY_HEADER_SIZE = 20
LEGACY_LUT_HEADER_SIZE = 12

# V1 keeps 57 ints, V2 reads one more, both loaders fill what the body doesn't cover with the defaults below
V1_INT_COUNT = 57
V2_INT_COUNT = 58

# The order registers 0x1D0 to 0x1D2 pack their seven 4 bit fields in, which is also the order of the body
TABLES = ("D0", "D1", "SP", "FR", "RR", "RG", "RB")

# The seven header offsets are not in that order, the loader rotates them by three
HEADER_TABLES = ("RR", "RG", "RB", "D0", "D1", "SP", "FR")

# Value of lutInput* in the fragment shaders
LUT_INPUTS = ("NH", "VH", "NV", "LN", "SP", "CP")

# lutScale*, the two holes are values the hardware doesn't define
LUT_SCALES = (1.0, 2.0, 4.0, 8.0, None, None, 0.25, 0.5)

COLORS = ("ambient", "emission", "diffuse", "specular0", "specular1")

# Body index of the first int of each field group
ABS_INPUT = 0
LUT_ENABLED = 7
INPUT_SELECT = 10
INPUT_SCALE = 17
LUT_POINTERS = 24
CONFIG = 31
COLOR = 32
FLAGS = 47

# (body index, field, is a flag the loader reduces to 0 or 1)
FLAG_LAYOUT = (
    (47, "shadow_selector", False),
    (48, "invert_shadow", True),
    (49, "shadow_primary", True),
    (50, "shadow_secondary", True),
    (51, "shadow_alpha", True),
    (52, "bump_renorm", True),
    (53, "bump_selector", False),
    (54, "bump_mode", False),
    (55, "clamp_highlights", True),
    # 0 uses no Fresnel term, 1 the primary colour, 2 the secondary one, 3 both
    (56, "fresnel_selector", False),
)

# Ints the loader never reads out of the file: 24 to 30 are the stack slots it overwrites with the
# LUT pointers, 57 is the V2 tail and holds uninitialised bytes in every shipped file
UNUSED_INTS = (24, 25, 26, 27, 28, 29, 30, 57)

# What the loaders prefill their buffer with, a shorter body keeps these
DEFAULTS = (
    [0] * 7                                     # abs input
    + [0, 0, 0]                                 # lut enabled
    + [3, 3, 4, 3, 3, 3, 3]                     # input select, SP reads the spot term
    + [0] * 7                                   # input scale
    + [0] * 7                                   # lut pointers
    + [0]                                       # config
    + [0x3E4CCCCD] * 3                          # ambient 0.2
    + [0] * 3                                   # emission
    + [0x3F4CCCCD] * 3                          # diffuse 0.8
    + [0] * 3                                   # specular0
    + [0] * 3                                   # specular1
    + [0] * 10                                  # flags
    + [0]                                       # V2 tail
)


FLAG_BOOL_FIELDS = {field for _, field, is_flag in FLAG_LAYOUT if is_flag}

LIGHTING_FIELDS = ("config", "lut_enabled_d0", "lut_enabled_d1", "lut_enabled_refl") + tuple(field for _, field, _ in FLAG_LAYOUT)


def _int_to_float(value):
    return unpack_from("<f", pack("<I", value))[0]


def _float_to_int(value):
    return unpack_from("<I", pack("<f", value))[0]

##########################################
# Table
##########################################

class MaterialTable:
    """Configuration of one lighting lookup table plus the table itself when the file carries one."""

    def __init__(self, abs_input=False, input_select=3, scale=0, lut=None):
        self.abs_input = bool(abs_input)
        self.input_select = int(input_select)
        self.scale = int(scale)
        self.lut = lut

    def __eq__(self, other):
        return isinstance(other, MaterialTable) and self.to_dict() == other.to_dict()

    def __repr__(self):
        return f"MaterialTable({self.to_dict()})"

    @property
    def scale_value(self):
        return LUT_SCALES[self.scale] if self.scale < len(LUT_SCALES) else None

    def to_dict(self):
        data = {
            "abs_input": self.abs_input,
            "input_select": LUT_INPUTS[self.input_select] if self.input_select < len(LUT_INPUTS) else self.input_select,
            "scale": self.scale,
        }

        if self.lut is not None:
            data["lut"] = self.lut.to_dict()

        return data

    @classmethod
    def from_dict(cls, data):
        input_select = data["input_select"]

        if isinstance(input_select, str):
            input_select = LUT_INPUTS.index(input_select)

        lut = data.get("lut")

        return cls(data["abs_input"], input_select, data["scale"], Lut.from_dict(lut) if lut else None)

##########################################
# Material
##########################################

class Material:
    """The lighting material of one mesh: five colours, the fragment lighting flags and up to seven LUTs."""

    def __init__(self, file_version=2):
        self.file_version = file_version

        for name in COLORS:
            setattr(self, name, (0.0, 0.0, 0.0))

        self.ambient = (0.2, 0.2, 0.2)
        self.diffuse = (0.8, 0.8, 0.8)

        self.tables = {name: MaterialTable(input_select=DEFAULTS[INPUT_SELECT + TABLES.index(name)]) for name in TABLES}

        self.config = 0
        self.lut_enabled_d0 = False
        self.lut_enabled_d1 = False
        self.lut_enabled_refl = False

        for _, field, _ in FLAG_LAYOUT:
            setattr(self, field, False if field in FLAG_BOOL_FIELDS else 0)

        self.unused = {index: 0 for index in UNUSED_INTS}
        self.legacy = False

    def __eq__(self, other):
        return isinstance(other, Material) and self.to_dict() == other.to_dict()

    def __repr__(self):
        return f"Material(V{self.file_version}, {sum(1 for table in self.tables.values() if table.lut)} LUTs)"

    def to_dict(self):
        return {
            "file_version": self.file_version,
            "colors": {name: [shortest_float32(value) for value in getattr(self, name)] for name in COLORS},
            "lighting": {field: getattr(self, field) for field in LIGHTING_FIELDS},
            "tables": {name: self.tables[name].to_dict() for name in TABLES},
            "unused": {str(index): self.unused[index] for index in UNUSED_INTS},
        }

    @classmethod
    def from_dict(cls, data):
        material = cls(data.get("file_version", 2))

        for name in COLORS:
            setattr(material, name, tuple(to_float32(value) for value in data["colors"][name]))

        for field in LIGHTING_FIELDS:
            if field not in data["lighting"]:
                raise KeyError(f"Missing MTR lighting field: {field}")
            setattr(material, field, data["lighting"][field])

        for name in TABLES:
            material.tables[name] = MaterialTable.from_dict(data["tables"][name])

        for index in UNUSED_INTS:
            material.unused[index] = data.get("unused", {}).get(str(index), 0)

        return material

##########################################
# Body
##########################################

def read_body(values, material):
    for index, name in enumerate(TABLES):
        table = material.tables[name]
        table.abs_input = values[ABS_INPUT + index] & 1 != 0
        table.input_select = values[INPUT_SELECT + index] & 0xFF
        table.scale = values[INPUT_SCALE + index] & 0xFF

    material.lut_enabled_d0 = values[LUT_ENABLED] & 1 != 0
    material.lut_enabled_d1 = values[LUT_ENABLED + 1] & 1 != 0
    material.lut_enabled_refl = values[LUT_ENABLED + 2] & 1 != 0
    material.config = values[CONFIG] & 0x1F

    for index, name in enumerate(COLORS):
        setattr(material, name, tuple(_int_to_float(values[COLOR + index * 3 + component]) for component in range(3)))

    for index, field, is_flag in FLAG_LAYOUT:
        value = values[index]
        setattr(material, field, value & 1 != 0 if is_flag else value & 0xFF)

    for index in UNUSED_INTS:
        material.unused[index] = values[index] if index < len(values) else 0


def write_body(material, int_count):
    values = list(DEFAULTS[:int_count])

    for index, name in enumerate(TABLES):
        table = material.tables[name]
        values[ABS_INPUT + index] = 1 if table.abs_input else 0
        values[INPUT_SELECT + index] = table.input_select
        values[INPUT_SCALE + index] = table.scale

    values[LUT_ENABLED] = 1 if material.lut_enabled_d0 else 0
    values[LUT_ENABLED + 1] = 1 if material.lut_enabled_d1 else 0
    values[LUT_ENABLED + 2] = 1 if material.lut_enabled_refl else 0
    values[CONFIG] = material.config & 0x1F

    for index, name in enumerate(COLORS):
        color = getattr(material, name)
        for component in range(3):
            values[COLOR + index * 3 + component] = _float_to_int(color[component])

    for index, field, is_flag in FLAG_LAYOUT:
        value = getattr(material, field)
        values[index] = (1 if value else 0) if is_flag else int(value) & 0xFF

    for index in UNUSED_INTS:
        if index < int_count:
            values[index] = material.unused[index] & 0xFFFFFFFF

    return pack(f"<{int_count}I", *values)

##########################################
# File
##########################################

def read_mtr(data):
    if data is None or len(data) < LEGACY_HEADER_SIZE:
        return None

    if data[:4] == LEGACY_MAGIC:
        # Legacy container, a few IEGO models still ship it (rpg bodies)
        legacy = True
        body_offset = unpack_from("<H", data, 4)[0] or LEGACY_HEADER_SIZE
        slots = unpack_from("<7H", data, 6)
    elif data[:3] == MAGIC and data[3:4] == PLATFORM:
        legacy = False
        body_offset = unpack_from("<H", data, 8)[0] or HEADER_SIZE
        slots = unpack_from("<7H", data, 10)
    else:
        print(f"MTR: unknown magic {data[:8]!r}")
        return None

    if body_offset + 4 > len(data):
        return None

    payload = decompress(data[body_offset:])
    if payload is None:
        print("MTR: unsupported compression method")
        return None

    # Some decoders produce a few extra bytes, the block header holds the real size
    payload = payload[:unpack_from("<I", data, body_offset)[0] >> 3]
    int_count = min(len(payload) // 4, V2_INT_COUNT)

    values = list(unpack_from(f"<{int_count}I", payload)) + DEFAULTS[int_count:]

    material = Material(1 if int_count <= V1_INT_COUNT else 2)
    material.legacy = legacy
    read_body(values, material)

    for index, name in enumerate(HEADER_TABLES):
        offset = slots[index]

        if not offset or offset >= len(data):
            continue

        try:
            material.tables[name].lut = read_legacy_lut(data[offset:]) if legacy else read_lut(data[offset:])
        except ValueError as error:
            print(f"MTR: LUT {name} skipped, {error}")

    return material


def read_legacy_lut(data):
    """The XLUT sub file of the legacy container: the flag is an int and the payload offset comes first."""
    if data[:4] != LEGACY_LUT_MAGIC:
        raise ValueError(f"Unknown LUT magic: {data[:4]!r}")

    payload_offset = unpack_from("<H", data, 4)[0] or LEGACY_LUT_HEADER_SIZE
    payload = decompress(data[payload_offset:])

    if payload is None or len(payload) < LUT_VALUE_COUNT * 8:
        raise ValueError("Unexpected LUT payload size")

    return Lut(unpack_from(f"<{LUT_VALUE_COUNT}f", payload, 0),
               unpack_from(f"<{LUT_VALUE_COUNT}f", payload, LUT_VALUE_COUNT * 4),
               unpack_from("<I", data, 8)[0] & 0xFF)


def write_mtr(material, file_version):
    """file_version is the one of the game engine, V1 writes a 57 int body and V2 a 58 int one."""
    if file_version not in (1, 2):
        raise ValueError(f"Unsupported MTR file version: {file_version}")

    body = compress(write_body(material, V1_INT_COUNT if file_version == 1 else V2_INT_COUNT))

    offsets = [0] * 7
    blocks = []
    written = {}
    position = HEADER_SIZE + len(body)

    for index, name in enumerate(HEADER_TABLES):
        lut = material.tables[name].lut

        if lut is None:
            continue

        # Tables that hold the same values share one sub file, like the shipped IEGO materials do
        block = write_lut(lut)

        if block in written:
            offsets[index] = written[block]
            continue

        written[block] = position
        offsets[index] = position
        position += len(block)
        blocks.append(block)

    header = MAGIC + PLATFORM + b"00" + b"\x00\x00" + pack("<H", HEADER_SIZE) + pack("<7H", *offsets)

    return header + body + b"".join(blocks)


def default_material(file_version):
    """A plain lit material: no LUT, the colours the engine constructors use."""
    material = Material(file_version)
    material.lut_enabled_d0 = True

    return material
