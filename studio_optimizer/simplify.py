"""Mesh simplification with quadric error metrics and half-edge collapses.

Error metric: Garland & Heckbert, "Surface Simplification Using Quadric Error Metrics" (1997) and
"Simplifying Surfaces with Color and Texture using Quadric Error Metrics" (1998): each triangle adds a
quadric in (position, UVs, color) space, so collapses that distort texturing are expensive.
Topology rules (manifold / border / seam / locked vertices, half-edge collapses, link condition and
triangle flip checks) follow meshoptimizer's simplifier (https://github.com/zeux/meshoptimizer, MIT).

A half-edge collapse removes a vertex by merging it into a neighbor, so no vertex is created: kept
vertices keep their exact position, normal, UVs, colors, bone weights and blend shape deltas. Skinning,
UV (UV_WARP) and material animations therefore keep working on the simplified mesh.

Moved from studio_x (unity/simplify.py). Works on MeshData (no Blender dependency); blender_mesh.py converts
Blender meshes to and from it.
"""

import heapq

import numpy as np

# Error limit (fraction of the bounding box diagonal) and attribute weights, tuned so FireTornado's
# Unity effect meshes end up with the triangle counts of the 3DS whs0001_ef1 meshes (studio_x import)
DEFAULT_MAX_ERROR = 0.01
UV_WEIGHT = 0.35
COLOR_WEIGHT = 0.05
BORDER_WEIGHT = 4.0
# Reject collapses that rotate a remaining triangle by more than ~75 degrees
MIN_NORMAL_COS = 0.25
# Maximum L1 difference between the bone weights of merged vertices
SKIN_TOLERANCE = 0.2

MANIFOLD, BORDER, SEAM, LOCKED = range(4)

class MeshData:
    """Per-vertex arrays of a triangle mesh.

    weld_ids: optional id per vertex, vertices with different ids are never merged (Blender vertices);
    source_indices: optional value per vertex carried through apply() (used to find the kept vertices).
    """

    def __init__(self, name=""):
        self.name = name
        self.positions = []
        self.normals = []
        self.tangents = []
        self.colors = []
        self.uvs = {}
        self.bone_indices = []
        self.bone_weights = []
        # list of triangle lists, one per sub-mesh (= material slot)
        self.submeshes = []
        self.blend_shapes = []
        self.weld_ids = None
        self.source_indices = None

def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

def _normal(points):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = points
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az

    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)

class _Simplifier:
    def __init__(self, mesh):
        self.mesh = mesh
        positions = np.asarray(mesh.positions, dtype=np.float64)
        self.size = float(np.linalg.norm(positions.max(axis=0) - positions.min(axis=0))) or 1.0
        self.positions = positions / self.size

        # Plain tuples: numpy is too slow for the many 3-component operations of the flip test
        self.points = [tuple(p) for p in self.positions.tolist()]
        self.skins = self._skins()

        self._weld()
        self._build_topology()
        self._build_quadrics()

    def _skins(self):
        mesh = self.mesh

        if not mesh.bone_weights:
            return None

        skins = []

        for indices, weights in zip(mesh.bone_indices, mesh.bone_weights):
            skin = {}

            for bone, weight in zip(indices, weights):
                if weight > 0.0:
                    skin[bone] = skin.get(bone, 0.0) + weight

            skins.append(skin)

        return skins

    def _weld(self):
        """Merge vertices with identical attributes, then group vertices by position."""
        mesh = self.mesh
        count = len(self.positions)
        uv_channels = sorted(mesh.uvs)
        wedge_keys = {}
        position_keys = {}
        self.wedge_of = [0] * count
        self.position_of = [0] * count

        for index in range(count):
            position_key = tuple(np.round(self.positions[index], 6))
            key = [position_key]

            if mesh.normals:
                key.append(tuple(round(c, 3) for c in mesh.normals[index]))

            for channel in uv_channels:
                key.append(tuple(round(c, 5) for c in mesh.uvs[channel][index]))

            if mesh.colors:
                key.append(tuple(round(c, 3) for c in mesh.colors[index]))

            if self.skins:
                key.append(tuple(sorted((bone, round(w, 3)) for bone, w in self.skins[index].items())))

            if mesh.weld_ids is not None:
                key.append(mesh.weld_ids[index])

            key = tuple(key)
            self.wedge_of[index] = wedge_keys.setdefault(key, index)
            self.position_of[index] = position_keys.setdefault(position_key, len(position_keys))

        self.position_count = len(position_keys)

        # Attribute vector of every vertex: position, UVs and color
        columns = [self.positions]

        for channel in uv_channels:
            columns.append(np.asarray(mesh.uvs[channel], dtype=np.float64) * UV_WEIGHT)

        if mesh.colors:
            columns.append(np.asarray([tuple(c) + (1.0,) * (4 - len(c)) for c in mesh.colors], dtype=np.float64) * COLOR_WEIGHT)

        self.vectors = np.hstack(columns)

    def _build_topology(self):
        self.triangles = []
        self.submesh_of = []

        for submesh, triangles in enumerate(self.mesh.submeshes):
            for triangle in triangles:
                wedges = [self.wedge_of[i] for i in triangle]

                if len({self.position_of[w] for w in wedges}) == 3:
                    self.triangles.append(wedges)
                    self.submesh_of.append(submesh)

        self.alive = [True] * len(self.triangles)

        # corners[triangle] = {position: vertex}, kept in sync with self.triangles
        self.corners = [{self.position_of[w]: w for w in wedges} for wedges in self.triangles]
        self.position_triangles = [set() for _ in range(self.position_count)]

        for index, wedges in enumerate(self.triangles):
            for wedge in wedges:
                self.position_triangles[self.position_of[wedge]].add(index)

        self.classify_cache = {}

    def _build_quadrics(self):
        count, dimension = self.vectors.shape
        self.quadric_a = np.zeros((count, dimension, dimension))
        self.quadric_b = np.zeros((count, dimension))
        self.quadric_c = np.zeros(count)
        self.quadric_weight = np.zeros(count)
        self.quadric_version = [0] * count
        self.error_cache = {}
        self.weights = [0.0] * count

        if not self.triangles:
            return

        corners = np.asarray(self.triangles)
        p1, p2, p3 = (self.vectors[corners[:, i]] for i in range(3))
        edge1 = p2 - p1
        edge2 = p3 - p1
        length1 = np.linalg.norm(edge1, axis=1)
        e1 = edge1 / np.maximum(length1, 1e-12)[:, None]
        orthogonal = edge2 - np.sum(e1 * edge2, axis=1)[:, None] * e1
        e2 = orthogonal / np.maximum(np.linalg.norm(orthogonal, axis=1), 1e-12)[:, None]
        area = 0.5 * np.linalg.norm(np.cross(edge1[:, :3], edge2[:, :3]), axis=1)
        area = np.maximum(area, 1e-12)

        identity = np.eye(dimension)
        a = identity[None] - e1[:, :, None] * e1[:, None, :] - e2[:, :, None] * e2[:, None, :]
        dot1 = np.sum(p1 * e1, axis=1)
        dot2 = np.sum(p1 * e2, axis=1)
        b = dot1[:, None] * e1 + dot2[:, None] * e2 - p1
        c = np.sum(p1 * p1, axis=1) - dot1 ** 2 - dot2 ** 2

        for corner in range(3):
            np.add.at(self.quadric_a, corners[:, corner], a * area[:, None, None])
            np.add.at(self.quadric_b, corners[:, corner], b * area[:, None])
            np.add.at(self.quadric_c, corners[:, corner], c * area)
            np.add.at(self.quadric_weight, corners[:, corner], area)

        self.weights = self.quadric_weight.tolist()

        # Border edges get a plane perpendicular to the surface so silhouettes are kept
        edge_triangles = {}

        for index, wedges in enumerate(self.triangles):
            for i in range(3):
                pa, pb = self.position_of[wedges[i]], self.position_of[wedges[(i + 1) % 3]]
                edge_triangles.setdefault((min(pa, pb), max(pa, pb)), []).append((index, wedges[i], wedges[(i + 1) % 3]))

        for items in edge_triangles.values():
            if len(items) != 1:
                continue

            index, wa, wb = items[0]
            pa = self.positions[wa]
            direction = self.positions[wb] - pa
            face_normal = np.cross(edge1[index, :3], edge2[index, :3])
            normal = np.cross(direction, face_normal)
            length = np.linalg.norm(normal)

            if length < 1e-12:
                continue

            normal /= length
            distance = -float(normal @ pa)
            weight = area[index] * BORDER_WEIGHT

            for wedge in (wa, wb):
                self.quadric_a[wedge, :3, :3] += weight * np.outer(normal, normal)
                self.quadric_b[wedge, :3] += weight * distance * normal
                self.quadric_c[wedge] += weight * distance * distance

    def _wedges_at(self, position, triangle):
        return self.corners[triangle][position]

    def _edges(self, position):
        """{neighbor position: [triangles sharing the edge]}"""
        edges = {}

        for triangle in self.position_triangles[position]:
            for other in self.corners[triangle]:
                if other != position:
                    edges.setdefault(other, []).append(triangle)

        return edges

    def _classify(self, position):
        result = self.classify_cache.get(position)

        if result is None:
            result = self.classify_cache[position] = self._classify_uncached(position)

        return result

    def _classify_uncached(self, position):
        edges = self._edges(position)

        if not edges or any(len(t) > 2 for t in edges.values()):
            return LOCKED, [], edges

        wedges = {self._wedges_at(position, t) for t in self.position_triangles[position]}
        borders = [q for q, t in edges.items() if len(t) == 1]

        if borders:
            if len(borders) == 2 and len(wedges) == 1:
                return BORDER, borders, edges

            return LOCKED, [], edges

        if len(wedges) == 1:
            return MANIFOLD, list(edges), edges

        seams = []

        for other, triangles in edges.items():
            first, second = triangles

            if (self._wedges_at(position, first) != self._wedges_at(position, second)
                    or self._wedges_at(other, first) != self._wedges_at(other, second)):
                seams.append(other)

        if len(wedges) == 2 and len(seams) == 2:
            return SEAM, seams, edges

        return LOCKED, [], edges

    def _match_wedges(self, a, b):
        """Map every vertex of position a to the vertex of b on the same side of seams."""
        mapping = {}

        for triangle in self.position_triangles[a]:
            corners = self.corners[triangle]
            wa = corners[a]
            wb = corners.get(b)

            if wb is None:
                mapping.setdefault(wa, None)
                continue

            if mapping.get(wa) not in (None, wb):
                return None

            mapping[wa] = wb

        if any(wb is None for wb in mapping.values()):
            return None

        return mapping

    def _mapping(self, a, b):
        """Wedge mapping of a -> b, or None when seams or skin weights forbid the collapse."""
        mapping = self._match_wedges(a, b)

        if mapping is None or not self.skins:
            return mapping

        for wa, wb in mapping.items():
            skin_a, skin_b = self.skins[wa], self.skins[wb]
            bones = set(skin_a) | set(skin_b)

            if sum(abs(skin_a.get(k, 0.0) - skin_b.get(k, 0.0)) for k in bones) > SKIN_TOLERANCE:
                return None

        return mapping

    def _quadric_costs(self, candidates):
        """Mean quadric error of each (b, mapping) candidate.

        Errors of (source, target) vertex pairs are cached until the source quadric changes, since most
        re-evaluations after a collapse concern untouched neighbors.
        """
        cache = self.error_cache
        missing = []

        for _, mapping in candidates:
            for pair in mapping.items():
                key = pair + (self.quadric_version[pair[0]],)

                if key not in cache:
                    missing.append(key)

        if missing:
            sources = [key[0] for key in missing]
            v = self.vectors[[key[1] for key in missing]]
            errors = (np.einsum("ij,ijk,ik->i", v, self.quadric_a[sources], v)
                      + 2.0 * np.einsum("ij,ij->i", self.quadric_b[sources], v) + self.quadric_c[sources])

            for key, error in zip(missing, errors.tolist()):
                cache[key] = error

        costs = []

        for _, mapping in candidates:
            error = sum(cache[(wa, wb, self.quadric_version[wa])] for wa, wb in mapping.items())
            weight = sum(self.weights[wa] for wa in mapping)
            costs.append(max(error, 0.0) / max(weight, 1e-12))

        return np.asarray(costs)

    def _topology_allows(self, a, b, edges):
        # Link condition: a and b may only share the vertices opposite to their common edge
        shared = set(edges) & set(self._edges(b))
        shared.discard(a)
        shared.discard(b)

        if len(shared) > len(edges[b]):
            return False

        # Remaining triangles must not flip or become degenerate
        position_b = self.points[self._any_wedge(b)]

        for triangle in self.position_triangles[a]:
            corners = self.corners[triangle]

            if b in corners:
                continue

            wedges = self.triangles[triangle]
            wa = corners[a]
            points = [self.points[w] for w in wedges]
            moved = [position_b if w == wa else p for w, p in zip(wedges, points)]
            old_normal = _normal(points)
            new_normal = _normal(moved)
            old_length = _dot(old_normal, old_normal) ** 0.5
            new_length = _dot(new_normal, new_normal) ** 0.5

            if new_length < 1e-12 or _dot(old_normal, new_normal) < MIN_NORMAL_COS * old_length * new_length:
                return False

        return True

    def _any_wedge(self, position):
        return self._wedges_at(position, next(iter(self.position_triangles[position])))

    def _best_collapse(self, a, limit, only=None):
        """Cheapest valid collapse (cost, b, mapping) of position a under the limit, or None."""
        if not self.position_triangles[a]:
            return None

        kind, targets, edges = self._classify(a)
        candidates = []

        for b in targets:
            if only is not None and b != only:
                continue

            if kind == BORDER and self._classify(b)[0] == SEAM:
                continue

            mapping = self._mapping(a, b)

            if mapping is not None:
                candidates.append((b, mapping))

        if not candidates:
            return None

        costs = self._quadric_costs(candidates)

        # Topology tests are slower: run them from the cheapest candidate up
        for index in np.argsort(costs):
            if costs[index] > limit:
                break

            b, mapping = candidates[index]

            if self._topology_allows(a, b, edges):
                return float(costs[index]), b, mapping

        return None

    def run(self, max_error):
        limit = max_error * max_error
        version = [0] * self.position_count
        heap = []

        for position in range(self.position_count):
            best = self._best_collapse(position, limit)

            if best is not None:
                heap.append((best[0], position, best[1], 0))

        heapq.heapify(heap)

        while heap:
            cost, a, b, stamp = heapq.heappop(heap)

            if stamp != version[a] or not self.position_triangles[a]:
                continue

            current = self._best_collapse(a, limit, only=b)

            if current is None:
                # The planned collapse became invalid: queue the next best one of this vertex
                best = self._best_collapse(a, limit)

                if best is not None:
                    heapq.heappush(heap, (best[0], a, best[1], stamp))

                continue

            if current[0] > cost + 1e-12:
                heapq.heappush(heap, (current[0], a, b, stamp))
                continue

            neighbors = set(self._edges(a)) | set(self._edges(b))
            self._collapse(a, b, current[2])

            for position in neighbors | {b}:
                if position == a:
                    continue

                version[position] += 1
                best = self._best_collapse(position, limit)

                if best is not None:
                    heapq.heappush(heap, (best[0], position, best[1], version[position]))

    def _collapse(self, a, b, mapping):
        # Only positions around a see their triangles change
        for position in self._edges(a):
            self.classify_cache.pop(position, None)

        self.classify_cache.pop(a, None)

        for triangle in list(self.position_triangles[a]):
            corners = self.corners[triangle]

            if b in corners:
                self.alive[triangle] = False

                for position in corners:
                    self.position_triangles[position].discard(triangle)
            else:
                wb = mapping[corners.pop(a)]
                corners[b] = wb
                self.triangles[triangle] = [wb if self.position_of[w] == a else w for w in self.triangles[triangle]]
                self.position_triangles[b].add(triangle)

        self.position_triangles[a].clear()

        for wa, wb in mapping.items():
            self.quadric_version[wb] += 1
            self.quadric_a[wb] += self.quadric_a[wa]
            self.quadric_b[wb] += self.quadric_b[wa]
            self.quadric_c[wb] += self.quadric_c[wa]
            self.quadric_weight[wb] += self.quadric_weight[wa]
            self.weights[wb] += self.weights[wa]

    def apply(self):
        """Write the remaining triangles and vertices back into the MeshData."""
        mesh = self.mesh
        used = sorted({w for index, wedges in enumerate(self.triangles) if self.alive[index] for w in wedges})
        remap = {old: new for new, old in enumerate(used)}

        def pick(values):
            return [values[i] for i in used] if values else values

        mesh.positions = pick(mesh.positions)
        mesh.normals = pick(mesh.normals)
        mesh.tangents = pick(mesh.tangents)
        mesh.colors = pick(mesh.colors)
        mesh.bone_indices = pick(mesh.bone_indices)
        mesh.bone_weights = pick(mesh.bone_weights)
        mesh.uvs = {channel: pick(values) for channel, values in mesh.uvs.items()}

        if mesh.weld_ids is not None:
            mesh.weld_ids = pick(mesh.weld_ids)

        if mesh.source_indices is not None:
            mesh.source_indices = pick(mesh.source_indices)

        mesh.blend_shapes = [(name, {remap[i]: d for i, d in deltas.items() if i in remap})
                             for name, deltas in mesh.blend_shapes]
        submeshes = [[] for _ in mesh.submeshes]

        for index, wedges in enumerate(self.triangles):
            if self.alive[index]:
                submeshes[self.submesh_of[index]].append(tuple(remap[w] for w in wedges))

        mesh.submeshes = submeshes

def simplify_mesh(mesh, max_error=DEFAULT_MAX_ERROR):
    """Simplify a MeshData in place. Returns (triangle count before, after)."""
    before = sum(len(triangles) for triangles in mesh.submeshes)

    if before < 2 or not mesh.positions:
        return before, before

    simplifier = _Simplifier(mesh)
    simplifier.run(max_error)
    simplifier.apply()

    return before, sum(len(triangles) for triangles in mesh.submeshes)
