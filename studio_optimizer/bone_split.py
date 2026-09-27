"""Split a skinned mesh into parts that each use at most a given number of bones.

The 3DS games upload the bone palette of a mesh in one vertex shader uniform, unf_vtx_bone, which holds
72 vec4 = 24 bones in every game. The Yo-kai Watch and Snack World engines send to the GPU as many vec4 as
the mesh has bones: past 24 the palette overwrites the silhouette uniforms and the model explodes in game
(studio_eleven .docs/formats/xmpr.md, "Bones per mesh").

Covering the triangles with the fewest groups of at most N bones is NP-hard (with disjoint bone sets it is bin
packing). The usual answer is a greedy one: open a group, keep adding the triangles that bring the fewest new
bones until nothing fits anymore, then open the next group:
- F. Paanakker, "Skinned Mesh Export: Optimization", Game Developer, 2007
  (https://www.gamedeveloper.com/programming/skinned-mesh-export-optimization);
- "Splitting up skinned mesh to reduce used bones", GameDev.net, 2015
  (https://gamedev.net/forums/topic/670321-splitting-up-skinned-mesh-to-reduce-used-bones/);
- Unreal Engine cuts a skeletal mesh section the same way when it has more bones than a platform allows
  (https://dev.epicgames.com/documentation/en-us/unreal-engine/skeletal-mesh-rendering-paths-in-unreal-engine).

Triangles with the same bone set always fit in the same group, so the greedy runs on the distinct bone sets
(a few hundred) instead of the triangles. Each group starts from the largest remaining set (first fit
decreasing, as for bin packing); the candidates are ranked by new bones, then shared bones (parts stay on the
same limbs), then triangle count. Groups whose union still fits are merged at the end.
"""

MAX_BONES = 24

def _best_candidate(remaining, bones, max_bones):
    best = None
    best_key = None

    for candidate, triangles in remaining.items():
        new = len(candidate - bones)

        if len(bones) + new > max_bones:
            continue

        key = (new, -len(candidate & bones), -len(triangles))

        if best_key is None or key < best_key:
            best = candidate
            best_key = key

    return best

def _merge_groups(groups, max_bones):
    merged = True

    while merged:
        merged = False

        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if len(groups[i][0] | groups[j][0]) <= max_bones:
                    groups[i] = (groups[i][0] | groups[j][0], groups[i][1] + groups[j][1])
                    del groups[j]
                    merged = True
                    break

            if merged:
                break

    return groups

def split_by_bones(face_bones, max_bones=MAX_BONES):
    """Group faces so each group uses at most max_bones bones. face_bones: bone set of every face.

    Returns a list of face index lists, a single group when the mesh already fits. A face that uses more
    than max_bones bones alone gets a group of its own.
    """
    sets = {}

    for index, bones in enumerate(face_bones):
        sets.setdefault(frozenset(bones), []).append(index)

    if len(frozenset().union(*sets)) <= max_bones:
        return [list(range(len(face_bones)))]

    remaining = dict(sets)
    groups = []

    while remaining:
        seed = max(remaining, key=lambda s: (len(s), len(remaining[s])))
        bones = set(seed)
        members = [seed]
        del remaining[seed]

        while True:
            candidate = _best_candidate(remaining, bones, max_bones)

            if candidate is None:
                break

            bones |= candidate
            members.append(candidate)
            del remaining[candidate]

        groups.append((frozenset(bones), members))

    groups = _merge_groups(groups, max_bones)

    return [sorted(face for member in members for face in sets[member]) for _, members in groups]
