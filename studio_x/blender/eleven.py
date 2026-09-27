"""Fill Studio Eleven's xpck export settings the way its own xpck import does.

Mirrors studio_eleven/operators/fileio_xpck.py (apply_animation_group, apply_animation_imports and the
camera markers of build_archive) and fileio_xcma.py set_camera_settings, so an imported Unity move can be
exported back as xpck with its animation names, split animations and cameras already filled in.
"""

import bpy

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


def _xpck_settings():
    try:
        from studio_eleven.operators import xpck_settings
    except ImportError:
        return None
    return xpck_settings


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


def create_split_actions(action, name, splits):
    """Copy each split range of the armature action into its own action starting at frame 0."""
    for split in splits:
        start, end = split["frame_start"], split["frame_end"]
        split_action = bpy.data.actions.new(name="%s_%s" % (name, split["name"]))
        split_action.use_fake_user = True
        for fcurve in action.fcurves:
            new_fcurve = split_action.fcurves.new(data_path=fcurve.data_path, index=fcurve.array_index,
                                                  action_group=fcurve.group.name if fcurve.group else "")
            # Keys were simplified, so the range edges are evaluated instead of copied
            frames = {start, end}
            frames.update(int(round(k.co.x)) for k in fcurve.keyframe_points if start <= k.co.x <= end)
            points = new_fcurve.keyframe_points
            points.add(len(frames))
            for point, frame in zip(points, sorted(frames)):
                point.co = (frame - start, fcurve.evaluate(frame))
                point.interpolation = "LINEAR"
            new_fcurve.update()


def store_armature_animation(armature, name, splits, animation_types, archive=None):
    """Fill the export settings of an armature. archive: 3DS archive name, which also names the animations
    of the included types (an animation archive holds one animation per type, named like the archive)."""
    settings_module = _xpck_settings()
    if settings_module is None or not hasattr(armature, "level5_archive"):
        return
    settings = armature.level5_archive
    if archive:
        settings.archive_name = archive
        name = animation_name(archive)
    for animation_type in ANIMATION_TYPES:
        if animation_type in animation_types:
            settings_module.set_animation_settings(settings.get_animation(animation_type), name, splits)
        else:
            settings.get_animation(animation_type).include = False
    settings_module.sync_archive_settings(armature)


def store_camera(context, camera_obj, name, frame, speed, archive=None):
    camera_eleven = camera_obj.parent
    if camera_eleven is not None and hasattr(camera_eleven, "level5_camera"):
        camera_eleven.level5_camera.animation_name = name
        camera_eleven.level5_camera.speed = max(0.1, speed)
        if archive:
            camera_eleven.level5_camera.archive_name = archive

    # Switch to this camera when the timeline reaches it
    marker = context.scene.timeline_markers.new(camera_obj.name, frame=frame)
    marker.camera = camera_obj
    if frame == 0 or context.scene.camera is None:
        context.scene.camera = camera_obj
