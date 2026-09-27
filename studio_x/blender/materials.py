"""Blender materials laid out like the ones Studio Eleven's xpck import makes (operators/io/fileio_xmpr.py
make_mesh), so its exporters and StudioRender read them the same way:
    texture slot 1 (material.level5_textures) = the baked Unity texture, with its sampler (wrap/filter)
    "Alpha Multiplier" (Math MULTIPLY) -> "Principled BSDF".Alpha, the static 1 - _Transparency
Studio Eleven's apply_material_textures builds the rest of the graph from the slot: the texture node,
the wrap nodes, the tint (vertex colors of the "Tint" layer) and, once add_material_animation_nodes has
added them, the "Level5 Transparency" value node that material animations key (TRANSPARENCY_DATA_PATH).
The render state (.atr) and texture wrap/filter come from render_state.py.
"""

import bpy

from . import render_state, textures

ALPHA_MULTIPLIER = "Alpha Multiplier"
PRINCIPLED = "Principled BSDF"


def material_floats(material):
    return dict(material["m_SavedProperties"]["m_Floats"])


def material_property_names(material):
    """Every animatable property name, including the "<texture>_ST" tiling/offset vectors."""
    saved = material["m_SavedProperties"]
    names = [name for name, _ in saved["m_TexEnvs"]]
    names += [name + "_ST" for name, _ in saved["m_TexEnvs"]]
    names += [name for name, _ in saved["m_Floats"]]
    names += [name for name, _ in saved["m_Colors"]]
    names += [name for name, _ in saved.get("m_Ints", [])]
    return names


def material_color(material):
    """The _Color the effect shaders multiply into the texture (white when the material has none)."""
    for name, value in material["m_SavedProperties"]["m_Colors"]:
        if name == "_Color":
            return tuple(min(max(value.get(component, 1.0), 0.0), 1.0) for component in "rgba")
    return (1.0, 1.0, 1.0, 1.0)


def base_alpha(material):
    """Static opacity of the effect shaders: 1 - _Transparency (see research notes in the README)."""
    return 1.0 - material_floats(material).get("_Transparency", 0.0)


def alpha_data_path(blender_material):
    """Data path of the animated transparency, the one Studio Eleven's import keys and StudioRender fades with."""
    from studio_eleven.operators.panels.material_textures import TRANSPARENCY_NODE

    return 'node_tree.nodes["%s"].outputs[0].default_value' % TRANSPARENCY_NODE


def add_transparency_animation(blender_material):
    """Add the value node a transparency animation keys; the animated values already hold the static
    1 - _Transparency, so the Alpha Multiplier stops applying it."""
    from studio_eleven.operators.panels.material_textures import add_material_animation_nodes

    add_material_animation_nodes(blender_material)
    multiplier = blender_material.node_tree.nodes.get(ALPHA_MULTIPLIER)
    if multiplier is not None:
        multiplier.inputs[1].default_value = 1.0
    return alpha_data_path(blender_material)


def build_material(name, material, sfile, cache, adapt_textures):
    from studio_eleven.operators.panels import material_textures

    blender_material = bpy.data.materials.new(name=name)
    blender_material.use_nodes = True
    # Like an imported material: Studio Eleven gives a new, uninitialized material the render state and
    # lighting of the scene template (rendering/project.py init_new_material), which would replace ours
    blender_material.level5_mtr.initialized = True
    nodes = blender_material.node_tree.nodes
    links = blender_material.node_tree.links

    output = nodes.get("Material Output") or nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.get(PRINCIPLED)
    if bsdf is None:
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.name = PRINCIPLED
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    image = None
    if cache is not None:
        image = textures.build_main_image(material, sfile, cache, adapt_textures)

    alpha = base_alpha(material)
    # Filling the slot must not rebuild the graph on every property
    material_textures.suspend_updates()
    try:
        blender_material.level5_textures.initialized = True
        if image is not None:
            slot = blender_material.level5_textures.slots.add()
            slot.image = image
            slot.show_expanded = False
            render_state.apply_sampler(slot, textures.uv_texture(material, sfile))
    finally:
        material_textures.resume_updates()

    if image is not None:
        # apply_material_textures wires the texture alpha into this node when its output is linked
        multiplier = nodes.new("ShaderNodeMath")
        multiplier.name = ALPHA_MULTIPLIER
        multiplier.operation = "MULTIPLY"
        multiplier.location = (-300, -150)
        multiplier.inputs[1].default_value = alpha
        links.new(multiplier.outputs[0], bsdf.inputs["Alpha"])
    else:
        bsdf.inputs["Alpha"].default_value = alpha

    if bpy.app.version < (4, 3, 0):
        blender_material.shadow_method = "CLIP"
    render_state.apply_render_state(blender_material, material)
    render_state.refresh_preview(blender_material)
    blender_material["unity_material"] = material.get("m_Name", "")
    return blender_material
