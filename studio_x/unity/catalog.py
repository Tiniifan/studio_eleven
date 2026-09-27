"""Find importable content in loaded files: models, the clips that drive them, timelines and cameras.

Clips are matched to a model either through a Timeline (PlayableDirector scene bindings) or by
checking how many of the clip's binding paths exist under the model's hierarchy.
"""

from . import animation
from .scene import Scene

KIND_MODEL = "MODEL"
KIND_CAMERA = "CAMERA"

RENDERER_TYPES = ("MeshRenderer", "SkinnedMeshRenderer")
MIN_CLIP_MATCH = 0.5


class TimelineClip:
    __slots__ = ("clip_info", "start", "duration", "clip_in", "time_scale")

    def __init__(self, clip_info, start, duration, clip_in, time_scale):
        self.clip_info = clip_info
        self.start = start
        self.duration = duration
        self.clip_in = clip_in
        self.time_scale = time_scale or 1.0


class TimelineTrack:
    def __init__(self, name, timeline_name, clips):
        self.name = name
        self.timeline_name = timeline_name
        self.clips = sorted(clips, key=lambda c: c.start)
        # Start times of the timeline cuts and end of the timeline, shared by every track of the timeline
        self.cuts = [c.start for c in self.clips]
        self.duration = max((c.start + c.duration for c in self.clips), default=0.0)


class ModelEntry:
    def __init__(self, sfile, scene, node, kind):
        self.sfile = sfile
        self.scene = scene
        self.node = node
        self.kind = kind
        self.clips = []       # ObjectInfo of AnimationClips matching this model
        self.tracks = []      # TimelineTrack bound to this model
        self._path_table = None

    @property
    def key(self):
        return "%s|%d" % (self.sfile.name, self.node.obj.path_id)

    @property
    def name(self):
        return self.node.name

    @property
    def path_table(self):
        if self._path_table is None:
            self._path_table = animation.build_path_table(
                [n.relative_path(self.node) for n in self.node.walk()])
        return self._path_table

    def import_sources(self):
        """What importing this entry brings: every timeline track, then the clips no track plays.

        A camera with a timeline only gets its tracks: its clips are the timeline's cuts and would
        otherwise become extra cameras all starting at frame 0.
        """
        used = {clip.clip_info.path_id for track in self.tracks for clip in track.clips}
        if self.kind == KIND_CAMERA and self.tracks:
            return list(self.tracks), []
        extra = [clip for clip in self.clips if clip.path_id not in used]
        return list(self.tracks), sorted(extra, key=lambda clip: clip.peek_name() or "")

    def renderer_count(self):
        return sum(1 for n in self.node.walk() for t in RENDERER_TYPES if n.get_component(t))


def _is_camera(node):
    if node.get_component("Camera"):
        return True
    for info in node.components.get("MonoBehaviour", []):
        try:
            data = info.read()
        except Exception:
            continue
        if "Lens" in data or "m_Lens" in data:
            return True
    return False


def _clip_match(clip_info, entry):
    """Return (ratio of the clip's bindings found in the model, number of distinct paths found)."""
    try:
        bindings = clip_info.read()["m_ClipBindingConstant"]["genericBindings"]
    except Exception:
        return 0.0, 0
    # The root path (hash 0) exists in every hierarchy, so it only counts for cameras/leaf nodes
    children = [b for b in bindings if b["path"] != 0]
    if not children:
        matched = bool(bindings) and (entry.kind == KIND_CAMERA or not entry.node.children)
        return (1.0, 1) if matched else (0.0, 0)
    table = entry.path_table
    found = [b["path"] for b in children if b["path"] in table]
    return len(found) / len(children), len(set(found))


def _read_timelines(sfile, scene, models_by_animator):
    for director_info in sfile.objects.values():
        if director_info.type_name != "PlayableDirector":
            continue
        director = director_info.read()
        timeline_info = sfile.get_object(director.get("m_PlayableAsset"))
        if timeline_info is None:
            continue
        timeline = timeline_info.read()
        bindings = {b["key"]["m_PathID"]: b["value"] for b in director.get("m_SceneBindings", [])}

        timeline_tracks = []
        pending = list(timeline.get("m_Tracks", []))
        while pending:
            track_info = sfile.get_object(pending.pop(0))
            if track_info is None:
                continue
            track = track_info.read()
            pending.extend(track.get("m_Children", []))
            bound = bindings.get(track_info.path_id)
            model = models_by_animator.get(bound["m_PathID"]) if bound else None
            if model is None:
                continue
            clips = []
            for clip in track.get("m_Clips", []):
                asset_info = sfile.get_object(clip.get("m_Asset"))
                if asset_info is None:
                    continue
                clip_info = sfile.get_object(asset_info.read().get("m_Clip"))
                if clip_info is None or clip_info.type_name != "AnimationClip":
                    continue
                clips.append(TimelineClip(clip_info, clip["m_Start"], clip["m_Duration"],
                                          clip.get("m_ClipIn", 0.0), clip.get("m_TimeScale", 1.0)))
            if clips:
                timeline_track = TimelineTrack(track.get("m_Name", ""), timeline.get("m_Name", ""), clips)
                model.tracks.append(timeline_track)
                timeline_tracks.append(timeline_track)

        # The track with the most clips (usually the camera) gives the cuts of the whole timeline
        if timeline_tracks:
            cuts = max(timeline_tracks, key=lambda t: len(t.clips)).cuts
            end = max(t.duration for t in timeline_tracks)
            for timeline_track in timeline_tracks:
                timeline_track.cuts = cuts
                timeline_track.duration = end


def build_catalog(environment):
    """Return the list of ModelEntry found in every loaded SerializedFile."""
    entries = []
    for sfile in environment.serialized_files.values():
        scene = Scene(sfile)
        models_by_animator = {}
        file_entries = []

        for node in scene.all_nodes():
            animator = node.get_component("Animator")
            if animator is None:
                continue
            entry = ModelEntry(sfile, scene, node, KIND_CAMERA if _is_camera(node) else KIND_MODEL)
            models_by_animator[animator.path_id] = entry
            file_entries.append(entry)

        # Renderer hierarchies without any Animator are still importable as static models
        covered = set()
        for entry in file_entries:
            covered.update(id(n) for n in entry.node.walk())
        for root in scene.roots:
            nodes = list(root.walk())
            if any(id(n) in covered for n in nodes):
                continue
            if any(n.get_component(t) for n in nodes for t in RENDERER_TYPES):
                file_entries.append(ModelEntry(sfile, scene, root, KIND_MODEL))

        _read_timelines(sfile, scene, models_by_animator)

        # A clip already driven by a PlayableDirector timeline track is authoritatively bound to
        # that track's model: skip it for the ratio-based matching below. Without this, a clip with
        # only self bindings (e.g. a VCam's position/rotation/FOV-as-scale) ties with any leaf model
        # that has no children of its own ("not entry.node.children" branch of _clip_match), so an
        # effect mesh with no sub-transforms (e.g. a ball's aura, single_bind) can end up importing
        # the camera's own clips as if they were its object animation.
        used_by_track = {c.clip_info.path_id for entry in file_entries for track in entry.tracks
                          for c in track.clips}
        clips = [o for o in sfile.objects.values()
                 if o.type_name == "AnimationClip" and o.path_id not in used_by_track]
        scores = {id(entry): [(c, _clip_match(c, entry)) for c in clips] for entry in file_entries}
        # A clip only goes to the models it fits best: the ball clips also partially match the
        # player hierarchy (shared "output/c_global_0_0" roots) but match the ball completely
        best = {}
        for scored in scores.values():
            for clip, (ratio, _) in scored:
                best[clip.path_id] = max(best.get(clip.path_id, 0.0), ratio)
        for entry in file_entries:
            scored = [item for item in scores[id(entry)]
                      if item[1][0] >= MIN_CLIP_MATCH and item[1][0] >= best[item[0].path_id] - 1e-6]
            scored.sort(key=lambda item: (-item[1][1], -item[1][0]))
            entry.clips = [c for c, _ in scored]
        entries.extend(file_entries)
    return entries
