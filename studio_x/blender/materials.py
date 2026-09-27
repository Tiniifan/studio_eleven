"""Blender materials laid out like Studio Eleven's make_mesh (operators/fileio_xmpr.py), so the
Studio Eleven exporters find the nodes they animate:
    "Image Texture" -> "Principled BSDF".Base Color
    "Image Texture".Alpha -> "Alpha Multiplier" (Math MULTIPLY) -> "Principled BSDF".Alpha
Transparency animations then target node_tree.nodes["Alpha Multiplier"].inputs[1].
The render state (.atr) and texture wrap/filter come from render_state.py.
"""

import bpy

from . import render_state, textures

ALPHA_MULTIPLIER = "Alpha Multiplier"
IMAGE_TEXTURE = "Image Texture"
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
    nodes = blender_material.node_tree.nodes
    if ALPHA_MULTIPLIER in nodes:
        return 'node_tree.nodes["%s"].inputs[1].default_value' % ALPHA_MULTIPLIER
    bsdf = nodes.get(PRINCIPLED)
    index = list(bsdf.inputs).index(bsdf.inputs["Alpha"])
    return 'node_tree.nodes["%s"].inputs[%d].default_value' % (PRINCIPLED, index)


def build_material(name, material, sfile, cache, adapt_textures, uv_layer_name):
    blender_material = bpy.data.materials.new(name=name)
    blender_material.use_nodes = True
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
    if image is not None:
        texture = nodes.new("ShaderNodeTexImage")
        texture.name = IMAGE_TEXTURE
        texture.image = image
        texture.location = (-600, 200)
        links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])

        if uv_layer_name:
            uv_map = nodes.new("ShaderNodeUVMap")
            uv_map.uv_map = uv_layer_name
            uv_map.location = (-850, 200)
            links.new(uv_map.outputs["UV"], texture.inputs["Vector"])

        multiplier = nodes.new("ShaderNodeMath")
        multiplier.name = ALPHA_MULTIPLIER
        multiplier.operation = "MULTIPLY"
        multiplier.location = (-300, -150)
        multiplier.inputs[1].default_value = alpha
        links.new(texture.outputs["Alpha"], multiplier.inputs[0])
        links.new(multiplier.outputs[0], bsdf.inputs["Alpha"])
        render_state.apply_sampler(blender_material, textures.uv_texture(material, sfile))
    else:
        bsdf.inputs["Alpha"].default_value = alpha

    if bpy.app.version < (4, 3, 0):
        blender_material.shadow_method = "CLIP"
    if not render_state.apply_render_state(blender_material, material):
        # Studio Eleven without render state support: preview only
        blender_material.blend_method = "BLEND"
        blender_material.alpha_threshold = 0.5
        blender_material.show_transparent_back = True
        # Unity _Cull: 0 = off, 1 = front, 2 = back
        blender_material.use_backface_culling = material_floats(material).get("_Cull", 0.0) == 2.0
    blender_material["unity_material"] = material.get("m_Name", "")
    return blender_material
