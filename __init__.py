import bpy
import pip

from .operators import *

# Only for Debug Mod (Press F8 to reload blender addon)    
if "fileio_xmpr" in locals():
    importlib.reload(fileio_xmpr) 
    importlib.reload(xmpr)
    
if "fileio_xmtn" in locals():
    importlib.reload(fileio_xmtn) 
    importlib.reload(xmtn)

if "fileio_xpck" in locals():
    importlib.reload(fileio_xpck) 
    importlib.reload(xpck)  
    importlib.reload(imgc)
    importlib.reload(mbn)
    importlib.reload(res)

bl_info = {
    "name": "Level 5 Lib For Blender",
    "category": "Import-Export",
    "description": "Support some Level 5 files for Blender",
    "author": "Tinifan",
    "version": (1, 0, 0),
    "blender": (2, 80, 2),
    "location": "File > Import-Export > Level 5", 
    "warning": "",
    "doc_url": "",
    "support": 'COMMUNITY',
}

class Level5_Menu(bpy.types.Menu):
    bl_label = "Level 5"
    bl_idname = "TOPBAR_MT_file_level5"

    def draw(self, context):
        layout = self.layout
        layout.operator(ExportMTN2.bl_idname, text="Animation (MTN2 File)", icon="POSE_HLT")
        layout.operator(ExportPRM.bl_idname, text="Mesh (PRM File)", icon="POSE_HLT")
        layout.operator(ExportXC.bl_idname, text="Model (XPCK Archive)", icon="POSE_HLT")
    
def draw_menu(self, context):
    self.layout.menu(Level5_Menu.bl_idname)

def register():
    bpy.utils.register_class(LibraryCollectionProperty)
    bpy.utils.register_class(ExportMTN2)
    bpy.utils.register_class(ExportXC)
    bpy.utils.register_class(ExportPRM)   
    bpy.utils.register_class(Level5_Menu)
    bpy.types.TOPBAR_MT_file_export.append(draw_menu)


def unregister():
    bpy.utils.unregister_class(ExportMTN2)
    bpy.utils.unregister_class(ExportXC)
    bpy.utils.unregister_class(ExportPRM)
    bpy.utils.unregister_class(Level5_Menu)
    bpy.utils.unregister_class(LibraryCollectionProperty)
    bpy.types.TOPBAR_MT_file_export.remove(draw_menu)    

if __name__ == "__main__":
    register()