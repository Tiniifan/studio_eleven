import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, PointerProperty, StringProperty

from ..formats import res

##########################################
# CONST
##########################################

# A RES material has 4 texture entries
MAX_TEXTURE_SLOTS = 4

TEXTURE_NODE_PREFIX = "Level5 Texture"
MIX_COLOR_PREFIX = "Level5 Mix Color"
MIX_ALPHA_PREFIX = "Level5 Mix Alpha"
SAMPLER_NODE_PREFIX = "Level5 Sampler"
SAMPLER_UV_NODE = SAMPLER_NODE_PREFIX + " Texture Coordinate"
SAMPLER_PARTS = ["Separate", "Combine", "Wrap X", "Wrap Y"]

# The node group the previous versions put in front of an Image Texture node to wrap each axis
LEGACY_WRAP_GROUP_PREFIX = "Level Five Wrap"

PIXEL_FORMAT_ITEMS = [
    ('RGBA8', "RGBA8", "32 bits per pixel with the alpha, the best quality"),
    ('RGBA4', "RGBA4", "16 bits per pixel, 16 levels for each channel and the alpha"),
    ('RBGR888', "RBGR888", "24 bits per pixel, no alpha"),
    ('RGB565', "RGB565", "16 bits per pixel, no alpha"),
]

FORMATS_WITHOUT_ALPHA = ['RBGR888', 'RGB565']

WRAP_ITEMS = [
    ('REPEAT', "Repeat", "The texture is tiled over and over"),
    ('EXTEND', "Extend", "Outside the texture, the pixels of its edge are stretched out"),
    ('CLIP', "Clip", "Outside the texture, the border of the texture is drawn, which is transparent black"),
    ('MIRROR', "Mirror", "The texture is tiled, every other copy being flipped"),
]

FILTER_ITEMS = [
    ('NEAREST', "Closest", "Take the nearest pixel of the texture, which keeps it sharp and blocky"),
    ('LINEAR', "Linear", "Mix the pixels of the texture together, which makes it smooth"),
]

MIPMAP_ITEMS = [
    ('ENABLED', "Enabled", "The game switches to smaller copies of the texture with the distance"),
    ('DISABLED', "Disabled", "The game always samples the full size texture"),
]

TEXTURE_MODE_ITEMS = [
    ('TEXTURE_2D', "2D Texture", "A usual texture, what every shipped material uses"),
    ('CUBE_MAP', "Cube Map", "The texture is read as a cube map. Only the first texture slot can use it"),
    ('SHADOW_2D', "Shadow 2D", "The texture is read as a shadow map. Only the first texture slot can use it"),
    ('SHADOW_CUBE', "Shadow Cube", "The texture is read as a cube shadow map. Only the first texture slot can use it"),
    ('PROJECTION', "Projection", "The texture is projected, its coordinates are divided like a slide projector. Only the first texture slot can use it"),
    ('DISABLED', "Disabled", "The game ignores the texture, as if the slot was empty"),
]

# Only the first texture unit can use these modes
UNIT_0_TEXTURE_MODES = ['CUBE_MAP', 'SHADOW_2D', 'SHADOW_CUBE', 'PROJECTION']

WRAP_OPERATIONS = {
    'REPEAT': 'FRACT',
    'MIRROR': 'PINGPONG',
    'EXTEND': 'ADD',
    'CLIP': 'ADD',
}

# Blender property of each sampler value and the modes it can take
SAMPLER_PROPERTIES = {
    "wrap_s": ["wrap_x", res.WRAP_MODES],
    "wrap_t": ["wrap_y", res.WRAP_MODES],
    "mag_filter": ["magnification", res.FILTER_MODES],
    "min_filter": ["minification", res.FILTER_MODES],
    "mip_filter": ["mipmap", res.MIPMAP_MODES],
}

##########################################
# Material Textures Function
##########################################

# Setting the slots from the code must not rebuild the shader graph on every property
suspended_updates = 0

def suspend_updates():
    global suspended_updates

    suspended_updates += 1

def resume_updates():
    global suspended_updates

    suspended_updates -= 1

def to_pixel_format(format_name):
    for item in PIXEL_FORMAT_ITEMS:
        if item[0] == format_name:
            return format_name

    # The formats the export can't write use the default one
    return 'RGBA8'

def sampler_to_properties(sampler, properties):
    for key in SAMPLER_PROPERTIES:
        name = SAMPLER_PROPERTIES[key][0]
        modes = SAMPLER_PROPERTIES[key][1]

        for mode in modes:
            if modes[mode] == sampler[key]:
                setattr(properties, name, mode)

def properties_to_sampler(properties):
    sampler = {}

    for key in SAMPLER_PROPERTIES:
        name = SAMPLER_PROPERTIES[key][0]
        modes = SAMPLER_PROPERTIES[key][1]
        value = getattr(properties, name, None)

        if value in modes:
            sampler[key] = modes[value]
        else:
            sampler[key] = res.DEFAULT_SAMPLER[key]

    return sampler

##########################################
# Properties
##########################################

def update_slot(self, context):
    if suspended_updates == 0:
        apply_material_textures(self.id_data)

def update_slot_image(self, context):
    if self.image is not None:
        self.show_expanded = True

    update_slot(self, context)

class Level5TextureSlot(bpy.types.PropertyGroup):
    image: PointerProperty(
        name="Image",
        description="Image of the texture, one of the blend file or one opened from a file",
        type=bpy.types.Image,
        update=update_slot_image
    )

    node_name: StringProperty(
        description="Image Texture node that shows this texture in the shader graph of the material"
    )

    show_expanded: BoolProperty(
        name="Show Settings",
        description="Show the settings of the texture",
        default=True
    )

    pixel_format: EnumProperty(
        name="Pixel Format",
        description="How the pixels of the texture are stored in the exported archive",
        items=PIXEL_FORMAT_ITEMS,
        default='RGBA8'
    )

    texture_mode: EnumProperty(
        name="Texture Mode",
        description="How the game reads the texture. Every shipped material uses 2D Texture",
        items=TEXTURE_MODE_ITEMS,
        default='TEXTURE_2D'
    )

    wrap_x: EnumProperty(
        name="Wrap X",
        description="What is drawn left and right of the texture, once the UVs go past its edge",
        items=WRAP_ITEMS,
        default='REPEAT',
        update=update_slot
    )

    wrap_y: EnumProperty(
        name="Wrap Y",
        description="What is drawn above and below the texture, once the UVs go past its edge",
        items=WRAP_ITEMS,
        default='REPEAT',
        update=update_slot
    )

    magnification: EnumProperty(
        name="Magnification",
        description="How the texture is sampled when it is drawn bigger than it really is, up close",
        items=FILTER_ITEMS,
        default='LINEAR',
        update=update_slot
    )

    minification: EnumProperty(
        name="Minification",
        description="How the texture is sampled when it is drawn smaller than it really is, far away",
        items=FILTER_ITEMS,
        default='LINEAR',
        update=update_slot
    )

    mipmap: EnumProperty(
        name="Mipmap",
        description="Whether the game samples smaller copies of the texture with the distance. Eevee does not show it",
        items=MIPMAP_ITEMS,
        default='DISABLED',
        update=update_slot
    )

class Level5TexturesProperties(bpy.types.PropertyGroup):
    slots: CollectionProperty(type=Level5TextureSlot)

    # False until the textures already in the shader graph have been taken as slots
    initialized: BoolProperty(default=False)

##########################################
# Shader graph
##########################################

def get_node(tree, name, bl_idname, location, label = None):
    node = tree.nodes.get(name)

    if node is not None and node.bl_idname != bl_idname:
        tree.nodes.remove(node)
        node = None

    if node is None:
        node = tree.nodes.new(bl_idname)
        node.name = name
        node.label = label or name
        node.location = location

    return node

def link(tree, output, target):
    if len(target.links) == 1 and target.links[0].from_socket == output:
        return

    for old in list(target.links):
        tree.links.remove(old)

    tree.links.new(output, target)

def unlink_from(tree, target, node_names):
    for old in list(target.links):
        if old.from_node.name in node_names or old.from_node.name.startswith("Level5 "):
            tree.links.remove(old)

def find_bsdf(tree):
    bsdf = tree.nodes.get("Principled BSDF")

    if bsdf is not None and bsdf.type == 'BSDF_PRINCIPLED':
        return bsdf

    for node in tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            return node

    return None

def get_texture_node(material, slot):
    if material.node_tree is None or not slot.node_name:
        return None

    node = material.node_tree.nodes.get(slot.node_name)

    if node is None or node.type != 'TEX_IMAGE':
        return None

    return node

def new_texture_node_name(tree):
    number = 1

    while f"{TEXTURE_NODE_PREFIX} {number}" in tree.nodes:
        number += 1

    return f"{TEXTURE_NODE_PREFIX} {number}"

def get_sampler_node_name(part, texture_name):
    return f"{SAMPLER_NODE_PREFIX} {part} {texture_name}"

def get_custom_uv_source(tree, texture_node):
    # An UV source wired by hand is kept, whether the wrap needs nodes or not
    sockets = []

    separate = tree.nodes.get(get_sampler_node_name("Separate", texture_node.name))
    if separate is not None:
        sockets.append(separate.inputs[0])

    sockets.append(texture_node.inputs['Vector'])

    for socket in sockets:
        for old in socket.links:
            if not old.from_node.name.startswith(SAMPLER_NODE_PREFIX):
                return old.from_socket

    return None

def remove_sampler_nodes(tree, texture_name):
    for part in SAMPLER_PARTS:
        node = tree.nodes.get(get_sampler_node_name(part, texture_name))

        if node is not None:
            tree.nodes.remove(node)

    uv_node = tree.nodes.get(SAMPLER_UV_NODE)

    if uv_node is None:
        return

    for output in uv_node.outputs:
        if output.is_linked:
            return

    tree.nodes.remove(uv_node)

def has_extension(texture_node, extension):
    # Mirror isn't in the extension enum of this node on every Blender version the addon supports (e.g. not on 3.4)
    return extension in texture_node.bl_rna.properties['extension'].enum_items.keys()

def get_image_extension(wrap_x, wrap_y):
    # The Image Texture node has one extension for both axes, the wrapping itself is done on the coordinates
    if wrap_x == 'CLIP' or wrap_y == 'CLIP':
        return 'CLIP'

    if wrap_x == 'REPEAT' and wrap_y == 'REPEAT':
        return 'REPEAT'

    return 'EXTEND'

def apply_texture_sampler(tree, texture_node, slot):
    # The node can't tell magnification from minification, the close view is what shows
    if slot.magnification == 'NEAREST':
        texture_node.interpolation = 'Closest'
    else:
        texture_node.interpolation = 'Linear'

    uv_source = get_custom_uv_source(tree, texture_node)

    if slot.wrap_x == slot.wrap_y and has_extension(texture_node, slot.wrap_x):
        remove_sampler_nodes(tree, texture_node.name)

        if uv_source is not None:
            link(tree, uv_source, texture_node.inputs['Vector'])

        texture_node.extension = slot.wrap_x
        return

    origin = texture_node.location

    separate = get_node(tree, get_sampler_node_name("Separate", texture_node.name), 'ShaderNodeSeparateXYZ', (origin.x - 700, origin.y), "Separate UV")
    combine = get_node(tree, get_sampler_node_name("Combine", texture_node.name), 'ShaderNodeCombineXYZ', (origin.x - 200, origin.y), "Combine UV")

    if uv_source is None:
        uv_node = get_node(tree, SAMPLER_UV_NODE, 'ShaderNodeTexCoord', (origin.x - 900, origin.y), "Texture Coordinate")
        uv_source = uv_node.outputs['UV']

    link(tree, uv_source, separate.inputs[0])

    axes = [["X", slot.wrap_x], ["Y", slot.wrap_y]]

    for i in range(2):
        axis = axes[i][0]
        mode = axes[i][1]

        math = get_node(tree, get_sampler_node_name("Wrap " + axis, texture_node.name), 'ShaderNodeMath', (origin.x - 450, origin.y - 150 * i), "Wrap " + axis)
        math.operation = WRAP_OPERATIONS[mode]
        math.use_clamp = mode == 'EXTEND'

        if mode == 'MIRROR':
            math.inputs[1].default_value = 1.0
        elif mode == 'EXTEND' or mode == 'CLIP':
            math.inputs[1].default_value = 0.0

        link(tree, separate.outputs[i], math.inputs[0])
        link(tree, math.outputs[0], combine.inputs[i])

    link(tree, separate.outputs[2], combine.inputs[2])
    link(tree, combine.outputs[0], texture_node.inputs['Vector'])

    texture_node.extension = get_image_extension(slot.wrap_x, slot.wrap_y)

def mix_textures(tree, textures, prefix, bl_idname, output_name):
    output = None
    if textures:
        output = textures[0].outputs[output_name]

    for i in range(1, MAX_TEXTURE_SLOTS):
        name = f"{prefix} {i}"

        if i >= len(textures):
            if name in tree.nodes:
                tree.nodes.remove(tree.nodes[name])
            continue

        texture = textures[i]
        mix = tree.nodes.get(name)

        # The blend mode is only set on creation, the one chosen in the shader editor is kept
        if mix is None or mix.bl_idname != bl_idname:
            if output_name == 'Color':
                mix = get_node(tree, name, bl_idname, (texture.location.x + 300, texture.location.y), "Mix Color")
            else:
                mix = get_node(tree, name, bl_idname, (texture.location.x + 300, texture.location.y - 180), "Mix Alpha")

            if bl_idname == 'ShaderNodeMixRGB':
                mix.blend_type = 'MULTIPLY'
                mix.inputs[0].default_value = 1.0
            else:
                mix.operation = 'MULTIPLY'

        if bl_idname == 'ShaderNodeMixRGB':
            link(tree, output, mix.inputs[1])
            link(tree, texture.outputs[output_name], mix.inputs[2])
        else:
            link(tree, output, mix.inputs[0])
            link(tree, texture.outputs[output_name], mix.inputs[1])

        output = mix.outputs[0]

    return output

def wire_textures(tree, textures, node_names):
    color = mix_textures(tree, textures, MIX_COLOR_PREFIX, 'ShaderNodeMixRGB', 'Color')
    alpha = mix_textures(tree, textures, MIX_ALPHA_PREFIX, 'ShaderNodeMath', 'Alpha')

    bsdf = find_bsdf(tree)

    if bsdf is None:
        return

    if color is not None:
        link(tree, color, bsdf.inputs['Base Color'])
    else:
        unlink_from(tree, bsdf.inputs['Base Color'], node_names)

    # The importer multiplies the alpha of the textures before the shader
    multiplier = tree.nodes.get("Alpha Multiplier")

    if multiplier is not None and multiplier.outputs[0].is_linked:
        target = multiplier.inputs[0]
    else:
        target = bsdf.inputs['Alpha']

    has_alpha = False
    for texture in textures:
        if texture.image.alpha_mode != 'NONE':
            has_alpha = True

    if alpha is not None and has_alpha:
        link(tree, alpha, target)
    else:
        unlink_from(tree, target, node_names)

def apply_material_textures(material):
    if material is None or not hasattr(material, "level5_textures"):
        return

    if not material.use_nodes:
        material.use_nodes = True

    tree = material.node_tree

    if tree is None:
        return

    origin = (0, 0)

    bsdf = find_bsdf(tree)
    if bsdf is not None:
        origin = bsdf.location

    slots = material.level5_textures.slots
    textures = []

    suspend_updates()

    try:
        for i, slot in enumerate(slots):
            node = get_texture_node(material, slot)

            if node is None:
                if slot.image is None:
                    continue

                node = tree.nodes.new('ShaderNodeTexImage')
                node.name = new_texture_node_name(tree)
                node.location = (origin[0] - 700, origin[1] + 250 - 320 * i)
                slot.node_name = node.name

            if node.name.startswith(TEXTURE_NODE_PREFIX):
                node.label = f"Level 5 Texture {i + 1}"

            if node.image != slot.image:
                node.image = slot.image

            apply_texture_sampler(tree, node, slot)

            if slot.image is not None:
                textures.append(node)

        node_names = []
        for slot in slots:
            if slot.node_name:
                node_names.append(slot.node_name)

        # The nodes of the slots that were removed
        for node in list(tree.nodes):
            if node.type == 'TEX_IMAGE' and node.name.startswith(TEXTURE_NODE_PREFIX) and node.name not in node_names:
                remove_sampler_nodes(tree, node.name)
                tree.nodes.remove(node)

        wire_textures(tree, textures, node_names)
    finally:
        resume_updates()

def remove_legacy_wrap_group(tree, texture_node):
    for old in list(texture_node.inputs['Vector'].links):
        group = old.from_node

        if group.type != 'GROUP' or group.node_tree is None or not group.node_tree.name.startswith(LEGACY_WRAP_GROUP_PREFIX):
            continue

        sources = []
        for source_link in group.inputs[0].links:
            sources.append(source_link.from_socket)

        tree.nodes.remove(group)

        for source in sources:
            if source.node.bl_idname == 'ShaderNodeUVMap' and source.node.label == LEGACY_WRAP_GROUP_PREFIX:
                tree.nodes.remove(source.node)
            else:
                tree.links.new(source, texture_node.inputs['Vector'])

def add_node_slot(material, node):
    slot = material.level5_textures.slots.add()
    slot.node_name = node.name
    slot.image = node.image
    slot.show_expanded = False

    # The sampler was stored on the Image (Image.level5_texture) before it moved to the texture slots
    old = node.image.get("level5_texture")

    if old is not None:
        sampler = {}
        for key in res.DEFAULT_SAMPLER:
            sampler[key] = old.get(key, res.DEFAULT_SAMPLER[key])

        sampler_to_properties(sampler, slot)

    return slot

def adopt_material_textures(material):
    """Take the Image Texture nodes already in the shader graph as the texture slots of the material."""
    properties = material.level5_textures

    if properties.initialized or material.library is not None:
        return

    suspend_updates()

    try:
        properties.initialized = True

        if material.node_tree is None:
            return

        for node in material.node_tree.nodes:
            if len(properties.slots) >= MAX_TEXTURE_SLOTS:
                break

            if node.type == 'TEX_IMAGE' and node.image is not None:
                remove_legacy_wrap_group(material.node_tree, node)
                add_node_slot(material, node)
    finally:
        resume_updates()

def adopt_all_materials():
    for material in bpy.data.materials:
        adopt_material_textures(material)

    for image in bpy.data.images:
        if image.library is None and "level5_texture" in image.keys():
            del image["level5_texture"]

    # Also used as a timer, which must not run again
    return None

def sync_material_from_nodes(material):
    """Report on the slots what was changed on their Image Texture nodes in the shader editor."""
    properties = material.level5_textures

    if not properties.initialized:
        adopt_material_textures(material)
        return

    tree = material.node_tree

    if tree is None or material.library is not None:
        return

    rewire = False
    removed = []

    suspend_updates()

    try:
        for i, slot in enumerate(properties.slots):
            if not slot.node_name:
                continue

            node = tree.nodes.get(slot.node_name)

            # The node was deleted, so is its texture
            if node is None or node.type != 'TEX_IMAGE':
                removed.append(i)
            elif node.image != slot.image:
                rewire = True
                slot.image = node.image

        for i in reversed(removed):
            properties.slots.remove(i)

        # An Image Texture node added in the shader editor becomes a slot as soon as it has an image
        node_names = []
        for slot in properties.slots:
            node_names.append(slot.node_name)

        for node in tree.nodes:
            if len(properties.slots) >= MAX_TEXTURE_SLOTS:
                break

            if node.type == 'TEX_IMAGE' and node.image is not None and node.name not in node_names:
                add_node_slot(material, node)
    finally:
        resume_updates()

    if rewire or removed:
        apply_material_textures(material)

@persistent
def sync_textures_from_nodes(scene, depsgraph = None):
    if suspended_updates > 0:
        return

    if depsgraph is None:
        depsgraph = bpy.context.evaluated_depsgraph_get()

    materials = []

    for update in depsgraph.updates:
        updated = update.id.original

        if isinstance(updated, bpy.types.Material):
            candidates = [updated]
        elif isinstance(updated, bpy.types.ShaderNodeTree):
            candidates = [material for material in bpy.data.materials if material.node_tree == updated]
        else:
            continue

        for material in candidates:
            if material not in materials:
                materials.append(material)

    for material in materials:
        sync_material_from_nodes(material)

@persistent
def adopt_textures_on_load(dummy = None):
    adopt_all_materials()

##########################################
# Register class
##########################################

class MATERIAL_OT_level5_texture_add(bpy.types.Operator):
    bl_idname = "material.level5_texture_add"
    bl_label = "Add Texture"
    bl_description = "Add a texture to the material, a material can have up to 4 textures"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        material = getattr(context, "material", None)

        return material is not None and len(material.level5_textures.slots) < MAX_TEXTURE_SLOTS

    def execute(self, context):
        material = context.material
        adopt_material_textures(material)

        slots = material.level5_textures.slots

        if len(slots) >= MAX_TEXTURE_SLOTS:
            self.report({'WARNING'}, f"A material can't have more than {MAX_TEXTURE_SLOTS} textures")
            return {'CANCELLED'}

        slot = slots.add()
        slot.show_expanded = True

        return {'FINISHED'}

class MATERIAL_OT_level5_texture_remove(bpy.types.Operator):
    bl_idname = "material.level5_texture_remove"
    bl_label = "Remove Texture"
    bl_description = "Remove this texture from the material and its node from the shader graph"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty()

    def execute(self, context):
        material = context.material
        slots = material.level5_textures.slots

        if self.index < 0 or self.index >= len(slots):
            return {'CANCELLED'}

        node = get_texture_node(material, slots[self.index])

        if node is not None:
            remove_sampler_nodes(material.node_tree, node.name)
            material.node_tree.nodes.remove(node)

        slots.remove(self.index)
        apply_material_textures(material)

        return {'FINISHED'}

class MATERIAL_OT_level5_texture_move(bpy.types.Operator):
    bl_idname = "material.level5_texture_move"
    bl_label = "Move Texture"
    bl_description = "Change the order of the textures, the order they have in the exported material"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty()
    direction: EnumProperty(items=[('UP', "Up", ""), ('DOWN', "Down", "")])

    def execute(self, context):
        material = context.material
        slots = material.level5_textures.slots

        if self.direction == 'UP':
            target = self.index - 1
        else:
            target = self.index + 1

        if self.index < 0 or self.index >= len(slots) or target < 0 or target >= len(slots):
            return {'CANCELLED'}

        slots.move(self.index, target)
        apply_material_textures(material)

        return {'FINISHED'}

class MATERIAL_PT_level5_textures(bpy.types.Panel):
    bl_label = "Textures"
    bl_idname = "MATERIAL_PT_level5_textures_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_parent_id = "MATERIAL_PT_level5_render_state_panel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.material is not None and hasattr(context.material, "level5_textures")

    def draw(self, context):
        layout = self.layout
        slots = context.material.level5_textures.slots

        row = layout.row()
        row.label(text=f"Textures: {len(slots)} / {MAX_TEXTURE_SLOTS}", icon='TEXTURE')

        if len(slots) < MAX_TEXTURE_SLOTS:
            row.operator(MATERIAL_OT_level5_texture_add.bl_idname, text="Add Texture", icon='ADD')
        else:
            row.label(text="Limit reached")

        if len(slots) == 0:
            layout.label(text="No texture, the material is exported without any", icon='INFO')
            return

        for i, slot in enumerate(slots):
            self.draw_slot(layout, i, slot, len(slots))

    def draw_slot(self, layout, index, slot, count):
        box = layout.box()
        header = box.row(align=True)

        if slot.image is not None:
            if slot.show_expanded:
                header.prop(slot, "show_expanded", text="", emboss=False, icon='TRIA_DOWN')
            else:
                header.prop(slot, "show_expanded", text="", emboss=False, icon='TRIA_RIGHT')

            header.label(text=f"{index + 1}. {slot.image.name}", icon_value=layout.icon(slot.image))
        else:
            header.label(text=f"{index + 1}. Choose an image", icon='IMAGE_DATA')

        buttons = header.row(align=True)

        up = buttons.row(align=True)
        up.enabled = index > 0
        operator = up.operator(MATERIAL_OT_level5_texture_move.bl_idname, text="", icon='TRIA_UP', emboss=False)
        operator.index = index
        operator.direction = 'UP'

        down = buttons.row(align=True)
        down.enabled = index < count - 1
        operator = down.operator(MATERIAL_OT_level5_texture_move.bl_idname, text="", icon='TRIA_DOWN', emboss=False)
        operator.index = index
        operator.direction = 'DOWN'

        operator = buttons.operator(MATERIAL_OT_level5_texture_remove.bl_idname, text="", icon='X', emboss=False)
        operator.index = index

        if slot.image is None:
            box.template_ID(slot, "image", open="image.open")
            return

        if not slot.show_expanded:
            return

        box.template_ID(slot, "image", open="image.open")

        preview = box.row()
        preview.alignment = 'CENTER'
        preview.template_icon(icon_value=layout.icon(slot.image), scale=6.0)

        column = box.column()
        column.use_property_split = True
        column.use_property_decorate = False
        column.prop(slot, "pixel_format")

        if slot.pixel_format in FORMATS_WITHOUT_ALPHA and slot.image.alpha_mode != 'NONE' and slot.image.channels == 4:
            column.label(text="This format has no alpha, the transparency is lost", icon='ERROR')

        column.prop(slot, "texture_mode")

        if index > 0 and slot.texture_mode in UNIT_0_TEXTURE_MODES:
            column.label(text="Only the first texture can use this mode, the game ignores this one", icon='ERROR')
        elif slot.texture_mode == 'DISABLED':
            column.label(text="The game ignores this texture", icon='INFO')

        if index >= 3:
            column.label(text="The game only reads the first 3 textures of a material", icon='ERROR')

        column.separator()
        column.prop(slot, "wrap_x")
        column.prop(slot, "wrap_y")
        column.prop(slot, "magnification")
        column.prop(slot, "minification")
        column.prop(slot, "mipmap")

        if slot.magnification != slot.minification:
            column.label(text="Eevee uses the Magnification for both", icon='INFO')

##########################################
# Register
##########################################

classes = (
    Level5TextureSlot,
    Level5TexturesProperties,
    MATERIAL_OT_level5_texture_add,
    MATERIAL_OT_level5_texture_remove,
    MATERIAL_OT_level5_texture_move,
    MATERIAL_PT_level5_textures,
)

def register_material_textures():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Material.level5_textures = PointerProperty(type=Level5TexturesProperties)

    bpy.app.handlers.load_post.append(adopt_textures_on_load)
    bpy.app.handlers.depsgraph_update_post.append(sync_textures_from_nodes)

    # bpy.data is restricted while the addon registers, and load_post has already run when it is enabled later
    bpy.app.timers.register(adopt_all_materials, first_interval=0.0)

def unregister_material_textures():
    if bpy.app.timers.is_registered(adopt_all_materials):
        bpy.app.timers.unregister(adopt_all_materials)

    if sync_textures_from_nodes in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(sync_textures_from_nodes)

    if adopt_textures_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(adopt_textures_on_load)

    del bpy.types.Material.level5_textures

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
