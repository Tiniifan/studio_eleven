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
    "version": (1, 1, 0),
    "blender": (2, 80, 2),
    "location": "File > Import-Export > Studio Eleven", 
    "warning": "",
    "doc_url": "",
    "support": 'COMMUNITY',
}

class Level5_Menu_Export(bpy.types.Menu):
    bl_label = "Studio Eleven (.mtn, .mtm, .imm, .prm, .xc, .cmr2)"
    bl_idname = "TOPBAR_MT_file_level5_export"

    def draw(self, context):
        layout = self.layout
        layout.operator(ExportXMTN.bl_idname, text="Animation (xmtn, xmtm, xima)", icon="POSE_HLT")
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
    
class Level5Material(PropertyGroup):
    def update_color(self, context):
        # Find the mesh that this material is associated with
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and hasattr(obj.data, 'level5_settings'):
                if obj.data.level5_settings.material == self:
                    mesh = obj.data
                    if mesh.materials:
                        material = mesh.materials[0]
                        material.use_nodes = True
                        nodes = material.node_tree.nodes
                        links = material.node_tree.links
                        
                        # Get or create the Material Output node
                        material_output = nodes.get("Material Output")
                        if not material_output:
                            material_output = nodes.new(type="ShaderNodeOutputMaterial")
                            material_output.location = (400, 0)

                        # Get or create the Principled BSDF node
                        bsdf = nodes.get("Principled BSDF")
                        if not bsdf:
                            bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
                            bsdf.location = (0, 0)
                            links.new(bsdf.outputs["BSDF"], material_output.inputs["Surface"])
                            
                        # Get or create the Mix Shader node
                        mix_shader = nodes.get("Mix Shader")
                        if not mix_shader:
                            mix_shader = nodes.new(type="ShaderNodeMixShader")
                            mix_shader.location = (200, 0)
                            mix_shader.inputs[0].default_value = 0.2    
                        
                        # Get or create the Transparent BSDF node
                        transparent_bsdf = nodes.get("Transparent BSDF")
                        if not transparent_bsdf:
                            transparent_bsdf = nodes.new(type="ShaderNodeBsdfTransparent")
                            transparent_bsdf.location = (0, -200)

                        # Check if the Alpha Multiplier node exists
                        alpha_multiplier = nodes.get("Alpha Multiplier")
                        if not alpha_multiplier:
                            # Create the Math node for alpha control
                            alpha_multiplier = nodes.new(type="ShaderNodeMath")
                            alpha_multiplier.name = "Alpha Multiplier"
                            alpha_multiplier.operation = 'MULTIPLY'
                            alpha_multiplier.location = (-300, 200)
                        
                        # Insert comment here
                        texture_node = nodes.get("Image Texture")
                        if texture_node:
                            if texture_node.outputs["Alpha"].is_linked:
                                # Set links for texture with alpha canal
                                links.new(alpha_multiplier.outputs[0], bsdf.inputs["Alpha"])
                                links.new(texture_node.outputs["Alpha"], alpha_multiplier.inputs[0])
                                
                                # Update dynamic alpha with self.color[3]-> transparency
                                alpha_multiplier.inputs[1].default_value = self.color[3]
                                
                                material.show_transparent_back = True
                            else:
                                # Set links for texture without alpha canal
                                links.new(mix_shader.outputs[0], material_output.inputs[0])
                                links.new(bsdf.outputs[0], mix_shader.inputs[1])
                                links.new(transparent_bsdf.outputs[0], mix_shader.inputs[2])
                                
                                # Update dynamic alpha with self.color[3]-> transparency
                                bsdf.inputs["Alpha"].default_value = self.color[3]
                                
                                material.show_transparent_back = False
                            
                            links.new(texture_node.outputs["Color"], bsdf.inputs["Base Color"])
                        else:
                            alpha_multiplier.inputs[0].default_value = 1.0  # Default value if no texture 
                        
                        # Update the emission with self.color[0], self.color[1], self.color[2] -> hsv
                        bsdf.inputs["Emission"].default_value = (self.color[0], self.color[1], self.color[2], 1.0)

                        # Set transparency parameters
                        material.blend_method = 'BLEND'
                        material.shadow_method = 'CLIP'
                        material.alpha_threshold = 0.5
                        material.use_backface_culling = False

    def get_name(self):
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and hasattr(obj.data, 'level5_settings'):
                if obj.data.level5_settings.material == self:
                    mesh = obj.data
                    name = mesh.materials[0].name
                    
                    if name.count('.') > 0 and len(name) > 3:
                        if name[len(name)-4] == '.':
                            match = re.search(r"^(.*?)(\.\d+)$", name)
                            
                            if match:
                                return match.group(1)
                    
                    return name
        return None

    color: FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        default=(0.0, 0.0, 0.0, 1.0),
        min=0.0,
        max=1.0,
        size=4,
        update=update_color,
        options={'ANIMATABLE'}
    )

class Level5Settings(PropertyGroup):
    material: PointerProperty(type=Level5Material)

class LEVEL5_PT_SettingsPanel(Panel):
    bl_label = "Level5 Settings"
    bl_idname = "LEVEL5_PT_SettingsPanel"
    bl_context = "data"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return context.mesh is not None

    def draw(self, context):
        level5_props = context.mesh.level5_settings
        
        layout = self.layout
        
        if context.mesh.materials:
            material = level5_props.material
            
            layout.label(text="Material")
            layout.use_property_split = True
            layout.use_property_decorate = True
            
            row = layout.row(align=True)
            indent_splitter = row.split(factor=0.05)
            indent_splitter.column()
            
            prop_splitter = indent_splitter.split(factor=0.95)
            prop_row = prop_splitter.row()
            prop_row.prop(material, "color", text=material.get_name())


def draw_menu_export(self, context):
    self.layout.menu(Level5_Menu_Export.bl_idname)
    
def draw_menu_import(self, context):
    self.layout.menu(Level5_Menu_Import.bl_idname)    

@persistent
def refresh_material_on_frame_change(scene):
    """Handler to refresh materials on frame change."""
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and hasattr(obj.data, 'level5_settings'):
            material = obj.data.level5_settings.material
            
            if material:
                # Check if there are keyframes on the color property
                if obj.data.animation_data and obj.data.animation_data.action:
                    for fcurve in obj.data.animation_data.action.fcurves:
                        if fcurve.data_path.startswith('level5_settings.material.color'):
                            material.update_color(bpy.context)
                            break

def register():
    # Level 5 Menu Export
    bpy.utils.register_class(ExportXC_AddAnimationItem)
    bpy.utils.register_class(ExportXC_RemoveAnimationItem)
    bpy.utils.register_class(AnimationItem)
    bpy.utils.register_class(TexturePropertyGroup)
    bpy.utils.register_class(LibPropertyGroup)
    bpy.utils.register_class(MeshPropertyGroup)
    bpy.utils.register_class(CameraPropertyGroup)
    bpy.utils.register_class(ArchivePropertyGroup)
    bpy.utils.register_class(TexprojPropertyGroup)
    bpy.types.Scene.export_xc_animations_items = bpy.props.CollectionProperty(type=AnimationItem)
    bpy.utils.register_class(ExportXMTN)
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
    
    # Level 5 Settings
    bpy.utils.register_class(Level5Material)
    bpy.utils.register_class(Level5Settings)
    bpy.utils.register_class(LEVEL5_PT_SettingsPanel)
    bpy.types.Mesh.level5_settings = PointerProperty(type=Level5Settings)
    bpy.app.handlers.frame_change_post.append(refresh_material_on_frame_change)

def unregister():
    # Level 5 Menu Export
    bpy.utils.unregister_class(ExportXMTN)
    bpy.utils.unregister_class(ExportXC)
    bpy.utils.unregister_class(ExportXPRM)
    bpy.utils.unregister_class(ExportXCMA)
    bpy.utils.unregister_class(Level5_Menu_Export)
    bpy.utils.unregister_class(AnimationItem)
    bpy.utils.unregister_class(TexturePropertyGroup)
    bpy.utils.unregister_class(LibPropertyGroup)
    bpy.utils.unregister_class(MeshPropertyGroup)
    bpy.utils.unregister_class(CameraPropertyGroup)
    bpy.utils.unregister_class(TexprojPropertyGroup)
    bpy.utils.unregister_class(ArchivePropertyGroup)
    del bpy.types.Scene.export_xc_animations_items
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
    
    # Level 5 Settings
    bpy.utils.unregister_class(Level5Material)
    bpy.utils.unregister_class(Level5Settings)
    bpy.utils.unregister_class(LEVEL5_PT_SettingsPanel)
    del bpy.types.Mesh.level5_settings
    bpy.app.handlers.frame_change_post.remove(refresh_material_on_frame_change)

if __name__ == "__main__":
    register()