from struct import pack, unpack, unpack_from, Struct

from ...compression import *

##########################################
# Constants
##########################################

MAGIC = b"ATR"
PLATFORM = b"C"
LEGACY_MAGIC = b"XATR"

HEADER_SIZE = 12
LEGACY_HEADER_SIZE = 8
V1_PAYLOAD_SIZE = 68
V2_PAYLOAD_SIZE = 60

# V1 compares some fields on 32 bits and others on their low 16 bits, both patterns inherit
INHERIT_32 = 0xFFFFFFFF
INHERIT_16 = 0x0000FFFF

INHERIT_BYTE = 0xFF
INHERIT_SHORT = 0xFFFF
# The engine gates the V2 floats with a ">= 0.0" test, so the sentinel is -1.0f, not a NaN
INHERIT_FLOAT = -1.0

# The index of each entry is the internal index used by V2, index 1 disables the test
COMPARE_FUNCTIONS = [
    ("NEVER", 0x0200),
    ("ALWAYS", 0x0207),
    ("EQUAL", 0x0202),
    ("NOTEQUAL", 0x0205),
    ("LESS", 0x0201),
    ("LEQUAL", 0x0203),
    ("GREATER", 0x0204),
    ("GEQUAL", 0x0206),
]

BLEND_EQUATIONS = [
    ("ADD", 0x8006),
    ("SUBTRACT", 0x800A),
    ("REVERSE_SUBTRACT", 0x800B),
    ("MIN", 0x8007),
    ("MAX", 0x8008),
]

BLEND_FACTORS = [
    ("ZERO", 0x0000),
    ("ONE", 0x0001),
    ("DST_COLOR", 0x0306),
    ("ONE_MINUS_DST_COLOR", 0x0307),
    ("DST_ALPHA", 0x0304),
    ("ONE_MINUS_DST_ALPHA", 0x0305),
    ("SRC_COLOR", 0x0300),
    ("ONE_MINUS_SRC_COLOR", 0x0301),
    ("SRC_ALPHA", 0x0302),
    ("ONE_MINUS_SRC_ALPHA", 0x0303),
    ("SRC_ALPHA_SATURATE", 0x0308),
    ("CONSTANT_COLOR", 0x8001),
    ("ONE_MINUS_CONSTANT_COLOR", 0x8002),
    ("CONSTANT_ALPHA", 0x8003),
    ("ONE_MINUS_CONSTANT_ALPHA", 0x8004),
]

GL_ALWAYS = 0x0207
GL_LESS = 0x0201
GL_ADD = 0x8006
GL_ONE = 0x0001
GL_ZERO = 0x0000
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303


def _tables(entries):
    name_to_value = {name: value for name, value in entries}
    value_to_name = {value: name for name, value in entries}
    index_to_value = [value for _, value in entries]
    value_to_index = {value: index for index, (_, value) in enumerate(entries)}
    return name_to_value, value_to_name, index_to_value, value_to_index


COMPARE_NAME_TO_VALUE, COMPARE_VALUE_TO_NAME, COMPARE_INDEX_TO_VALUE, COMPARE_VALUE_TO_INDEX = _tables(COMPARE_FUNCTIONS)
EQUATION_NAME_TO_VALUE, EQUATION_VALUE_TO_NAME, EQUATION_INDEX_TO_VALUE, EQUATION_VALUE_TO_INDEX = _tables(BLEND_EQUATIONS)
FACTOR_NAME_TO_VALUE, FACTOR_VALUE_TO_NAME, FACTOR_INDEX_TO_VALUE, FACTOR_VALUE_TO_INDEX = _tables(BLEND_FACTORS)

# Defaults template compatible for V1 and V2 render
DEFAULT_STATE = {
    "cull": True,
    "depth_test": True,
    "depth_write": True,
    "depth_func": GL_LESS,
    "alpha_test": False,
    "alpha_func": GL_ALWAYS,
    "alpha_ref": 0.0,
    "blend": True,
    "blend_rgb_equation": GL_ADD,
    "blend_rgb_source": GL_SRC_ALPHA,
    "blend_rgb_destination": GL_ONE_MINUS_SRC_ALPHA,
    "blend_alpha_equation": GL_ADD,
    "blend_alpha_source": GL_ONE,
    "blend_alpha_destination": GL_ZERO,
    "color_mask": (True, True, True, True),
}

##########################################
# Header
##########################################

class Header:
    STRCT = Struct("<3s1s2s2xHH")

    def __init__(self, Magic, Platform, Version, DataOffset, Unused):
        self.Magic = Magic
        self.Platform = Platform
        self.Version = Version
        self.DataOffset = DataOffset
        self.Unused = Unused

    @classmethod
    def Unpack(cls, data):
        return cls(*cls.STRCT.unpack_from(data.read(cls.STRCT.size)))

    def Pack(self):
        return pack(self.STRCT.format, self.Magic, self.Platform, self.Version, self.DataOffset, self.Unused)

    @property
    def file_version(self):
        try:
            return int(self.Version.decode("ascii")) + 1
        except (UnicodeDecodeError, ValueError):
            return None

##########################################
# State
##########################################

STATE_FIELDS = (
    "cull",
    "depth_test",
    "depth_write",
    "depth_func",
    "depth_bias_enable",
    "depth_bias",
    "alpha_test",
    "alpha_func",
    "alpha_ref",
    "blend",
    "blend_rgb_equation",
    "blend_rgb_source",
    "blend_rgb_destination",
    "blend_alpha_equation",
    "blend_alpha_source",
    "blend_alpha_destination",
    "color_mask_r",
    "color_mask_g",
    "color_mask_b",
    "color_mask_a",
    "stencil_test",
    "stencil_func",
    "stencil_ref",
    "stencil_compare_mask",
    "stencil_write_mask",
    "stencil_fail_op",
    "stencil_zfail_op",
    "stencil_zpass_op",
)


class AtrState:
    """Render state of one material, None means inherit. Values are GL constants."""

    def __init__(self, **kwargs):
        for field in STATE_FIELDS:
            setattr(self, field, None)

        self.file_version = None

        for name, value in kwargs.items():
            if name not in STATE_FIELDS and name != "file_version":
                raise KeyError(f"Unknown ATR field: {name}")
            setattr(self, name, value)

    def copy(self):
        state = AtrState()
        for field in STATE_FIELDS:
            setattr(state, field, getattr(self, field))
        state.file_version = self.file_version
        return state

    def to_dict(self):
        return {field: getattr(self, field) for field in STATE_FIELDS}

    def __eq__(self, other):
        if not isinstance(other, AtrState):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __repr__(self):
        values = ", ".join(f"{field}={getattr(self, field)!r}" for field in STATE_FIELDS if getattr(self, field) is not None)
        return f"AtrState({values})"

    @property
    def color_mask(self):
        masks = (self.color_mask_r, self.color_mask_g, self.color_mask_b, self.color_mask_a)
        return None if None in masks else masks

    @color_mask.setter
    def color_mask(self, value):
        if value is None:
            self.color_mask_r = self.color_mask_g = self.color_mask_b = self.color_mask_a = None
        else:
            self.color_mask_r, self.color_mask_g, self.color_mask_b, self.color_mask_a = [bool(mask) for mask in value]

    def resolve(self):
        """Inherited fields replaced by the engine defaults, only meant to preview a material."""
        resolved = dict(DEFAULT_STATE)

        for field in ("cull", "depth_test", "depth_write", "depth_func", "alpha_func", "alpha_ref",
                      "blend_rgb_equation", "blend_rgb_source", "blend_rgb_destination",
                      "blend_alpha_equation", "blend_alpha_source", "blend_alpha_destination"):
            value = getattr(self, field)
            if value is not None:
                resolved[field] = value

        resolved["alpha_test"] = self.alpha_test if self.alpha_test is not None else resolved["alpha_func"] != GL_ALWAYS
        resolved["depth_test"] = resolved["depth_test"] and resolved["depth_func"] != GL_ALWAYS

        if self.blend is not None:
            resolved["blend"] = self.blend

        color_mask = self.color_mask
        if color_mask is not None:
            resolved["color_mask"] = color_mask

        return resolved


def default_state(file_version=None):
    state = state_from_properties(_DefaultProperties())
    state.file_version = file_version
    return state

##########################################
# V1 (ATRC00)
##########################################

# (index, field, inherit pattern used by the shipped files)
V1_LAYOUT = (
    (0, "cull", INHERIT_32),
    (1, "depth_write", INHERIT_32),
    (2, "depth_test", INHERIT_32),
    (3, "depth_func", INHERIT_16),
    (5, "alpha_func", INHERIT_16),
    (7, "blend_rgb_equation", INHERIT_16),
    (8, "blend_rgb_source", INHERIT_32),
    (9, "blend_rgb_destination", INHERIT_32),
    (10, "blend_alpha_equation", INHERIT_16),
    (11, "blend_alpha_source", INHERIT_32),
    (12, "blend_alpha_destination", INHERIT_32),
    (13, "color_mask_r", INHERIT_32),
    (14, "color_mask_g", INHERIT_32),
    (15, "color_mask_b", INHERIT_32),
    (16, "color_mask_a", INHERIT_32),
)

V1_BOOL_FIELDS = {"cull", "depth_write", "depth_test", "color_mask_r", "color_mask_g", "color_mask_b", "color_mask_a"}


def _is_inherited(value):
    return value == INHERIT_32 or (value & 0xFFFF) == 0xFFFF


def _int_to_float(value):
    return unpack("<f", pack("<I", value))[0]


def _float_to_int(value):
    return unpack("<I", pack("<f", value))[0]


def read_v1(payload):
    # The loader prefills its buffer with 0xFF, a shorter payload leaves the tail inherited
    payload = payload[:V1_PAYLOAD_SIZE].ljust(V1_PAYLOAD_SIZE, b"\xFF")
    values = unpack_from("<17I", payload)

    state = AtrState()
    state.file_version = 1

    for index, field, _ in V1_LAYOUT:
        value = values[index]

        if _is_inherited(value):
            continue

        if field in V1_BOOL_FIELDS:
            setattr(state, field, value != 0)
        else:
            setattr(state, field, value)

    # Ints 4 and 6 can't be inherited, the loader forces them to 0 when they are missing
    state.depth_bias = _int_to_float(values[4])
    state.alpha_ref = _int_to_float(values[6])

    return state


def write_v1(state):
    values = [INHERIT_32] * 17

    for index, field, inherit in V1_LAYOUT:
        value = getattr(state, field)

        if value is None:
            values[index] = inherit
        elif field in V1_BOOL_FIELDS:
            values[index] = 1 if value else 0
        else:
            values[index] = int(value) & 0xFFFFFFFF

    # The engine applies the colour masks only when the four of them are set
    if state.color_mask is None:
        for index in (13, 14, 15, 16):
            values[index] = INHERIT_32

    values[4] = _float_to_int(state.depth_bias if state.depth_bias is not None and state.depth_bias >= 0.0 else 0.0)
    values[6] = _float_to_int(state.alpha_ref if state.alpha_ref is not None and state.alpha_ref >= 0.0 else 0.0)

    return pack("<17I", *values)

##########################################
# V2 (ATRC01)
##########################################

# (index, byte index, field), the bytes left out are never read and stay at 0xFF
V2_BYTE_LAYOUT = (
    (1, 1, "depth_write"),
    (2, 1, "blend"),
    (2, 2, "alpha_test"),
    (2, 3, "depth_test"),
    (3, 0, "depth_bias_enable"),
    (3, 1, "stencil_test"),
    (3, 3, "cull"),
    (6, 0, "blend_rgb_equation"),
    (6, 1, "blend_rgb_source"),
    (6, 2, "blend_rgb_destination"),
    (6, 3, "blend_alpha_equation"),
    (7, 0, "blend_alpha_source"),
    (7, 1, "blend_alpha_destination"),
    (10, 0, "alpha_func"),
    (11, 0, "depth_func"),
    (12, 0, "stencil_func"),
    (12, 1, "stencil_fail_op"),
    (12, 2, "stencil_zfail_op"),
    (12, 3, "stencil_zpass_op"),
)

V2_BOOL_FIELDS = {"depth_write", "blend", "alpha_test", "depth_test", "depth_bias_enable", "stencil_test", "cull"}

# ASSUMPTION: V2 stores the internal index of the enums and reuses the V1 order above
V2_INDEX_FIELDS = {
    "depth_func": (COMPARE_INDEX_TO_VALUE, COMPARE_VALUE_TO_INDEX),
    "alpha_func": (COMPARE_INDEX_TO_VALUE, COMPARE_VALUE_TO_INDEX),
    "stencil_func": (COMPARE_INDEX_TO_VALUE, COMPARE_VALUE_TO_INDEX),
    "blend_rgb_equation": (EQUATION_INDEX_TO_VALUE, EQUATION_VALUE_TO_INDEX),
    "blend_alpha_equation": (EQUATION_INDEX_TO_VALUE, EQUATION_VALUE_TO_INDEX),
    "blend_rgb_source": (FACTOR_INDEX_TO_VALUE, FACTOR_VALUE_TO_INDEX),
    "blend_rgb_destination": (FACTOR_INDEX_TO_VALUE, FACTOR_VALUE_TO_INDEX),
    "blend_alpha_source": (FACTOR_INDEX_TO_VALUE, FACTOR_VALUE_TO_INDEX),
    "blend_alpha_destination": (FACTOR_INDEX_TO_VALUE, FACTOR_VALUE_TO_INDEX),
}

# The meaning of the stencil operation values is undocumented, they go through untouched
V2_RAW_FIELDS = {"stencil_fail_op", "stencil_zfail_op", "stencil_zpass_op"}


def read_v2(payload):
    payload = payload[:V2_PAYLOAD_SIZE].ljust(V2_PAYLOAD_SIZE, b"\xFF")
    values = unpack_from("<15I", payload)

    state = AtrState()
    state.file_version = 2

    for index, byte_index, field in V2_BYTE_LAYOUT:
        value = (values[index] >> (byte_index * 8)) & 0xFF

        if value == INHERIT_BYTE:
            continue

        if field in V2_BOOL_FIELDS:
            setattr(state, field, value != 0)
        elif field in V2_RAW_FIELDS:
            setattr(state, field, value)
        else:
            index_to_value = V2_INDEX_FIELDS[field][0]
            if value < len(index_to_value):
                setattr(state, field, index_to_value[value])
            else:
                print(f"ATR: unknown {field} index {value}, the field is left inherited")

    color_mask = values[1] & 0xFF
    if color_mask != INHERIT_BYTE:
        state.color_mask = (color_mask & 1 != 0, color_mask & 2 != 0, color_mask & 4 != 0, color_mask & 8 != 0)

    stencil_write_mask = (values[1] >> 16) & 0xFF
    if stencil_write_mask != INHERIT_BYTE:
        state.stencil_write_mask = stencil_write_mask

    stencil_ref = values[13] & 0xFFFF
    if stencil_ref != INHERIT_SHORT:
        state.stencil_ref = stencil_ref

    stencil_compare_mask = (values[13] >> 16) & 0xFFFF
    if stencil_compare_mask != INHERIT_SHORT:
        state.stencil_compare_mask = stencil_compare_mask

    depth_bias = _int_to_float(values[8])
    if depth_bias >= 0.0:
        state.depth_bias = depth_bias

    alpha_ref = _int_to_float(values[9])
    if alpha_ref >= 0.0:
        state.alpha_ref = alpha_ref

    return state


def write_v2(state):
    payload = bytearray(b"\xFF" * V2_PAYLOAD_SIZE)

    def set_byte(index, byte_index, value):
        payload[index * 4 + byte_index] = value & 0xFF

    def set_int(index, value):
        payload[index * 4:index * 4 + 4] = pack("<I", value & 0xFFFFFFFF)

    # The first int holds the payload size, the loader sets it itself and never reads it back
    set_int(0, V2_PAYLOAD_SIZE)

    for index, byte_index, field in V2_BYTE_LAYOUT:
        value = getattr(state, field)

        if value is None:
            continue

        if field in V2_BOOL_FIELDS:
            set_byte(index, byte_index, 1 if value else 0)
        elif field in V2_RAW_FIELDS:
            set_byte(index, byte_index, int(value))
        else:
            value_to_index = V2_INDEX_FIELDS[field][1]
            if value in value_to_index:
                set_byte(index, byte_index, value_to_index[value])
            else:
                print(f"ATR: unknown {field} value {value}, the field is left inherited")

    color_mask = state.color_mask
    if color_mask is not None:
        set_byte(1, 0, sum(1 << i for i, mask in enumerate(color_mask) if mask))

    if state.stencil_write_mask is not None:
        set_byte(1, 2, int(state.stencil_write_mask))

    stencil_ref = INHERIT_SHORT if state.stencil_ref is None else int(state.stencil_ref) & 0xFFFF
    stencil_compare_mask = INHERIT_SHORT if state.stencil_compare_mask is None else int(state.stencil_compare_mask) & 0xFFFF
    set_int(13, (stencil_compare_mask << 16) | stencil_ref)

    depth_bias = state.depth_bias if state.depth_bias is not None and state.depth_bias >= 0.0 else INHERIT_FLOAT
    alpha_ref = state.alpha_ref if state.alpha_ref is not None and state.alpha_ref >= 0.0 else INHERIT_FLOAT
    set_int(8, _float_to_int(depth_bias))
    set_int(9, _float_to_int(alpha_ref))

    return bytes(payload)

##########################################
# File
##########################################

def compress_stored(data):
    return pack("<I", (len(data) << 3) | 0) + data


def read_atr(data):
    if data is None or len(data) < LEGACY_HEADER_SIZE:
        return None

    if data[:4] == LEGACY_MAGIC:
        # Legacy container, always V1, still used by a few models (rpg/body/uzatest.xc)
        file_version = 1
        data_offset = unpack_from("<H", data, 4)[0] or LEGACY_HEADER_SIZE
    else:
        if len(data) < HEADER_SIZE:
            return None

        header = Header(data[0:3], data[3:4], data[4:6], *unpack_from("<HH", data, 8))
        file_version = header.file_version
        data_offset = header.DataOffset or HEADER_SIZE

        if file_version not in (1, 2):
            print(f"ATR: unsupported version {header.Version}")
            return None

    if data_offset >= len(data):
        return None

    payload = decompress(data[data_offset:])
    if payload is None:
        print("ATR: unsupported compression method")
        return None

    # Some decoders produce a few extra bytes, the block header holds the real size
    payload = payload[:unpack_from("<I", data, data_offset)[0] >> 3]

    if file_version == 1:
        return read_v1(payload)

    return read_v2(payload)


def write_atr(state, file_version):
    """file_version is the one of the export templates: 1 writes ATRC00, 2 writes ATRC01."""
    if file_version == 1:
        version = b"00"
        payload = write_v1(state)
    elif file_version == 2:
        version = b"01"
        payload = write_v2(state)
    else:
        raise ValueError(f"Unsupported ATR file version: {file_version}")

    header = Header(MAGIC, PLATFORM, version, HEADER_SIZE, 0)

    return header.Pack() + compress_stored(payload)

##########################################
# Blender properties
##########################################

INHERIT = 'INHERIT'

INHERIT_ITEM_DESCRIPTION = ("Don't write this setting in the file: the game keeps whatever the mesh drawn "
                           "before was using. Handy to reproduce an imported file, risky otherwise")

BOOL_ITEMS = [
    (INHERIT, "Inherit", INHERIT_ITEM_DESCRIPTION),
    ('OFF', "Off", "Turn this setting off"),
    ('ON', "On", "Turn this setting on"),
]


def _enum_items(entries, descriptions=None):
    items = [(INHERIT, "Inherit", INHERIT_ITEM_DESCRIPTION)]

    for name, _ in entries:
        items.append((name, name.replace("_", " ").title(), (descriptions or {}).get(name, "")))

    return items


COMPARE_FUNCTION_ITEMS = _enum_items(COMPARE_FUNCTIONS, {
    "NEVER": "Never passes, nothing is drawn",
    "ALWAYS": "Always passes, which turns the test off",
    "EQUAL": "Passes when both values are the same",
    "NOTEQUAL": "Passes when the two values differ",
    "LESS": "Passes when the new value is smaller than the stored one",
    "LEQUAL": "Passes when the new value is smaller than or equal to the stored one",
    "GREATER": "Passes when the new value is bigger than the stored one",
    "GEQUAL": "Passes when the new value is bigger than or equal to the stored one",
})
BLEND_EQUATION_ITEMS = _enum_items(BLEND_EQUATIONS)
BLEND_FACTOR_ITEMS = _enum_items(BLEND_FACTORS)

# The numbers use -1 to inherit, like the files do
PROPERTY_FIELDS = (
    ("cull", "bool", None),
    ("depth_test", "bool", None),
    ("depth_write", "bool", None),
    ("depth_func", "enum", COMPARE_NAME_TO_VALUE),
    ("depth_bias_enable", "bool", None),
    ("depth_bias", "float", None),
    ("alpha_test", "bool", None),
    ("alpha_func", "enum", COMPARE_NAME_TO_VALUE),
    ("alpha_ref", "float", None),
    ("blend", "bool", None),
    ("blend_rgb_equation", "enum", EQUATION_NAME_TO_VALUE),
    ("blend_rgb_source", "enum", FACTOR_NAME_TO_VALUE),
    ("blend_rgb_destination", "enum", FACTOR_NAME_TO_VALUE),
    ("blend_alpha_equation", "enum", EQUATION_NAME_TO_VALUE),
    ("blend_alpha_source", "enum", FACTOR_NAME_TO_VALUE),
    ("blend_alpha_destination", "enum", FACTOR_NAME_TO_VALUE),
    ("stencil_test", "bool", None),
    ("stencil_func", "enum", COMPARE_NAME_TO_VALUE),
    ("stencil_ref", "int", None),
    ("stencil_compare_mask", "int", None),
    ("stencil_write_mask", "int", None),
    ("stencil_fail_op", "int", None),
    ("stencil_zfail_op", "int", None),
    ("stencil_zpass_op", "int", None),
)

VALUE_TO_NAME_TABLES = {
    "depth_func": COMPARE_VALUE_TO_NAME,
    "alpha_func": COMPARE_VALUE_TO_NAME,
    "stencil_func": COMPARE_VALUE_TO_NAME,
    "blend_rgb_equation": EQUATION_VALUE_TO_NAME,
    "blend_alpha_equation": EQUATION_VALUE_TO_NAME,
    "blend_rgb_source": FACTOR_VALUE_TO_NAME,
    "blend_rgb_destination": FACTOR_VALUE_TO_NAME,
    "blend_alpha_source": FACTOR_VALUE_TO_NAME,
    "blend_alpha_destination": FACTOR_VALUE_TO_NAME,
}


def state_from_properties(properties):
    state = AtrState()

    for name, kind, table in PROPERTY_FIELDS:
        value = getattr(properties, name, None)

        if kind == "bool":
            if value in ('OFF', 'ON'):
                setattr(state, name, value == 'ON')
        elif kind == "enum":
            if value in table:
                setattr(state, name, table[value])
        elif value is not None and value >= 0:
            setattr(state, name, float(value) if kind == "float" else int(value))

    if getattr(properties, "color_mask_override", False):
        state.color_mask = tuple(properties.color_mask)

    return state


def state_to_properties(state, properties):
    for name, kind, _ in PROPERTY_FIELDS:
        value = getattr(state, name)

        if kind == "bool":
            setattr(properties, name, INHERIT if value is None else ('ON' if value else 'OFF'))
        elif kind == "enum":
            setattr(properties, name, VALUE_TO_NAME_TABLES[name].get(value, INHERIT))
        elif kind == "float":
            setattr(properties, name, -1.0 if value is None else float(value))
        else:
            setattr(properties, name, -1 if value is None else int(value))

    color_mask = state.color_mask
    properties.color_mask_override = color_mask is not None
    properties.color_mask = color_mask if color_mask is not None else (True, True, True, True)

##########################################
# Render modes
##########################################

# Fields driven and recognised by the render mode. cull is left out on purpose, the double
# sided toggle owns it and stays usable whatever the render mode is.
RENDER_PRESETS = {
    'OPAQUE': {
        "depth_test": 'ON',
        "depth_write": 'ON',
        "alpha_test": 'OFF',
        "alpha_func": 'ALWAYS',
        "blend": 'ON',
        "blend_rgb_equation": 'ADD',
        "blend_rgb_source": 'ONE',
        "blend_rgb_destination": 'ZERO',
        "blend_alpha_equation": 'ADD',
        "blend_alpha_source": 'ONE',
        "blend_alpha_destination": 'ZERO',
    },
    'CUTOUT': {
        "depth_test": 'ON',
        "depth_write": 'ON',
        "alpha_test": 'ON',
        "alpha_func": 'GREATER',
        "blend": 'ON',
        "blend_rgb_equation": 'ADD',
        "blend_rgb_source": 'ONE',
        "blend_rgb_destination": 'ZERO',
        "blend_alpha_equation": 'ADD',
        "blend_alpha_source": 'ONE',
        "blend_alpha_destination": 'ZERO',
    },
    'TRANSLUCENT': {
        "depth_test": 'ON',
        "depth_write": 'OFF',
        "alpha_test": 'OFF',
        "alpha_func": 'ALWAYS',
        "blend": 'ON',
        "blend_rgb_equation": 'ADD',
        "blend_rgb_source": 'SRC_ALPHA',
        "blend_rgb_destination": 'ONE_MINUS_SRC_ALPHA',
        "blend_alpha_equation": 'ADD',
        "blend_alpha_source": 'ZERO',
        "blend_alpha_destination": 'ONE',
    },
    'ADDITIVE': {
        "depth_test": 'ON',
        "depth_write": 'OFF',
        "alpha_test": 'OFF',
        "alpha_func": 'ALWAYS',
        "blend": 'ON',
        "blend_rgb_equation": 'ADD',
        "blend_rgb_source": 'SRC_ALPHA',
        "blend_rgb_destination": 'ONE',
        "blend_alpha_equation": 'ADD',
        "blend_alpha_source": 'ZERO',
        "blend_alpha_destination": 'ONE',
    },
}

# Simple mode only ever shows these four, "Custom" isn't a pick - it's Expert mode
RENDER_MODES = ('OPAQUE', 'CUTOUT', 'TRANSLUCENT', 'ADDITIVE')

RENDER_MODE_ITEMS = [
    ('OPAQUE', "Opaque", "A normal solid material: it completely hides whatever is behind it. "
                         "Use it for skin, clothes, walls and most of a model", 0),
    ('CUTOUT', "Cutout", "Solid, but pixels more transparent than the alpha cutoff below are thrown away "
                         "instead of being drawn. Use it for leaves, fences, hair strands and anything "
                         "that needs hard holes rather than a soft fade", 1),
    ('TRANSLUCENT', "Translucent", "See-through: the material is mixed with what is behind it following the "
                                   "transparency of its texture. Use it for glass, water, shadows and ghosts", 2),
    ('ADDITIVE', "Additive", "For glow, light and fire effects: the colors add up, so overlapping parts get "
                             "brighter and black areas of the texture become invisible", 3),
]

RENDER_MODE_INDEX = {name: index for index, name in enumerate(RENDER_MODES)}

# What a material nobody configured exports. Everything a normal opaque mesh needs is given
# an explicit value: an inherited field keeps whatever the previous mesh left on the GPU in
# the V2 format, which would make a fresh material depend on the drawing order. The colour
# mask and the stencil stay inherited, every shipped file leaves them to the engine.
PROPERTY_DEFAULTS = dict(RENDER_PRESETS['OPAQUE'])
PROPERTY_DEFAULTS.update({
    "cull": 'ON',
    "depth_func": 'LESS',
    "depth_bias_enable": 'OFF',
    "depth_bias": -1.0,
    "alpha_ref": 0.5,
    "stencil_test": INHERIT,
    "stencil_func": INHERIT,
    "stencil_ref": -1,
    "stencil_compare_mask": -1,
    "stencil_write_mask": -1,
    "stencil_fail_op": -1,
    "stencil_zfail_op": -1,
    "stencil_zpass_op": -1,
    "color_mask_override": False,
    "color_mask": (True, True, True, True),
})


class _DefaultProperties:
    def __init__(self):
        self.__dict__.update(PROPERTY_DEFAULTS)


def detect_render_mode(properties):
    for name, preset in RENDER_PRESETS.items():
        if all(getattr(properties, field, None) == value for field, value in preset.items()):
            return name

    return 'CUSTOM'


def apply_render_mode(properties, name):
    for field, value in RENDER_PRESETS.get(name, {}).items():
        setattr(properties, field, value)
