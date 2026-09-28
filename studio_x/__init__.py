"""Studio X: import Unity asset bundles (models, textures, bone/UV/material animations, cameras)
in the Studio Eleven formats. Requires the Studio Eleven addon."""

bl_info = {
    "name": "Studio X",
    "category": "Import-Export",
    "description": "Import Unity asset bundles as Studio Eleven compatible models, animations and cameras",
    "author": "Tinifan",
    "version": (1, 3, 0),
    "blender": (2, 80, 2),
    "location": "File > Import > Studio X, 3D View > Sidebar > Studio X",
    "warning": "Requires the Studio Eleven addon",
    "doc_url": "",
    "support": "COMMUNITY",
}

from .blender import operators, panel


def register():
    panel.register()
    operators.register()


def unregister():
    operators.unregister()
    panel.unregister()
