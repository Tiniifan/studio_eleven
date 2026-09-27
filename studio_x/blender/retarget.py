"""Replace Unity players ("Ally ...", "Opponent ...") and balls ("Ball ...") by the 3DS default armatures and
retarget their animations onto them.

The armatures (data/default_armatures.json) are the bones Studio Eleven builds from the 3DS files
uaa0001/uba0001/usa0001/uta0001 (normal/fat/small/tall bodies) and bal00 (ball), extracted by
research-help/agent-script/extract_default_armatures.py.

Rules measured on FireTornado (Unity "Ally 0" / "Ball 0") against the same move on 3DS, whs0001_aa1 on the
normal body and whs0001_bl1 on the ball, plus the game's own fat/small/tall versions (ba1/sa1/ta1), see
research-help/agent-script/analyze_retarget.py:
- the Victory Road player bones share the frames of the 3DS normal body (c_c_1_0 = c_c1, r_a_1_1 = r_a3...)
  except the hands, turned by 90 degrees on Z (thumbs have their own offset): with W_3ds = W_unity * C,
  L_3ds = C_parent^-1 * L_unity * C;
- the game adapts a normal body animation to another body with rest_body * rest_normal^-1 * rotation
  (exact on every bone the animators did not retouch), keeps the body rest translations and moves the
  hips by the difference of rest hip heights;
- ball: local transforms are copied (rot = c_c_1_0 relative to output, add = c_add_1_0), scale included.
Hair and cape bones have no reliable Unity equivalent (their rigs depend on the character) and keep their
rest pose.
"""

import json
import math
import os
import re

import bpy
from mathutils import Euler, Matrix, Vector

from . import animations, convert, eleven

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "default_armatures.json")

BODY = "body"
BALL = "ball"
BODY_KINDS = ("fat", "normal", "small", "tall")
# Node name prefix -> role, used for the replacement and for the 3DS archive names, ignoring case: Ocean
# Birth names its ball "ball_b000002" where FireTornado says "Ball 0". The "... Root" nodes only hold the
# player node itself.
ROLES = (("Ally Root", None), ("Opponent Root", None), ("Ally", "ally"), ("Opponent", "opponent"), ("Ball", "ball"))


def _sided(table):
    """Expand "s_" entries into the l_ and r_ bones. Offsets (XYZ euler degrees) are given for the left side
    and mirrored on X for the right side, like the Studio Eleven space."""
    bones = {}
    for bone, (sources, offset) in table.items():
        if not bone.startswith("s_"):
            bones[bone] = (sources, offset)
            continue
        for side, sign in (("l", 1.0), ("r", -1.0)):
            mirrored = None if offset is None else (offset[0], sign * offset[1], sign * offset[2])
            bones[side + bone[1:]] = (tuple(side + source[1:] for source in sources), mirrored)
    return bones


class Profile:
    def __init__(self, kinds, reference, bones, root, rest_translation, hips=None, legs=()):
        self.kinds = kinds
        self.reference = reference      # 3DS armature whose bone frames match the Unity rig
        self.bones = bones              # 3DS bone -> (Unity node names by preference, frame offset)
        self.root = root
        self.rest_translation = rest_translation  # translations come from the 3DS rest, except root/hips
        self.hips = hips
        self.legs = legs                # bones whose lengths give the leg length (hip height ratio)


PROFILES = {
    BODY: Profile(
        BODY_KINDS, "normal",
        _sided({
            "Output": (("output",), None),
            "c_c1": (("c_c_1_0",), None),
            "c_c2": (("c_c_1_1",), None),
            "c_c3": (("c_n_1_0",), None),
            "c_head": (("c_head_1_0",), None),
            "s_a1": (("s_s_1_0",), None),
            "s_a2": (("s_a_1_0",), None),
            "s_a3": (("s_a_1_1",), None),
            "s_a4": (("s_w_1_0",), (0.0, 0.0, 90.0)),
            "s_a51": (("s_thb_1_0",), (-53.0, 4.0, 94.0)),
            "s_a61": (("s_mid_1_0", "s_idx_1_0"), (0.0, 0.0, 90.0)),
            "s_a71": (("s_pky_1_0", "s_rng_1_0"), (0.0, 0.0, 90.0)),
            "s_l1": (("s_l_1_0",), None),
            "s_l2": (("s_l_1_1",), None),
            "s_l3": (("s_foot_1_0",), None),
            "s_l4": (("s_foot_1_1",), None),
        }),
        root="Output", rest_translation=True, hips="c_c1", legs=("r_l2", "r_l3")),
    BALL: Profile(
        ("ball",), "ball",
        {"bl1_output": (("output",), None), "rot": (("c_c_1_0",), None), "add": (("c_add_1_0",), None)},
        root="bl1_output", rest_translation=False),
}

_armatures = None


def default_armatures():
    """{kind: {"bones": [{name, parent, matrix, length, deform}]}} (cached)."""
    global _armatures
    if _armatures is None:
        with open(DATA_PATH, "r") as stream:
            _armatures = json.load(stream)
    return _armatures


def role_of(entry):
    """"ally", "opponent" or "ball" from the node name, None for anything else."""
    name = entry.name.lower()
    for prefix, role in ROLES:
        if name.startswith(prefix.lower()):
            return role
    return None


def index_of(entry):
    """Number of the node ("Ally 2" -> 2), 0 when it has none: the 3DS archives number them from 1.
    Only a separate number counts: the digits of "ball_b000002" are the model id, not an index."""
    match = re.search(r"(?:^|\s)(\d+)\s*$", entry.name)
    return int(match.group(1)) if match else 0


def replacement(entry):
    """BODY or BALL when a 3DS armature replaces this Unity model, else None."""
    role = role_of(entry)
    names = {node.name for node in entry.node.walk()}
    if role == "ball" and "c_c_1_0" in names:
        return BALL
    if role in ("ally", "opponent") and {"c_c_1_0", "c_c_1_1"} <= names:
        return BODY
    return None


class RestSkeleton:
    """Rest matrices of a default armature: armature space and relative to the parent bone."""

    def __init__(self, kind):
        bones = default_armatures()[kind]["bones"]
        self.kind = kind
        self.bones = bones
        self.parent = {bone["name"]: bone["parent"] for bone in bones}
        self.matrix = {bone["name"]: Matrix(bone["matrix"]) for bone in bones}
        self.relative = {}
        for name, matrix in self.matrix.items():
            parent = self.parent[name]
            self.relative[name] = self.matrix[parent].inverted() @ matrix if parent else matrix.copy()


def build_default_armature(context, kind, name):
    """Create a default 3DS armature exactly as Studio Eleven imports it (Y-up data turned by 90 degrees on X)."""
    skeleton = RestSkeleton(kind)
    armature_data = bpy.data.armatures.new(name)
    armature = bpy.data.objects.new(name, armature_data)
    context.collection.objects.link(armature)
    armature.rotation_euler = convert.ARMATURE_ROTATION
    armature["studio_x_3ds_model"] = kind

    for obj in context.view_layer.objects:
        obj.select_set(False)
    armature.select_set(True)
    context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    for bone in skeleton.bones:
        edit_bone = armature_data.edit_bones.new(bone["name"])
        edit_bone.head = (0.0, 0.0, 0.0)
        edit_bone.tail = (0.0, bone["length"], 0.0)
        edit_bone.matrix = skeleton.matrix[bone["name"]]
        edit_bone.use_deform = bone["deform"]
        if bone["parent"]:
            edit_bone.parent = armature_data.edit_bones[bone["parent"]]
    bpy.ops.object.mode_set(mode="OBJECT")
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"

    if hasattr(armature, "level5_archive"):
        # Like the 3DS move archives (whs0001_aa1): the body itself comes from the game
        armature.level5_archive.export_mode = "ANIMATION"
    return armature, skeleton


class _Mapping:
    """Unity nodes of the profile bones, and the frame offsets of the mapped bones."""

    def __init__(self, profile, model_node, reference):
        by_name = {}
        for node in model_node.walk():
            by_name.setdefault(node.name, node)
        self.profile = profile
        self.model_node = model_node
        self.sources = {}
        self.offsets = {}
        for bone, (candidates, offset) in profile.bones.items():
            node = next((by_name[c] for c in candidates if c in by_name), None)
            if node is None or bone not in reference.parent:
                continue
            self.sources[bone] = node
            self.offsets[bone] = Euler([math.radians(a) for a in offset], "XYZ").to_matrix().to_4x4() if offset else Matrix.Identity(4)
        self.reference = reference
        # Closest mapped ancestor of every mapped bone (None: the Unity model space)
        self.parent = {}
        for bone in self.sources:
            parent = reference.parent[bone]
            while parent is not None and parent not in self.sources:
                parent = reference.parent[parent]
            self.parent[bone] = parent

    def local(self, bone, worlds):
        """Unity local matrix of a bone expressed in the frames of the reference 3DS armature."""
        parent = self.parent[bone]
        world = worlds[id(self.sources[bone])]
        if parent is None:
            return world @ self.offsets[bone]
        return self.offsets[parent].inverted() @ worlds[id(self.sources[parent])].inverted() @ world @ self.offsets[bone]


def _world_matrices(model_node, locals_of):
    worlds = {}

    def walk(node, parent_matrix):
        matrix = parent_matrix @ locals_of(node)
        worlds[id(node)] = matrix
        for child in node.children:
            walk(child, matrix)

    walk(model_node, Matrix.Identity(4))
    return worlds


def _static_worlds(model_node, scale):
    return _world_matrices(model_node, lambda n: convert.local_matrix(n.position, n.rotation, n.scale, scale))


def closest_body(entry, options):
    """Body kind whose bone lengths are the closest to the Unity rig (Transforms of the prefab)."""
    profile = PROFILES[BODY]
    reference = RestSkeleton(profile.reference)
    mapping = _Mapping(profile, entry.node, reference)
    worlds = _static_worlds(entry.node, options.scale)
    lengths = {bone: mapping.local(bone, worlds).translation.length
               for bone in mapping.sources if mapping.parent[bone] is not None and bone != profile.hips}
    scores = {}
    for kind in profile.kinds:
        skeleton = RestSkeleton(kind)
        scores[kind] = sum((length - skeleton.relative[bone].translation.length) ** 2 for bone, length in lengths.items())
    return min(profile.kinds, key=lambda kind: scores[kind]), scores


class Retargeter:
    def __init__(self, entry, kind, options):
        self.profile = PROFILES[kind]
        self.reference = RestSkeleton(self.profile.reference)
        self.mapping = _Mapping(self.profile, entry.node, self.reference)
        self.entry = entry
        self.options = options
        # Hip height of the Unity rig, from its leg length compared to the reference body
        self.source_hip_height = None
        profile = self.profile
        if profile.hips in self.mapping.sources and all(b in self.mapping.sources for b in profile.legs):
            worlds = _static_worlds(entry.node, options.scale)
            source_leg = sum(self.mapping.local(b, worlds).translation.length for b in profile.legs)
            reference_leg = sum(self.reference.relative[b].translation.length for b in profile.legs)
            if reference_leg > 1e-6:
                self.source_hip_height = self.reference.relative[profile.hips].translation.y * source_leg / reference_leg

    def sample(self, sampler):
        """Unity local matrices of the mapped bones per frame (reference frames) and the bones to key."""
        matrices, animated = animations.sample_local_matrices(self.entry.node, sampler, self.options)
        locals_per_frame = []
        for index in range(len(sampler.frames)):
            worlds = _world_matrices(self.entry.node, lambda n: matrices[id(n)][index])
            locals_per_frame.append({bone: self.mapping.local(bone, worlds) for bone in self.mapping.sources})

        keyed = []
        for bone, node in self.mapping.sources.items():
            if bone == self.profile.root:
                # The 3DS moves have no track on the root bone: only key it when Unity moves it
                chain = []
                walker = node
                while walker is not None and walker is not self.entry.node.parent:
                    chain.append(id(walker))
                    walker = walker.parent
                if not animated.intersection(chain):
                    continue
            keyed.append(bone)
        return locals_per_frame, keyed

    def bake(self, action, skeleton, sampler, sampled):
        locals_per_frame, keyed = sampled
        profile = self.profile
        for bone in keyed:
            rest = skeleton.relative[bone]
            rest_inverse = rest.inverted()
            # rest_body * rest_reference^-1 * rotation, as the game adapts its moves to the other bodies
            adapt = rest.to_quaternion() @ self.reference.relative[bone].to_quaternion().inverted()
            hip_offset = Vector((0.0, 0.0, 0.0))
            if bone == profile.hips and self.source_hip_height is not None:
                hip_offset.y = rest.translation.y - self.source_hip_height
            bases = []
            for local in locals_per_frame:
                location, rotation, scale = local[bone].decompose()
                if profile.rest_translation and bone not in (profile.root, profile.hips):
                    location = rest.translation
                else:
                    location = location + hip_offset
                matrix = convert.trs_matrix(location, (adapt @ rotation).normalized(), scale)
                bases.append(rest_inverse @ matrix)
            animations.write_bone_curves(action, bone, sampler.frames, bases, self.options.scale)


def import_replacement(context, entry, kind, sources, options, report):
    """Build the 3DS armature(s) replacing a Unity model and retarget every source onto them."""
    retargeter = Retargeter(entry, kind, options)
    if kind == BODY:
        closest, _ = closest_body(entry, options)
        report({"INFO"}, "%s: closest 3DS body is %s" % (entry.name, closest))
        kinds = [closest] + [k for k in BODY_KINDS if k != closest]
        names = ["%s_%s" % (entry.name, k) for k in kinds]
    else:
        kinds = ["ball"]
        names = [entry.name]
    missing = [b for b in retargeter.profile.bones if b not in retargeter.mapping.sources and b in retargeter.reference.parent]
    if missing:
        report({"WARNING"}, "%s: no Unity bone for %s" % (entry.name, ", ".join(sorted(missing))))

    role = role_of(entry)
    number = index_of(entry)
    archives = [eleven.model_archive_name(options.waza_name, role, number, body) for body in kinds]

    targets = [build_default_armature(context, k, n) for k, n in zip(kinds, names)]
    first_actions = {}
    for index, source in enumerate(sources):
        sampler = animations.Sampler(source, options)
        sampled = retargeter.sample(sampler)
        splits = eleven.split_animations(source, options.fps)
        for (armature, skeleton), kind_name, archive in zip(targets, kinds, archives):
            if source.is_timeline:
                name = "%s_%s" % (source.name, armature.name)
            else:
                name = source.name if kind == BALL else "%s_%s" % (source.name, kind_name)
            action = bpy.data.actions.new(name)
            if len(sources) > 1:
                action.use_fake_user = True
            retargeter.bake(action, skeleton, sampler, sampled)
            eleven.create_split_actions(action, action.name, splits)
            if index == 0:
                first_actions[armature.name] = action
                eleven.store_armature_animation(armature, action.name, splits, {"armature"}, archive)
    for armature, _ in targets:
        action = first_actions.get(armature.name)
        if action is not None:
            armature.animation_data_create()
            armature.animation_data.action = action
    return [armature for armature, _ in targets]
