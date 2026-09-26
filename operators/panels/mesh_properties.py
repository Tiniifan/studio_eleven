import bpy
from bpy.props import IntProperty, EnumProperty, PointerProperty, StringProperty

from ...rendering import project as rendering_project
from ...templates import TEMPLATES

##########################################
# Mesh Properties Function
##########################################

def get_render_default_choice(self):
    names = [item[0] for item in rendering_project.render_default_items()]

    if self.render_default in names:
        return names.index(self.render_default)

    return 0

def set_render_default_choice(self, value):
    self.render_default = rendering_project.render_default_items()[value][0]
    self.unresolved_render_program = ""

def render_default_choice_items(self, context):
    return rendering_project.render_default_items()

def get_program_name(render_program):
    """Name of a render program hash (hexadecimal) when a template uses it, the hash otherwise."""
    for template in TEMPLATES.values():
        if f"{template['render_program_hash']:08X}" == render_program:
            return template["render_program"]

    return render_program

##########################################
# Register class
##########################################

class Level5MeshProperties(bpy.types.PropertyGroup):
    render_default: StringProperty(
        name="Render Default Name",
        description="Render default of the mesh, it belongs to the game engine of the project",
        default=""
    )

    render_default_choice: EnumProperty(
        name="Render Default",
        description="Render program of the mesh, the ones of the game engine of the project are listed",
        items=render_default_choice_items,
        get=get_render_default_choice,
        set=set_render_default_choice
    )

    unresolved_render_program: StringProperty(
        name="Original Render Program",
        description="Render program hash (hexadecimal) of the mesh when the game engine of the project does not have it, the export writes it back",
        default=""
    )

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
            properties = mesh.level5_properties

            layout.prop(properties, "render_default_choice")

            if properties.unresolved_render_program:
                layout.label(text=f"Program {get_program_name(properties.unresolved_render_program)} is kept on export", icon='INFO')

            layout.prop(properties, "draw_priority")
            layout.prop(properties, "mesh_type")
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
