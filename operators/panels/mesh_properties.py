import bpy
from bpy.props import IntProperty, EnumProperty, PointerProperty

##########################################
# Register class
##########################################

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

##########################################
# Register
##########################################

def register_mesh_properties():
    bpy.utils.register_class(Level5MeshProperties)
    bpy.utils.register_class(Level5_Panel)

    bpy.types.Mesh.level5_properties = PointerProperty(type=Level5MeshProperties)

def unregister_mesh_properties():
    bpy.utils.unregister_class(Level5_Panel)
    bpy.utils.unregister_class(Level5MeshProperties)

    del bpy.types.Mesh.level5_properties
