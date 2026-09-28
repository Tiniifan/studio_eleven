"""Unity (Cinemachine) cameras -> Studio Eleven CameraEleven (camera + target + lens + roll).

Uses CameraElevenObject from studio_eleven/controls/camera.py and the same keyframed properties
as studio_eleven/operators/fileio_xcma.py create_camera(), so ExportXCMA can write them back.
The Unity camera looks along its local +Z; the target is placed along that axis.

Measured against the 3DS cameras of whs0001 and who0003:
    - the .cmr2 "focal_length" track is the full vertical field of view in radians: ShippuuDash (who0003)
      keeps the 3DS FOV and matches to 4 decimals (Unity 35.05 deg = 0.6117, 18.9 deg = 0.3300).
      FireTornado's Unity FOVs were retouched for Inazuma Eleven Cross and cannot be compared.
      Studio Eleven writes it as `lens - 33`, so the lens holds 33 + that value and the sensor height is
      animated to keep Blender's preview at the right field of view;
    - the .cmr2 roll value equals minus the Unity roll angle in radians. Studio Eleven imports and exports
      it unchanged in rotation_euler.z, so the camera stores it as is;
    - the field of view of a move spans the long side of the screen. Inazuma Eleven Cross (portrait 9:16)
      uses it as the vertical FOV; Inazuma Eleven Victory Road (16:9) plays the same camera clips with it as
      the horizontal FOV (Ocean Birth against its Victory Road version: players 1.8 to 1.9 times larger than
      the same camera with a vertical FOV, 1.78 expected). A landscape screen, the 3DS one included, gets
      that horizontal FOV and a narrower vertical one; the camera keeps its position. That framing fits
      Flame Dance in the 3DS game but Ocean Birth wants about 0.7 times its size (its subjects stand 30 to 180
      units away, Flame Dance's 7 to 22): no geometric rule gives both, so the Camera Zoom option (and the Studio
      X panel after the import) scales tan(FOV / 2);
    - every focal key is exported (lens keyed on the camera object's action, see _write_lens);
    - each split camera is named after its split ("01", "02"...): the game looks cameras up by that hash;
    - speed 0.5 plays 30 fps keys on the 60 Hz game loop;
    - camera keys match Unity time f / 30 without the +1/60 used for bones (roll error 0.0005 rad).
"""

import math

import bpy
from mathutils import Matrix, Vector

from . import animations, convert, eleven
from ..unity import animation

# Offset applied by studio_eleven/operators/fileio_xcma.py between the lens and the focal_length track
ELEVEN_LENS_OFFSET = 33.0


def screen_vertical_fov(fov_degrees, aspect):
    """Vertical FOV (degrees) showing a move's FOV along the long side of a width / height screen."""
    if aspect <= 1.0:
        return fov_degrees
    half = math.radians(max(1.0, min(179.0, fov_degrees))) * 0.5
    return math.degrees(2.0 * math.atan(math.tan(half) / aspect))


def _lens_field_of_view(node):
    for info in node.components.get("MonoBehaviour", []):
        data = info.read()
        lens = data.get("Lens") or data.get("m_Lens")
        if lens and data.get("m_Enabled", 1):
            return lens.get("FieldOfView", 60.0)
    camera = node.get_component("Camera")
    if camera is not None:
        return camera.read().get("field of view", 60.0)
    return 60.0


def vertical_fov_to_eleven(fov_degrees):
    """Unity vertical FOV (degrees) -> value of the .cmr2 focal_length track (vertical FOV, radians)."""
    return math.radians(max(1.0, min(179.0, fov_degrees)))


# Custom properties of a camera: its focal values before the zoom, their frames and the zoom it shows
FOCALS_PROPERTY = "studio_x_focals"
FRAMES_PROPERTY = "studio_x_frames"
ZOOM_PROPERTY = "studio_x_zoom"
MAX_FOCAL = math.radians(179.0)


def zoomed_focal(focal_value, zoom):
    """Focal value (vertical FOV, radians) making everything zoom times larger on screen.

    No single rule frames every move like the game wants: Flame Dance was validated with the long side rule
    as is, Ocean Birth about 0.7 times as large (its subjects stand much further from the camera), so the
    zoom is left to the user."""
    return min(2.0 * math.atan(math.tan(focal_value * 0.5) / max(zoom, 1e-3)), MAX_FOCAL)


def is_studio_x_camera(camera):
    return FOCALS_PROPERTY in camera.keys()


def apply_zoom(camera, zoom):
    """Rewrite the lens of a camera made by studio_x for another zoom, exactly as an import with that zoom."""
    focals = [zoomed_focal(value, zoom) for value in camera[FOCALS_PROPERTY]]
    frames = list(camera[FRAMES_PROPERTY])
    lenses = [eleven_lens(value) for value in focals]
    sensors = [preview_sensor_height(value) for value in focals]
    camera.data.lens = lenses[0]
    camera.data.sensor_height = sensors[0]
    action = camera.animation_data.action if camera.animation_data else None
    if action is not None:
        for curve in [c for c in action.fcurves if c.data_path in ("data.lens", "data.sensor_height")]:
            action.fcurves.remove(curve)
        if len(frames) > 1:
            _write_lens(action, frames, lenses, sensors)
    camera[ZOOM_PROPERTY] = zoom


def _write_lens(action, frames, lenses, sensors):
    # The lens is keyed in the camera object's action ("data.lens"): Studio Eleven's cmr2 export only reads
    # that action, and wrote the focal of the first and last keys alone from the camera data's own action.
    # The game then drew a straight line between them (Ocean Birth's first shot widens from 0.52 to 0.67 rad
    # and narrows back to 0.37: far too close in the middle of the shot)
    animations.write_curve(action, "data.lens", 0, frames, lenses, 1e-4)
    animations.write_curve(action, "data.sensor_height", 0, frames, sensors, 1e-3)


def eleven_lens(focal_value):
    return ELEVEN_LENS_OFFSET + focal_value


def preview_sensor_height(focal_value):
    """Sensor height giving the real vertical FOV with the lens Studio Eleven needs for export."""
    return 2.0 * eleven_lens(focal_value) * math.tan(focal_value * 0.5)


def _parent_world(node, scale):
    matrix = Matrix.Identity(4)
    chain = []
    walker = node.parent
    while walker is not None:
        chain.append(walker)
        walker = walker.parent
    for parent in reversed(chain):
        matrix = matrix @ convert.local_matrix(parent.position, parent.rotation, parent.scale, scale)
    return matrix


def camera_name(source, index):
    return "%s_%03d" % (source.name, index)


def build_cameras(context, entry, source, options):
    """Create CameraEleven objects: one per timeline clip when split_camera is set, else a single one."""
    speed_factor = options.fps / 60.0
    # Every camera of a move lives in the same <waza>_cam.xv archive
    archive = eleven.camera_archive_name(options.waza_name)
    if source is None:
        camera = _build_camera(context, entry, entry.name, [0], [(None, 0.0)], options).camera_obj
        eleven.store_camera(context, camera, entry.name, 0, speed_factor, archive)
        return [camera]

    sampler = animations.Sampler(source, options, options.camera_frame_offset)
    if not options.split_camera or len(source.segments) == 1:
        camera = _build_camera(context, entry, source.name, sampler.frames, sampler.samples, options).camera_obj
        eleven.store_camera(context, camera, source.name, 0, source.segments[0][3] * speed_factor, archive)
        return [camera]

    cameras = []
    for index, segment in enumerate(source.segments):
        # Keys stay at their global frames, like studio_eleven's xpck camera import
        frames = source.segment_frames(index, options.fps)
        samples = [source.locate_in(index, frame / options.fps + sampler.offset) for frame in frames]
        camera = _build_camera(context, entry, camera_name(source, index), frames, samples, options).camera_obj
        eleven.store_camera(context, camera, eleven.split_name(index), frames[0], segment[3] * speed_factor, archive)
        cameras.append(camera)
    return cameras


class CameraSampler:
    """Evaluate a Unity camera node in Studio Eleven's Blender space (Z-up, mirrored X, scaled)."""

    def __init__(self, entry, options):
        self.node = entry.node
        self.scale = options.scale
        self.static_fov = _lens_field_of_view(self.node)
        self.parent_world = convert.Y_UP_TO_Z_UP @ _parent_world(self.node, self.scale)

    def _transform(self, clip, time):
        node = self.node
        bindings = {}
        if clip is not None:
            for binding in clip.bindings:
                if binding.path_hash == 0 and binding.type_id == animation.CLASS_TRANSFORM:
                    bindings[binding.attribute] = binding
        t = time + animations.STEP_EPSILON
        position = bindings[animation.TRANSFORM_POSITION].evaluate(t) if animation.TRANSFORM_POSITION in bindings else node.position
        if animation.TRANSFORM_ROTATION in bindings:
            rotation = bindings[animation.TRANSFORM_ROTATION].evaluate(t)
        elif animation.TRANSFORM_EULER in bindings:
            rotation = convert.euler_zxy_to_quaternion(bindings[animation.TRANSFORM_EULER].evaluate(t))
        else:
            rotation = node.rotation
        local_scale = bindings[animation.TRANSFORM_SCALE].evaluate(t) if animation.TRANSFORM_SCALE in bindings else node.scale
        return position, rotation, local_scale

    def pose(self, clip, time):
        """Return (location, forward, fov_degrees, roll) at a clip's local time, roll in .cmr2 units."""
        position, rotation, local_scale = self._transform(clip, time)
        world = self.parent_world @ convert.trs_matrix(convert.position(position, self.scale), convert.rotation(rotation).normalized(), (1.0, 1.0, 1.0))
        axes = world.to_3x3().normalized()
        forward = (axes @ Vector((0.0, 0.0, 1.0))).normalized()
        up = (axes @ Vector((0.0, 1.0, 0.0))).normalized()

        # This game animates the vertical FOV through the camera's localScale.x
        fov = local_scale[0] if 1.0 < local_scale[0] < 179.0 else self.static_fov
        # Roll: angle between the camera up vector and the world-up projected on the view plane.
        # The 3DS roll turns the other way, hence the sign (checked on the four whs0001 cuts).
        world_up = Vector((0.0, 0.0, 1.0))
        reference = world_up - forward * world_up.dot(forward)
        roll = 0.0
        if reference.length > 1e-6:
            reference.normalize()
            roll = -math.atan2(forward.dot(reference.cross(up)), reference.dot(up))
        return world.translation.copy(), forward, fov, roll


def _build_camera(context, entry, name, frames, samples, options):
    from studio_eleven.controls import CameraElevenObject

    sampler = CameraSampler(entry, options)
    camera_eleven = CameraElevenObject.create(name, [0.0, 0.0, 0.0])
    camera = camera_eleven.camera_obj
    target = camera_eleven.target_obj
    camera.data.sensor_fit = "VERTICAL"

    locations, targets, lenses, sensors, rolls, focals = [], [], [], [], [], []
    distance = options.camera_target_distance * options.scale
    for clip, time in samples:
        origin, forward, fov, roll = sampler.pose(clip, time)
        focals.append(vertical_fov_to_eleven(screen_vertical_fov(fov, options.screen_aspect)))
        focal_value = zoomed_focal(focals[-1], options.camera_zoom)
        locations.append(origin)
        targets.append(origin + forward * distance)
        lenses.append(eleven_lens(focal_value))
        sensors.append(preview_sensor_height(focal_value))
        # Already in radians, stored as is like studio_eleven/operators/fileio_xcma.py create_camera()
        rolls.append(roll)

    camera.location = locations[0]
    target.location = targets[0]
    camera.data.lens = lenses[0]
    camera.data.sensor_height = sensors[0]
    camera.rotation_euler = (0.0, 0.0, rolls[0])
    # What the Studio X panel needs to change the zoom later (apply_zoom)
    camera[FOCALS_PROPERTY] = focals
    camera[FRAMES_PROPERTY] = list(frames)
    camera[ZOOM_PROPERTY] = options.camera_zoom
    if samples[0][0] is None:
        return camera_eleven

    for obj, values in ((camera, locations), (target, targets)):
        obj.animation_data_create()
        action = bpy.data.actions.new("%s.%s" % (name, obj.name))
        obj.animation_data.action = action
        for index in range(3):
            animations.write_curve(action, "location", index, frames, [v[index] for v in values], 1e-4 * options.scale)
        if obj is camera:
            animations.write_curve(action, "rotation_euler", 2, frames, rolls, 1e-6)
            _write_lens(action, frames, lenses, sensors)
    return camera_eleven
