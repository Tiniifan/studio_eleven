import math

import mathutils

##########################################
# CONST
##########################################

LUT_ENTRY_COUNT = 256
LUT_TEXTURE_WIDTH = 512
LUT_TEXTURE_HEIGHT = 32
MAX_LIGHTS = 8

# Table row of each LUT: the getLutInSelect calls of FRG001, and the hardware ids the game uploads the material LUTs to
LUT_TABLES = ("D0", "D1", "FR", "RB", "RG", "RR")
LUT_TABLE_INDEX = {name: index for index, name in enumerate(LUT_TABLES)}

# Input of a LUT, in the order of the getLutInSelect ternary
LUT_INPUTS = ("NH", "VH", "NV", "LN", "SP", "CP")

# Reflection tables each config reads: 0, 1, 2 and 6 copy RR to RG and RB, 3 reads none
REFLECTION_TABLES = {
    0: ("RR",),
    1: ("RR",),
    2: ("RR",),
    3: (),
    6: ("RR",),
}

ALL_REFLECTION_TABLES = ("RR", "RG", "RB")

##########################################
# LUT Function
##########################################

def fetch_lut(values, deltas, index, fraction):
    index = min(max(int(index), 0), LUT_ENTRY_COUNT - 1)

    return values[index] + deltas[index] * fraction


def sample_lut(values, deltas, value, absolute):
    """Reference port of getLut, the texture fetch of the shipped shader clamps out of range indices."""
    if absolute:
        value = abs(value)
        index = min(math.floor(value * 256.0), 255.0)
        return fetch_lut(values, deltas, index, value * 256.0 - index)

    if value < 0.0:
        floored = math.floor(value * 127.0)
        return fetch_lut(values, deltas, 255.0 + floored, value * 128.0 - floored)

    index = min(math.floor(value * 128.0), 127.0)

    return fetch_lut(values, deltas, index, value * 128.0 - index)


def sample(table, value, absolute):
    return sample_lut(table.values, table.deltas, value, absolute)


def material_tables(material):
    """Lut object of every table the .mtr material embeds, missing ones are left out."""
    tables = {}

    for name in LUT_TABLES:
        table = material.tables[name].lut
        if table is not None:
            tables[name] = table

    return tables


def lut_texture_rows(material):
    """One row per table, 256 values then 256 deltas, laid out the way FRG001 indexes the LUT texture."""
    rows = [[0.0] * LUT_TEXTURE_WIDTH for _ in range(LUT_TEXTURE_HEIGHT)]

    # The hardware table quantizes both to 12 bits, the shipped GLSL samples the floats as they are
    for name, table in material_tables(material).items():
        rows[LUT_TABLE_INDEX[name]] = list(table.values) + list(table.deltas)

    return rows

##########################################
# Scene Lights
##########################################

def new_light():
    """One DMP_LIGHT_SOURCE, the vectors are in eye space like the varyings the vertex stage writes."""
    return {
        "position": (0.0, 0.0, 1.0, 0.0),
        "ambient": (0.0, 0.0, 0.0, 1.0),
        "diffuse": (1.0, 1.0, 1.0, 1.0),
        "specular0": (0.0, 0.0, 0.0, 1.0),
        "specular1": (0.0, 0.0, 0.0, 1.0),
        "two_side_diffuse": False,
    }


def default_light():
    """StudioRender choice: a white light coming from the upper left of the viewer, for scenes without any light."""
    light = new_light()
    length = math.sqrt(0.3 * 0.3 + 0.5 * 0.5 + 1.0)

    light["position"] = (-0.3 / length, 0.5 / length, 1.0 / length, 0.0)
    light["specular0"] = (1.0, 1.0, 1.0, 1.0)
    light["specular1"] = (1.0, 1.0, 1.0, 1.0)

    return light


def collect_lights(depsgraph, view_matrix, limit=MAX_LIGHTS):
    """Blender lights mapped on DMP light sources (StudioRender choice: SUN is directional, the others are point lights)."""
    lights = []

    for instance in depsgraph.object_instances:
        if len(lights) >= limit:
            break

        obj = instance.object
        if obj.type != 'LIGHT' or not obj.visible_get():
            continue

        data = obj.data
        matrix = view_matrix @ instance.matrix_world
        light = new_light()

        if data.type == 'SUN':
            direction = matrix.to_3x3() @ mathutils.Vector((0.0, 0.0, 1.0))
            light["position"] = (direction.x, direction.y, direction.z, 0.0)
            energy = data.energy
        else:
            location = matrix.translation
            light["position"] = (location.x, location.y, location.z, 1.0)
            energy = data.energy / (4.0 * math.pi)

        # The game builds its lights from data the addon does not read, the ambient of a light stays black
        color = tuple(channel * energy for channel in data.color)
        light["diffuse"] = color + (1.0,)
        light["specular0"] = color + (1.0,)
        light["specular1"] = color + (1.0,)

        lights.append(light)

    if len(lights) == 0 and limit > 0:
        lights.append(default_light())

    return lights

##########################################
# Light Environment
##########################################

def new_environment():
    """DMP_LIGHT_ENV plus DMP_MATERIAL, the fields the ported shader reads."""
    return {
        "enabled": False,
        "config": 0,
        "scene_ambient": (0.0, 0.0, 0.0),
        "emission": (0.0, 0.0, 0.0, 1.0),
        "ambient": (1.0, 1.0, 1.0, 1.0),
        "diffuse": (1.0, 1.0, 1.0, 1.0),
        "specular0": (0.0, 0.0, 0.0, 1.0),
        "specular1": (0.0, 0.0, 0.0, 1.0),
        "lut_enabled_d0": False,
        "lut_enabled_d1": False,
        "lut_enabled_refl": False,
        "lut_input": {name: 0 for name in LUT_TABLES},
        "lut_abs": {name: True for name in LUT_TABLES},
        "lut_scale": {name: 1.0 for name in LUT_TABLES},
        "fresnel_selector": 0,
        "clamp_highlights": False,
        "two_side_diffuse": False,
    }


def has_reflection_tables(material):
    """The reflection tables the config of the material reads are all embedded in it."""
    names = REFLECTION_TABLES.get(material.config, ALL_REFLECTION_TABLES)

    for name in names:
        if material.tables[name].lut is None:
            return False

    return True


def environment_of(material, scene_ambient=(0.0, 0.0, 0.0)):
    """The light environment of an .mtr material (formats/mtr.py Material), a table enabled without its LUT is left out."""
    environment = new_environment()
    tables = material.tables

    environment["enabled"] = True
    environment["config"] = material.config
    environment["scene_ambient"] = tuple(scene_ambient)
    environment["emission"] = tuple(material.emission) + (1.0,)
    environment["ambient"] = tuple(material.ambient) + (1.0,)
    environment["diffuse"] = tuple(material.diffuse) + (1.0,)
    environment["specular0"] = tuple(material.specular0) + (1.0,)
    environment["specular1"] = tuple(material.specular1) + (1.0,)

    # The hardware would read the previous contents of a table the file does not hold
    environment["lut_enabled_d0"] = material.lut_enabled_d0 and tables["D0"].lut is not None
    environment["lut_enabled_d1"] = material.lut_enabled_d1 and tables["D1"].lut is not None
    environment["lut_enabled_refl"] = material.lut_enabled_refl and has_reflection_tables(material)

    for name in LUT_TABLES:
        environment["lut_input"][name] = min(tables[name].input_select, len(LUT_INPUTS) - 1)
        environment["lut_abs"][name] = tables[name].abs_input

        # The two undefined scale indices are not used by any shipped material
        environment["lut_scale"][name] = tables[name].scale_value or 1.0

    environment["fresnel_selector"] = material.fresnel_selector
    environment["clamp_highlights"] = material.clamp_highlights

    return environment

##########################################
# Reference Evaluator
##########################################

def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def normalize(vector):
    length = math.sqrt(dot(vector, vector))

    if length <= 0.0:
        return (0.0, 0.0, 0.0)

    return tuple(value / length for value in vector)


def apply_config(config, values):
    """The eight dmp_LightEnv.config layouts of FRG001, values holds rr, rg, rb, d0, d1, fr, sp."""
    values = dict(values)

    if config == 0:
        values["rg"] = values["rr"]
        values["rb"] = values["rr"]
        values["d1"] = 1.0
        values["fr"] = 1.0
    elif config == 1:
        values["rg"] = values["rr"]
        values["rb"] = values["rr"]
        values["d0"] = 1.0
        values["d1"] = 1.0
    elif config == 2:
        values["rg"] = values["rr"]
        values["rb"] = values["rr"]
        values["fr"] = 1.0
        values["sp"] = 1.0
    elif config == 3:
        values["rr"] = 1.0
        values["rg"] = 1.0
        values["rb"] = 1.0
        values["sp"] = 1.0
    elif config == 4:
        values["fr"] = 1.0
    elif config == 5:
        values["d1"] = 1.0
    elif config == 6:
        values["rg"] = values["rr"]
        values["rb"] = values["rr"]

    return values


def lut_of(environment, tables, name, inputs):
    table = tables.get(name)

    if table is None:
        return 1.0

    value = inputs[environment["lut_input"][name]]

    return environment["lut_scale"][name] * sample(table, value, environment["lut_abs"][name])


def evaluate_lighting(environment, lights, tables, normal, eye_position):
    """Reference port of the FRG001 lighting block, returns (clr_1st, clr_2nd) as 4 float tuples."""
    if not environment["enabled"]:
        return (1.0, 1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)

    normal = normalize(normal)
    view = normalize(tuple(-value for value in eye_position))
    normal_view = dot(normal, view)

    primary = [0.0, 0.0, 0.0]
    secondary = [0.0, 0.0, 0.0]
    fresnel = 0.0

    for light in lights:
        position = light["position"]

        if position[3] == 0.0:
            direction = normalize(position[0:3])
        else:
            direction = normalize(tuple(position[index] - eye_position[index] for index in range(3)))

        half = normalize(tuple(view[index] + direction[index] for index in range(3)))
        inputs = (dot(normal, half), dot(view, half), normal_view, dot(direction, normal), 0.0, 0.0)

        values = {"rr": 1.0, "rg": 1.0, "rb": 1.0, "d0": 1.0, "d1": 1.0, "sp": 1.0}
        values["fr"] = lut_of(environment, tables, "FR", inputs)

        if environment["lut_enabled_refl"]:
            values["rr"] = lut_of(environment, tables, "RR", inputs)
            values["rg"] = lut_of(environment, tables, "RG", inputs)
            values["rb"] = lut_of(environment, tables, "RB", inputs)

        if environment["lut_enabled_d0"]:
            values["d0"] = lut_of(environment, tables, "D0", inputs)

        if environment["lut_enabled_d1"]:
            values["d1"] = lut_of(environment, tables, "D1", inputs)

        values = apply_config(environment["config"], values)

        if environment["lut_enabled_refl"]:
            reflection = (values["rr"], values["rg"], values["rb"])
        else:
            reflection = environment["specular1"][0:3]

        if light["two_side_diffuse"]:
            light_dot = abs(inputs[3])
        else:
            light_dot = max(0.0, inputs[3])

        for index in range(3):
            diffuse = environment["diffuse"][index] * light["diffuse"][index]
            ambient = environment["ambient"][index] * light["ambient"][index]
            primary[index] += values["sp"] * (diffuse * light_dot + ambient)

        highlight = 1.0
        if environment["clamp_highlights"] and inputs[3] < 0.0:
            highlight = 0.0

        for index in range(3):
            specular0 = light["specular0"][index] * environment["specular0"][index] * values["d0"]
            specular1 = light["specular1"][index] * reflection[index] * values["d1"]
            secondary[index] += highlight * values["sp"] * (specular0 + specular1)

        fresnel = values["fr"]

    first = []
    for index in range(3):
        ambient = environment["scene_ambient"][index] * environment["ambient"][index]
        first.append(min(1.0, environment["emission"][index] + ambient + primary[index]))

    second = [min(1.0, value) for value in secondary]

    if environment["fresnel_selector"] in (1, 3):
        first.append(fresnel)
    else:
        first.append(1.0)

    if environment["fresnel_selector"] in (2, 3):
        second.append(fresnel)
    else:
        second.append(1.0)

    return tuple(first), tuple(second)

##########################################
# GLSL Function
##########################################

LUT_SAMPLER_GLSL = """
float studio_lut(int table, float value, bool absolute, float scale) {
    float index;
    float fraction;
    if (absolute) {
        value = abs(value);
        index = min(floor(value * 256.0), 255.0);
        fraction = value * 256.0 - index;
    } else if (value < 0.0) {
        float floored = floor(value * 127.0);
        index = 255.0 + floored;
        fraction = value * 128.0 - floored;
    } else {
        index = min(floor(value * 128.0), 127.0);
        fraction = value * 128.0 - index;
    }
    float x = index / 512.0;
    float dx = (index + 256.0) / 512.0;
    float y = float(table) / 32.0;
    return scale * (texture(unf_frg_txt_lut, vec2(x, y)).r + texture(unf_frg_txt_lut, vec2(dx, y)).r * fraction);
}

float studio_lut_select(int table, int input_id, bool absolute, float scale,
                        float NH, float VH, float NV, float LN, float SP, float CP) {
    float value = (0 == input_id) ? NH : (1 == input_id) ? VH : (2 == input_id) ? NV
                : (3 == input_id) ? LN : (4 == input_id) ? SP : (5 == input_id) ? CP : 0.0;
    return studio_lut(table, value, absolute, scale);
}
"""

CONFIG_GLSL = """
void studio_config(int config, inout float rr, inout float rg, inout float rb,
                   inout float d0, inout float d1, inout float fr, inout float sp) {
    if (config == 0) { rg = rr; rb = rr; d1 = 1.0; fr = 1.0; }
    else if (config == 1) { rg = rr; rb = rr; d0 = 1.0; d1 = 1.0; }
    else if (config == 2) { rg = rr; rb = rr; fr = 1.0; sp = 1.0; }
    else if (config == 3) { rr = 1.0; rg = 1.0; rb = 1.0; sp = 1.0; }
    else if (config == 4) { fr = 1.0; }
    else if (config == 5) { d1 = 1.0; }
    else if (config == 6) { rg = rr; rb = rr; }
}
"""


def lighting_uniforms(light_count):
    lines = [
        "uniform sampler2D unf_frg_txt_lut;",
        "uniform int unf_lgt_config;",
        "uniform vec3 unf_lgt_scene_ambient;",
        "uniform vec4 unf_mat_emission;",
        "uniform vec4 unf_mat_ambient;",
        "uniform vec4 unf_mat_diffuse;",
        "uniform vec4 unf_mat_specular0;",
        "uniform vec4 unf_mat_specular1;",
        "uniform int unf_lgt_fresnel_selector;",
        "uniform bool unf_lgt_clamp_highlights;",
        "uniform bool unf_lgt_two_side_diffuse;",
        "uniform bool unf_lgt_enabled_d0;",
        "uniform bool unf_lgt_enabled_d1;",
        "uniform bool unf_lgt_enabled_refl;",
    ]

    for table in LUT_TABLES:
        lines.append(f"uniform int unf_lut_input_{table};")
        lines.append(f"uniform bool unf_lut_abs_{table};")
        lines.append(f"uniform float unf_lut_scale_{table};")

    # One uniform per light instead of a struct array, Python can only set named scalar uniforms
    for index in range(light_count):
        for field in ("position", "ambient", "diffuse", "specular0", "specular1"):
            lines.append(f"uniform vec4 unf_lgt_{field}_{index};")

    return "\n".join(lines)


def light_block(index):
    return f"""
    {{
        vec3 L = (unf_lgt_position_{index}.w == 0.0) ? normalize(unf_lgt_position_{index}.xyz)
               : normalize(unf_lgt_position_{index}.xyz - eye_position);
        vec3 H = normalize(V + L);
        float NH = dot(N, H);
        float VH = dot(V, H);
        float LN = dot(L, N);
        float rr = 1.0, rg = 1.0, rb = 1.0, d0 = 1.0, d1 = 1.0, sp = 1.0;
        float fr = studio_lut_select({LUT_TABLE_INDEX["FR"]}, unf_lut_input_FR, unf_lut_abs_FR, unf_lut_scale_FR, NH, VH, NV, LN, 0.0, 0.0);
        if (unf_lgt_enabled_refl) {{
            rr = studio_lut_select({LUT_TABLE_INDEX["RR"]}, unf_lut_input_RR, unf_lut_abs_RR, unf_lut_scale_RR, NH, VH, NV, LN, 0.0, 0.0);
            rg = studio_lut_select({LUT_TABLE_INDEX["RG"]}, unf_lut_input_RG, unf_lut_abs_RG, unf_lut_scale_RG, NH, VH, NV, LN, 0.0, 0.0);
            rb = studio_lut_select({LUT_TABLE_INDEX["RB"]}, unf_lut_input_RB, unf_lut_abs_RB, unf_lut_scale_RB, NH, VH, NV, LN, 0.0, 0.0);
        }}
        if (unf_lgt_enabled_d0) {{
            d0 = studio_lut_select({LUT_TABLE_INDEX["D0"]}, unf_lut_input_D0, unf_lut_abs_D0, unf_lut_scale_D0, NH, VH, NV, LN, 0.0, 0.0);
        }}
        if (unf_lgt_enabled_d1) {{
            d1 = studio_lut_select({LUT_TABLE_INDEX["D1"]}, unf_lut_input_D1, unf_lut_abs_D1, unf_lut_scale_D1, NH, VH, NV, LN, 0.0, 0.0);
        }}
        studio_config(unf_lgt_config, rr, rg, rb, d0, d1, fr, sp);
        if (!unf_lgt_enabled_refl) {{
            rr = unf_mat_specular1.x; rg = unf_mat_specular1.y; rb = unf_mat_specular1.z;
        }}
        float dpLN = unf_lgt_two_side_diffuse ? abs(LN) : max(0.0, LN);
        primary += sp * (unf_mat_diffuse.xyz * unf_lgt_diffuse_{index}.xyz * dpLN
                         + unf_mat_ambient.xyz * unf_lgt_ambient_{index}.xyz);
        vec3 spc0 = unf_lgt_specular0_{index}.xyz * unf_mat_specular0.xyz * d0;
        vec3 spc1 = unf_lgt_specular1_{index}.xyz * vec3(rr, rg, rb) * d1;
        float fi = (unf_lgt_clamp_highlights && LN < 0.0) ? 0.0 : 1.0;
        secondary += fi * sp * (spc0 + spc1);
        fresnel = fr;
    }}"""


def lighting_glsl(light_count):
    """Emits studio_lighting(), which fills the two fragment colours the combiner can read."""
    blocks = "".join(light_block(index) for index in range(light_count))

    return f"""{LUT_SAMPLER_GLSL}{CONFIG_GLSL}
void studio_lighting(vec3 normal, vec3 eye_position, out vec4 clr_1st, out vec4 clr_2nd) {{
    vec3 N = normalize(normal);
    vec3 V = -normalize(eye_position);
    float NV = dot(N, V);
    vec3 primary = vec3(0.0);
    vec3 secondary = vec3(0.0);
    float fresnel = 0.0;
{blocks}
    clr_1st = vec4(min(vec3(1.0), unf_mat_emission.xyz + unf_lgt_scene_ambient * unf_mat_ambient.xyz + primary),
                   (unf_lgt_fresnel_selector == 1 || unf_lgt_fresnel_selector == 3) ? fresnel : 1.0);
    clr_2nd = vec4(min(vec3(1.0), secondary),
                   (unf_lgt_fresnel_selector == 2 || unf_lgt_fresnel_selector == 3) ? fresnel : 1.0);
}}
"""
