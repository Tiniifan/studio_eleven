"""Unity material render settings -> Studio Eleven material render state (.atr) and texture samplers.

Fills material.level5_atr (studio_eleven/formats/material/atr.py, edited through
operators/panels/material_render.py) and the sampler of the material's texture slot
(material.level5_textures.slots, operators/panels/material_textures.py), then lets Studio Eleven's
own fileio_xmpr.apply_atr_state and material_textures.apply_material_textures set up the Blender
preview, exactly like its xpck import (operators/io/fileio_xmpr.py make_mesh) does. The export and
StudioRender (rendering/studio_render/material.py samplers_of) read the same slots, so these values
drive the render as well as the RES.bin.

Rules measured on FireTornado (Unity materials vs the whs0001_ef1 .atr / RES.bin of the 3DS move):
    _Cull 0 -> cull off, 2 -> cull on (both sides of the X mirror keep the same culled side)
    _ZWrite 0 -> depth write off
    _SrcBlend One / _DstBlend OneMinusSrcAlpha -> SRC_ALPHA / ONE_MINUS_SRC_ALPHA
    _SrcBlend One / _DstBlend One -> SRC_ALPHA / ONE (the effect shaders premultiply, the 3DS doesn't)
    alpha channel of blended materials -> ZERO / ONE, alpha_ref 0
    texture m_WrapU / m_WrapV 0, 1, 2 -> REPEAT, EXTEND (the 3DS clamp), MIRROR (wrap X / wrap Y)
    mesh vertex colors of blended materials == the 3DS tint (vertex buffer slot 1)
    draw priority: the 3DS order of the meshes (17..47) is the order of the Unity render queues (3101..3130),
    and the 0x100 bit is set exactly on the materials with _BillboardMode 1 (282 = 0x100 | 26)
"""

UNITY_BLEND_FACTORS = {
    0: "ZERO", 1: "ONE", 2: "DST_COLOR", 3: "SRC_COLOR", 4: "ONE_MINUS_DST_COLOR", 5: "SRC_ALPHA",
    6: "ONE_MINUS_SRC_COLOR", 7: "DST_ALPHA", 8: "ONE_MINUS_DST_ALPHA", 9: "SRC_ALPHA_SATURATE",
    10: "ONE_MINUS_SRC_ALPHA",
}
UNITY_BLEND_OPS = {0: "ADD", 1: "SUBTRACT", 2: "REVERSE_SUBTRACT", 3: "MIN", 4: "MAX"}
# UnityEngine.Rendering.CompareFunction (0 = disabled)
UNITY_COMPARE = {1: "NEVER", 2: "LESS", 3: "EQUAL", 4: "LEQUAL", 5: "GREATER", 6: "NOTEQUAL", 7: "GEQUAL", 8: "ALWAYS"}
# TextureWrapMode: Repeat, Clamp, Mirror, MirrorOnce (-1 = importer default, Repeat).
# Unity's Clamp is what studio_eleven/formats/res.py calls EXTEND (value 0 of the 3DS sampler).
UNITY_WRAP = {0: "REPEAT", 1: "EXTEND", 2: "MIRROR", 3: "MIRROR"}

TRANSPARENT_QUEUE = 2450
# Unity draws the queues below this value in the opaque pass, before every transparent one
OPAQUE_PASS_END = 2500
# First priority of the 3DS effect meshes (whs0001_ef1: 17 = base + first rank)
DRAW_PRIORITY_BASE = 16
BILLBOARD_PRIORITY_FLAG = 0x100
RENDERERS = ("MeshRenderer", "SkinnedMeshRenderer")
# studio_eleven/formats/atr.py: leave the field out of the file, the engine default applies
INHERIT = "INHERIT"


def _floats(material):
    return dict(material["m_SavedProperties"]["m_Floats"])


def is_blended(material):
    """True for see-through materials (effects), False for solid ones (characters, props)."""
    floats = _floats(material)
    if "_DstBlend" in floats:
        # Anything but a ZERO destination lets what is behind show through
        return int(floats["_DstBlend"]) != 0
    return material.get("m_CustomRenderQueue", -1) >= TRANSPARENT_QUEUE


def unity_render_state(material):
    """Return the level5_atr property values (Studio Eleven enum names) for a Unity material."""
    floats = _floats(material)
    blended = is_blended(material)
    state = {
        "cull": "OFF" if int(floats.get("_Cull", 2.0)) == 0 else "ON",
        # Every shipped file (whs0001_ef1, the 3DS bodies and ball) leaves blend and the depth bias switch
        # out and writes a depth bias of 0; blending is on by default in the engine
        "depth_bias_enable": INHERIT,
        "depth_bias": 0.0,
        "blend": INHERIT,
        "blend_rgb_equation": UNITY_BLEND_OPS.get(int(floats.get("_BlendOp", 0.0)), "ADD"),
        "blend_alpha_equation": "ADD",
        "depth_write": "ON" if floats.get("_ZWrite", 0.0 if blended else 1.0) >= 0.5 else "OFF",
    }

    # The shipped files leave a field out when it matches the engine default (LESS depth, no alpha test),
    # which is what "inherit" writes: keep the same bytes as an original file re-exported by Studio Eleven
    z_test = int(floats.get("_ZTest", 2.0))
    state["depth_test"] = "OFF" if z_test in (0, 8) else "ON"
    state["depth_func"] = INHERIT if z_test in (0, 2) else UNITY_COMPARE.get(z_test, "LESS")

    cutout = floats.get("_AlphaClip", 0.0) >= 0.5 or floats.get("_AlphaToMask", 0.0) >= 0.5
    state["alpha_test"] = "ON" if cutout else INHERIT
    state["alpha_func"] = "GREATER" if cutout else INHERIT
    state["alpha_ref"] = floats.get("_Cutoff", 0.5) if cutout else 0.0

    source = int(floats.get("_SrcBlend", 5.0 if blended else 1.0))
    destination = int(floats.get("_DstBlend", 10.0 if blended else 0.0))
    if blended:
        # Premultiplied in Unity, straight alpha in the 3DS textures
        state["blend_rgb_source"] = "SRC_ALPHA" if source == 1 else UNITY_BLEND_FACTORS.get(source, "SRC_ALPHA")
        state["blend_rgb_destination"] = UNITY_BLEND_FACTORS.get(destination, "ONE_MINUS_SRC_ALPHA")
        state["blend_alpha_source"] = "ZERO"
        state["blend_alpha_destination"] = "ONE"
    else:
        state["blend_rgb_source"] = UNITY_BLEND_FACTORS.get(source, "ONE")
        state["blend_rgb_destination"] = "ZERO"
        state["blend_alpha_source"] = "ONE"
        state["blend_alpha_destination"] = "ZERO"
    return state


def render_queue(material):
    """Effective render queue; -1 means the shader's queue, which lives in another bundle."""
    queue = material.get("m_CustomRenderQueue", -1)
    if queue >= 0:
        return queue
    return 3000 if is_blended(material) else 2000


def draw_priorities(sfile):
    """{renderer path_id: draw priority} for every renderer of a serialized file.

    Unity sorts what it draws by pass (opaque before transparent), sorting layer, order in layer, then
    render queue (distance only breaks ties). Renderers are ranked with that key over the whole file, so
    the player, the ball and the effects keep their relative order across the exported archives.
    """
    keys = {}
    billboards = set()
    for info in sfile.objects.values():
        if info.type_name not in RENDERERS:
            continue
        renderer = info.read()
        material_info = sfile.get_object(renderer["m_Materials"][0]) if renderer.get("m_Materials") else None
        material = material_info.read() if material_info is not None else None
        queue = render_queue(material) if material is not None else 2000
        keys[info.path_id] = (queue >= OPAQUE_PASS_END, renderer.get("m_SortingLayer", 0), renderer.get("m_SortingOrder", 0), queue)
        if material is not None and int(_floats(material).get("_BillboardMode", 0.0)) == 1:
            billboards.add(info.path_id)

    ranks = {key: rank for rank, key in enumerate(sorted(set(keys.values())), 1)}
    priorities = {}
    for path_id, key in keys.items():
        priority = DRAW_PRIORITY_BASE + ranks[key]
        if path_id in billboards:
            priority |= BILLBOARD_PRIORITY_FLAG
        priorities[path_id] = min(priority, 65535)
    return priorities


def apply_render_state(blender_material, material):
    """Store the render state on the material and preview it."""
    from studio_eleven.operators.io import fileio_xmpr
    from studio_eleven.operators.panels.material_render import state_from_properties

    properties = blender_material.level5_atr
    for name, value in unity_render_state(material).items():
        setattr(properties, name, value)
    # Same preview and panel mode (simple / expert) as Studio Eleven's xpck import
    fileio_xmpr.apply_atr_state(blender_material, state_from_properties(properties))


def unity_sampler(texture):
    """Texture slot sampler values (Level5TextureSlot) for a Unity Texture2D."""
    settings = texture.get("m_TextureSettings", {})
    filter_mode = settings.get("m_FilterMode", 1)
    has_mips = texture.get("m_MipCount", 1) > 1
    smooth = "NEAREST" if filter_mode == 0 else "LINEAR"
    return {
        "wrap_x": UNITY_WRAP.get(settings.get("m_WrapU", 0), "REPEAT"),
        "wrap_y": UNITY_WRAP.get(settings.get("m_WrapV", 0), "REPEAT"),
        "magnification": smooth,
        "minification": smooth,
        # Trilinear blends mip levels; the 3DS files leave mipmapping off otherwise
        "mipmap": "ENABLED" if filter_mode == 2 and has_mips else "DISABLED",
    }


def apply_sampler(slot, texture):
    """Store the wrap/filter of a Unity texture on the texture slot that samples it.

    Mirrored wrapping matters: the effect shaders store a glow as one quarter of it and let the
    mirror rebuild the whole (Ocean Birth's ball lights, UVs -0.9..0.9 on a MIRROR texture); read as
    REPEAT the quarter is tiled instead and the glow becomes a hard edged wedge.
    """
    if texture is None:
        return
    for name, value in unity_sampler(texture).items():
        setattr(slot, name, value)


def refresh_preview(blender_material):
    """Let Studio Eleven rebuild the shader graph of a material from its texture slots: sampler wrap
    (math nodes, mirror = ping pong), tint and animated transparency.

    The tint needs the material to be on its mesh already, so models.py calls this again after that.
    """
    from studio_eleven.operators.panels.material_textures import apply_material_textures

    apply_material_textures(blender_material)
