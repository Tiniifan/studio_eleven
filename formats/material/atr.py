import io
import struct

from ...compression import *

##########################################
# CONST
##########################################

# V1 stores the value, V2 stores its index in the dict
COMPARE_FUNCTIONS = {
    "NEVER": 0x0200,
    "ALWAYS": 0x0207,
    "EQUAL": 0x0202,
    "NOTEQUAL": 0x0205,
    "LESS": 0x0201,
    "LEQUAL": 0x0203,
    "GREATER": 0x0204,
    "GEQUAL": 0x0206,
}

BLEND_EQUATIONS = {
    "ADD": 0x8006,
    "SUBTRACT": 0x800A,
    "REVERSE_SUBTRACT": 0x800B,
    "MIN": 0x8007,
    "MAX": 0x8008,
}

BLEND_FACTORS = {
    "ZERO": 0x0000,
    "ONE": 0x0001,
    "DST_COLOR": 0x0306,
    "ONE_MINUS_DST_COLOR": 0x0307,
    "DST_ALPHA": 0x0304,
    "ONE_MINUS_DST_ALPHA": 0x0305,
    "SRC_COLOR": 0x0300,
    "ONE_MINUS_SRC_COLOR": 0x0301,
    "SRC_ALPHA": 0x0302,
    "ONE_MINUS_SRC_ALPHA": 0x0303,
    "SRC_ALPHA_SATURATE": 0x0308,
    "CONSTANT_COLOR": 0x8001,
    "ONE_MINUS_CONSTANT_COLOR": 0x8002,
    "CONSTANT_ALPHA": 0x8003,
    "ONE_MINUS_CONSTANT_ALPHA": 0x8004,
}

GL_ALWAYS = 0x0207
GL_LESS = 0x0201
GL_ADD = 0x8006
GL_ONE = 0x0001
GL_ZERO = 0x0000
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303

# A field set to None isn't written, the game keeps what the mesh drawn before was using
FIELDS = [
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
]

# What the engine uses for a field that isn't set, only to preview a material
ENGINE_DEFAULTS = {
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
# ATR Function
##########################################

def new_state(version = None):
    state = {"version": version}

    for field in FIELDS:
        state[field] = None

    return state

def get_color_mask(state):
    color_mask = (state["color_mask_r"], state["color_mask_g"], state["color_mask_b"], state["color_mask_a"])

    # The engine applies the four channels together or not at all
    if None in color_mask:
        return None

    return color_mask

def set_color_mask(state, color_mask):
    if color_mask is None:
        state["color_mask_r"] = None
        state["color_mask_g"] = None
        state["color_mask_b"] = None
        state["color_mask_a"] = None
    else:
        state["color_mask_r"] = bool(color_mask[0])
        state["color_mask_g"] = bool(color_mask[1])
        state["color_mask_b"] = bool(color_mask[2])
        state["color_mask_a"] = bool(color_mask[3])

def resolve_state(state):
    resolved = dict(ENGINE_DEFAULTS)

    for field in ["cull", "depth_test", "depth_write", "depth_func", "alpha_func", "alpha_ref", "blend_rgb_equation", "blend_rgb_source",
                  "blend_rgb_destination", "blend_alpha_equation", "blend_alpha_source", "blend_alpha_destination"]:
        if state[field] is not None:
            resolved[field] = state[field]

    if state["alpha_test"] is not None:
        resolved["alpha_test"] = state["alpha_test"]
    else:
        resolved["alpha_test"] = resolved["alpha_func"] != GL_ALWAYS

    resolved["depth_test"] = resolved["depth_test"] and resolved["depth_func"] != GL_ALWAYS

    if state["blend"] is not None:
        resolved["blend"] = state["blend"]

    color_mask = get_color_mask(state)
    if color_mask is not None:
        resolved["color_mask"] = color_mask

    return resolved

def int_to_float(value):
    return struct.unpack("<f", struct.pack("<I", value))[0]

def float_to_int(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]

##########################################
# ATR V1
##########################################

# Int of each field and the value the files write when it isn't set: V1 compares some fields on 32 bits and others on their low 16 bits
V1_FIELDS = [
    [0, "cull", 0xFFFFFFFF],
    [1, "depth_write", 0xFFFFFFFF],
    [2, "depth_test", 0xFFFFFFFF],
    [3, "depth_func", 0x0000FFFF],
    [5, "alpha_func", 0x0000FFFF],
    [7, "blend_rgb_equation", 0x0000FFFF],
    [8, "blend_rgb_source", 0xFFFFFFFF],
    [9, "blend_rgb_destination", 0xFFFFFFFF],
    [10, "blend_alpha_equation", 0x0000FFFF],
    [11, "blend_alpha_source", 0xFFFFFFFF],
    [12, "blend_alpha_destination", 0xFFFFFFFF],
    [13, "color_mask_r", 0xFFFFFFFF],
    [14, "color_mask_g", 0xFFFFFFFF],
    [15, "color_mask_b", 0xFFFFFFFF],
    [16, "color_mask_a", 0xFFFFFFFF],
]

V1_BOOL_FIELDS = ["cull", "depth_write", "depth_test", "color_mask_r", "color_mask_g", "color_mask_b", "color_mask_a"]

def read_v1(atr_data):
    # The engine fills its buffer with 0xFF, shorter data leave the last fields not set
    atr_data = atr_data[:68].ljust(68, b"\xFF")
    values = struct.unpack("<17I", atr_data)

    state = new_state(1)

    for index, field, not_set in V1_FIELDS:
        value = values[index]

        if value == 0xFFFFFFFF or (value & 0xFFFF) == 0xFFFF:
            continue

        if field in V1_BOOL_FIELDS:
            state[field] = value != 0
        else:
            state[field] = value

    # Ints 4 and 6 can't be left out, the engine uses 0 when they are missing
    state["depth_bias"] = int_to_float(values[4])
    state["alpha_ref"] = int_to_float(values[6])

    return state

def write_v1(state):
    values = [0xFFFFFFFF] * 17

    for index, field, not_set in V1_FIELDS:
        value = state[field]

        if value is None:
            values[index] = not_set
        elif field in V1_BOOL_FIELDS:
            if value:
                values[index] = 1
            else:
                values[index] = 0
        else:
            values[index] = int(value) & 0xFFFFFFFF

    if get_color_mask(state) is None:
        for index in [13, 14, 15, 16]:
            values[index] = 0xFFFFFFFF

    depth_bias = 0.0
    if state["depth_bias"] is not None and state["depth_bias"] >= 0.0:
        depth_bias = state["depth_bias"]

    alpha_ref = 0.0
    if state["alpha_ref"] is not None and state["alpha_ref"] >= 0.0:
        alpha_ref = state["alpha_ref"]

    values[4] = float_to_int(depth_bias)
    values[6] = float_to_int(alpha_ref)

    out = bytes()

    for value in values:
        out += int(value).to_bytes(4, 'little')

    return out

##########################################
# ATR V2
##########################################

# Int and byte of each field, the bytes left out are never read and stay at 0xFF
V2_FIELDS = [
    [1, 1, "depth_write"],
    [2, 1, "blend"],
    [2, 2, "alpha_test"],
    [2, 3, "depth_test"],
    [3, 0, "depth_bias_enable"],
    [3, 1, "stencil_test"],
    [3, 3, "cull"],
    [6, 0, "blend_rgb_equation"],
    [6, 1, "blend_rgb_source"],
    [6, 2, "blend_rgb_destination"],
    [6, 3, "blend_alpha_equation"],
    [7, 0, "blend_alpha_source"],
    [7, 1, "blend_alpha_destination"],
    [10, 0, "alpha_func"],
    [11, 0, "depth_func"],
    [12, 0, "stencil_func"],
    [12, 1, "stencil_fail_op"],
    [12, 2, "stencil_zfail_op"],
    [12, 3, "stencil_zpass_op"],
]

V2_BOOL_FIELDS = ["depth_write", "blend", "alpha_test", "depth_test", "depth_bias_enable", "stencil_test", "cull"]

# Supposed to use the same order as V1
V2_ENUM_FIELDS = {
    "depth_func": COMPARE_FUNCTIONS,
    "alpha_func": COMPARE_FUNCTIONS,
    "stencil_func": COMPARE_FUNCTIONS,
    "blend_rgb_equation": BLEND_EQUATIONS,
    "blend_alpha_equation": BLEND_EQUATIONS,
    "blend_rgb_source": BLEND_FACTORS,
    "blend_rgb_destination": BLEND_FACTORS,
    "blend_alpha_source": BLEND_FACTORS,
    "blend_alpha_destination": BLEND_FACTORS,
}

# Nobody knows what the stencil operation values mean, they are written as they were read
V2_RAW_FIELDS = ["stencil_fail_op", "stencil_zfail_op", "stencil_zpass_op"]

def read_v2(atr_data):
    atr_data = atr_data[:60].ljust(60, b"\xFF")
    values = struct.unpack("<15I", atr_data)

    state = new_state(2)

    for index, byte_index, field in V2_FIELDS:
        value = (values[index] >> (byte_index * 8)) & 0xFF

        if value == 0xFF:
            continue

        if field in V2_BOOL_FIELDS:
            state[field] = value != 0
        elif field in V2_RAW_FIELDS:
            state[field] = value
        else:
            enum_values = list(V2_ENUM_FIELDS[field].values())

            if value < len(enum_values):
                state[field] = enum_values[value]
            else:
                print(f"ATR: unknown {field} index {value}, the field is left inherited")

    color_mask = values[1] & 0xFF
    if color_mask != 0xFF:
        set_color_mask(state, (color_mask & 1 != 0, color_mask & 2 != 0, color_mask & 4 != 0, color_mask & 8 != 0))

    stencil_write_mask = (values[1] >> 16) & 0xFF
    if stencil_write_mask != 0xFF:
        state["stencil_write_mask"] = stencil_write_mask

    stencil_ref = values[13] & 0xFFFF
    if stencil_ref != 0xFFFF:
        state["stencil_ref"] = stencil_ref

    stencil_compare_mask = (values[13] >> 16) & 0xFFFF
    if stencil_compare_mask != 0xFFFF:
        state["stencil_compare_mask"] = stencil_compare_mask

    # The engine only uses the floats that are >= 0.0, -1.0 means not set
    depth_bias = int_to_float(values[8])
    if depth_bias >= 0.0:
        state["depth_bias"] = depth_bias

    alpha_ref = int_to_float(values[9])
    if alpha_ref >= 0.0:
        state["alpha_ref"] = alpha_ref

    return state

def set_byte(atr_data, index, byte_index, value):
    atr_data[index * 4 + byte_index] = value & 0xFF

def set_int(atr_data, index, value):
    atr_data[index * 4:index * 4 + 4] = int(value & 0xFFFFFFFF).to_bytes(4, 'little')

def write_v2(state):
    atr_data = bytearray(b"\xFF" * 60)

    # The first int is the size of the data, the engine sets it itself and never reads it
    set_int(atr_data, 0, 60)

    for index, byte_index, field in V2_FIELDS:
        value = state[field]

        if value is None:
            continue

        if field in V2_BOOL_FIELDS:
            if value:
                set_byte(atr_data, index, byte_index, 1)
            else:
                set_byte(atr_data, index, byte_index, 0)
        elif field in V2_RAW_FIELDS:
            set_byte(atr_data, index, byte_index, int(value))
        else:
            enum_values = list(V2_ENUM_FIELDS[field].values())

            if value in enum_values:
                set_byte(atr_data, index, byte_index, enum_values.index(value))
            else:
                print(f"ATR: unknown {field} value {value}, the field is left inherited")

    color_mask = get_color_mask(state)
    if color_mask is not None:
        mask = 0
        for i in range(4):
            if color_mask[i]:
                mask |= 1 << i

        set_byte(atr_data, 1, 0, mask)

    if state["stencil_write_mask"] is not None:
        set_byte(atr_data, 1, 2, int(state["stencil_write_mask"]))

    stencil_ref = 0xFFFF
    if state["stencil_ref"] is not None:
        stencil_ref = int(state["stencil_ref"]) & 0xFFFF

    stencil_compare_mask = 0xFFFF
    if state["stencil_compare_mask"] is not None:
        stencil_compare_mask = int(state["stencil_compare_mask"]) & 0xFFFF

    set_int(atr_data, 13, (stencil_compare_mask << 16) | stencil_ref)

    depth_bias = -1.0
    if state["depth_bias"] is not None and state["depth_bias"] >= 0.0:
        depth_bias = state["depth_bias"]

    alpha_ref = -1.0
    if state["alpha_ref"] is not None and state["alpha_ref"] >= 0.0:
        alpha_ref = state["alpha_ref"]

    set_int(atr_data, 8, float_to_int(depth_bias))
    set_int(atr_data, 9, float_to_int(alpha_ref))

    return bytes(atr_data)

##########################################
# ATR Write Function
##########################################

def write_atr(state, version):
    if version == 1:
        atr_data = write_v1(state)
    elif version == 2:
        atr_data = write_v2(state)
    else:
        raise Exception(f"Unsupported ATR version: {version}")

    out = bytes()

    out += b"ATRC"
    out += str(version - 1).rjust(2, "0").encode("ascii")
    out += int(0).to_bytes(2, 'little')
    out += int(12).to_bytes(2, 'little')
    out += int(0).to_bytes(2, 'little')

    # Stored without compression
    out += int(len(atr_data) << 3).to_bytes(4, 'little')
    out += atr_data

    return out

##########################################
# ATR Open Function
##########################################

def read_atr(data):
    if data is None or len(data) < 8:
        return None

    reader = io.BytesIO(data)

    if data[:4] == b"XATR":
        # Old container, always V1, still used by a few models
        version = 1
        reader.seek(4)
        data_offset = struct.unpack("<H", reader.read(2))[0]

        if data_offset == 0:
            data_offset = 8
    else:
        if len(data) < 12:
            return None

        atr_magic = reader.read(4)
        atr_version = reader.read(2)
        reader.read(2)
        data_offset = struct.unpack("<H", reader.read(2))[0]
        unk = struct.unpack("<H", reader.read(2))[0]

        if data_offset == 0:
            data_offset = 12

        # "00" is V1 and "01" is V2
        try:
            version = int(atr_version.decode("ascii")) + 1
        except (UnicodeDecodeError, ValueError):
            version = None

        if version != 1 and version != 2:
            print(f"ATR: unsupported version {atr_version}")
            return None

    reader.close()

    if data_offset >= len(data):
        return None

    atr_data = decompress(data[data_offset:])

    if atr_data is None:
        print("ATR: unsupported compression method")
        return None

    # Some decompressions give a few extra bytes, the real size is in the compression header
    atr_data = atr_data[:struct.unpack("<I", data[data_offset:data_offset + 4])[0] >> 3]

    if version == 1:
        return read_v1(atr_data)
    else:
        return read_v2(atr_data)
