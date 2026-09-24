import bpy
from bpy.props import EnumProperty

from ...compression import compressor

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

##########################################
# Register class
##########################################

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

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "default_compression")

##########################################
# Register
##########################################

def register_addon_settings():
    bpy.utils.register_class(StudioElevenSettings)

    # The saved preferences are loaded with the addon, give their compression to the compressor
    settings = get_addon_settings(bpy.context)

    if settings is not None:
        update_default_compression(settings, bpy.context)

def unregister_addon_settings():
    compressor.set_default_compression(compressor.BEST_COMPRESSION)

    bpy.utils.unregister_class(StudioElevenSettings)
