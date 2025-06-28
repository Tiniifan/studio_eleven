import re
import bpy

from bpy.app.handlers import persistent
from bpy.types import PropertyGroup, Panel, UIList
from bpy.props import IntProperty, StringProperty, FloatVectorProperty, CollectionProperty, PointerProperty

from .operators import *
from .controls import *

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
    "version": (1, 2, 0),
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
    
    mesh_type: IntProperty(
        name="Mesh Type",
        description="Type of the mesh",
        default=1,
        min=0,
        max=65535
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
    bpy.utils.register_class(ExportXC_AddAnimationItem)
    bpy.utils.register_class(ExportXC_RemoveAnimationItem)
    bpy.utils.register_class(Animation)
    bpy.utils.register_class(AnimationItem)
    bpy.utils.register_class(TexturePropertyGroup)
    bpy.utils.register_class(LibPropertyGroup)
    bpy.utils.register_class(MeshPropertyGroup)
    bpy.utils.register_class(CameraPropertyGroup)
    bpy.utils.register_class(ArchivePropertyGroup)
    bpy.utils.register_class(TexprojPropertyGroup)
    
    bpy.types.Scene.animation_armature = bpy.props.CollectionProperty(type=Animation)
    bpy.types.Scene.animation_uv = bpy.props.CollectionProperty(type=Animation)
    bpy.types.Scene.animation_material = bpy.props.CollectionProperty(type=Animation)
    bpy.types.Scene.animation_camera = bpy.props.CollectionProperty(type=Animation)
    bpy.types.Scene.animation_items_armature = bpy.props.CollectionProperty(type=AnimationItem)
    bpy.types.Scene.animation_items_uv = bpy.props.CollectionProperty(type=AnimationItem)
    bpy.types.Scene.animation_items_material = bpy.props.CollectionProperty(type=AnimationItem)
    bpy.types.Scene.animation_items_camera = bpy.props.CollectionProperty(type=AnimationItem)
    
    bpy.utils.register_class(ExportAnimation)
    bpy.utils.register_class(ExportXC)
    bpy.utils.register_class(ExportXPRM)
    bpy.utils.register_class(ExportXCMA) 
    bpy.utils.register_class(Level5_Menu_Export)
    bpy.types.TOPBAR_MT_file_export.append(draw_menu_export)
    
    # Level 5 Menu Import
    bpy.utils.register_class(ImportAnimation)
    bpy.utils.register_class(ImportXC)
    bpy.utils.register_class(ImportXMPR)
    bpy.utils.register_class(ImportXCMA)
    bpy.utils.register_class(Level5_Menu_Import)
    bpy.types.TOPBAR_MT_file_import.append(draw_menu_import)
    
    # Level 5 Panel
    bpy.utils.register_class(Level5MeshProperties)
    bpy.utils.register_class(Level5_Panel)
    bpy.types.Mesh.level5_properties = bpy.props.PointerProperty(type=Level5MeshProperties)

def unregister():
    # Level 5 Menu Export
    bpy.utils.unregister_class(BoneCheckbox)
    bpy.utils.unregister_class(ExportAnimation)
    bpy.utils.unregister_class(ExportXC)
    bpy.utils.unregister_class(ExportXPRM)
    bpy.utils.unregister_class(ExportXCMA)
    bpy.utils.unregister_class(Level5_Menu_Export)
    bpy.utils.unregister_class(Animation)
    bpy.utils.unregister_class(AnimationItem)
    bpy.utils.unregister_class(TexturePropertyGroup)
    bpy.utils.unregister_class(LibPropertyGroup)
    bpy.utils.unregister_class(MeshPropertyGroup)
    bpy.utils.unregister_class(CameraPropertyGroup)
    bpy.utils.unregister_class(TexprojPropertyGroup)
    bpy.utils.unregister_class(ArchivePropertyGroup)
    
    del bpy.types.Scene.animation_armature
    del bpy.types.Scene.animation_uv
    del bpy.types.Scene.animation_material
    del bpy.types.Scene.animation_camera
    del bpy.types.Scene.animation_items_armature
    del bpy.types.Scene.animation_items_uv
    del bpy.types.Scene.animation_items_material
    del bpy.types.Scene.animation_items_camera
    
    bpy.utils.unregister_class(ExportXC_AddAnimationItem)
    bpy.utils.unregister_class(ExportXC_RemoveAnimationItem)    
    bpy.types.TOPBAR_MT_file_export.remove(draw_menu_export)
    
    # Level 5 Menu Import
    bpy.utils.unregister_class(ImportAnimation)
    bpy.utils.unregister_class(ImportXC)
    bpy.utils.unregister_class(ImportXMPR)
    bpy.utils.unregister_class(ImportXCMA)
    bpy.utils.unregister_class(Level5_Menu_Import)      
    bpy.types.TOPBAR_MT_file_import.remove(draw_menu_import)
    
    # Level 5 Panel
    bpy.utils.unregister_class(Level5_Panel)
    bpy.utils.unregister_class(Level5MeshProperties)
    del bpy.types.Mesh.level5_properties

if __name__ == "__main__":
    register()