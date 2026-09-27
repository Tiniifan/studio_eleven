"""Billboards: the game turns some nodes (flag of the .mbn) and meshes (bits 8-9 of the draw priority) to the camera every frame."""

from math import atan2, radians

from mathutils import Matrix

# Same name as the importer gives it (fileio_animation_manager), the flag of the .mbn node
BONE_FLAG_PROPERTY = "level5_flag"

FACE_CAMERA = 1
FACE_CAMERA_YAW = 2

# The importer turns the Y up space of the game into the Z up space of Blender on the armature object
GAME_AXES = Matrix.Rotation(radians(90), 3, 'X')

##########################################
# Billboard Function
##########################################

def normalized(matrix):
    matrix = matrix.copy()

    for index in range(3):
        matrix.col[index] = matrix.col[index].normalized()

    return matrix


def node_mode(bone):
    flag = bone.get(BONE_FLAG_PROPERTY)

    if flag is None:
        return 0

    return int(flag) & 3


def mesh_mode(draw_priority):
    return (draw_priority >> 8) & 3


def facing_rotation(mode, armature_world, camera_world, position):
    """Rotation of the node in the space of the model: the axes of the camera, or a turn around the up axis of the game towards it."""
    model = normalized(armature_world.to_3x3())

    if mode == FACE_CAMERA:
        return model.inverted() @ normalized(camera_world.to_3x3())

    direction = GAME_AXES.inverted() @ (camera_world.translation - position)

    yaw = 0.0
    if direction.x != 0.0 or direction.z != 0.0:
        yaw = atan2(direction.x, direction.z)

    return Matrix.Rotation(yaw, 3, 'Y') @ (GAME_AXES.inverted() @ model).inverted()


def rotated_channels(armature):
    """Bones whose rotation is animated: a billboard node without rotation track keeps no rotation of its own."""
    names = set()
    animation = armature.animation_data

    if animation is None:
        return names

    actions = []
    if animation.action is not None:
        actions.append(animation.action)

    for track in animation.nla_tracks:
        for strip in track.strips:
            if strip.action is not None:
                actions.append(strip.action)

    for action in actions:
        for fcurve in action.fcurves:
            if fcurve.data_path.startswith('pose.bones["') and fcurve.data_path.endswith(('rotation_quaternion', 'rotation_euler')):
                names.add(fcurve.data_path[len('pose.bones["'):fcurve.data_path.index('"]')])

    return names


def turned_bones(armature, camera_world):
    """Pose matrices of the billboard nodes and of every node under them, turned to the camera like the game does."""
    bones = armature.data.bones
    turned = {}

    billboards = [bone for bone in bones if node_mode(bone) in (FACE_CAMERA, FACE_CAMERA_YAW)]
    if len(billboards) == 0:
        return turned

    armature_world = armature.matrix_world
    pose_bones = armature.pose.bones
    rotated = rotated_channels(armature)

    # Parents first, a child reads the turned matrix of its parent
    pending = [bone for bone in bones if bone.parent is None]

    while pending:
        bone = pending.pop(0)
        pending.extend(bone.children)

        mode = node_mode(bone)
        pose = pose_bones[bone.name].matrix
        parent_turned = None
        parent_pose = Matrix.Identity(4)

        if bone.parent is not None:
            parent_turned = turned.get(bone.parent.name)
            parent_pose = pose_bones[bone.parent.name].matrix

        if mode not in (FACE_CAMERA, FACE_CAMERA_YAW) and parent_turned is None:
            continue

        parent = parent_pose
        if parent_turned is not None:
            parent = parent_turned

        local = parent_pose.inverted() @ pose

        if mode in (FACE_CAMERA, FACE_CAMERA_YAW):
            # The animated rotation is applied after the camera one, a node without rotation track has none
            rotation = Matrix.Identity(3)
            if bone.name in rotated:
                rotation = local.to_quaternion().to_matrix()

            position = armature_world @ (parent @ local.translation)
            facing = facing_rotation(mode, armature_world, camera_world, position)
            local = Matrix.Translation(local.translation) @ (facing @ rotation @ Matrix.Diagonal(local.to_scale())).to_4x4()

        turned[bone.name] = parent @ local

    return turned


def turn_mesh(armature, bone_name, draw_priority, camera_world, matrix_world, turned):
    """World matrix of a mesh fixed on a bone once its node or itself faces the camera, the matrix as it is otherwise."""
    pose_bone = armature.pose.bones.get(bone_name)
    if pose_bone is None:
        return matrix_world

    armature_world = armature.matrix_world
    pose = pose_bone.matrix
    node = turned.get(bone_name, pose)
    mode = mesh_mode(draw_priority)

    if mode in (FACE_CAMERA, FACE_CAMERA_YAW):
        # Only the node of the mesh turns, with its own scale and its place after the skeleton
        local_scale = pose_bone.scale
        if pose_bone.parent is not None:
            local_scale = (pose_bone.parent.matrix.inverted() @ pose).to_scale()

        facing = facing_rotation(mode, armature_world, camera_world, armature_world @ node.translation)
        node = Matrix.Translation(node.translation) @ (facing @ Matrix.Diagonal(local_scale)).to_4x4()
    elif bone_name not in turned:
        return matrix_world

    return armature_world @ node @ pose.inverted() @ armature_world.inverted() @ matrix_world
