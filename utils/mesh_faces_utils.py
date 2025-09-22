import bpy
import bmesh
import math

from mathutils import Vector

class MeshFaceUtils:
    @staticmethod
    def get_face_duplicates_info(obj, remove_first_duplicate=False):
        if obj is None or obj.type != 'MESH':
            return [], []

        bm = bmesh.new()
        bm.from_mesh(obj.data)
        mat_world = obj.matrix_world

        # Calculate face centers in world space
        face_centers = [(mat_world @ f.calc_center_median()) for f in bm.faces]
        face_centers = [(v.x, v.y, v.z) for v in face_centers]

        eps = 0.0002
        used = [False] * len(face_centers)
        duplicated_faces = set()
        non_duplicated_faces = []

        for i, ci in enumerate(face_centers):
            if used[i]:
                continue
            matching_faces = [i]

            for j in range(i + 1, len(face_centers)):
                if used[j]:
                    continue
                cj = face_centers[j]
                if all(math.isclose(ci[k], cj[k], abs_tol=eps) for k in range(3)):
                    matching_faces.append(j)
                    used[j] = True
            used[i] = True

            if len(matching_faces) >= 2:
                if remove_first_duplicate:
                    duplicated_faces.update(matching_faces[1:])  # Remove duplicates, keep first
                    non_duplicated_faces.append(matching_faces[0])
                else:
                    duplicated_faces.update(matching_faces)
            else:
                non_duplicated_faces.extend(matching_faces)

        bm.free()
        return list(duplicated_faces), non_duplicated_faces

    @staticmethod
    def get_duplicate_groups(obj):
        if obj is None or obj.type != 'MESH':
            return []
            
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        mat_world = obj.matrix_world
        
        # Calculate face centers in world space
        face_centers = [(mat_world @ f.calc_center_median()) for f in bm.faces]
        face_centers = [(v.x, v.y, v.z) for v in face_centers]
        
        eps = 0.0002
        used = [False] * len(face_centers)
        duplicate_groups = []
        
        for i, ci in enumerate(face_centers):
            if used[i]:
                continue
            matching_faces = [i]
            for j in range(i + 1, len(face_centers)):
                if used[j]:
                    continue
                cj = face_centers[j]
                if all(math.isclose(ci[k], cj[k], abs_tol=eps) for k in range(3)):
                    matching_faces.append(j)
                    used[j] = True
            used[i] = True
            
            if len(matching_faces) >= 2:
                duplicate_groups.append(matching_faces)
        
        bm.free()
        return duplicate_groups

    @staticmethod
    def preserve_vertex_colors(obj, original_face_count=None, highlight_new_faces=False):
        existing_vcols = None
        if "Col" in obj.data.vertex_colors:
            existing_vcols = []
            vcol_layer = obj.data.vertex_colors["Col"]
            for poly in obj.data.polygons:
                for li in poly.loop_indices:
                    existing_vcols.append(vcol_layer.data[li].color[:])
            obj.data.vertex_colors.remove(obj.data.vertex_colors["Col"])

        vcol = obj.data.vertex_colors.new(name="Col")

        loop_index = 0
        for poly_idx, poly in enumerate(obj.data.polygons):
            for li in poly.loop_indices:
                if original_face_count is not None and poly_idx >= original_face_count and highlight_new_faces:
                    vcol.data[li].color = (1, 0, 0, 1)  # Highlight new faces
                elif existing_vcols and loop_index < len(existing_vcols):
                    vcol.data[li].color = existing_vcols[loop_index]
                else:
                    vcol.data[li].color = (0, 0, 0, 1)
                loop_index += 1

    @staticmethod
    def edit_faces(obj, face_indices, action='DUPLICATE'):
        if not face_indices:
            return obj

        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_mode(type='FACE')

        bm = bmesh.from_edit_mesh(obj.data)
        bm.faces.ensure_lookup_table()
        for face_idx in face_indices:
            if face_idx < len(bm.faces):
                bm.faces[face_idx].select = True
        bmesh.update_edit_mesh(obj.data)

        if action == 'DUPLICATE':
            bpy.ops.mesh.duplicate()
            bpy.ops.mesh.flip_normals()
        elif action == 'DELETE':
            bpy.ops.mesh.delete(type='FACE')

        bpy.ops.object.mode_set(mode='OBJECT')
        return obj
