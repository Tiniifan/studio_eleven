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
SAMPLER_UV_NODE = f"{SAMPLER_NODE_PREFIX} Texture Coordinate"
SAMPLER_PARTS = ("Separate", "Combine", "Wrap X", "Wrap Y")

# The node group the previous versions put in front of an Image Texture node to wrap each axis
LEGACY_WRAP_GROUP_PREFIX = "Level Five Wrap"

PIXEL_FORMAT_ITEMS = [
    ('RGBA8', "RGBA8", "32 bits per pixel with the alpha, the best quality"),
    ('RGBA4', "RGBA4", "16 bits per pixel, 16 levels for each channel and the alpha"),
    ('RBGR888', "RBGR888", "24 bits per pixel, no alpha"),
    ('RGB565', "RGB565", "16 bits per pixel, no alpha"),
]

PIXEL_FORMATS = {identifier for identifier, _, _ in PIXEL_FORMAT_ITEMS}
FORMATS_WITHOUT_ALPHA = {'RBGR888', 'RGB565'}

WRAP_OPERATIONS = {
    'REPEAT': 'FRACT',
    'MIRROR': 'PINGPONG',
    'EXTEND': 'ADD',
    'CLIP': 'ADD',
}

_suspended = 0

class suspend_updates:
    """Setting the slots from the code must not rebuild the shader graph on every property."""

    def __enter__(self):
        global _suspended
        _suspended += 1

    def __exit__(self, *args):
        global _suspended
        _suspended -= 1

def to_pixel_format(format_name):
    # The formats the export cannot write fall back to the default one
    return format_name if format_name in PIXEL_FORMATS else 'RGBA8'

##########################################
# Properties
##########################################

def update_slot(self, context):
    if not _suspended:
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
        items=res.TEXTURE_MODE_ITEMS,
        default='TEXTURE_2D'
    )

    wrap_x: EnumProperty(
        name="Wrap X",
        description="What is drawn left and right of the texture, once the UVs go past its edge",
        items=res.WRAP_ITEMS,
        default='REPEAT',
        update=update_slot
    )

    wrap_y: EnumProperty(
        name="Wrap Y",
        description="What is drawn above and below the texture, once the UVs go past its edge",
        items=res.WRAP_ITEMS,
        default='REPEAT',
        update=update_slot
    )

    magnification: EnumProperty(
        name="Magnification",
        description="How the texture is sampled when it is drawn bigger than it really is, up close",
        items=res.FILTER_ITEMS,
        default='LINEAR',
        update=update_slot
    )

    minification: EnumProperty(
        name="Minification",
        description="How the texture is sampled when it is drawn smaller than it really is, far away",
        items=res.FILTER_ITEMS,
        default='LINEAR',
        update=update_slot
    )

    mipmap: EnumProperty(
        name="Mipmap",
        description="Whether the game samples smaller copies of the texture with the distance. Eevee does not show it",
        items=res.MIPMAP_ITEMS,
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

def get_node(tree, name, bl_idname, location, label=None):
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

    if bsdf is None or bsdf.type != 'BSDF_PRINCIPLED':
        bsdf = next((node for node in tree.nodes if node.type == 'BSDF_PRINCIPLED'), None)

    return bsdf

def get_texture_node(material, slot):
    if material.node_tree is None or not slot.node_name:
        return None

    node = material.node_tree.nodes.get(slot.node_name)

    return node if node is not None and node.type == 'TEX_IMAGE' else None

def new_texture_node_name(tree):
    number = 1

    while f"{TEXTURE_NODE_PREFIX} {number}" in tree.nodes:
        number += 1

    return f"{TEXTURE_NODE_PREFIX} {number}"

def sampler_node_name(part, texture_name):
    return f"{SAMPLER_NODE_PREFIX} {part} {texture_name}"

def is_sampler_node(node):
    return node.name.startswith(SAMPLER_NODE_PREFIX)

def get_custom_uv_source(tree, texture_node):
    # An UV source wired by hand is kept, whether the wrap needs nodes or not
    separate = tree.nodes.get(sampler_node_name("Separate", texture_node.name))
    sockets = [separate.inputs[0]] if separate is not None else []
    sockets.append(texture_node.inputs['Vector'])

    for socket in sockets:
        for old in socket.links:
            if not is_sampler_node(old.from_node):
                return old.from_socket

    return None

def remove_sampler_nodes(tree, texture_name):
    for part in SAMPLER_PARTS:
        node = tree.nodes.get(sampler_node_name(part, texture_name))

        if node is not None:
            tree.nodes.remove(node)

    uv_node = tree.nodes.get(SAMPLER_UV_NODE)

    if uv_node is not None and not any(output.is_linked for output in uv_node.outputs):
        tree.nodes.remove(uv_node)

def has_extension(texture_node, extension):
    # Mirror isn't in this node's extension enum on every Blender version this addon supports (e.g. not on 3.4)
    return extension in texture_node.bl_rna.properties['extension'].enum_items.keys()

def get_image_extension(wrap_x, wrap_y):
    # The Image Texture node has one extension for both axes, the wrapping itself is done on the coordinates
    if 'CLIP' in (wrap_x, wrap_y):
        return 'CLIP'

    if wrap_x == wrap_y == 'REPEAT':
        return 'REPEAT'

    return 'EXTEND'

def apply_texture_sampler(tree, texture_node, slot):
    # One interpolation for both filters: the node cannot tell magnification from minification, the close view is what shows
    texture_node.interpolation = 'Closest' if slot.magnification == 'NEAREST' else 'Linear'

    uv_source = get_custom_uv_source(tree, texture_node)

    if slot.wrap_x == slot.wrap_y and has_extension(texture_node, slot.wrap_x):
        remove_sampler_nodes(tree, texture_node.name)

        if uv_source is not None:
            link(tree, uv_source, texture_node.inputs['Vector'])

        texture_node.extension = slot.wrap_x
        return

    origin = texture_node.location

    separate = get_node(tree, sampler_node_name("Separate", texture_node.name), 'ShaderNodeSeparateXYZ',
                        (origin.x - 700, origin.y), "Separate UV")
    combine = get_node(tree, sampler_node_name("Combine", texture_node.name), 'ShaderNodeCombineXYZ',
                       (origin.x - 200, origin.y), "Combine UV")

    if uv_source is None:
        uv_node = get_node(tree, SAMPLER_UV_NODE, 'ShaderNodeTexCoord', (origin.x - 900, origin.y), "Texture Coordinate")
        uv_source = uv_node.outputs['UV']

    link(tree, uv_source, separate.inputs[0])

    for index, (axis, mode) in enumerate((("X", slot.wrap_x), ("Y", slot.wrap_y))):
        math = get_node(tree, sampler_node_name(f"Wrap {axis}", texture_node.name), 'ShaderNodeMath',
                        (origin.x - 450, origin.y - 150 * index), f"Wrap {axis}")
        math.operation = WRAP_OPERATIONS[mode]
        math.use_clamp = mode == 'EXTEND'

        if mode == 'MIRROR':
            math.inputs[1].default_value = 1.0
        elif mode in ('EXTEND', 'CLIP'):
            math.inputs[1].default_value = 0.0

        link(tree, separate.outputs[index], math.inputs[0])
        link(tree, math.outputs[0], combine.inputs[index])

    link(tree, separate.outputs[2], combine.inputs[2])
    link(tree, combine.outputs[0], texture_node.inputs['Vector'])

    texture_node.extension = get_image_extension(slot.wrap_x, slot.wrap_y)

def mix_textures(tree, textures, prefix, bl_idname, output_name):
    """Chain the outputs of the textures through one mix node per extra texture, return the last output."""
    output = textures[0].outputs[output_name] if textures else None

    for index in range(1, MAX_TEXTURE_SLOTS):
        name = f"{prefix} {index}"

        if index >= len(textures):
            if name in tree.nodes:
                tree.nodes.remove(tree.nodes[name])
            continue

        texture = textures[index]
        mix = tree.nodes.get(name)

        # The blend mode is only set on creation, the one chosen in the shader editor is kept
        if mix is None or mix.bl_idname != bl_idname:
            location = (texture.location.x + 300, texture.location.y - (0 if output_name == 'Color' else 180))
            mix = get_node(tree, name, bl_idname, location, "Mix Color" if output_name == 'Color' else "Mix Alpha")

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

    if alpha is not None and any(texture.image.alpha_mode != 'NONE' for texture in textures):
        link(tree, alpha, target)
    else:
        unlink_from(tree, target, node_names)

def apply_material_textures(material):
    """Build the Image Texture, sampler and mix nodes of the shader graph from the texture slots."""
    if material is None or not hasattr(material, "level5_textures"):
        return

    if not material.use_nodes:
        material.use_nodes = True

    tree = material.node_tree

    if tree is None:
        return

    bsdf = find_bsdf(tree)
    origin = bsdf.location if bsdf is not None else (0, 0)
    slots = material.level5_textures.slots
    textures = []

    with suspend_updates():
        for index, slot in enumerate(slots):
            node = get_texture_node(material, slot)

            if node is None:
                if slot.image is None:
                    continue

                node = tree.nodes.new('ShaderNodeTexImage')
                node.name = new_texture_node_name(tree)
                node.location = (origin[0] - 700, origin[1] + 250 - 320 * index)
                slot.node_name = node.name

            if node.name.startswith(TEXTURE_NODE_PREFIX):
                node.label = f"Level 5 Texture {index + 1}"

            if node.image != slot.image:
                node.image = slot.image

            apply_texture_sampler(tree, node, slot)

            if slot.image is not None:
                textures.append(node)

        node_names = {slot.node_name for slot in slots if slot.node_name}

        # The nodes of the slots that were removed
        for node in list(tree.nodes):
            if node.type == 'TEX_IMAGE' and node.name.startswith(TEXTURE_NODE_PREFIX) and node.name not in node_names:
                remove_sampler_nodes(tree, node.name)
                tree.nodes.remove(node)

        wire_textures(tree, textures, node_names)

def remove_legacy_wrap_group(tree, texture_node):
    for old in list(texture_node.inputs['Vector'].links):
        group = old.from_node

        if group.type != 'GROUP' or group.node_tree is None or not group.node_tree.name.startswith(LEGACY_WRAP_GROUP_PREFIX):
            continue

        sources = [source_link.from_socket for source_link in group.inputs[0].links]
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
        values = {field: old.get(field, getattr(res.DEFAULT_SAMPLER, field)) for field in res.SamplerState._fields}
        res.sampler_to_properties(res.SamplerState(**values), slot)

    return slot

def adopt_material_textures(material):
    """Take the Image Texture nodes already in the shader graph as the texture slots of the material."""
    properties = material.level5_textures

    if properties.initialized or material.library is not None:
        return

    with suspend_updates():
        properties.initialized = True

        if material.node_tree is None:
            return

        for node in material.node_tree.nodes:
            if len(properties.slots) >= MAX_TEXTURE_SLOTS:
                break

            if node.type == 'TEX_IMAGE' and node.image is not None:
                remove_legacy_wrap_group(material.node_tree, node)
                add_node_slot(material, node)

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

    with suspend_updates():
        for index, slot in enumerate(properties.slots):
            if not slot.node_name:
                continue

            node = tree.nodes.get(slot.node_name)

            # The node was deleted, so is its texture
            if node is None or node.type != 'TEX_IMAGE':
                removed.append(index)
            elif node.image != slot.image:
                rewire = True
                slot.image = node.image

        for index in reversed(removed):
            properties.slots.remove(index)

        # An Image Texture node added in the shader editor becomes a slot as soon as it has an image
        node_names = {slot.node_name for slot in properties.slots}

        for node in tree.nodes:
            if len(properties.slots) >= MAX_TEXTURE_SLOTS:
                break

            if node.type == 'TEX_IMAGE' and node.image is not None and node.name not in node_names:
                add_node_slot(material, node)

    if rewire or removed:
        apply_material_textures(material)

@persistent
def sync_textures_from_nodes(scene, depsgraph=None):
    if _suspended:
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
def adopt_textures_on_load(_dummy=None):
    adopt_all_materials()

##########################################
# Operators
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

        if not 0 <= self.index < len(slots):
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
        target = self.index - 1 if self.direction == 'UP' else self.index + 1

        if not (0 <= self.index < len(slots) and 0 <= target < len(slots)):
            return {'CANCELLED'}

        slots.move(self.index, target)
        apply_material_textures(material)

        return {'FINISHED'}

##########################################
# Panel
##########################################

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

        if not slots:
            layout.label(text="No texture, the material is exported without any", icon='INFO')
            return

        for index, slot in enumerate(slots):
            self.draw_slot(layout, index, slot, len(slots))

    def draw_slot(self, layout, index, slot, count):
        box = layout.box()
        header = box.row(align=True)

        if slot.image is not None:
            header.prop(slot, "show_expanded", text="", emboss=False,
                        icon='TRIA_DOWN' if slot.show_expanded else 'TRIA_RIGHT')
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

        if index > 0 and slot.texture_mode in res.UNIT_0_TEXTURE_MODES:
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
