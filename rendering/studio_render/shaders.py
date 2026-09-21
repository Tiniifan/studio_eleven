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

# Extrusion of gls/VTX012.vert, unf_vtx_silhouette_0 = (on, depth min, depth max, per vertex flags)
# and unf_vtx_silhouette_1 = (width, 1 - first color, 1 - second color, clamp the depth).
# With the per vertex flags off every vertex takes the width and the first color of the outline settings,
# on, atr_pr2.x scales the width of the vertex and atr_pr2.y picks the second color.
OUTLINE_BODY = """
in vec4 atr_pr2;

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
    float flag_x = (1.0 - unf_vtx_silhouette_0.w) + atr_pr2.x * unf_vtx_silhouette_0.w;
    float flag_y = atr_pr2.y * unf_vtx_silhouette_0.w;
    float width = unf_vtx_silhouette_0.x * depth * flag_x * unf_vtx_silhouette_1.x * unf_vtx_outline_view;
    vec3 offset = normal * width;

    vec4 tint = unf_vtx_clr * atr_clr * 0.5;
    tint.xyz = tint.xyz * (1.0 - (unf_vtx_silhouette_1.y * floor(flag_x + 0.95) * (1.0 - flag_y)
                                  + unf_vtx_silhouette_1.z * flag_y) * unf_vtx_silhouette_0.x);

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


# The GPU texture of Blender 3.4 has a fixed sampler, wrap and filtering are done here on the texels: unf_frg_smp_N is
# (wrap S, wrap T, magnification | minification << 1, size of the image when the texture holds its mip chain), the wrap
# values are the ones of the PICA (0 clamp, 1 border, 2 repeat, 3 mirror), a border texel is transparent black
SAMPLER_GLSL = """
int studio_wrap_index(int i, int n, int mode, inout bool inside) {
    if (mode == 2) {
        return i - n * int(floor(float(i) / float(n)));
    }
    if (mode == 3) {
        int period = 2 * n;
        int m = i - period * int(floor(float(i) / float(period)));
        return m < n ? m : period - 1 - m;
    }
    if (mode == 1 && (i < 0 || i >= n)) {
        inside = false;
    }
    return clamp(i, 0, n - 1);
}

vec4 studio_texel(sampler2D smp, ivec2 p, ivec2 size, ivec2 mode, ivec2 origin) {
    bool inside = true;
    ivec2 texel = ivec2(studio_wrap_index(p.x, size.x, mode.x, inside), studio_wrap_index(p.y, size.y, mode.y, inside));
    return inside ? texelFetch(smp, origin + texel, 0) : vec4(0.0);
}

vec4 studio_filter(sampler2D smp, vec2 uv, ivec2 mode, ivec2 size, ivec2 origin, bool linear) {
    vec2 scaled = uv * vec2(size);
    if (!linear) {
        return studio_texel(smp, ivec2(floor(scaled)), size, mode, origin);
    }
    vec2 corner = scaled - 0.5;
    ivec2 first = ivec2(floor(corner));
    vec2 f = corner - vec2(first);
    vec4 a = studio_texel(smp, first, size, mode, origin);
    vec4 b = studio_texel(smp, first + ivec2(1, 0), size, mode, origin);
    vec4 c = studio_texel(smp, first + ivec2(0, 1), size, mode, origin);
    vec4 d = studio_texel(smp, first + ivec2(1, 1), size, mode, origin);
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

vec4 studio_level(sampler2D smp, vec2 uv, ivec2 mode, ivec2 size0, int level, bool linear) {
    if (level == 0) {
        return studio_filter(smp, uv, mode, size0, ivec2(0), linear);
    }
    int row = 0;
    for (int j = 1; j < level; j++) {
        row += max(size0.y >> j, 1);
    }
    return studio_filter(smp, uv, mode, max(size0 >> level, ivec2(1)), ivec2(size0.x, row), linear);
}

vec4 studio_sample(sampler2D smp, vec2 uv, ivec4 setup) {
    bool chain = setup.w != 0;
    ivec2 size0 = chain ? ivec2(setup.w & 65535, setup.w >> 16) : textureSize(smp, 0);
    vec2 dx = dFdx(uv * vec2(size0));
    vec2 dy = dFdy(uv * vec2(size0));
    float lod = 0.5 * log2(max(max(dot(dx, dx), dot(dy, dy)), 0.00000001));
    bool minify = lod > 0.0;
    bool linear = ((setup.z >> (minify ? 1 : 0)) & 1) != 0;
    if (!chain || !minify) {
        return studio_level(smp, uv, setup.xy, size0, 0, linear);
    }
    int top = int(floor(log2(float(max(size0.x, size0.y)))));
    float level = min(lod, float(top));
    int lower = int(floor(level));
    return mix(studio_level(smp, uv, setup.xy, size0, lower, linear),
               studio_level(smp, uv, setup.xy, size0, min(lower + 1, top), linear), level - float(lower));
}
"""


def sampler_uniforms(units):
    lines = []
    for unit in units:
        lines.append(f"uniform sampler2D unf_frg_txt_2d_{unit};")
        lines.append(f"uniform ivec4 unf_frg_smp_{unit};")

    return "\n".join(lines)


def output_line(options):
    # The final render blends in display space like the 3DS does, the frame is converted to scene linear once it is read back
    if options.gamma_correct and not options.display_output:
        return "    fragColor = vec4(studio_to_scene(result.rgb), result.a);"

    return "    fragColor = result;"


def texture_fetch(unit, coordinate, gamma_correct):
    fetch = f"studio_sample(unf_frg_txt_2d_{unit}, {coordinate}, unf_frg_smp_{unit})"
    return f"vec4(studio_to_display({fetch}.rgb), {fetch}.a)" if gamma_correct else fetch


def combiner_function(program):
    parameters = ", ".join(f"vec4 {name}" for name in
                           ("var_clr", "tex0", "tex1", "tex2", "tex3", "clr_1st", "clr_2nd"))
    return f"vec4 studio_combiner({parameters}) {{\n{combiner.generate_glsl(program)}\n}}\n"


class ShaderOptions:
    def __init__(self, texture_units=(), fragment_lighting=False, light_count=0, alpha_test=False,
                 alpha_func=None, gamma_correct=True, outline=False, display_output=False):
        self.texture_units = tuple(sorted(texture_units))
        self.fragment_lighting = bool(fragment_lighting)
        self.light_count = int(light_count)
        self.alpha_test = bool(alpha_test)
        self.alpha_func = alpha_func
        self.gamma_correct = bool(gamma_correct)
        self.display_output = bool(display_output and gamma_correct)
        self.outline = bool(outline)

    def key(self):
        return (self.texture_units, self.fragment_lighting, self.light_count, self.alpha_test,
                self.alpha_func, self.gamma_correct, self.outline, self.display_output)


def vertex_source(options):
    return VERTEX_COMMON + (OUTLINE_BODY if options.outline else VERTEX_BODY)


def fragment_source(program, options):
    lines = [FRAGMENT_HEADER]

    if options.texture_units:
        lines.append(sampler_uniforms(options.texture_units))
        lines.append(SAMPLER_GLSL)

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
            samples.append(f"    vec4 tex{unit} = {texture_fetch(unit, coordinates[unit], options.gamma_correct)};")
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

    output = output_line(options)

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
        return OUTLINE_FRAGMENT.replace("vec4(studio_to_scene(result.rgb), result.a)", "result") if options.display_output else OUTLINE_FRAGMENT

    lines = [OUTLINE_FRAGMENT_HEADER]
    if options.texture_units:
        lines.append(sampler_uniforms(options.texture_units))
        lines.append(SAMPLER_GLSL)

    if base is not None:
        for channel in sorted(set(base.palette_channels.values())):
            lines.append(f"uniform vec4 unf_frg_palette_{channel};")
        lines.append(combiner_function(base))

    samples = []
    coordinates = {0: "frg_tx0", 1: "frg_tx1", 2: "frg_tx2", 3: "frg_tx2"}
    for unit in range(MAX_TEXTURES):
        if unit in options.texture_units:
            samples.append(f"    vec4 tex{unit} = {texture_fetch(unit, coordinates[unit], options.gamma_correct)};")
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

    output = output_line(options)

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
