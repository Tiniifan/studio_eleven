import re
import bpy

from bpy.app.handlers import persistent
from bpy.types import PropertyGroup, Panel, UIList
from bpy.props import BoolProperty, BoolVectorProperty, FloatProperty, IntProperty, StringProperty, FloatVectorProperty, CollectionProperty, PointerProperty, EnumProperty

from .operators import *
from .controls import *
from .formats import atr, res

# Only for Debug Mod (Press F8 to reload blender addon) 
if "fileio_xcma" in locals():
    importlib.reload(fileio_xcma) 
    importlib.reload(xcma)
    
if "fileio_xmpr" in locals():
    importlib.reload(fileio_xmpr) 
    importlib.reload(xmpr)
    
if "fileio_animation_manager" in locals():
    importlib.reload(fileio_animation_manager) 
    importlib.reload(animation_manager)

if "fileio_xpck" in locals():
    importlib.reload(xpck_settings)
    importlib.reload(fileio_xpck) 
    importlib.reload(xpck)  
    importlib.reload(imgc)
    importlib.reload(mbn)
    importlib.reload(res)
    importlib.reload(minf)
    importlib.reload(xcmt)
    importlib.reload(atr)

bl_info = {
    "name": "Studio Eleven",
    "category": "Import-Export",
    "description": "Support some Level 5 files for Blender",
    "author": "Tinifan",
    "version": (1, 3, 0),
    "blender": (2, 80, 2),
    "location": "File > Import-Export > Studio Eleven", 
    "warning": "",
    "doc_url": "",
    "support": 'COMMUNITY',
}

class Level5MeshProperties(bpy.types.PropertyGroup):
    draw_priority: IntProperty(
        name="Draw Priority",
        description="Priority used for drawing the mesh",
        default=0,
        min=0,
        max=65535
    )
    
    mesh_type: EnumProperty(
        name="Mesh Type",
        description="Type of the mesh",
        items=[
            ('UNK',       "Unk",       "Unknown mesh type"),
            ('MODEL',     "Model",     "Model mesh"),
            ('COLLISION', "Collision", "Collision mesh"),
        ],
        default='MODEL'
    )

class Level5_Panel(bpy.types.Panel):
    bl_label = "Level 5"
    bl_idname = "MESH_PT_level5_draw_priority_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return context.mesh is not None

    def draw(self, context):
        layout = self.layout
        mesh = context.mesh
        if hasattr(mesh, "level5_properties"):
            layout.prop(mesh.level5_properties, "draw_priority")
            layout.prop(mesh.level5_properties, "mesh_type")
        else:
            layout.label(text="No Level 5 properties found.")

INHERIT_NUMBER_DESCRIPTION = ("Set it to -1 to leave the setting out of the file, the game then keeps whatever "
                             "the mesh drawn before was using")

def get_render_mode(self):
    return atr.RENDER_MODE_INDEX.get(atr.detect_render_mode(self), 0)

def set_render_mode(self, value):
    name = atr.RENDER_MODES[value] if 0 <= value < len(atr.RENDER_MODES) else 'OPAQUE'
    atr.apply_render_mode(self, name)

def get_double_sided(self):
    return self.cull == 'OFF'

def set_double_sided(self, value):
    self.cull = 'OFF' if value else 'ON'

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
        items=atr.RENDER_MODE_ITEMS,
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
        items=atr.BOOL_ITEMS,
        default=atr.PROPERTY_DEFAULTS["cull"]
    )

    depth_test: EnumProperty(
        name="Depth Test",
        description="Check how far each pixel is from the camera before drawing it, so that nearer meshes properly "
                    "hide the ones behind them. Turning it off makes the material draw over everything else, which "
                    "is mostly useful for interface elements",
        items=atr.BOOL_ITEMS,
        default=atr.PROPERTY_DEFAULTS["depth_test"]
    )

    depth_write: EnumProperty(
        name="Depth Write",
        description="Whether this material records its own distance from the camera, so that meshes drawn later "
                    "know it is in front of them. Turn it off for see-through materials such as glass or effects, "
                    "otherwise they hide whatever is drawn behind them afterwards",
        items=atr.BOOL_ITEMS,
        default=atr.PROPERTY_DEFAULTS["depth_write"]
    )

    depth_func: EnumProperty(
        name="Depth Comparison",
        description="The test a pixel has to pass against the distance already recorded to be drawn. Less means "
                    "\"only draw it if it is nearer than what is already there\", which is the usual choice",
        items=atr.COMPARE_FUNCTION_ITEMS,
        default=atr.PROPERTY_DEFAULTS["depth_func"]
    )

    alpha_test: EnumProperty(
        name="Alpha Test",
        description="Throw away the pixels that are more transparent than the reference below, instead of mixing "
                    "them with the background. Use it for leaves, fences or hair, where you want hard holes rather "
                    "than a soft fade",
        items=atr.BOOL_ITEMS,
        default=atr.PROPERTY_DEFAULTS["alpha_test"]
    )

    alpha_func: EnumProperty(
        name="Alpha Comparison",
        description="How the transparency of a pixel is compared to the reference below to decide whether to keep "
                    "it. Greater keeps the pixels more opaque than the reference. Always keeps everything, which "
                    "turns the test off",
        items=atr.COMPARE_FUNCTION_ITEMS,
        default=atr.PROPERTY_DEFAULTS["alpha_func"]
    )

    alpha_ref: FloatProperty(
        name="Alpha Reference",
        description="The transparency the alpha test compares each pixel against, from 0 (fully transparent) to 1 "
                    "(fully opaque). " + INHERIT_NUMBER_DESCRIPTION,
        default=atr.PROPERTY_DEFAULTS["alpha_ref"],
        min=-1.0,
        max=1.0
    )

    blend: EnumProperty(
        name="Blending",
        description="Mix the color of this material with what is already drawn behind it instead of replacing it. "
                    "This is what makes transparency, glow and similar effects possible. The equation and the "
                    "factors below decide exactly how the two colors are combined",
        items=atr.BOOL_ITEMS,
        default=atr.PROPERTY_DEFAULTS["blend"]
    )

    blend_rgb_equation: EnumProperty(
        name="RGB Equation",
        description="How the color of this material and the color already on screen are put together once each has "
                    "been multiplied by its factor below. Add sums them, which is what nearly every material uses",
        items=atr.BLEND_EQUATION_ITEMS,
        default=atr.PROPERTY_DEFAULTS["blend_rgb_equation"]
    )

    blend_rgb_source: EnumProperty(
        name="RGB Source Factor",
        description="What the color of this material is multiplied by before being combined. One keeps it as it is "
                    "(solid material), Src Alpha scales it by its own transparency (see-through material)",
        items=atr.BLEND_FACTOR_ITEMS,
        default=atr.PROPERTY_DEFAULTS["blend_rgb_source"]
    )

    blend_rgb_destination: EnumProperty(
        name="RGB Destination Factor",
        description="What the color already on screen is multiplied by before being combined. Zero erases it, so "
                    "the material looks solid. One Minus Src Alpha keeps the part this material doesn't cover, "
                    "which is how normal transparency works. One adds on top of it, which is how glow works",
        items=atr.BLEND_FACTOR_ITEMS,
        default=atr.PROPERTY_DEFAULTS["blend_rgb_destination"]
    )

    blend_alpha_equation: EnumProperty(
        name="Alpha Equation",
        description="Same as the RGB equation, but for the transparency channel instead of the color. It decides "
                    "how transparent the screen becomes where this material is drawn",
        items=atr.BLEND_EQUATION_ITEMS,
        default=atr.PROPERTY_DEFAULTS["blend_alpha_equation"]
    )

    blend_alpha_source: EnumProperty(
        name="Alpha Source Factor",
        description="What the transparency of this material is multiplied by before being combined",
        items=atr.BLEND_FACTOR_ITEMS,
        default=atr.PROPERTY_DEFAULTS["blend_alpha_source"]
    )

    blend_alpha_destination: EnumProperty(
        name="Alpha Destination Factor",
        description="What the transparency already on screen is multiplied by before being combined",
        items=atr.BLEND_FACTOR_ITEMS,
        default=atr.PROPERTY_DEFAULTS["blend_alpha_destination"]
    )

    # The engine applies the four channels together or not at all
    color_mask_override: BoolProperty(
        name="Color Mask",
        description="Choose which of the red, green, blue and transparency channels this material is allowed to "
                    "draw, the four of them being applied together. Turning all four off draws the mesh into the "
                    "depth buffer only, which makes it an invisible wall that hides what is behind it",
        default=atr.PROPERTY_DEFAULTS["color_mask_override"]
    )

    color_mask: BoolVectorProperty(
        name="Channels",
        description="Red, green, blue and transparency channels this material is allowed to draw",
        size=4,
        default=atr.PROPERTY_DEFAULTS["color_mask"],
        subtype='NONE'
    )

    depth_bias_enable: EnumProperty(
        name="Depth Bias",
        description="Push the material slightly towards the camera when it is compared to the others. Use it on a "
                    "surface lying exactly on another one, like a decal, a shadow or a marking painted on the "
                    "ground, to stop the two from flickering against each other",
        items=atr.BOOL_ITEMS,
        default=atr.PROPERTY_DEFAULTS["depth_bias_enable"]
    )

    depth_bias: FloatProperty(
        name="Depth Bias Value",
        description="How far the material is pushed towards the camera. Small values are enough, raise it only "
                    "until the flickering stops. " + INHERIT_NUMBER_DESCRIPTION,
        default=atr.PROPERTY_DEFAULTS["depth_bias"],
        min=-1.0
    )

    stencil_test: EnumProperty(
        name="Stencil Test",
        description="The stencil buffer is a scratch pad where a mesh can leave a mark so that the meshes drawn "
                    "afterwards only appear inside or outside that mark. It is used for masks, mirrors and "
                    "portal-like effects",
        items=atr.BOOL_ITEMS,
        default=atr.PROPERTY_DEFAULTS["stencil_test"]
    )

    stencil_func: EnumProperty(
        name="Stencil Comparison",
        description="How the mark already in the stencil buffer is compared to the reference below to decide "
                    "whether the pixel is drawn. Always passes everywhere, which turns the test off",
        items=atr.COMPARE_FUNCTION_ITEMS,
        default=atr.PROPERTY_DEFAULTS["stencil_func"]
    )

    stencil_ref: IntProperty(
        name="Stencil Reference",
        description="The value the stencil buffer is compared against, and the mark written into it when the "
                    "operations below ask to replace it. " + INHERIT_NUMBER_DESCRIPTION,
        default=atr.PROPERTY_DEFAULTS["stencil_ref"],
        min=-1,
        max=1023
    )

    stencil_compare_mask: IntProperty(
        name="Stencil Compare Mask",
        description="Which bits of the stencil buffer the comparison looks at, the other ones are ignored. "
                    + INHERIT_NUMBER_DESCRIPTION,
        default=atr.PROPERTY_DEFAULTS["stencil_compare_mask"],
        min=-1,
        max=255
    )

    stencil_write_mask: IntProperty(
        name="Stencil Write Mask",
        description="Which bits of the stencil buffer this material is allowed to change. "
                    + INHERIT_NUMBER_DESCRIPTION,
        default=atr.PROPERTY_DEFAULTS["stencil_write_mask"],
        min=-1,
        max=15
    )

    # The meaning of the stencil operation values is undocumented, they stay raw numbers
    stencil_fail_op: IntProperty(
        name="Fail Operation",
        description="What happens to the stencil buffer when a pixel fails the stencil test. What each number "
                    "means is undocumented, so this is mostly there to export an imported material unchanged. "
                    + INHERIT_NUMBER_DESCRIPTION,
        default=atr.PROPERTY_DEFAULTS["stencil_fail_op"],
        min=-1,
        max=255
    )

    stencil_zfail_op: IntProperty(
        name="Depth Fail Operation",
        description="What happens to the stencil buffer when a pixel passes the stencil test but fails the depth "
                    "test. What each number means is undocumented, so this is mostly there to export an imported "
                    "material unchanged. " + INHERIT_NUMBER_DESCRIPTION,
        default=atr.PROPERTY_DEFAULTS["stencil_zfail_op"],
        min=-1,
        max=255
    )

    stencil_zpass_op: IntProperty(
        name="Depth Pass Operation",
        description="What happens to the stencil buffer when a pixel passes both the stencil and the depth test. "
                    "What each number means is undocumented, so this is mostly there to export an imported "
                    "material unchanged. " + INHERIT_NUMBER_DESCRIPTION,
        default=atr.PROPERTY_DEFAULTS["stencil_zpass_op"],
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
        layout = self.layout
        material = context.material

        if not hasattr(material, "level5_atr"):
            layout.label(text="No Level 5 properties found.")
            return

        properties = material.level5_atr

        box = layout.box()
        box.label(text="Material Render:")
        box.prop(properties, "panel_mode", expand=True)

        if properties.panel_mode == 'SIMPLE':
            box.prop(properties, "render_mode")
            box.prop(properties, "double_sided")

            if properties.render_mode == 'CUTOUT':
                box.prop(properties, "alpha_cutoff")

            return

        group = box.box()
        group.label(text="Culling & Depth:")
        group.prop(properties, "cull")
        group.prop(properties, "depth_test")
        group.prop(properties, "depth_write")
        group.prop(properties, "depth_func")

        group = box.box()
        group.label(text="Alpha Test:")
        group.prop(properties, "alpha_test")
        group.prop(properties, "alpha_func")
        group.prop(properties, "alpha_ref")

        group = box.box()
        group.label(text="Blending:")
        group.prop(properties, "blend")
        group.prop(properties, "blend_rgb_equation")
        group.prop(properties, "blend_rgb_source")
        group.prop(properties, "blend_rgb_destination")
        group.prop(properties, "blend_alpha_equation")
        group.prop(properties, "blend_alpha_source")
        group.prop(properties, "blend_alpha_destination")

        group = box.box()
        group.label(text="Color Mask:")
        group.prop(properties, "color_mask_override", text="Write Color Mask")

        if properties.color_mask_override:
            row = group.row(align=True)
            for index, channel in enumerate("RGBA"):
                row.prop(properties, "color_mask", index=index, text=channel, toggle=True)

        group = box.box()
        group.label(text="Advanced:")
        group.label(text="These additional options only apply to games using the V2 render format.", icon='INFO')
        group.prop(properties, "depth_bias_enable")
        group.prop(properties, "depth_bias")
        group.prop(properties, "stencil_test")
        group.prop(properties, "stencil_func")
        group.prop(properties, "stencil_ref")
        group.prop(properties, "stencil_compare_mask")
        group.prop(properties, "stencil_write_mask")
        group.prop(properties, "stencil_fail_op")
        group.prop(properties, "stencil_zfail_op")
        group.prop(properties, "stencil_zpass_op")

def update_sampler_preview(self, context):
    refresh_sampler_preview(self.id_data)

class Level5TextureProperties(bpy.types.PropertyGroup):
    wrap_s: EnumProperty(
        name="Wrap X",
        description="What is drawn left and right of the texture, once the UVs go past its edge",
        items=res.WRAP_ITEMS,
        default='REPEAT',
        update=update_sampler_preview
    )

    wrap_t: EnumProperty(
        name="Wrap Y",
        description="What is drawn above and below the texture, once the UVs go past its edge",
        items=res.WRAP_ITEMS,
        default='REPEAT',
        update=update_sampler_preview
    )

    mag_filter: EnumProperty(
        name="Magnification",
        description="How the texture is sampled when it is drawn bigger than it really is, up close",
        items=res.FILTER_ITEMS,
        default='LINEAR',
        update=update_sampler_preview
    )

    min_filter: EnumProperty(
        name="Minification",
        description="How the texture is sampled when it is drawn smaller than it really is, far away",
        items=res.FILTER_ITEMS,
        default='LINEAR',
        update=update_sampler_preview
    )

    mip_filter: EnumProperty(
        name="Mipmap",
        description="How the smaller copies of the texture the game switches to with the distance are mixed. "
                    "Linear fades from one to the next, Nearest jumps straight to it",
        items=res.FILTER_ITEMS,
        default='NEAREST',
        update=update_sampler_preview
    )

class Level5_Texture_Panel(bpy.types.Panel):
    bl_label = "Level 5"
    bl_idname = "NODE_PT_level5_texture_panel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Item"

    @classmethod
    def poll(cls, context):
        if context.space_data is None or context.space_data.tree_type != 'ShaderNodeTree':
            return False

        node = context.active_node

        return node is not None and node.type == 'TEX_IMAGE' and node.image is not None

    def draw(self, context):
        layout = self.layout
        image = context.active_node.image

        if not hasattr(image, "level5_texture"):
            layout.label(text="No Level 5 properties found.")
            return

        properties = image.level5_texture

        box = layout.box()
        box.label(text="Wrap:")
        box.prop(properties, "wrap_s")
        box.prop(properties, "wrap_t")

        box = layout.box()
        box.label(text="Filter:")
        box.prop(properties, "mag_filter")
        box.prop(properties, "min_filter")
        box.prop(properties, "mip_filter")

class Level5_Menu_Export(bpy.types.Menu):
    bl_label = "Studio Eleven (.mtn, .mtm, .imm, .prm, .xc, .cmr2)"
    bl_idname = "TOPBAR_MT_file_level5_export"

    def draw(self, context):
        layout = self.layout
        layout.operator(ExportAnimation.bl_idname, text="Animation (xmtn, xmtm, xima)", icon="POSE_HLT")
        layout.operator(ExportXPRM.bl_idname, text="Mesh (xprm)", icon="MESH_DATA")
        layout.operator(ExportXC.bl_idname, text="Archive (xpck)", icon="FILE_3D")
        layout.operator(ExportXCMA.bl_idname, text="Camera (xcma)", icon="OUTLINER_OB_CAMERA")
        
class Level5_Menu_Import(bpy.types.Menu):
    bl_label = "Studio Eleven (.mtn, .prm, .xc, .cmr2)"
    bl_idname = "TOPBAR_MT_file_level5_import"

    def draw(self, context):
        layout = self.layout
        layout.operator(ImportAnimation.bl_idname, text="Animation (xmtn, xmtm, xima)", icon="POSE_HLT")
        layout.operator(ImportXMPR.bl_idname, text="Mesh (xprm)", icon="MESH_DATA")
        layout.operator(ImportXC.bl_idname, text="Archive (xpck)", icon="FILE_3D")  
        layout.operator(ImportXCMA.bl_idname, text="Camera (xcma)", icon="OUTLINER_OB_CAMERA")
    
def draw_menu_export(self, context):
    self.layout.menu(Level5_Menu_Export.bl_idname)
    
def draw_menu_import(self, context):
    self.layout.menu(Level5_Menu_Import.bl_idname)    

def register():
    # Level 5 Menu Export
    bpy.utils.register_class(BoneCheckbox)
    bpy.utils.register_class(TexturePropertyGroup)
    bpy.utils.register_class(LibPropertyGroup)
    bpy.utils.register_class(MeshPropertyGroup)
    bpy.utils.register_class(ArchivePropertyGroup)
    bpy.utils.register_class(TexprojPropertyGroup)
    
    # XPCK export settings saved on objects
    register_settings()
    
    bpy.utils.register_class(ExportAnimation)
    bpy.utils.register_class(ExportXC)
    bpy.utils.register_class(ExportXPRM)
    bpy.utils.register_class(ExportXCMA) 
    bpy.utils.register_class(Level5_Menu_Export)
    bpy.types.TOPBAR_MT_file_export.append(draw_menu_export)
    
    # Level 5 Menu Import
    bpy.utils.register_class(ImportAnimation)
    bpy.utils.register_class(ImportAnimationChoice)
    bpy.utils.register_class(ImportXC_ChooseAnimations)
    bpy.utils.register_class(ImportXC)
    bpy.utils.register_class(ImportXMPR)
    bpy.utils.register_class(ImportXCMA)
    bpy.utils.register_class(Level5_Menu_Import)
    bpy.types.TOPBAR_MT_file_import.append(draw_menu_import)
    
    # Level 5 Panel
    bpy.utils.register_class(Level5MeshProperties)
    bpy.utils.register_class(Level5_Panel)
    bpy.types.Mesh.level5_properties = bpy.props.PointerProperty(type=Level5MeshProperties)

    # Level 5 Material Panel
    bpy.utils.register_class(Level5MaterialProperties)
    bpy.utils.register_class(Level5_Material_Panel)
    bpy.types.Material.level5_atr = bpy.props.PointerProperty(type=Level5MaterialProperties)

    # Level 5 Texture Panel
    bpy.utils.register_class(Level5TextureProperties)
    bpy.utils.register_class(Level5_Texture_Panel)
    bpy.types.Image.level5_texture = bpy.props.PointerProperty(type=Level5TextureProperties)

    # Auto Collision Generator
    bpy.utils.register_class(OBJECT_OT_CreateFloorCollision)
    bpy.utils.register_class(OBJECT_OT_CreateWallCollision)
    bpy.types.VIEW3D_MT_object_context_menu.append(auto_collision_menu_func)

def unregister():
    # Level 5 Menu Export
    bpy.utils.unregister_class(BoneCheckbox)
    bpy.utils.unregister_class(ExportAnimation)
    bpy.utils.unregister_class(ExportXC)
    bpy.utils.unregister_class(ExportXPRM)
    bpy.utils.unregister_class(ExportXCMA)
    bpy.utils.unregister_class(Level5_Menu_Export)
    bpy.utils.unregister_class(TexturePropertyGroup)
    bpy.utils.unregister_class(LibPropertyGroup)
    bpy.utils.unregister_class(MeshPropertyGroup)
    bpy.utils.unregister_class(TexprojPropertyGroup)
    bpy.utils.unregister_class(ArchivePropertyGroup)
    
    unregister_settings()
    
    bpy.types.TOPBAR_MT_file_export.remove(draw_menu_export)
    
    # Level 5 Menu Import
    bpy.utils.unregister_class(ImportAnimation)
    bpy.utils.unregister_class(ImportXC)
    bpy.utils.unregister_class(ImportXC_ChooseAnimations)
    bpy.utils.unregister_class(ImportAnimationChoice)
    bpy.utils.unregister_class(ImportXMPR)
    bpy.utils.unregister_class(ImportXCMA)
    bpy.utils.unregister_class(Level5_Menu_Import)      
    bpy.types.TOPBAR_MT_file_import.remove(draw_menu_import)
    
    # Level 5 Panel
    bpy.utils.unregister_class(Level5_Panel)
    bpy.utils.unregister_class(Level5MeshProperties)
    del bpy.types.Mesh.level5_properties

    # Level 5 Material Panel
    bpy.utils.unregister_class(Level5_Material_Panel)
    bpy.utils.unregister_class(Level5MaterialProperties)
    del bpy.types.Material.level5_atr

    # Level 5 Texture Panel
    bpy.utils.unregister_class(Level5_Texture_Panel)
    bpy.utils.unregister_class(Level5TextureProperties)
    del bpy.types.Image.level5_texture

    # Auto Collision Generator
    bpy.utils.unregister_class(OBJECT_OT_CreateFloorCollision)
    bpy.utils.unregister_class(OBJECT_OT_CreateWallCollision)
    bpy.types.VIEW3D_MT_object_context_menu.remove(auto_collision_menu_func)

if __name__ == "__main__":
    register()