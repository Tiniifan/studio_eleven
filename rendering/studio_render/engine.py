"""The StudioRender render engine: viewport drawing and F12 through a GPUOffScreen.

Everything touching the gpu module is imported inside the functions, so registering the engine works
in background mode where Blender has no GPU backend.
"""

import bpy
from collections import namedtuple
from mathutils import Vector

from bpy.props import BoolProperty, FloatVectorProperty, IntProperty, PointerProperty

from ..engines import get_engine
from . import draw, lighting, material, resources, shaders, state

STATUS = "viewport and offscreen paths need a GPU, they are never exercised by the validation script"

ENGINE_ID = 'STUDIO_RENDER'

# Panels of the other engines StudioRender can reuse as they are
COMPATIBLE_PANELS = (
    "RENDER_PT_color_management",
    "RENDER_PT_color_management_curves",
    "DATA_PT_camera",
    "DATA_PT_lens",
    "DATA_PT_camera_dof",
    "DATA_PT_light",
    "DATA_PT_EEVEE_light",
    "WORLD_PT_context_world",
)

class StudioRenderSettings(bpy.types.PropertyGroup):
    tint: FloatVectorProperty(
        name="Object Color",
        description="Color every mesh is multiplied by, white leaves the textures as they are (the game uses it to fade an object)",
        size=4, subtype='COLOR', min=0.0, max=2.0, default=(1.0, 1.0, 1.0, 1.0)
    )

    gamma_correct: BoolProperty(
        name="Combine In Display Space",
        description="The 3DS combines the textures on their stored 8 bit values while Blender hands out linear ones, keep it on to look like the game",
        default=True
    )

    fragment_lighting: BoolProperty(
        name="Fragment Lighting",
        description="Light the meshes with the lights of the scene the way the 3DS lighting unit does, for the render defaults that use it",
        default=True
    )

    light_limit: IntProperty(name="Lights", description="Number of scene lights used, the 3DS lighting unit handles up to 8",
                             default=4, min=0, max=lighting.MAX_LIGHTS)

    scene_ambient: FloatVectorProperty(name="Scene Ambient", description="Ambient light added everywhere", size=3,
                                       subtype='COLOR', min=0.0, max=1.0, default=(0.2, 0.2, 0.2))

    outline: BoolProperty(
        name="Draw Outlines",
        description="Draw the outlines of the export settings of the armatures, their width, color and depth range are set there",
        default=True
    )


Outline = namedtuple("Outline", ("thickness", "visibility", "scale", "depth_min", "depth_max", "open_width", "color"))

# unf_vtx_silhouette_1.x of the game is the thickness times this when the width follows the screen
OUTLINE_WIDTH_SCALE = 4.219409

# The game multiplies the width by params[128] = 1 / projection[1][1], which cancels the lens: the ring is a fixed share of
# the half height of the view, a thickness of 0.002 is one pixel of the 240 lines of the game screen (0.002 * 4.219409 * 120 = 1.01)
OUTLINE_REFERENCE_PROJECTION = 1.0

# The outline is never thicker than this share of the size of the character on screen: the game shows its
# characters at 240 lines, Blender views are much taller and get zoomed out much further
OUTLINE_SIZE_SHARE = 0.025

def settings_of(scene):
    return getattr(scene, "studio_render", None)


def outline_map(depsgraph):
    """Mesh object name to its Outline, read from the archive settings of the armatures."""
    outlines = {}

    for obj in depsgraph.scene.objects:
        archive = getattr(obj, "level5_archive", None)
        if obj.type != 'ARMATURE' or archive is None:
            continue

        for outline in archive.outlines:
            for mesh in outline.meshes:
                if mesh.assigned:
                    outlines[mesh.name] = Outline(outline.thickness, outline.visibility, outline.scale,
                                                  outline.depth_min, outline.depth_max,
                                                  outline.open_width, tuple(outline.color))

    return outlines


def background_color(scene):
    world = scene.world
    return tuple(world.color) + (1.0,) if world else (0.05, 0.05, 0.05, 1.0)

##########################################
# Uniforms
##########################################

def _set(setter, name, value):
    try:
        setter(name, value)
    except (ValueError, TypeError):
        # A uniform the compiler removed is not an error, the draw simply does not need it
        pass


def _bind_transforms(shader, model_matrix, view_matrix, projection_matrix, tint):
    _set(shader.uniform_float, "unf_vtx_lcl_glb", model_matrix)
    _set(shader.uniform_float, "unf_vtx_glb_cmr", view_matrix)
    _set(shader.uniform_float, "unf_vtx_cmr_prj", projection_matrix)
    _set(shader.uniform_float, "unf_vtx_clr", tuple(tint))

    for index, row in enumerate(((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0)) * 3):
        _set(shader.uniform_float, f"unf_vtx_txt_{index}", row)


def _bind_lighting(shader, settings, lights, material_lighting):
    environment = lighting.environment_of(material_lighting)

    _set(shader.uniform_int, "unf_lgt_config", environment.config)
    _set(shader.uniform_float, "unf_lgt_scene_ambient", tuple(settings.scene_ambient))
    _set(shader.uniform_float, "unf_mat_emission", environment.emission)
    _set(shader.uniform_float, "unf_mat_ambient", environment.ambient)
    _set(shader.uniform_float, "unf_mat_diffuse", environment.diffuse)
    _set(shader.uniform_float, "unf_mat_specular0", environment.specular0)
    _set(shader.uniform_float, "unf_mat_specular1", environment.specular1)
    _set(shader.uniform_int, "unf_lgt_fresnel_selector", environment.fresnel_selector)
    _set(shader.uniform_bool, "unf_lgt_clamp_highlights", [environment.clamp_highlights])
    _set(shader.uniform_bool, "unf_lgt_two_side_diffuse", [environment.two_side_diffuse])
    _set(shader.uniform_bool, "unf_lgt_enabled_d0", [environment.lut_enabled_d0])
    _set(shader.uniform_bool, "unf_lgt_enabled_d1", [environment.lut_enabled_d1])
    _set(shader.uniform_bool, "unf_lgt_enabled_refl", [environment.lut_enabled_refl])

    for table in lighting.LUT_TABLES:
        _set(shader.uniform_int, f"unf_lut_input_{table}", environment.lut_input[table])
        _set(shader.uniform_bool, f"unf_lut_abs_{table}", [environment.lut_abs[table]])
        _set(shader.uniform_float, f"unf_lut_scale_{table}", environment.lut_scale[table])

    for index, light in enumerate(lights):
        _set(shader.uniform_float, f"unf_lgt_position_{index}", light.position)
        _set(shader.uniform_float, f"unf_lgt_ambient_{index}", light.ambient)
        _set(shader.uniform_float, f"unf_lgt_diffuse_{index}", light.diffuse)
        _set(shader.uniform_float, f"unf_lgt_specular0_{index}", light.specular0)
        _set(shader.uniform_float, f"unf_lgt_specular1_{index}", light.specular1)

    _set(shader.uniform_sampler, "unf_frg_txt_lut", _lut_texture(material_lighting))


# The material is kept next to its texture so its id can't be given to another material
_lut_textures = {}


def _lut_texture(material_lighting):
    import gpu

    key = id(material_lighting)
    if key not in _lut_textures:
        rows = lighting.lut_texture_rows(material_lighting)
        values = [value for row in rows for value in row]
        buffer = gpu.types.Buffer('FLOAT', len(values), values)
        texture = gpu.types.GPUTexture(
            (lighting.LUT_TEXTURE_WIDTH, lighting.LUT_TEXTURE_HEIGHT), format='R32F', data=buffer)
        _lut_textures[key] = (material_lighting, texture)

    return _lut_textures[key][1]


_image_textures = {}


def _image_texture(image):
    import gpu

    key = image.name_full
    if key not in _image_textures:
        _image_textures[key] = gpu.texture.from_image(image)

    return _image_textures[key]


def clear_caches():
    _lut_textures.clear()
    _image_textures.clear()
    material.clear_palettes()
    shaders.clear_cache()
    resources.clear_cache()
    material.clear_cache()

##########################################
# Engine
##########################################

class StudioRenderEngine(bpy.types.RenderEngine):
    bl_idname = ENGINE_ID
    bl_label = "StudioRender"
    bl_use_preview = False

    def __init__(self):
        self.geometry = {}

    def view_update(self, context, depsgraph):
        self.geometry.clear()

    def view_draw(self, context, depsgraph):
        import gpu

        region_data = context.region_data
        gpu.state.blend_set('NONE')
        self.draw_scene(depsgraph, region_data.view_matrix, region_data.window_matrix, context.region.height)
        state.reset()

    def draw_scene(self, depsgraph, view_matrix, projection_matrix, viewport_height):
        scene = depsgraph.scene
        settings = settings_of(scene)
        if settings is None:
            return

        engine_id = material.scene_engine_id(scene)
        file_version = get_engine(engine_id).file_version
        lights = lighting.collect_lights(depsgraph, view_matrix, settings.light_limit) \
            if settings.fragment_lighting else []
        outlines = outline_map(depsgraph) if settings.outline else {}

        # The meshes of a character are drawn together: every outline first, then every mesh over them.
        # Instances and their objects are only valid inside the loop that yields them.
        groups = {}

        for instance in depsgraph.object_instances:
            obj = instance.object
            if obj.type == 'MESH':
                key = obj.parent.name if obj.parent else obj.name
                points = [instance.matrix_world @ Vector(corner) for corner in obj.bound_box]
                extent = groups.setdefault(key, [])
                extent.extend((min(point[axis] for point in points) for axis in range(3)))
                extent.extend((max(point[axis] for point in points) for axis in range(3)))

        eye = view_matrix.inverted().translation
        perspective = projection_matrix[3][3] == 0.0

        for key, extent in groups.items():
            # Share of the half height of the view the character takes, the outline never gets thicker than a bit of it
            size_ndc = None
            if perspective:
                lower = Vector((min(extent[0::6]), min(extent[1::6]), min(extent[2::6])))
                upper = Vector((max(extent[3::6]), max(extent[4::6]), max(extent[5::6])))
                distance = max(((lower + upper) * 0.5 - eye).length, 0.0001)
                size_ndc = max(upper - lower) * abs(projection_matrix[1][1]) / distance

            for draw_outlines in (True, False):
                for instance in depsgraph.object_instances:
                    obj = instance.object

                    if obj.type != 'MESH' or (obj.parent.name if obj.parent else obj.name) != key:
                        continue

                    geometry = self.geometry.get(obj.name)
                    if geometry is None:
                        geometry = draw.extract(obj, depsgraph)
                        self.geometry[obj.name] = geometry
                    if geometry is None:
                        continue

                    if draw_outlines:
                        outline = outlines.get(obj.name)
                        if outline is not None:
                            self.draw_outline(engine_id, file_version, obj, geometry, instance.matrix_world,
                                              view_matrix, projection_matrix, settings, outline,
                                              size_ndc, viewport_height)
                    else:
                        self.draw_object(engine_id, file_version, obj, geometry, instance.matrix_world,
                                         view_matrix, projection_matrix, settings, lights)

    def draw_object(self, engine_id, file_version, obj, geometry, model_matrix, view_matrix,
                    projection_matrix, settings, lights):
        slots = list(obj.material_slots) or [None]

        for index, slot in enumerate(slots):
            if index not in geometry.triangles:
                continue

            bound = material.build(engine_id, obj.data, slot.material if slot else None, file_version)
            if bound.program is None:
                continue

            options = shaders.ShaderOptions(
                texture_units=bound.texture_units,
                fragment_lighting=settings.fragment_lighting and bound.fragment_lighting,
                light_count=len(lights),
                alpha_test=bound.state.alpha_test,
                alpha_func=bound.state.alpha_func,
                gamma_correct=settings.gamma_correct,
            )

            shader = shaders.get_shader(bound.program, options, bound.program_key)
            batch = draw.make_batch(shader, geometry, index)
            if batch is None:
                continue

            state.apply(bound.state)
            shader.bind()
            _bind_transforms(shader, model_matrix, view_matrix, projection_matrix, settings.tint)
            _set(shader.uniform_float, "unf_frg_alpha_ref", bound.state.alpha_ref)

            for unit in options.texture_units:
                _set(shader.uniform_sampler, f"unf_frg_txt_2d_{unit}", _image_texture(bound.images[unit]))

            if bound.program.palette_channels and bound.images:
                for channel, color in material.palette_of(bound.images[0]).items():
                    _set(shader.uniform_float, f"unf_frg_palette_{channel}", color)

            if options.fragment_lighting:
                _bind_lighting(shader, settings, lights, bound.lighting)

            batch.draw(shader)

    def draw_outline(self, engine_id, file_version, obj, geometry, model_matrix, view_matrix, projection_matrix,
                     settings, outline, size_ndc=None, viewport_height=900):
        import gpu

        # open_width is the scaleByW flag of the outline: on, the thickness is a share of the screen
        # and the depth range is unused, off, it is a distance kept between depth_min and depth_max
        if outline.open_width:
            width, clamp_depth = outline.thickness * OUTLINE_WIDTH_SCALE, 0.0
        else:
            width, clamp_depth = outline.thickness, 1.0

        # A model holds the triangles of its outline as a second copy with the opposite winding: the game
        # draws only those (front face culling), the mesh covers the hull since it writes the depth alone
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(False)
        gpu.state.face_culling_set('BACK' if model_matrix.determinant() < 0 else 'FRONT')

        view_scale = 1.0
        if outline.open_width and width > 0.0:
            # Half height share of the ring: the game one, or less when the character is small on screen, a pixel at least
            ring = width * OUTLINE_REFERENCE_PROJECTION
            if size_ndc is not None:
                ring = max(2.0 / max(viewport_height, 1), min(ring, OUTLINE_SIZE_SHARE * size_ndc))
            view_scale = ring / (width * max(abs(projection_matrix[1][1]), 0.0001))
        slots = list(obj.material_slots) or [None]

        for index in geometry.triangles:
            slot = slots[index] if index < len(slots) else None
            bound = material.build(engine_id, obj.data, slot.material if slot else None, file_version)

            # The second combiner of the .sil (texture x primary color) is used for the textured meshes,
            # a character merges its textures first
            base = bound.program.base if bound.program is not None else None
            if base is not None:
                units = tuple(unit for unit in sorted(base.texture_units) if unit < len(bound.images))
            else:
                units = (0,) if 0 in bound.texture_units else ()
            textured = bool(units)
            options = shaders.ShaderOptions(
                texture_units=units,
                alpha_test=textured and bound.state.alpha_test,
                alpha_func=bound.state.alpha_func if textured else None,
                gamma_correct=settings.gamma_correct,
                outline=True,
            )
            shader = shaders.get_shader(base, options, ("outline", bound.program_key))

            batch = draw.make_batch(shader, geometry, index)
            if batch is None:
                continue

            shader.bind()
            _bind_transforms(shader, model_matrix, view_matrix, projection_matrix, settings.tint)
            _set(shader.uniform_float, "unf_frg_outline_color", outline.color)
            _set(shader.uniform_float, "unf_frg_alpha_ref", bound.state.alpha_ref)
            _set(shader.uniform_float, "unf_vtx_silhouette_0",
                 (1.0, outline.depth_min, outline.depth_max, 1.0 if geometry.has_silhouette else 0.0))
            _set(shader.uniform_float, "unf_vtx_silhouette_1", (width, 1.0 - outline.visibility, 1.0 - outline.scale, clamp_depth))
            _set(shader.uniform_float, "unf_vtx_outline_view", view_scale)

            for unit in units:
                _set(shader.uniform_sampler, f"unf_frg_txt_2d_{unit}", _image_texture(bound.images[unit]))

            if base is not None and base.palette_channels and bound.images:
                for channel, color in material.palette_of(bound.images[0]).items():
                    _set(shader.uniform_float, f"unf_frg_palette_{channel}", color)

            batch.draw(shader)

    def render(self, depsgraph):
        import gpu

        scene = depsgraph.scene
        settings = settings_of(scene)
        scale = scene.render.resolution_percentage / 100.0
        width = max(1, int(scene.render.resolution_x * scale))
        height = max(1, int(scene.render.resolution_y * scale))

        camera = scene.camera
        if camera is None or settings is None:
            return

        view_matrix = camera.matrix_world.inverted()
        projection_matrix = camera.calc_matrix_camera(depsgraph, x=width, y=height)

        offscreen = gpu.types.GPUOffScreen(width, height)
        try:
            with offscreen.bind():
                framebuffer = gpu.state.active_framebuffer_get()
                framebuffer.clear(color=background_color(scene), depth=1.0)
                self.geometry.clear()
                self.draw_scene(depsgraph, view_matrix, projection_matrix, height)
                state.reset()
                buffer = framebuffer.read_color(0, 0, width, height, 4, 0, 'FLOAT')
        finally:
            offscreen.free()

        # The pass takes one RGBA list per pixel
        pixels = [list(pixel) for row in buffer.to_list() for pixel in row]
        result = self.begin_result(0, 0, width, height)
        result.layers[0].passes["Combined"].rect = pixels
        self.end_result(result)

##########################################
# Panel
##########################################

def scene_has_outlines(scene):
    return any(obj.type == 'ARMATURE' and obj.level5_archive.outlines for obj in scene.objects)


class STUDIORENDER_OT_standard_view(bpy.types.Operator):
    bl_idname = "studio_render.standard_view"
    bl_label = "Use Standard View Transform"
    bl_description = "The game shows its colors as they are, Filmic and the other transforms make everything lighter"

    def execute(self, context):
        context.scene.view_settings.view_transform = 'Standard'
        return {'FINISHED'}


class STUDIORENDER_OT_create_outlines(bpy.types.Operator):
    bl_idname = "studio_render.create_outlines"
    bl_label = "Create Outlines"
    bl_description = "Add an outline to the armatures that have none, with the values most of the game models use"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ...operators.xpck_settings import find_unused_index, get_armature_meshes, sync_outline_meshes

        engine_id = material.scene_engine_id(context.scene)
        created = 0

        for armature in context.scene.objects:
            if armature.type != 'ARMATURE' or armature.level5_archive.outlines:
                continue

            meshes = get_armature_meshes(armature)
            names = [mesh.name for mesh in meshes]
            if not names:
                continue

            outline = armature.level5_archive.outlines.add()
            outline.private_index = find_unused_index([])
            outline.name = "outline_" + str(outline.private_index)
            outline.thickness, outline.visibility, outline.scale = 0.002, 0.6, 0.7
            outline.depth_min, outline.depth_max = 10.0, 60.0
            outline.color = (0.0, 0.0, 0.0, 1.0)
            sync_outline_meshes(outline, names)

            for item, mesh in zip(outline.meshes, meshes):
                render_default = material.render_default_of(engine_id, mesh.data)
                item.assigned = "SIL" in render_default.data["vertex_program"]
            created += 1

        self.report({'INFO'}, f"{created} outline(s) created")
        return {'FINISHED'}


class STUDIORENDER_OT_reset_settings(bpy.types.Operator):
    bl_idname = "studio_render.reset_settings"
    bl_label = "Reset To Default"
    bl_description = "Put every StudioRender setting back to its default value"

    def execute(self, context):
        settings = settings_of(context.scene)
        for prop in settings.bl_rna.properties:
            if prop.identifier != "rna_type":
                settings.property_unset(prop.identifier)

        clear_caches()
        return {'FINISHED'}


class StudioRenderPanel:
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    COMPAT_ENGINES = {ENGINE_ID}

    @classmethod
    def poll(cls, context):
        return context.engine in cls.COMPAT_ENGINES


class STUDIORENDER_PT_settings(StudioRenderPanel, bpy.types.Panel):
    bl_label = "StudioRender"

    def draw(self, context):
        layout = self.layout
        settings = settings_of(context.scene)
        if settings is None:
            return

        layout.prop(context.scene, "level5_installed_engine")

        if context.scene.view_settings.view_transform != 'Standard':
            box = layout.box()
            box.label(text="The view transform makes colors lighter than the game", icon='ERROR')
            box.operator("studio_render.standard_view")

        layout.prop(settings, "outline")
        if settings.outline and not scene_has_outlines(context.scene):
            box = layout.box()
            box.label(text="No outline in the export settings of the armatures", icon='INFO')
            box.operator("studio_render.create_outlines")

        layout.prop(settings, "tint")
        layout.operator("studio_render.reset_settings", icon='LOOP_BACK')


class STUDIORENDER_PT_advanced(StudioRenderPanel, bpy.types.Panel):
    bl_label = "Advanced"
    bl_parent_id = "STUDIORENDER_PT_settings"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        self.layout.prop(settings_of(context.scene), "gamma_correct")


class STUDIORENDER_PT_lighting(StudioRenderPanel, bpy.types.Panel):
    bl_label = "Fragment Lighting"
    bl_parent_id = "STUDIORENDER_PT_advanced"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        self.layout.prop(settings_of(context.scene), "fragment_lighting", text="")

    def draw(self, context):
        layout = self.layout
        settings = settings_of(context.scene)
        layout.active = settings.fragment_lighting

        layout.label(text="The scene lights light the meshes like the 3DS does.")
        layout.prop(settings, "light_limit")
        layout.prop(settings, "scene_ambient")

        layout.label(text="Material values and lookup tables come from the .mtr of each material.")


CLASSES = (StudioRenderSettings, StudioRenderEngine, STUDIORENDER_OT_standard_view, STUDIORENDER_OT_create_outlines, STUDIORENDER_OT_reset_settings, STUDIORENDER_PT_settings,
           STUDIORENDER_PT_advanced, STUDIORENDER_PT_lighting)


def _compatible_panels():
    for name in COMPATIBLE_PANELS:
        panel = getattr(bpy.types, name, None)
        if panel is not None and hasattr(panel, "COMPAT_ENGINES"):
            yield panel


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    bpy.types.Scene.studio_render = PointerProperty(type=StudioRenderSettings)

    for panel in _compatible_panels():
        panel.COMPAT_ENGINES.add(ENGINE_ID)


def unregister():
    for panel in _compatible_panels():
        panel.COMPAT_ENGINES.discard(ENGINE_ID)

    if hasattr(bpy.types.Scene, "studio_render"):
        del bpy.types.Scene.studio_render

    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

    clear_caches()
