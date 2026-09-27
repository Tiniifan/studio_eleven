import bpy

from .fileio_xmpr import ExportXPRM, ImportXMPR
from .fileio_animation_manager import ExportAnimation, ImportAnimation
from .fileio_xpck import ExportXC, ImportXC
from .fileio_xcma import ExportXCMA, ImportXCMA

##########################################
# Register class
##########################################

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

##########################################
# Register
##########################################

def register_menus():
    bpy.utils.register_class(Level5_Menu_Export)
    bpy.utils.register_class(Level5_Menu_Import)

    bpy.types.TOPBAR_MT_file_export.append(draw_menu_export)
    bpy.types.TOPBAR_MT_file_import.append(draw_menu_import)

def unregister_menus():
    bpy.types.TOPBAR_MT_file_import.remove(draw_menu_import)
    bpy.types.TOPBAR_MT_file_export.remove(draw_menu_export)

    bpy.utils.unregister_class(Level5_Menu_Import)
    bpy.utils.unregister_class(Level5_Menu_Export)
