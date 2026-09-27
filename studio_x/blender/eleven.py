"""Fill Studio Eleven's xpck export settings the way its own xpck import does.

Mirrors studio_eleven/operators/io/fileio_xpck.py (apply_animation_imports and the camera markers of
build_archive) and fileio_xcma.py set_camera_settings, so an imported Unity move can be exported back
as xpck with its animation names, split animations and cameras already filled in.
"""

ANIMATION_TYPES = ("armature", "uv", "material")

# Archive names of a 3DS move, built from the move (waza) name: <waza>_<body><side><number>.xc for the
# players, <waza>_bl<number>.xc for the ball, <waza>_ef<number>.xc for the effect models and <waza>_cam.xv
# for the cameras. whs0001_aa1.xc is the first ally on a normal body, whs0001_td2.xc the second opponent on a
# tall body. The animation of an archive has its name without the extension.
BODY_CODES = {"normal": "a", "fat": "b", "small": "s", "tall": "t"}
SIDE_CODES = {"ally": "a", "opponent": "d"}


def model_archive_name(waza, role, index, body=None):
    """Archive name of the index-th (0 based) ally, opponent or ball of a move, None without a waza name."""
    if not waza:
        return None
    code = "bl" if role == "ball" else BODY_CODES[body] + SIDE_CODES[role]
    return "%s_%s%d.xc" % (waza, code, index + 1)


def effect_archive_name(waza, index):
    """Archive of the index-th (0 based) effect model of a move: <waza>_ef1.xc, _ef2.xc..."""
    return "%s_ef%d.xc" % (waza, index + 1) if waza else None


def camera_archive_name(waza):
    return "%s_cam.xv" % waza if waza else None


def animation_name(archive):
    """Animation name of an archive: its name without the extension."""
    return archive.rsplit(".", 1)[0] if archive else None


def split_name(index):
    """Split names of the 3DS mtninf files; the cameras of a cut use the same name."""
    return "%02d" % (index + 1)


def split_animations(source, fps):
    """One split per timeline cut, named 01, 02... like the 3DS mtninf files.

    The game loop runs at 60 Hz: the 3DS moves store 30 fps keys with a speed of 0.5.
    """
    if len(source.cuts) < 2:
        return []
    splits = []
    for index in range(len(source.cuts)):
        frames = source.cut_frames(index, fps)
        splits.append({"name": split_name(index), "speed": fps / 60.0, "frame_start": frames[0], "frame_end": frames[-1]})
    return splits


def store_armature_animation(armature, action, splits, animation_types, archive=None, material_actions=None):
    """Add the animation an armature plays to its export settings (level5_archive.animations).

    action: the armature action, which its meshes play too (bones and UV curves); material_actions:
    {material name: action} of the material animations. archive: 3DS archive name, which also names the
    animation (an animation archive holds one animation, named like the archive). The splits are only
    ranges of the action shown on the timeline, like Studio Eleven's import they get no action of their own.
    """
    from studio_eleven.operators.io import xpck_settings

    settings = armature.level5_archive
    name = action.name
    if archive:
        settings.archive_name = archive
        name = animation_name(archive)
    # Bones, texprojs and materials of the armature, which the export lists
    xpck_settings.sync_archive_settings(armature)
    animation = xpck_settings.add_animation(settings, name, action, material_actions or {})
    for animation_type in ANIMATION_TYPES:
        if animation_type in animation_types:
            xpck_settings.set_animation_settings(animation.get_animation(animation_type), name, splits)
        else:
            animation.get_animation(animation_type).include = False
    xpck_settings.setup_timeline(armature)


def store_camera(context, camera_obj, name, frame, speed, archive=None):
    camera_eleven = camera_obj.parent
    if camera_eleven is not None:
        camera_eleven.level5_camera.animation_name = name
        camera_eleven.level5_camera.speed = max(0.1, speed)
        if archive:
            camera_eleven.level5_camera.archive_name = archive

    # Switch to this camera when the timeline reaches it
    marker = context.scene.timeline_markers.new(camera_obj.name, frame=frame)
    marker.camera = camera_obj
    if frame == 0 or context.scene.camera is None:
        context.scene.camera = camera_obj
