import bpy
import hashlib
from bpy.props import BoolProperty, EnumProperty, StringProperty

from ...compression import compressor
from ...rendering import project as rendering_project, game_setup

##########################################
# CONST
##########################################

# The addon package, the preferences are registered under its name
ADDON_NAME = __package__.rsplit(".", 2)[0]

COMPRESSION_ENUM_TO_INT = {
    'BEST': compressor.BEST_COMPRESSION,
    'NONE': compressor.NO_COMPRESSION,
    'LZ10': compressor.LZ10,
    'HUFFMAN_4': compressor.HUFFMAN_4,
    'HUFFMAN_8': compressor.HUFFMAN_8,
    'RLE': compressor.RLE,
}

# Only the hash of the password that unlocks StudioRender is kept
STUDIO_RENDER_PASSWORD_HASH = "9a9c1dab6bcc217432d2a7adfd52cc1ca8222a3a5722b5af5a52341412c3b891"

##########################################
# Settings Function
##########################################

def get_addon_settings(context):
    addon = context.preferences.addons.get(ADDON_NAME)

    if addon is None:
        return None

    return addon.preferences

def update_default_compression(self, context):
    compressor.set_default_compression(COMPRESSION_ENUM_TO_INT[self.default_compression])

def set_studio_render(enabled):
    """Register the StudioRender engine, or remove it (the scenes that render with it go back to Eevee)."""
    from ...rendering import studio_render
    from ...rendering.studio_render import engine

    registered = engine.StudioRenderEngine.is_registered

    if enabled and not registered:
        studio_render.register()
    elif not enabled and registered:
        # bpy.data is restricted while the addon registers or unregisters
        for scene in getattr(bpy.data, "scenes", []):
            if scene.render.engine == studio_render.ENGINE_ID:
                scene.render.engine = 'BLENDER_EEVEE'

        studio_render.unregister()

def update_studio_render(self, context):
    set_studio_render(self.studio_render_unlocked and self.studio_render_enabled)

    # Without StudioRender the scenes go back to the game engine of their template
    rendering_project.sync_scene_engines()

##########################################
# Register class
##########################################

class UnlockStudioRender(bpy.types.Operator):
    bl_idname = "studio_eleven.unlock_studio_render"
    bl_label = "Confirm"
    bl_description = "Unlock the options in beta with the password"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        settings = get_addon_settings(context)

        if settings is None:
            return {'CANCELLED'}

        password = settings.studio_render_password
        settings.studio_render_password = ""

        if hashlib.sha256(password.encode("utf-8")).hexdigest() != STUDIO_RENDER_PASSWORD_HASH:
            self.report({'ERROR'}, "Wrong password")
            return {'CANCELLED'}

        settings.studio_render_unlocked = True
        self.report({'INFO'}, "StudioRender unlocked")

        return {'FINISHED'}

class StudioElevenSettings(bpy.types.AddonPreferences):
    bl_idname = ADDON_NAME

    default_compression: EnumProperty(
        name="Default Compression",
        description="Compression of the blocks of the exported files",
        items=[
            ('BEST', "Use the best compression", "Pick for every block the compression that makes it the smallest, without compressing it with each one"),
            ('NONE', "No compression", "Store the blocks as they are"),
            ('HUFFMAN_4', "Huffman 4 bit", "Huffman code on the 4 bit halves of the bytes"),
            ('HUFFMAN_8', "Huffman 8 bit", "Huffman code on the bytes"),
            ('LZ10', "LZ10", "Replace the repeated bytes with a reference to their previous copy"),
            ('RLE', "RLE", "Replace the runs of a same byte with the byte and its count"),
        ],
        default='BEST',
        update=update_default_compression
    )

    studio_render_password: StringProperty(
        name="Password",
        description="Password of the options in beta",
        default="",
        subtype='PASSWORD',
        options={'SKIP_SAVE'}
    )

    studio_render_unlocked: BoolProperty(
        name="StudioRender Unlocked",
        default=False,
        options={'HIDDEN'}
    )

    studio_render_enabled: BoolProperty(
        name="Enable StudioRender",
        description="Render the scenes like the games do with the StudioRender engine and choose the game engine of a blend "
                    "among the installed games, the template of the blend isn't used anymore",
        default=False,
        update=update_studio_render
    )

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "default_compression")

        if not self.studio_render_unlocked:
            row = layout.row(align=True)
            row.prop(self, "studio_render_password")
            row.operator("studio_eleven.unlock_studio_render")
            return

        layout.prop(self, "studio_render_enabled")

        if self.studio_render_enabled:
            game_setup.draw_game_engines(layout)

##########################################
# Register
##########################################

def register_addon_settings():
    bpy.utils.register_class(UnlockStudioRender)
    bpy.utils.register_class(StudioElevenSettings)

    # The saved preferences are loaded with the addon, give their compression to the compressor
    settings = get_addon_settings(bpy.context)

    if settings is not None:
        update_default_compression(settings, bpy.context)

        if settings.studio_render_unlocked and settings.studio_render_enabled:
            set_studio_render(True)

def unregister_addon_settings():
    compressor.set_default_compression(compressor.BEST_COMPRESSION)

    set_studio_render(False)

    bpy.utils.unregister_class(StudioElevenSettings)
    bpy.utils.unregister_class(UnlockStudioRender)
