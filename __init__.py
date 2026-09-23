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

def register():
    # Import-Export
    register_settings()
    register_animation_manager()
    register_xmpr()
    register_xcma()
    register_xpck()
    register_menus()

    # Level 5 Mesh Panel
    register_mesh_properties()

    # Level 5 Material Panel
    register_material_render()

    # Level 5 Textures Panel (a sub panel of the Material Panel)
    register_material_textures()

    # Studio Eleven Tools Panel
    register_panel_tools()

    # Auto Collision Generator
    register_auto_collision()

def unregister():
    # Auto Collision Generator
    unregister_auto_collision()

    # Studio Eleven Tools Panel
    unregister_panel_tools()

    # Level 5 Textures Panel (before its parent panel)
    unregister_material_textures()

    # Level 5 Material Panel
    unregister_material_render()

    # Level 5 Mesh Panel
    unregister_mesh_properties()

    # Import-Export
    unregister_menus()
    unregister_xpck()
    unregister_xcma()
    unregister_xmpr()
    unregister_animation_manager()
    unregister_settings()

if __name__ == "__main__":
    register()