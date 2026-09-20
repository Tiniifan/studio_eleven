"""Texture combiner of the fixed fragment pipeline, ported from the DMP_COMBINER emulation of gls/FRG000.frag.

STATUS: the stage chain, the operand table, every combine function, the scale, the clamp, the buffer
update window and the initial buffer colour are transcribed from that shipped GLSL (confirmed).
MULT_ADD (0x6401) is a0*a1+a2 and ADD_MULT (0x6402) is clamp(a0+a1)*a2: the shipped GLSL only knows the hardware
numbers 8 and 9, the constants are matched by how the shipped combiners use them (formats/cmb.py).
"""

from ...formats.cmb import ALPHA_OPERANDS, COMBINE_FUNCTIONS, RGB_OPERANDS, SOURCES

STATUS = "confirmed against gls/FRG000.frag"

# Every source reads a vec4, CONSTANT is the only one the stage itself carries
SOURCE_VARIABLES = {
    "PREVIOUS": "prv",
    "PRIMARY_COLOR": "var_clr",
    "TEXTURE0": "tex0",
    "TEXTURE1": "tex1",
    "TEXTURE2": "tex2",
    "TEXTURE3": "tex3",
    "FRAGMENT_PRIMARY_COLOR": "clr_1st",
    "FRAGMENT_SECONDARY_COLOR": "clr_2nd",
    "PREVIOUS_BUFFER": "buf",
}

# The shipped emulators wire three samplers only, the hardware has four
TEXTURE_UNITS = {"TEXTURE0": 0, "TEXTURE1": 1, "TEXTURE2": 2, "TEXTURE3": 3}

STATE_VARIABLES = ("prv", "buf")

MAX_SCALE = 4.0

##########################################
# Expression nodes
##########################################

def lit(width, values):
    return ("lit", width, tuple(float(value) for value in values))


def chan(name, swizzle):
    return ("chan", 3 if swizzle == "xyz" else 1, name, swizzle)


def splat(name, component):
    return ("splat", 3, name, component)


def splat1(node):
    return ("splat1", 3, node)


def tmp(width, name):
    return ("tmp", width, name)


def one_minus(node):
    return ("one_minus", node[1], node)


def add(a, b):
    return ("add", a[1], a, b)


def sub(a, b):
    return ("sub", a[1], a, b)


def mul(a, b):
    return ("mul", a[1], a, b)


def addc(node, value):
    return ("addc", node[1], node, float(value))


def dot3(a, b):
    return ("dot3", 1, a, b)


def scale(node, value):
    return ("scale", node[1], node, float(value))


def clamp01(node):
    return ("clamp01", node[1], node)


def vec4(rgb, alpha):
    return ("vec4", 4, rgb, alpha)

##########################################
# Stage translation
##########################################

def _rgb_operand(variable, operand_name):
    if operand_name == "SRC_COLOR":
        return chan(variable, "xyz")
    if operand_name == "ONE_MINUS_SRC_COLOR":
        return one_minus(chan(variable, "xyz"))

    component = {"SRC_ALPHA": "w", "ONE_MINUS_SRC_ALPHA": "w", "SRC_R": "x", "ONE_MINUS_SRC_R": "x",
                 "SRC_G": "y", "ONE_MINUS_SRC_G": "y", "SRC_B": "z", "ONE_MINUS_SRC_B": "z"}[operand_name]
    node = splat(variable, component)

    return one_minus(node) if operand_name.startswith("ONE_MINUS") else node


def _alpha_operand(variable, operand_name):
    component = {"SRC_ALPHA": "w", "ONE_MINUS_SRC_ALPHA": "w", "SRC_R": "x", "ONE_MINUS_SRC_R": "x",
                 "SRC_G": "y", "ONE_MINUS_SRC_G": "y", "SRC_B": "z", "ONE_MINUS_SRC_B": "z"}[operand_name]
    node = chan(variable, component)

    return one_minus(node) if operand_name.startswith("ONE_MINUS") else node


def _combine_rgb(function_name, args):
    a0, a1, a2 = args

    if function_name == "REPLACE":
        return a0
    if function_name == "MODULATE":
        return mul(a0, a1)
    if function_name == "ADD":
        return add(a0, a1)
    if function_name == "SUBTRACT":
        return sub(a0, a1)
    if function_name == "ADD_SIGNED":
        return addc(add(a0, a1), -0.5)
    if function_name in ("DOT3_RGB", "DOT3_RGBA"):
        return splat1(scale(dot3(addc(a0, -0.5), addc(a1, -0.5)), 4.0))
    if function_name == "INTERPOLATE":
        return add(mul(sub(a0, a1), a2), a1)
    if function_name == "ADD_MULT":
        return mul(clamp01(add(a0, a1)), a2)
    if function_name == "MULT_ADD":
        return add(mul(a0, a1), a2)

    raise ValueError(f"Unknown combine function: {function_name}")


def _combine_alpha(function_name, args, rgb_args):
    a0, a1, a2 = args

    if function_name == "REPLACE":
        return a0
    if function_name == "MODULATE":
        return mul(a0, a1)
    if function_name == "ADD":
        return add(a0, a1)
    if function_name == "SUBTRACT":
        return sub(a0, a1)
    if function_name == "ADD_SIGNED":
        return addc(add(a0, a1), -0.5)
    if function_name == "DOT3_RGBA":
        return scale(dot3(addc(rgb_args[0], -0.5), addc(rgb_args[1], -0.5)), 4.0)
    if function_name == "DOT3_RGB":
        # The alpha chain of FRG000 has no case for it, the whole ternary falls through to 0.0
        return lit(1, (0.0,))
    if function_name == "INTERPOLATE":
        return add(mul(sub(a0, a1), a2), a1)
    if function_name == "ADD_MULT":
        return mul(clamp01(add(a0, a1)), a2)
    if function_name == "MULT_ADD":
        return add(mul(a0, a1), a2)

    raise ValueError(f"Unknown combine function: {function_name}")

##########################################
# Program
##########################################

class CombinerProgram:
    """A stage list unrolled into assignments, shared by the reference evaluator and the GLSL generator."""

    def __init__(self, statements, buffer_color, sources, texture_units, palette_channels=None):
        self.statements = statements
        self.buffer_color = buffer_color
        self.sources = sources
        self.texture_units = texture_units
        # Stage index to the mask channel (R, G or B) it multiplies its constant with
        self.palette_channels = palette_channels or {}
        # The program of the stages before any lighting, the color of the merged textures of a character
        self.base = None

    @property
    def uses_fragment_lighting(self):
        return bool(self.sources & {"FRAGMENT_PRIMARY_COLOR", "FRAGMENT_SECONDARY_COLOR"})

    @property
    def uses_primary_color(self):
        return "PRIMARY_COLOR" in self.sources


def _color(values):
    return tuple(float(value) / 255.0 for value in values)


PALETTE_OPERANDS = {"SRC_R": "r", "SRC_G": "g", "SRC_B": "b"}

LIGHT_SOURCES = {"FRAGMENT_PRIMARY_COLOR", "FRAGMENT_SECONDARY_COLOR", "PRIMARY_COLOR"}


def texture_stage_count(stages):
    """Number of leading stages that read no vertex color nor lighting."""
    count = 0
    for stage in stages:
        data = stage.to_dict()
        if LIGHT_SOURCES & set(data["rgb"]["source"] + data["alpha"]["source"]):
            break
        count += 1

    return count


def build_program(stages, with_base=True):
    statements = []
    sources = set()
    texture_units = set()
    palette_channels = {}
    count = len(stages)

    for index, stage in enumerate(stages):
        data = stage.to_dict()
        rgb, alpha = data["rgb"], data["alpha"]

        constant = f"k{index}"
        if "CONSTANT" in rgb["source"] + alpha["source"]:
            statements.append((constant, 4, lit(4, _color(data["constant_color"]))))

        # Mask stage of the characters (MIXI_MAX): the constant is a color of the model, not of the combiner
        if rgb["source"][:2] == ["CONSTANT", "TEXTURE0"] and rgb["operand"][1] in PALETTE_OPERANDS:
            palette_channels[index] = PALETTE_OPERANDS[rgb["operand"][1]]

        def variable(source_name):
            sources.add(source_name)
            if source_name in TEXTURE_UNITS:
                texture_units.add(TEXTURE_UNITS[source_name])
            return constant if source_name == "CONSTANT" else SOURCE_VARIABLES[source_name]

        rgb_args = []
        alpha_args = []
        for argument in range(3):
            rgb_name = f"s{index}rgb{argument}"
            alpha_name = f"s{index}alp{argument}"
            statements.append((rgb_name, 3, _rgb_operand(variable(rgb["source"][argument]), rgb["operand"][argument])))
            statements.append((alpha_name, 1, _alpha_operand(variable(alpha["source"][argument]), alpha["operand"][argument])))
            rgb_args.append(tmp(3, rgb_name))
            alpha_args.append(tmp(1, alpha_name))

        # The buffer keeps the result of the stage before, only stages 1 to n-2 ever update it
        if 0 < index < count - 1:
            buffer_rgb = chan("prv" if rgb["buffer_input"] == "PREVIOUS" else "buf", "xyz")
            buffer_alpha = chan("prv" if alpha["buffer_input"] == "PREVIOUS" else "buf", "w")
            statements.append(("buf", 4, vec4(buffer_rgb, buffer_alpha)))

        combined_rgb = scale(_combine_rgb(rgb["combine"], rgb_args), rgb["scale"])
        combined_alpha = scale(_combine_alpha(alpha["combine"], alpha_args, rgb_args), alpha["scale"])
        statements.append(("prv", 4, clamp01(vec4(combined_rgb, combined_alpha))))

    buffer_color = _color(stages[0].to_dict()["buffer_color"]) if stages else (0.0, 0.0, 0.0, 0.0)

    program = CombinerProgram(statements, buffer_color, sources, texture_units, palette_channels)
    if palette_channels and with_base:
        program.base = build_program(stages[:texture_stage_count(stages)], with_base=False)

    return program

##########################################
# Reference evaluator
##########################################

def _broadcast(values, width):
    return values * width if len(values) == 1 else values


def evaluate_node(node, values):
    kind, width = node[0], node[1]

    if kind == "lit":
        return node[2]
    if kind == "chan":
        source = values[node[2]]
        if node[3] == "xyz":
            return source[0:3]
        return (source["xyzw".index(node[3])],)
    if kind == "splat":
        return (values[node[2]]["xyzw".index(node[3])],) * 3
    if kind == "splat1":
        return evaluate_node(node[2], values) * 3
    if kind == "tmp":
        return values[node[2]]
    if kind == "one_minus":
        return tuple(1.0 - value for value in evaluate_node(node[2], values))
    if kind == "addc":
        return tuple(value + node[3] for value in evaluate_node(node[2], values))
    if kind == "scale":
        return tuple(value * node[3] for value in evaluate_node(node[2], values))
    if kind == "clamp01":
        return tuple(min(max(value, 0.0), 1.0) for value in evaluate_node(node[2], values))
    if kind == "dot3":
        left, right = evaluate_node(node[2], values), evaluate_node(node[3], values)
        return (sum(a * b for a, b in zip(left, right)),)
    if kind == "vec4":
        return evaluate_node(node[2], values) + evaluate_node(node[3], values)

    left = _broadcast(evaluate_node(node[2], values), width)
    right = _broadcast(evaluate_node(node[3], values), width)

    if kind == "add":
        return tuple(a + b for a, b in zip(left, right))
    if kind == "sub":
        return tuple(a - b for a, b in zip(left, right))
    if kind == "mul":
        return tuple(a * b for a, b in zip(left, right))

    raise ValueError(f"Unknown node: {kind}")


def evaluate(program, inputs):
    """inputs holds a 4 float tuple per source variable, returns the RGBA of the last stage."""
    values = dict(inputs)
    values["prv"] = (0.0, 0.0, 0.0, 0.0)
    values["buf"] = program.buffer_color

    for name, _, node in program.statements:
        values[name] = evaluate_node(node, values)

    return values["prv"]

##########################################
# GLSL generator
##########################################

GLSL_TYPES = {1: "float", 3: "vec3", 4: "vec4"}


def _number(value):
    # Full precision, a rounded literal would make the shader and the reference evaluator disagree
    text = repr(float(value))
    return text if "." in text or "e" in text else text + ".0"


def generate_node(node):
    kind = node[0]

    if kind == "lit":
        values = node[2]
        if len(values) == 1:
            return _number(values[0])
        return f"{GLSL_TYPES[node[1]]}({', '.join(_number(value) for value in values)})"
    if kind == "chan":
        return f"{node[2]}.{node[3]}"
    if kind == "splat":
        return f"vec3({node[2]}.{node[3]})"
    if kind == "splat1":
        return f"vec3({generate_node(node[2])})"
    if kind == "tmp":
        return node[2]
    if kind == "one_minus":
        return f"(1.0 - {generate_node(node[2])})"
    if kind == "addc":
        return f"({generate_node(node[2])} + {_number(node[3])})"
    if kind == "scale":
        return f"({generate_node(node[2])} * {_number(node[3])})"
    if kind == "clamp01":
        return f"clamp({generate_node(node[2])}, 0.0, 1.0)"
    if kind == "dot3":
        return f"dot({generate_node(node[2])}, {generate_node(node[3])})"
    if kind == "vec4":
        return f"vec4({generate_node(node[2])}, {generate_node(node[3])})"
    if kind in ("add", "sub", "mul"):
        operator = {"add": "+", "sub": "-", "mul": "*"}[kind]
        return f"({generate_node(node[2])} {operator} {generate_node(node[3])})"

    raise ValueError(f"Unknown node: {kind}")


def generate_glsl(program, indent="    "):
    """Body of a function whose locals are the combiner inputs and which returns the last stage colour."""
    lines = [f"{indent}vec4 prv = vec4(0.0, 0.0, 0.0, 0.0);",
             f"{indent}vec4 buf = vec4({', '.join(_number(value) for value in program.buffer_color)});"]
    declared = set(STATE_VARIABLES)

    palette = {f"k{index}": channel for index, channel in program.palette_channels.items()}

    for name, width, node in program.statements:
        prefix = "" if name in declared else GLSL_TYPES[width] + " "
        declared.add(name)
        value = f"unf_frg_palette_{palette[name]}" if name in palette else generate_node(node)
        lines.append(f"{indent}{prefix}{name} = {value};")

    lines.append(f"{indent}return prv;")

    return "\n".join(lines)


def declared_names(program):
    return set(STATE_VARIABLES) | {name for name, _, _ in program.statements}


def referenced_names(program):
    names = set()

    def walk(node):
        kind = node[0]
        if kind in ("chan", "splat", "tmp"):
            names.add(node[2])
            return
        for argument in node[2:]:
            if isinstance(argument, tuple):
                walk(argument)

    for _, _, node in program.statements:
        walk(node)

    return names
