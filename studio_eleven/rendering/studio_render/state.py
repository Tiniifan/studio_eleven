"""Resolved ATR render state mapped on what the Blender 3.4 gpu module can set.

gpu.state only exposes blend presets, a depth compare mode, a depth mask, face culling and the
colour mask. Everything else of the ATR state is either emulated in the shader or dropped, see
UNSUPPORTED_FIELDS.
"""

from ...formats import atr

STATUS = "gpu.state coverage checked against Blender 3.4"

# What the gpu module of 3.4 has no entry point for
UNSUPPORTED_FIELDS = ("depth_bias_enable", "depth_bias", "stencil_test", "stencil_func", "stencil_ref",
                      "stencil_compare_mask", "stencil_write_mask", "stencil_fail_op", "stencil_zfail_op",
                      "stencil_zpass_op")

DEPTH_MODES = {
    atr.COMPARE_FUNCTIONS["ALWAYS"]: 'ALWAYS',
    atr.COMPARE_FUNCTIONS["LESS"]: 'LESS',
    atr.COMPARE_FUNCTIONS["LEQUAL"]: 'LESS_EQUAL',
    atr.COMPARE_FUNCTIONS["EQUAL"]: 'EQUAL',
    atr.COMPARE_FUNCTIONS["GREATER"]: 'GREATER',
    atr.COMPARE_FUNCTIONS["GEQUAL"]: 'GREATER_EQUAL',
}

# NEVER and NOTEQUAL have no gpu.state mode, the closest safe answer is to keep the test on
DEPTH_FALLBACK = 'LESS'

_FACTOR = atr.BLEND_FACTORS
_EQUATION = atr.BLEND_EQUATIONS

# (rgb equation, rgb source, rgb destination) of the presets gpu.state.blend_set offers
BLEND_PRESETS = {
    (_EQUATION["ADD"], _FACTOR["ONE"], _FACTOR["ZERO"]): 'NONE',
    (_EQUATION["ADD"], _FACTOR["SRC_ALPHA"], _FACTOR["ONE_MINUS_SRC_ALPHA"]): 'ALPHA',
    (_EQUATION["ADD"], _FACTOR["ONE"], _FACTOR["ONE_MINUS_SRC_ALPHA"]): 'ALPHA_PREMULT',
    (_EQUATION["ADD"], _FACTOR["SRC_ALPHA"], _FACTOR["ONE"]): 'ADDITIVE',
    (_EQUATION["ADD"], _FACTOR["ONE"], _FACTOR["ONE"]): 'ADDITIVE_PREMULT',
    (_EQUATION["ADD"], _FACTOR["DST_COLOR"], _FACTOR["ZERO"]): 'MULTIPLY',
    (_EQUATION["ADD"], _FACTOR["ZERO"], _FACTOR["SRC_COLOR"]): 'MULTIPLY',
    (_EQUATION["REVERSE_SUBTRACT"], _FACTOR["ONE"], _FACTOR["ONE"]): 'SUBTRACT',
    (_EQUATION["SUBTRACT"], _FACTOR["ONE"], _FACTOR["ONE"]): 'SUBTRACT',
}

BLEND_FALLBACK = 'ALPHA'

# A blend without preset is still exact when the fragment stage applies the source factor to the colour and the destination
# is one of the premultiplied presets (the shader writes colour * factor, the alpha is kept)
SHADER_SOURCE_FACTORS = {
    _FACTOR["ZERO"]: "ZERO",
    _FACTOR["ONE"]: "ONE",
    _FACTOR["SRC_COLOR"]: "SRC_COLOR",
    _FACTOR["ONE_MINUS_SRC_COLOR"]: "ONE_MINUS_SRC_COLOR",
    _FACTOR["SRC_ALPHA"]: "SRC_ALPHA",
    _FACTOR["ONE_MINUS_SRC_ALPHA"]: "ONE_MINUS_SRC_ALPHA",
}

SHADER_DESTINATIONS = {
    _FACTOR["ZERO"]: 'NONE',
    _FACTOR["ONE"]: 'ADDITIVE_PREMULT',
    _FACTOR["ONE_MINUS_SRC_ALPHA"]: 'ALPHA_PREMULT',
}


class ResolvedState:
    """An ATR state with every inherited field filled in, plus what the shader has to emulate."""

    def __init__(self, resolved):
        self.cull = bool(resolved["cull"])
        self.depth_test = bool(resolved["depth_test"])
        self.depth_write = bool(resolved["depth_write"])
        self.depth_func = resolved["depth_func"]
        self.alpha_test = bool(resolved["alpha_test"])
        self.alpha_func = resolved["alpha_func"]
        self.alpha_ref = float(resolved["alpha_ref"])
        self.blend = bool(resolved["blend"])
        self.blend_rgb_equation = resolved["blend_rgb_equation"]
        self.blend_rgb_source = resolved["blend_rgb_source"]
        self.blend_rgb_destination = resolved["blend_rgb_destination"]
        self.blend_alpha_equation = resolved["blend_alpha_equation"]
        self.blend_alpha_source = resolved["blend_alpha_source"]
        self.blend_alpha_destination = resolved["blend_alpha_destination"]
        self.color_mask = tuple(resolved["color_mask"])

    @property
    def depth_mode(self):
        if not self.depth_test:
            return 'NONE'
        return DEPTH_MODES.get(self.depth_func, DEPTH_FALLBACK)

    @property
    def blend_plan(self):
        """(gpu.state preset, source factor the fragment stage applies to the colour or None, exact)."""
        if not self.blend:
            return 'NONE', None, True

        key = (self.blend_rgb_equation, self.blend_rgb_source, self.blend_rgb_destination)
        # The separate alpha equation of the file is not settable either
        same_alpha = self.blend_alpha_equation == self.blend_rgb_equation

        if key in BLEND_PRESETS:
            return BLEND_PRESETS[key], None, same_alpha

        equation, source, destination = key
        if equation == _EQUATION["ADD"] and source in SHADER_SOURCE_FACTORS and destination in SHADER_DESTINATIONS:
            return SHADER_DESTINATIONS[destination], SHADER_SOURCE_FACTORS[source], same_alpha

        return BLEND_FALLBACK, None, False

    @property
    def blend_mode(self):
        return self.blend_plan[0]

    @property
    def blend_source(self):
        return self.blend_plan[1]

    @property
    def blend_is_exact(self):
        """False when neither gpu.state nor the fragment stage can do the blend of the file, the draw then uses the closest preset."""
        return self.blend_plan[2]

    @property
    def cull_mode(self):
        return 'BACK' if self.cull else 'NONE'


def resolve(state):
    return ResolvedState(atr.resolve_state(state))


def apply(resolved):
    import gpu

    gpu.state.blend_set(resolved.blend_mode)
    gpu.state.depth_test_set(resolved.depth_mode)
    gpu.state.depth_mask_set(resolved.depth_write)
    gpu.state.face_culling_set(resolved.cull_mode)
    gpu.state.color_mask_set(*resolved.color_mask)


def reset():
    import gpu

    gpu.state.blend_set('NONE')
    gpu.state.depth_test_set('NONE')
    gpu.state.depth_mask_set(False)
    gpu.state.face_culling_set('NONE')
    gpu.state.color_mask_set(True, True, True, True)


# The alpha test becomes a discard, the compare is the one of the shipped fragment emulators
ALPHA_TEST_GLSL = {
    atr.COMPARE_FUNCTIONS["NEVER"]: "false",
    atr.COMPARE_FUNCTIONS["ALWAYS"]: "true",
    atr.COMPARE_FUNCTIONS["LESS"]: "unf_frg_alpha_ref > alpha",
    atr.COMPARE_FUNCTIONS["LEQUAL"]: "unf_frg_alpha_ref >= alpha",
    atr.COMPARE_FUNCTIONS["EQUAL"]: "unf_frg_alpha_ref == alpha",
    atr.COMPARE_FUNCTIONS["NOTEQUAL"]: "unf_frg_alpha_ref != alpha",
    atr.COMPARE_FUNCTIONS["GREATER"]: "unf_frg_alpha_ref < alpha",
    atr.COMPARE_FUNCTIONS["GEQUAL"]: "unf_frg_alpha_ref <= alpha",
}


def alpha_test_expression(alpha_func):
    return ALPHA_TEST_GLSL.get(alpha_func, "true")
