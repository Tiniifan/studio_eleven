from struct import pack, unpack_from

from ..compression import *

##########################################
# Constants
##########################################

V1_MAGIC = b"XCMB"
V2_MAGIC = b"CMBC00\x00\x00"

V1_STAGE_SIZE = 80
V2_STAGE_SIZE = 32
MAX_STAGES = 6

# Every table is indexed by the internal value of the engine, V2 files store that index, V1 files the GL constant
SOURCES = [
    ("PREVIOUS", 0x8578),
    ("CONSTANT", 0x8576),
    ("PRIMARY_COLOR", 0x8577),
    ("TEXTURE0", 0x84C0),
    ("TEXTURE1", 0x84C1),
    ("TEXTURE2", 0x84C2),
    ("TEXTURE3", 0x84C3),
    ("FRAGMENT_PRIMARY_COLOR", 0x6210),
    ("FRAGMENT_SECONDARY_COLOR", 0x6211),
    ("PREVIOUS_BUFFER", 0x8579),
]

RGB_OPERANDS = [
    ("SRC_COLOR", 0x0300),
    ("ONE_MINUS_SRC_COLOR", 0x0301),
    ("SRC_ALPHA", 0x0302),
    ("ONE_MINUS_SRC_ALPHA", 0x0303),
    ("SRC_R", 0x8580),
    ("ONE_MINUS_SRC_R", 0x8583),
    ("SRC_G", 0x8581),
    ("ONE_MINUS_SRC_G", 0x8584),
    ("SRC_B", 0x8582),
    ("ONE_MINUS_SRC_B", 0x8585),
]

# The alpha table is the RGB one without the two color entries
ALPHA_OPERANDS = RGB_OPERANDS[2:]

# The two DMP entries are named after how the shipped combiners use them (0x6401 masks a specular with a texture then adds, 0x6402 adds two lit colors then multiplies)
COMBINE_FUNCTIONS = [
    ("REPLACE", 0x1E01),
    ("MODULATE", 0x2100),
    ("ADD", 0x0104),
    ("SUBTRACT", 0x84E7),
    ("ADD_SIGNED", 0x8574),
    ("DOT3_RGB", 0x86AE),
    ("DOT3_RGBA", 0x86AF),
    ("INTERPOLATE", 0x8575),
    ("ADD_MULT", 0x6402),
    ("MULT_ADD", 0x6401),
]

SCALES = [1, 2, 4]

BUFFER_INPUTS = [
    ("PREVIOUS", 0x8578),
    ("PREVIOUS_BUFFER", 0x8579),
]


def _names(entries):
    return [name for name, _ in entries]


def _values(entries):
    return [value for _, value in entries]


class CombinerStage:
    """One texture combiner stage, every enum is an index in the tables above."""

    FIELDS = (
        "source_rgb", "operand_rgb", "combine_rgb", "scale_rgb", "buffer_input_rgb",
        "source_alpha", "operand_alpha", "combine_alpha", "scale_alpha", "buffer_input_alpha",
        "constant_color", "buffer_color",
    )

    def __init__(self, source_rgb=(0, 0, 0), operand_rgb=(0, 0, 0), combine_rgb=0, scale_rgb=0, buffer_input_rgb=0,
                 source_alpha=(0, 0, 0), operand_alpha=(0, 0, 0), combine_alpha=0, scale_alpha=0, buffer_input_alpha=0,
                 constant_color=(0, 0, 0, 0), buffer_color=(0, 0, 0, 0)):
        self.source_rgb = tuple(source_rgb)
        self.operand_rgb = tuple(operand_rgb)
        self.combine_rgb = combine_rgb
        self.scale_rgb = scale_rgb
        self.buffer_input_rgb = buffer_input_rgb
        self.source_alpha = tuple(source_alpha)
        self.operand_alpha = tuple(operand_alpha)
        self.combine_alpha = combine_alpha
        self.scale_alpha = scale_alpha
        self.buffer_input_alpha = buffer_input_alpha
        self.constant_color = tuple(constant_color)
        self.buffer_color = tuple(buffer_color)

    def __eq__(self, other):
        return isinstance(other, CombinerStage) and self.to_dict() == other.to_dict()

    def __repr__(self):
        return f"CombinerStage({self.to_dict()})"

    def to_dict(self):
        return {
            "rgb": {
                "source": [SOURCES[i][0] for i in self.source_rgb],
                "operand": [RGB_OPERANDS[i][0] for i in self.operand_rgb],
                "combine": COMBINE_FUNCTIONS[self.combine_rgb][0],
                "scale": SCALES[self.scale_rgb],
                "buffer_input": BUFFER_INPUTS[self.buffer_input_rgb][0],
            },
            "alpha": {
                "source": [SOURCES[i][0] for i in self.source_alpha],
                "operand": [ALPHA_OPERANDS[i][0] for i in self.operand_alpha],
                "combine": COMBINE_FUNCTIONS[self.combine_alpha][0],
                "scale": SCALES[self.scale_alpha],
                "buffer_input": BUFFER_INPUTS[self.buffer_input_alpha][0],
            },
            "constant_color": list(self.constant_color),
            "buffer_color": list(self.buffer_color),
        }

    @classmethod
    def from_dict(cls, data):
        rgb, alpha = data["rgb"], data["alpha"]
        return cls(
            [_names(SOURCES).index(name) for name in rgb["source"]],
            [_names(RGB_OPERANDS).index(name) for name in rgb["operand"]],
            _names(COMBINE_FUNCTIONS).index(rgb["combine"]),
            SCALES.index(rgb["scale"]),
            _names(BUFFER_INPUTS).index(rgb["buffer_input"]),
            [_names(SOURCES).index(name) for name in alpha["source"]],
            [_names(ALPHA_OPERANDS).index(name) for name in alpha["operand"]],
            _names(COMBINE_FUNCTIONS).index(alpha["combine"]),
            SCALES.index(alpha["scale"]),
            _names(BUFFER_INPUTS).index(alpha["buffer_input"]),
            data["constant_color"],
            data["buffer_color"],
        )

    @property
    def uses_fragment_lighting(self):
        fragment_sources = (_names(SOURCES).index("FRAGMENT_PRIMARY_COLOR"), _names(SOURCES).index("FRAGMENT_SECONDARY_COLOR"))
        return any(source in fragment_sources for source in self.source_rgb + self.source_alpha)

##########################################
# Stages
##########################################

def _index(entries, value, what):
    try:
        return _values(entries).index(value)
    except ValueError:
        raise ValueError(f"Unknown combiner {what}: {value:#x}")


def read_stage_v1(data):
    values = unpack_from("<20I", data)

    def color(value):
        return tuple(value.to_bytes(4, "little"))

    return CombinerStage(
        [_index(SOURCES, value, "source") for value in values[0:3]],
        [_index(RGB_OPERANDS, value, "operand") for value in values[6:9]],
        _index(COMBINE_FUNCTIONS, values[12], "function"),
        SCALES.index(values[15]),
        _index(BUFFER_INPUTS, values[17], "buffer input"),
        [_index(SOURCES, value, "source") for value in values[3:6]],
        [_index(ALPHA_OPERANDS, value, "operand") for value in values[9:12]],
        _index(COMBINE_FUNCTIONS, values[13], "function"),
        SCALES.index(values[16]),
        _index(BUFFER_INPUTS, values[18], "buffer input"),
        color(values[14]),
        color(values[19]),
    )


def write_stage_v1(stage):
    def color(value):
        return int.from_bytes(bytes(value), "little")

    return pack(
        "<20I",
        *[SOURCES[i][1] for i in stage.source_rgb],
        *[SOURCES[i][1] for i in stage.source_alpha],
        *[RGB_OPERANDS[i][1] for i in stage.operand_rgb],
        *[ALPHA_OPERANDS[i][1] for i in stage.operand_alpha],
        COMBINE_FUNCTIONS[stage.combine_rgb][1],
        COMBINE_FUNCTIONS[stage.combine_alpha][1],
        color(stage.constant_color),
        SCALES[stage.scale_rgb],
        SCALES[stage.scale_alpha],
        BUFFER_INPUTS[stage.buffer_input_rgb][1],
        BUFFER_INPUTS[stage.buffer_input_alpha][1],
        color(stage.buffer_color),
    )


def read_stage_v2(data):
    return CombinerStage(
        data[0:3], data[3:6], data[6], data[7], data[8],
        data[12:15], data[15:18], data[18], data[19], data[20],
        data[24:28], data[28:32],
    )


def write_stage_v2(stage):
    return (bytes(stage.source_rgb) + bytes(stage.operand_rgb)
            + bytes((stage.combine_rgb, stage.scale_rgb, stage.buffer_input_rgb, 0, 0, 0))
            + bytes(stage.source_alpha) + bytes(stage.operand_alpha)
            + bytes((stage.combine_alpha, stage.scale_alpha, stage.buffer_input_alpha, 0, 0, 0))
            + bytes(stage.constant_color) + bytes(stage.buffer_color))

##########################################
# File
##########################################

def read_cmb(data):
    """Returns (file_version, stages), the V2 engine reads both formats."""
    if data[:4] == V1_MAGIC:
        version, stage_size, read_stage = 1, V1_STAGE_SIZE, read_stage_v1
    elif data[:8] == V2_MAGIC:
        version, stage_size, read_stage = 2, V2_STAGE_SIZE, read_stage_v2
    else:
        raise ValueError(f"Unknown combiner magic: {data[:8]!r}")

    if version == 1:
        payload_offset, count = unpack_from("<HH", data, 4)
    else:
        payload_offset, count = unpack_from("<HH", data, 8)

    payload = compressor.decompress(data[payload_offset:])
    return version, [read_stage(payload[i * stage_size:(i + 1) * stage_size]) for i in range(count)]


def write_cmb(stages, file_version):
    if not 1 <= len(stages) <= MAX_STAGES:
        raise ValueError(f"A combiner needs 1 to {MAX_STAGES} stages, got {len(stages)}")

    if file_version == 1:
        header = V1_MAGIC + pack("<HH", 8, len(stages))
        payload = b"".join(write_stage_v1(stage) for stage in stages)
    else:
        header = V2_MAGIC + pack("<HH", 12, len(stages))
        payload = b"".join(write_stage_v2(stage) for stage in stages)

    return header + compress(payload)
