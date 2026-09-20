"""GLSL sources and GPUShader cache.

The shipped GLSL sources cannot be handed to Blender as they are: they declare '#version 150' while
GPUShader forces 330, they use the 'varying' / 'attribute' aliases, and their DMP_* struct uniforms
cannot be set from Python. The vertex stages below are transcriptions of gls/VTX002.vert and
gls/VTX012.vert with the vec4[3] / vec4[4] uniform arrays written as matrices and the struct uniforms
flattened. Skinning is left out on purpose: StudioRender draws the mesh the depsgraph already
evaluated, so the armature deformation of the game vertex stage is redundant.
"""

from . import combiner, lighting, state

STATUS = "transcription of the shipped vertex stages, never compiled headless"

MAX_TEXTURES = 4

VERTEX_COMMON = """
in vec3 atr_pos;
in vec3 atr_nrm;
in vec4 atr_clr;
in vec2 atr_tx0;
in vec2 atr_tx1;
in vec2 atr_tx2;

out vec4 frg_clr;
out vec2 frg_tx0;
out vec2 frg_tx1;
out vec2 frg_tx2;
out vec3 frg_nrm;
out vec3 frg_prm;

uniform mat4 unf_vtx_lcl_glb;
uniform mat4 unf_vtx_glb_cmr;
uniform mat4 unf_vtx_cmr_prj;
uniform vec4 unf_vtx_txt_0;
uniform vec4 unf_vtx_txt_1;
uniform vec4 unf_vtx_txt_2;
uniform vec4 unf_vtx_txt_3;
uniform vec4 unf_vtx_txt_4;
uniform vec4 unf_vtx_txt_5;
uniform vec4 unf_vtx_clr;

vec2 studio_uv(vec2 uv, vec4 row_x, vec4 row_y) {
    vec4 source = vec4(uv, 0.0, 1.0);
    return vec2(dot(source, row_x), dot(source, row_y));
}
"""

# The stages halve the colour and the combiners double it back, the flat shaders (VTX014 + FRG005) return unf_vtx_clr as it is
VERTEX_BODY = """
void main() {
    vec4 world = unf_vtx_lcl_glb * vec4(atr_pos, 1.0);
    vec4 eye = unf_vtx_glb_cmr * world;
    vec3 normal = normalize(mat3(unf_vtx_lcl_glb) * atr_nrm);
    normal = normalize(mat3(unf_vtx_glb_cmr) * normal);

    frg_clr = unf_vtx_clr * atr_clr * 0.5;
    frg_tx0 = studio_uv(atr_tx0, unf_vtx_txt_0, unf_vtx_txt_1);
    frg_tx1 = studio_uv(atr_tx1, unf_vtx_txt_2, unf_vtx_txt_3);
    frg_tx2 = studio_uv(atr_tx2, unf_vtx_txt_4, unf_vtx_txt_5);
    frg_nrm = normal;
    frg_prm = eye.xyz;

    gl_Position = unf_vtx_cmr_prj * eye;
}
"""

# Extrusion of gls/VTX012.vert, unf_vtx_silhouette_0 = (on, depth min, depth max, per vertex width)
# and unf_vtx_silhouette_1 = (width, 1 - first color, 1 - second color, clamp the depth).
# atr_pr2 is not in the batch, so silhouette_0.w stays at 0: every vertex takes the width and the
# first color of the export settings.
OUTLINE_BODY = """
uniform vec4 unf_vtx_silhouette_0;
uniform vec4 unf_vtx_silhouette_1;
uniform float unf_vtx_outline_view;

void main() {
    vec4 world = unf_vtx_lcl_glb * vec4(atr_pos, 1.0);
    vec4 eye = unf_vtx_glb_cmr * world;
    vec3 normal = normalize(mat3(unf_vtx_lcl_glb) * atr_nrm);
    normal = normalize(mat3(unf_vtx_glb_cmr) * normal);

    // The game adds t * projection * (normal, 0) to the clip position, that is a move of t along the eye normal
    vec4 position = unf_vtx_cmr_prj * eye;
    float clamped = min(max(position.w, unf_vtx_silhouette_0.y), unf_vtx_silhouette_0.z);
    float depth = mix(position.w, position.w / clamped, unf_vtx_silhouette_1.w);
    float width = unf_vtx_silhouette_0.x * depth * unf_vtx_silhouette_1.x * unf_vtx_outline_view;
    vec3 offset = normal * width;

    vec4 tint = unf_vtx_clr * atr_clr * 0.5;
    tint.xyz = tint.xyz * (1.0 - unf_vtx_silhouette_1.y * unf_vtx_silhouette_0.x);

    frg_clr = tint;
    frg_tx0 = studio_uv(atr_tx0, unf_vtx_txt_0, unf_vtx_txt_1);
    frg_tx1 = studio_uv(atr_tx1, unf_vtx_txt_2, unf_vtx_txt_3);
    frg_tx2 = studio_uv(atr_tx2, unf_vtx_txt_4, unf_vtx_txt_5);
    frg_nrm = normal;
    frg_prm = eye.xyz;

    gl_Position = unf_vtx_cmr_prj * vec4(eye.xyz + offset, eye.w);
}
"""

FRAGMENT_HEADER = """
in vec4 frg_clr;
in vec2 frg_tx0;
in vec2 frg_tx1;
in vec2 frg_tx2;
in vec3 frg_nrm;
in vec3 frg_prm;

out vec4 fragColor;

uniform float unf_frg_alpha_ref;
"""

# The combiner works on the stored 8 bit values, Blender hands out scene linear samples
GAMMA_GLSL = """
vec3 studio_to_display(vec3 color) {
    vec3 low = color * 12.92;
    vec3 high = 1.055 * pow(max(color, vec3(0.0)), vec3(1.0 / 2.4)) - 0.055;
    return mix(high, low, step(color, vec3(0.0031308)));
}

vec3 studio_to_scene(vec3 color) {
    vec3 low = color / 12.92;
    vec3 high = pow((max(color, vec3(0.0)) + 0.055) / 1.055, vec3(2.4));
    return mix(high, low, step(color, vec3(0.04045)));
}
"""


def combiner_function(program):
    parameters = ", ".join(f"vec4 {name}" for name in
                           ("var_clr", "tex0", "tex1", "tex2", "tex3", "clr_1st", "clr_2nd"))
    return f"vec4 studio_combiner({parameters}) {{\n{combiner.generate_glsl(program)}\n}}\n"


class ShaderOptions:
    def __init__(self, texture_units=(), fragment_lighting=False, light_count=0, alpha_test=False,
                 alpha_func=None, gamma_correct=True, outline=False):
        self.texture_units = tuple(sorted(texture_units))
        self.fragment_lighting = bool(fragment_lighting)
        self.light_count = int(light_count)
        self.alpha_test = bool(alpha_test)
        self.alpha_func = alpha_func
        self.gamma_correct = bool(gamma_correct)
        self.outline = bool(outline)

    def key(self):
        return (self.texture_units, self.fragment_lighting, self.light_count, self.alpha_test,
                self.alpha_func, self.gamma_correct, self.outline)


def vertex_source(options):
    return VERTEX_COMMON + (OUTLINE_BODY if options.outline else VERTEX_BODY)


def fragment_source(program, options):
    lines = [FRAGMENT_HEADER]

    for unit in options.texture_units:
        lines.append(f"uniform sampler2D unf_frg_txt_2d_{unit};")

    if options.fragment_lighting:
        lines.append(lighting.lighting_uniforms(options.light_count))
        lines.append(lighting.lighting_glsl(options.light_count))

    for channel in sorted(set(program.palette_channels.values())):
        lines.append(f"uniform vec4 unf_frg_palette_{channel};")

    lines.append(GAMMA_GLSL)
    lines.append(combiner_function(program))

    coordinates = {0: "frg_tx0", 1: "frg_tx1", 2: "frg_tx2", 3: "frg_tx2"}
    samples = []
    for unit in range(MAX_TEXTURES):
        if unit in options.texture_units:
            fetch = f"texture(unf_frg_txt_2d_{unit}, {coordinates[unit]})"
            if options.gamma_correct:
                fetch = f"vec4(studio_to_display({fetch}.rgb), {fetch}.a)"
            samples.append(f"    vec4 tex{unit} = {fetch};")
        else:
            # samplerType 0 gives an opaque white sample in the shipped emulators
            samples.append(f"    vec4 tex{unit} = vec4(1.0, 1.0, 1.0, 1.0);")

    if options.fragment_lighting:
        lighting_call = ("    vec4 clr_1st;\n    vec4 clr_2nd;\n"
                         "    studio_lighting(frg_nrm, frg_prm, clr_1st, clr_2nd);")
    else:
        lighting_call = ("    vec4 clr_1st = vec4(1.0, 1.0, 1.0, 1.0);\n"
                         "    vec4 clr_2nd = vec4(0.0, 0.0, 0.0, 1.0);")

    discard = ""
    if options.alpha_test:
        discard = (f"    float alpha = result.a;\n"
                   f"    if (!({state.alpha_test_expression(options.alpha_func)})) {{ discard; }}\n")

    output = "    fragColor = vec4(studio_to_scene(result.rgb), result.a);" if options.gamma_correct \
        else "    fragColor = result;"

    body = "\n".join(samples)
    lines.append(f"""
void main() {{
{body}
{lighting_call}
    vec4 result = studio_combiner(frg_clr, tex0, tex1, tex2, tex3, clr_1st, clr_2nd);
{discard}{output}
}}
""")

    return "\n".join(lines)


# The .sil has two combiners: Constant x PrimaryColor, and Texture0 x PrimaryColor for the textured meshes,
# both doubled since the vertex stage halved the color. The textured one is what makes the outline the
# color of the mesh, darkened by the vertex stage
OUTLINE_FRAGMENT_HEADER = """
in vec4 frg_clr;
in vec2 frg_tx0;
in vec2 frg_tx1;
in vec2 frg_tx2;
in vec3 frg_nrm;
in vec3 frg_prm;

out vec4 fragColor;

uniform vec4 unf_frg_outline_color;
uniform float unf_frg_alpha_ref;
""" + GAMMA_GLSL

OUTLINE_FRAGMENT = OUTLINE_FRAGMENT_HEADER + """
void main() {
    vec4 result = unf_frg_outline_color * frg_clr * 2.0;
    fragColor = vec4(studio_to_scene(result.rgb), result.a);
}
"""


def outline_fragment_source(options, base=None):
    """The textured outline: texture 0 x primary color, or the merged color of a character (base program)."""
    if base is None and 0 not in options.texture_units:
        return OUTLINE_FRAGMENT

    lines = [OUTLINE_FRAGMENT_HEADER]
    for unit in options.texture_units:
        lines.append(f"uniform sampler2D unf_frg_txt_2d_{unit};")

    if base is not None:
        for channel in sorted(set(base.palette_channels.values())):
            lines.append(f"uniform vec4 unf_frg_palette_{channel};")
        lines.append(combiner_function(base))

    samples = []
    coordinates = {0: "frg_tx0", 1: "frg_tx1", 2: "frg_tx2", 3: "frg_tx2"}
    for unit in range(MAX_TEXTURES):
        if unit in options.texture_units:
            fetch = f"texture(unf_frg_txt_2d_{unit}, {coordinates[unit]})"
            if options.gamma_correct:
                fetch = f"vec4(studio_to_display({fetch}.rgb), {fetch}.a)"
            samples.append(f"    vec4 tex{unit} = {fetch};")
        else:
            samples.append(f"    vec4 tex{unit} = vec4(1.0, 1.0, 1.0, 1.0);")

    if base is not None:
        color = "studio_combiner(vec4(1.0), tex0, tex1, tex2, tex3, vec4(1.0), vec4(0.0, 0.0, 0.0, 1.0))"
    else:
        color = "tex0"

    discard = ""
    if options.alpha_test:
        discard = (f"    float alpha = result.a;\n"
                   f"    if (!({state.alpha_test_expression(options.alpha_func)})) {{ discard; }}\n")

    output = "    fragColor = vec4(studio_to_scene(result.rgb), result.a);" if options.gamma_correct \
        else "    fragColor = result;"

    body = "\n".join(samples)
    lines.append(f"""
void main() {{
{body}
    vec4 result = {color} * frg_clr * 2.0;
{discard}{output}
}}
""")

    return "\n".join(lines)


_shaders = {}


def clear_cache():
    _shaders.clear()


def get_shader(program, options, program_key):
    """Builds the GPUShader lazily, calling it without a GPU backend raises."""
    import gpu

    key = (program_key, options.key())
    if key not in _shaders:
        source = outline_fragment_source(options, program) if options.outline else fragment_source(program, options)
        _shaders[key] = gpu.types.GPUShader(vertex_source(options), source, name="StudioRender")

    return _shaders[key]
