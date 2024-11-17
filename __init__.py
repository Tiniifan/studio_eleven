import bpy
import pip

from .operators import *
from .controls import *

# Only for Debug Mod (Press F8 to reload blender addon) 
if "fileio_xcma" in locals():
    importlib.reload(fileio_xcma) 
    importlib.reload(xcma)
    
if "fileio_xmpr" in locals():
    importlib.reload(fileio_xmpr) 
    importlib.reload(xmpr)
    
if "fileio_xmtn" in locals():
    importlib.reload(fileio_xmtn) 
    importlib.reload(animation_manager)

if "fileio_xpck" in locals():
    importlib.reload(fileio_xpck) 
    importlib.reload(xpck)  
    importlib.reload(imgc)
    importlib.reload(mbn)
    importlib.reload(res)
    importlib.reload(minf)

bl_info = {
    "name": "Studio Eleven",
    "category": "Import-Export",
    "description": "Support some Level 5 files for Blender",
    "author": "Tinifan",
    "version": (1, 1, 0),
    "blender": (2, 80, 2),
    "location": "File > Import-Export > Studio Eleven", 
    "warning": "",
    "doc_url": "",
    "support": 'COMMUNITY',
}

class Level5_Menu_Export(bpy.types.Menu):
    bl_label = "Studio Eleven (.mtn, .prm, .xc, .cmr2)"
    bl_idname = "TOPBAR_MT_file_level5_export"

    def draw(self, context):
        layout = self.layout
        layout.operator(ExportXMTN.bl_idname, text="Animation (xmtn)", icon="POSE_HLT")
        layout.operator(ExportXPRM.bl_idname, text="Mesh (xprm)", icon="MESH_DATA")
        layout.operator(ExportXC.bl_idname, text="Archive (xpck)", icon="FILE_3D")
        layout.operator(ExportXCMA.bl_idname, text="Camera (xcma)", icon="OUTLINER_OB_CAMERA")
        
class Level5_Menu_Import(bpy.types.Menu):
    bl_label = "Studio Eleven (.mtn, .prm, .xc, .cmr2)"
    bl_idname = "TOPBAR_MT_file_level5_import"

    def draw(self, context):
        layout = self.layout
        layout.operator(ImportXMTN.bl_idname, text="Animation (xmtn)", icon="POSE_HLT")
        layout.operator(ImportXMPR.bl_idname, text="Mesh (xprm)", icon="MESH_DATA")
        layout.operator(ImportXC.bl_idname, text="Archive (xpck)", icon="FILE_3D")  
        layout.operator(ImportXCMA.bl_idname, text="Camera (xcma)", icon="OUTLINER_OB_CAMERA")
    
def draw_menu_export(self, context):
    self.layout.menu(Level5_Menu_Export.bl_idname)
    
def draw_menu_import(self, context):
    self.layout.menu(Level5_Menu_Import.bl_idname)    

def register():
    bpy.utils.register_class(ExportXC_AddAnimationItem)
    bpy.utils.register_class(ExportXC_RemoveAnimationItem)
    bpy.utils.register_class(AnimationItem)
    bpy.utils.register_class(TexturePropertyGroup)
    bpy.utils.register_class(LibPropertyGroup)
    bpy.utils.register_class(MeshPropertyGroup)
    bpy.utils.register_class(TexprojPropertyGroup)
    bpy.utils.register_class(CameraPropertyGroup)
    bpy.utils.register_class(ArchivePropertyGroup)
    bpy.types.Scene.export_xc_animations_items = bpy.props.CollectionProperty(type=AnimationItem)
    bpy.utils.register_class(ExportXMTN)
    bpy.utils.register_class(ExportXC)
    bpy.utils.register_class(ExportXPRM)
    bpy.utils.register_class(ExportXCMA) 
    bpy.utils.register_class(Level5_Menu_Export)
    bpy.types.TOPBAR_MT_file_export.append(draw_menu_export)
    
    bpy.utils.register_class(ImportXMTN)
    bpy.utils.register_class(ImportXC)
    bpy.utils.register_class(ImportXMPR)
    bpy.utils.register_class(ImportXCMA)
    bpy.utils.register_class(Level5_Menu_Import)
    bpy.types.TOPBAR_MT_file_import.append(draw_menu_import)


def unregister():
    bpy.utils.unregister_class(ExportXMTN)
    bpy.utils.unregister_class(ExportXC)
    bpy.utils.unregister_class(ExportXPRM)
    bpy.utils.unregister_class(ExportXCMA)
    bpy.utils.unregister_class(Level5_Menu_Export)
    bpy.utils.unregister_class(AnimationItem)
    bpy.utils.unregister_class(TexturePropertyGroup)
    bpy.utils.unregister_class(LibPropertyGroup)
    bpy.utils.unregister_class(MeshPropertyGroup)
    bpy.utils.unregister_class(TexprojPropertyGroup)
    bpy.utils.unregister_class(CameraPropertyGroup)
    bpy.utils.unregister_class(ArchivePropertyGroup)
    del bpy.types.Scene.export_xc_animations_items
    bpy.utils.unregister_class(ExportXC_AddAnimationItem)
    bpy.utils.unregister_class(ExportXC_RemoveAnimationItem)    
    bpy.types.TOPBAR_MT_file_export.remove(draw_menu_export)
    
    bpy.utils.unregister_class(ImportXMTN)
    bpy.utils.unregister_class(ImportXC)
    bpy.utils.unregister_class(ImportXMPR)
    bpy.utils.unregister_class(ImportXCMA)
    bpy.utils.unregister_class(Level5_Menu_Import)      
    bpy.types.TOPBAR_MT_file_import.remove(draw_menu_import)

if __name__ == "__main__":
    register()
