import bpy
from types import SimpleNamespace
from bpy.props import BoolProperty, BoolVectorProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty

from ..formats import atr

##########################################
# CONST
##########################################

INHERIT = 'INHERIT'

INHERIT_ITEM_DESCRIPTION = ("Don't write this setting in the file: the game keeps whatever the mesh drawn "
                            "before was using. Handy to reproduce an imported file, risky otherwise")

INHERIT_NUMBER_DESCRIPTION = ("Set it to -1 to leave the setting out of the file, the game then keeps whatever "
                              "the mesh drawn before was using")

BOOL_ITEMS = [
    (INHERIT, "Inherit", INHERIT_ITEM_DESCRIPTION),
    ('OFF', "Off", "Turn this setting off"),
    ('ON', "On", "Turn this setting on"),
]

COMPARE_FUNCTION_DESCRIPTIONS = {
    "NEVER": "Never passes, nothing is drawn",
    "ALWAYS": "Always passes, which turns the test off",
    "EQUAL": "Passes when both values are the same",
    "NOTEQUAL": "Passes when the two values differ",
    "LESS": "Passes when the new value is smaller than the stored one",
    "LEQUAL": "Passes when the new value is smaller than or equal to the stored one",
    "GREATER": "Passes when the new value is bigger than the stored one",
    "GEQUAL": "Passes when the new value is bigger than or equal to the stored one",
}

# Name of each property, its kind and the values of the file for the enums, the numbers use -1 to inherit like the files do
PROPERTY_FIELDS = [
    ["cull", "bool", None],
    ["depth_test", "bool", None],
    ["depth_write", "bool", None],
    ["depth_func", "enum", atr.COMPARE_FUNCTIONS],
    ["depth_bias_enable", "bool", None],
    ["depth_bias", "float", None],
    ["alpha_test", "bool", None],
    ["alpha_func", "enum", atr.COMPARE_FUNCTIONS],
    ["alpha_ref", "float", None],
    ["blend", "bool", None],
    ["blend_rgb_equation", "enum", atr.BLEND_EQUATIONS],
    ["blend_rgb_source", "enum", atr.BLEND_FACTORS],
    ["blend_rgb_destination", "enum", atr.BLEND_FACTORS],
    ["blend_alpha_equation", "enum", atr.BLEND_EQUATIONS],
    ["blend_alpha_source", "enum", atr.BLEND_FACTORS],
    ["blend_alpha_destination", "enum", atr.BLEND_FACTORS],
    ["stencil_test", "bool", None],
    ["stencil_func", "enum", atr.COMPARE_FUNCTIONS],
    ["stencil_ref", "int", None],
    ["stencil_compare_mask", "int", None],
    ["stencil_write_mask", "int", None],
    ["stencil_fail_op", "int", None],
    ["stencil_zfail_op", "int", None],
    ["stencil_zpass_op", "int", None],
]

# Fields set by the render mode, cull is left out: the double sided toggle owns it whatever the render mode is
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

# The simple mode only shows these four, a custom render is the expert mode
RENDER_MODES = ['OPAQUE', 'CUTOUT', 'TRANSLUCENT', 'ADDITIVE']

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

# A new material gets a value for everything an opaque mesh needs, an inherited field would depend on the mesh drawn before it
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

##########################################
# Material Render Function
##########################################

def get_enum_items(values, descriptions = {}):
    items = [(INHERIT, "Inherit", INHERIT_ITEM_DESCRIPTION)]

    for name in values:
        items.append((name, name.replace("_", " ").title(), descriptions.get(name, "")))

    return items

COMPARE_FUNCTION_ITEMS = get_enum_items(atr.COMPARE_FUNCTIONS, COMPARE_FUNCTION_DESCRIPTIONS)
BLEND_EQUATION_ITEMS = get_enum_items(atr.BLEND_EQUATIONS)
BLEND_FACTOR_ITEMS = get_enum_items(atr.BLEND_FACTORS)

def state_from_properties(properties):
    state = atr.new_state()

    for name, kind, values in PROPERTY_FIELDS:
        value = getattr(properties, name, None)

        if kind == "bool":
            if value == 'OFF' or value == 'ON':
                state[name] = value == 'ON'
        elif kind == "enum":
            if value in values:
                state[name] = values[value]
        elif value is not None and value >= 0:
            if kind == "float":
                state[name] = float(value)
            else:
                state[name] = int(value)

    if getattr(properties, "color_mask_override", False):
        atr.set_color_mask(state, tuple(properties.color_mask))

    return state

def state_to_properties(state, properties):
    for name, kind, values in PROPERTY_FIELDS:
        value = state[name]

        if kind == "bool":
            if value is None:
                setattr(properties, name, INHERIT)
            elif value:
                setattr(properties, name, 'ON')
            else:
                setattr(properties, name, 'OFF')
        elif kind == "enum":
            setattr(properties, name, INHERIT)

            for enum_name in values:
                if values[enum_name] == value:
                    setattr(properties, name, enum_name)
        elif kind == "float":
            if value is None:
                setattr(properties, name, -1.0)
            else:
                setattr(properties, name, float(value))
        else:
            if value is None:
                setattr(properties, name, -1)
            else:
                setattr(properties, name, int(value))

    color_mask = atr.get_color_mask(state)

    if color_mask is not None:
        properties.color_mask_override = True
        properties.color_mask = color_mask
    else:
        properties.color_mask_override = False
        properties.color_mask = (True, True, True, True)

def default_state(version = None):
    state = state_from_properties(SimpleNamespace(**PROPERTY_DEFAULTS))
    state["version"] = version

    return state

def detect_render_mode(properties):
    for name in RENDER_PRESETS:
        is_preset = True

        for field in RENDER_PRESETS[name]:
            if getattr(properties, field, None) != RENDER_PRESETS[name][field]:
                is_preset = False

        if is_preset:
            return name

    return 'CUSTOM'

def apply_render_mode(properties, name):
    for field, value in RENDER_PRESETS.get(name, {}).items():
        setattr(properties, field, value)

##########################################
# Register class
##########################################

def get_render_mode(self):
    render_mode = detect_render_mode(self)

    if render_mode in RENDER_MODES:
        return RENDER_MODES.index(render_mode)

    return 0

def set_render_mode(self, value):
    if value >= 0 and value < len(RENDER_MODES):
        apply_render_mode(self, RENDER_MODES[value])
    else:
        apply_render_mode(self, 'OPAQUE')

def get_double_sided(self):
    return self.cull == 'OFF'

def set_double_sided(self, value):
    if value:
        self.cull = 'OFF'
    else:
        self.cull = 'ON'

def get_alpha_cutoff(self):
    return min(max(self.alpha_ref, 0.0), 1.0)

def set_alpha_cutoff(self, value):
    self.alpha_ref = value

class Level5MaterialProperties(bpy.types.PropertyGroup):
    panel_mode: EnumProperty(
        name="Mode",
        description="How many settings the panel shows",
        items=[
            ('SIMPLE', "Simple", "Pick the kind of material and let the render settings be filled in for you"),
            ('EXPERT', "Expert", "Show and edit every render setting one by one"),
        ],
        default='SIMPLE'
    )

    render_mode: EnumProperty(
        name="Render Mode",
        description="The kind of material to render, it fills in the depth, alpha test and blending settings for you",
        items=RENDER_MODE_ITEMS,
        get=get_render_mode,
        set=set_render_mode
    )

    double_sided: BoolProperty(
        name="Double-Sided",
        description="Draw both sides of every face. Turn it on for flat objects that have to stay visible from "
                    "behind, like a cape, a leaf or a flag. Leave it off for closed shapes such as a body or a "
                    "box: hiding their invisible inner side is faster and avoids artifacts",
        get=get_double_sided,
        set=set_double_sided
    )

    alpha_cutoff: FloatProperty(
        name="Alpha Cutoff",
        description="Pixels of the texture more transparent than this are thrown away instead of being drawn. "
                    "Raise it to eat more of the faded edges, lower it to keep them",
        get=get_alpha_cutoff,
        set=set_alpha_cutoff,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    )

    cull: EnumProperty(
        name="Face Culling",
        description="Skip drawing the back of every face. Faces have a front and a back, and the back of a closed "
                    "shape is never visible, so skipping it is faster. Turn it off for flat objects that must be "
                    "seen from both sides",
        items=BOOL_ITEMS,
        default=PROPERTY_DEFAULTS["cull"]
    )

    depth_test: EnumProperty(
        name="Depth Test",
        description="Check how far each pixel is from the camera before drawing it, so that nearer meshes properly "
                    "hide the ones behind them. Turning it off makes the material draw over everything else, which "
                    "is mostly useful for interface elements",
        items=BOOL_ITEMS,
        default=PROPERTY_DEFAULTS["depth_test"]
    )

    depth_write: EnumProperty(
        name="Depth Write",
        description="Whether this material records its own distance from the camera, so that meshes drawn later "
                    "know it is in front of them. Turn it off for see-through materials such as glass or effects, "
                    "otherwise they hide whatever is drawn behind them afterwards",
        items=BOOL_ITEMS,
        default=PROPERTY_DEFAULTS["depth_write"]
    )

    depth_func: EnumProperty(
        name="Depth Comparison",
        description="The test a pixel has to pass against the distance already recorded to be drawn. Less means "
                    "\"only draw it if it is nearer than what is already there\", which is the usual choice",
        items=COMPARE_FUNCTION_ITEMS,
        default=PROPERTY_DEFAULTS["depth_func"]
    )

    alpha_test: EnumProperty(
        name="Alpha Test",
        description="Throw away the pixels that are more transparent than the reference below, instead of mixing "
                    "them with the background. Use it for leaves, fences or hair, where you want hard holes rather "
                    "than a soft fade",
        items=BOOL_ITEMS,
        default=PROPERTY_DEFAULTS["alpha_test"]
    )

    alpha_func: EnumProperty(
        name="Alpha Comparison",
        description="How the transparency of a pixel is compared to the reference below to decide whether to keep "
                    "it. Greater keeps the pixels more opaque than the reference. Always keeps everything, which "
                    "turns the test off",
        items=COMPARE_FUNCTION_ITEMS,
        default=PROPERTY_DEFAULTS["alpha_func"]
    )

    alpha_ref: FloatProperty(
        name="Alpha Reference",
        description="The transparency the alpha test compares each pixel against, from 0 (fully transparent) to 1 "
                    "(fully opaque). " + INHERIT_NUMBER_DESCRIPTION,
        default=PROPERTY_DEFAULTS["alpha_ref"],
        min=-1.0,
        max=1.0
    )

    blend: EnumProperty(
        name="Blending",
        description="Mix the color of this material with what is already drawn behind it instead of replacing it. "
                    "This is what makes transparency, glow and similar effects possible. The equation and the "
                    "factors below decide exactly how the two colors are combined",
        items=BOOL_ITEMS,
        default=PROPERTY_DEFAULTS["blend"]
    )

    blend_rgb_equation: EnumProperty(
        name="RGB Equation",
        description="How the color of this material and the color already on screen are put together once each has "
                    "been multiplied by its factor below. Add sums them, which is what nearly every material uses",
        items=BLEND_EQUATION_ITEMS,
        default=PROPERTY_DEFAULTS["blend_rgb_equation"]
    )

    blend_rgb_source: EnumProperty(
        name="RGB Source Factor",
        description="What the color of this material is multiplied by before being combined. One keeps it as it is "
                    "(solid material), Src Alpha scales it by its own transparency (see-through material)",
        items=BLEND_FACTOR_ITEMS,
        default=PROPERTY_DEFAULTS["blend_rgb_source"]
    )

    blend_rgb_destination: EnumProperty(
        name="RGB Destination Factor",
        description="What the color already on screen is multiplied by before being combined. Zero erases it, so "
                    "the material looks solid. One Minus Src Alpha keeps the part this material doesn't cover, "
                    "which is how normal transparency works. One adds on top of it, which is how glow works",
        items=BLEND_FACTOR_ITEMS,
        default=PROPERTY_DEFAULTS["blend_rgb_destination"]
    )

    blend_alpha_equation: EnumProperty(
        name="Alpha Equation",
        description="Same as the RGB equation, but for the transparency channel instead of the color. It decides "
                    "how transparent the screen becomes where this material is drawn",
        items=BLEND_EQUATION_ITEMS,
        default=PROPERTY_DEFAULTS["blend_alpha_equation"]
    )

    blend_alpha_source: EnumProperty(
        name="Alpha Source Factor",
        description="What the transparency of this material is multiplied by before being combined",
        items=BLEND_FACTOR_ITEMS,
        default=PROPERTY_DEFAULTS["blend_alpha_source"]
    )

    blend_alpha_destination: EnumProperty(
        name="Alpha Destination Factor",
        description="What the transparency already on screen is multiplied by before being combined",
        items=BLEND_FACTOR_ITEMS,
        default=PROPERTY_DEFAULTS["blend_alpha_destination"]
    )

    # The engine applies the four channels together or not at all
    color_mask_override: BoolProperty(
        name="Color Mask",
        description="Choose which of the red, green, blue and transparency channels this material is allowed to "
                    "draw, the four of them being applied together. Turning all four off draws the mesh into the "
                    "depth buffer only, which makes it an invisible wall that hides what is behind it",
        default=PROPERTY_DEFAULTS["color_mask_override"]
    )

    color_mask: BoolVectorProperty(
        name="Channels",
        description="Red, green, blue and transparency channels this material is allowed to draw",
        size=4,
        default=PROPERTY_DEFAULTS["color_mask"],
        subtype='NONE'
    )

    depth_bias_enable: EnumProperty(
        name="Depth Bias",
        description="Push the material slightly towards the camera when it is compared to the others. Use it on a "
                    "surface lying exactly on another one, like a decal, a shadow or a marking painted on the "
                    "ground, to stop the two from flickering against each other",
        items=BOOL_ITEMS,
        default=PROPERTY_DEFAULTS["depth_bias_enable"]
    )

    depth_bias: FloatProperty(
        name="Depth Bias Value",
        description="How far the material is pushed towards the camera. Small values are enough, raise it only "
                    "until the flickering stops. " + INHERIT_NUMBER_DESCRIPTION,
        default=PROPERTY_DEFAULTS["depth_bias"],
        min=-1.0
    )

    stencil_test: EnumProperty(
        name="Stencil Test",
        description="The stencil buffer is a scratch pad where a mesh can leave a mark so that the meshes drawn "
                    "afterwards only appear inside or outside that mark. It is used for masks, mirrors and "
                    "portal-like effects",
        items=BOOL_ITEMS,
        default=PROPERTY_DEFAULTS["stencil_test"]
    )

    stencil_func: EnumProperty(
        name="Stencil Comparison",
        description="How the mark already in the stencil buffer is compared to the reference below to decide "
                    "whether the pixel is drawn. Always passes everywhere, which turns the test off",
        items=COMPARE_FUNCTION_ITEMS,
        default=PROPERTY_DEFAULTS["stencil_func"]
    )

    stencil_ref: IntProperty(
        name="Stencil Reference",
        description="The value the stencil buffer is compared against, and the mark written into it when the "
                    "operations below ask to replace it. " + INHERIT_NUMBER_DESCRIPTION,
        default=PROPERTY_DEFAULTS["stencil_ref"],
        min=-1,
        max=1023
    )

    stencil_compare_mask: IntProperty(
        name="Stencil Compare Mask",
        description="Which bits of the stencil buffer the comparison looks at, the other ones are ignored. "
                    + INHERIT_NUMBER_DESCRIPTION,
        default=PROPERTY_DEFAULTS["stencil_compare_mask"],
        min=-1,
        max=255
    )

    stencil_write_mask: IntProperty(
        name="Stencil Write Mask",
        description="Which bits of the stencil buffer this material is allowed to change. "
                    + INHERIT_NUMBER_DESCRIPTION,
        default=PROPERTY_DEFAULTS["stencil_write_mask"],
        min=-1,
        max=15
    )

    # The meaning of the stencil operation values is undocumented, they stay raw numbers
    stencil_fail_op: IntProperty(
        name="Fail Operation",
        description="What happens to the stencil buffer when a pixel fails the stencil test. What each number "
                    "means is undocumented, so this is mostly there to export an imported material unchanged. "
                    + INHERIT_NUMBER_DESCRIPTION,
        default=PROPERTY_DEFAULTS["stencil_fail_op"],
        min=-1,
        max=255
    )

    stencil_zfail_op: IntProperty(
        name="Depth Fail Operation",
        description="What happens to the stencil buffer when a pixel passes the stencil test but fails the depth "
                    "test. What each number means is undocumented, so this is mostly there to export an imported "
                    "material unchanged. " + INHERIT_NUMBER_DESCRIPTION,
        default=PROPERTY_DEFAULTS["stencil_zfail_op"],
        min=-1,
        max=255
    )

    stencil_zpass_op: IntProperty(
        name="Depth Pass Operation",
        description="What happens to the stencil buffer when a pixel passes both the stencil and the depth test. "
                    "What each number means is undocumented, so this is mostly there to export an imported "
                    "material unchanged. " + INHERIT_NUMBER_DESCRIPTION,
        default=PROPERTY_DEFAULTS["stencil_zpass_op"],
        min=-1,
        max=255
    )

class Level5_Material_Panel(bpy.types.Panel):
    bl_label = "Level 5"
    bl_idname = "MATERIAL_PT_level5_render_state_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"

    @classmethod
    def poll(cls, context):
        return context.material is not None

    def draw(self, context):
        if not hasattr(context.material, "level5_atr"):
            self.layout.label(text="No Level 5 properties found.")

class Level5_Material_Render_Panel(bpy.types.Panel):
    bl_label = "Material Render"
    bl_idname = "MATERIAL_PT_level5_material_render_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_parent_id = "MATERIAL_PT_level5_render_state_panel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.material is not None and hasattr(context.material, "level5_atr")

    def draw(self, context):
        layout = self.layout
        properties = context.material.level5_atr

        layout.prop(properties, "panel_mode", expand=True)

        if properties.panel_mode == 'SIMPLE':
            layout.prop(properties, "render_mode")
            layout.prop(properties, "double_sided")

            if properties.render_mode == 'CUTOUT':
                layout.prop(properties, "alpha_cutoff")

# The groups of the expert mode, each one folds on its own inside Material Render
class Level5RenderStateSubPanel:
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_parent_id = "MATERIAL_PT_level5_material_render_panel"

    @classmethod
    def poll(cls, context):
        material = context.material

        return material is not None and hasattr(material, "level5_atr") and material.level5_atr.panel_mode == 'EXPERT'

class Level5_Culling_Depth_Panel(Level5RenderStateSubPanel, bpy.types.Panel):
    bl_label = "Culling & Depth"
    bl_idname = "MATERIAL_PT_level5_culling_depth_panel"

    def draw(self, context):
        properties = context.material.level5_atr
        self.layout.prop(properties, "cull")
        self.layout.prop(properties, "depth_test")
        self.layout.prop(properties, "depth_write")
        self.layout.prop(properties, "depth_func")

class Level5_Alpha_Test_Panel(Level5RenderStateSubPanel, bpy.types.Panel):
    bl_label = "Alpha Test"
    bl_idname = "MATERIAL_PT_level5_alpha_test_panel"

    def draw(self, context):
        properties = context.material.level5_atr
        self.layout.prop(properties, "alpha_test")
        self.layout.prop(properties, "alpha_func")
        self.layout.prop(properties, "alpha_ref")

class Level5_Blending_Panel(Level5RenderStateSubPanel, bpy.types.Panel):
    bl_label = "Blending"
    bl_idname = "MATERIAL_PT_level5_blending_panel"

    def draw(self, context):
        properties = context.material.level5_atr
        self.layout.prop(properties, "blend")
        self.layout.prop(properties, "blend_rgb_equation")
        self.layout.prop(properties, "blend_rgb_source")
        self.layout.prop(properties, "blend_rgb_destination")
        self.layout.prop(properties, "blend_alpha_equation")
        self.layout.prop(properties, "blend_alpha_source")
        self.layout.prop(properties, "blend_alpha_destination")

class Level5_Color_Mask_Panel(Level5RenderStateSubPanel, bpy.types.Panel):
    bl_label = "Color Mask"
    bl_idname = "MATERIAL_PT_level5_color_mask_panel"

    def draw(self, context):
        properties = context.material.level5_atr
        self.layout.prop(properties, "color_mask_override", text="Write Color Mask")

        if properties.color_mask_override:
            row = self.layout.row(align=True)
            for i, channel in enumerate("RGBA"):
                row.prop(properties, "color_mask", index=i, text=channel, toggle=True)

class Level5_Advanced_Panel(Level5RenderStateSubPanel, bpy.types.Panel):
    bl_label = "Advanced"
    bl_idname = "MATERIAL_PT_level5_advanced_panel"

    def draw(self, context):
        layout = self.layout
        properties = context.material.level5_atr
        layout.label(text="These additional options only apply to games using the V2 render format.", icon='INFO')
        layout.prop(properties, "depth_bias_enable")
        layout.prop(properties, "depth_bias")
        layout.prop(properties, "stencil_test")
        layout.prop(properties, "stencil_func")
        layout.prop(properties, "stencil_ref")
        layout.prop(properties, "stencil_compare_mask")
        layout.prop(properties, "stencil_write_mask")
        layout.prop(properties, "stencil_fail_op")
        layout.prop(properties, "stencil_zfail_op")
        layout.prop(properties, "stencil_zpass_op")

# Parents first, the sub panels are drawn in this order
MATERIAL_PANELS = (
    Level5_Material_Panel,
    Level5_Material_Render_Panel,
    Level5_Culling_Depth_Panel,
    Level5_Alpha_Test_Panel,
    Level5_Blending_Panel,
    Level5_Color_Mask_Panel,
    Level5_Advanced_Panel,
)

##########################################
# Register
##########################################

def register_material_render():
    bpy.utils.register_class(Level5MaterialProperties)

    for panel in MATERIAL_PANELS:
        bpy.utils.register_class(panel)

    bpy.types.Material.level5_atr = PointerProperty(type=Level5MaterialProperties)

def unregister_material_render():
    for panel in reversed(MATERIAL_PANELS):
        bpy.utils.unregister_class(panel)

    bpy.utils.unregister_class(Level5MaterialProperties)

    del bpy.types.Material.level5_atr
