import bpy
import json
from bpy.props import BoolProperty, PointerProperty, StringProperty

from ...formats import mtr
from ...rendering import project as rendering_project

##########################################
# Material Lighting Function
##########################################

def get_material_lighting(material, scene):
    """The lighting material the export writes: the one of the model, the default of the project otherwise."""
    if material.level5_mtr.data:
        return mtr.Material.from_dict(json.loads(material.level5_mtr.data))

    return mtr.read_mtr(rendering_project.get_default_mtr(scene))

def write_material_lighting(material_name, scene, file_version):
    material = bpy.data.materials.get(material_name)

    if material is not None and hasattr(material, "level5_mtr") and material.level5_mtr.data:
        return mtr.write_mtr(mtr.Material.from_dict(json.loads(material.level5_mtr.data)), file_version)

    return rendering_project.get_default_mtr(scene)

def format_color(color):
    return "(" + ", ".join(str(round(value, 2)) for value in color) + ")"

##########################################
# Register class
##########################################

class Level5MtrProperties(bpy.types.PropertyGroup):
    data: StringProperty(
        name="Lighting Material",
        description="The lighting material of the game as JSON: colors, fragment lighting flags and lookup tables, empty to use the default one",
        default=""
    )

    # A material made in Blender gets the values of the template once
    initialized: BoolProperty(
        default=False,
        options={'HIDDEN'}
    )

class MATERIAL_OT_level5_reset_mtr(bpy.types.Operator):
    bl_idname = "material.level5_reset_mtr"
    bl_label = "Use The Default Lighting Material"
    bl_description = "Forget the lighting material of the material, the export writes the one of the template"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.material.level5_mtr.data = ""

        return {'FINISHED'}

class Level5_Mtr_Panel(bpy.types.Panel):
    bl_label = "Lighting Material"
    bl_idname = "MATERIAL_PT_level5_mtr_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_parent_id = "MATERIAL_PT_level5_render_state_panel"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.material is not None and hasattr(context.material, "level5_mtr")

    def draw(self, context):
        layout = self.layout
        material = get_material_lighting(context.material, context.scene)

        if context.material.level5_mtr.data:
            layout.label(text="Own lighting material")
        elif rendering_project.is_studio_render_enabled():
            layout.label(text="Game engine default")
        else:
            layout.label(text="Template default")

        layout.label(text=f"Ambient {format_color(material.ambient)}  Diffuse {format_color(material.diffuse)}")
        layout.label(text=f"Specular 0 {format_color(material.specular0)}  Specular 1 {format_color(material.specular1)}")

        tables = []
        for name, table in material.tables.items():
            if table.lut:
                tables.append(name)

        if tables:
            layout.label(text="Lookup tables: " + ", ".join(tables))
        else:
            layout.label(text="Lookup tables: none")

        layout.operator("material.level5_reset_mtr")

##########################################
# Register
##########################################

def register_material_lighting():
    bpy.utils.register_class(Level5MtrProperties)
    bpy.utils.register_class(MATERIAL_OT_level5_reset_mtr)
    bpy.utils.register_class(Level5_Mtr_Panel)

    bpy.types.Material.level5_mtr = PointerProperty(type=Level5MtrProperties)

def unregister_material_lighting():
    bpy.utils.unregister_class(Level5_Mtr_Panel)
    bpy.utils.unregister_class(MATERIAL_OT_level5_reset_mtr)
    bpy.utils.unregister_class(Level5MtrProperties)

    del bpy.types.Material.level5_mtr
