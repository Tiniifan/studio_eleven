import os
import bpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, EnumProperty

from ..formats import xmpr
from ..templates import templates

##########################################
# XMPR Function
##########################################

def get_bone_names(armature):
    for bone in armature.pose.bones:
        yield(bone.name)

def get_weights(ob):
    for i, v in enumerate(ob.data.vertices):
        weight = {}
        for g in v.groups:
            if g.weight != 0:
                weight[g.group] = g.weight       
        yield(i, weight)
            
def get_mesh_information(mesh):
    vertices_dict = {}
    uv_dict = {}
    normal_dict = {}
    color_dict = {}
    face_indices = []

    vertices_info = {}
    uv_info = {}
    normal_info = {}
    color_info = {}

    if mesh.data.vertex_colors.active is not None:
        vertex_colors = mesh.data.vertex_colors.active.data

    for face in mesh.data.polygons:
        face_index = {}
        indices = []
        vt_indices = []
        vn_indices = []
        color_indices = []

        for loop_index in face.loop_indices:
            vertex_index = mesh.data.loops[loop_index].vertex_index
            if vertex_index not in vertices_dict:
                vertices_dict[vertex_index] = len(vertices_dict)
                vertices_info[vertices_dict[vertex_index]] = mesh.data.vertices[vertex_index].co
            indices.append(vertices_dict[vertex_index])

            uv = tuple(mesh.data.uv_layers.active.data[loop_index].uv)
            if uv not in uv_dict:
                uv_dict[uv] = len(uv_dict)
                uv_info[uv_dict[uv]] = uv
            vt_indices.append(uv_dict[uv])

            normal = tuple(mesh.data.vertices[vertex_index].normal)
            if normal not in normal_dict:
                normal_dict[normal] = len(normal_dict)
                normal_info[normal_dict[normal]] = normal
            vn_indices.append(normal_dict[normal])

            if mesh.data.vertex_colors.active is not None:
                color = vertex_colors[loop_index].color
                if color not in color_dict:
                    color_dict[color] = len(color_dict)
                    color_info[color_dict[color]] = color
                color_indices.append(color_dict[color])

        face_index["v"] = indices
        face_index["vt"] = vt_indices
        face_index["vn"] = vn_indices
        face_index["vc"] = color_indices
        face_indices.append(face_index)

    return face_indices, vertices_info, uv_info, normal_info, color_info
  
def fileio_write_xmpr(context, mesh_name, library_name, template):
    # Get Mesh
    mesh = bpy.data.objects[mesh_name]
    
    indices, vertices, uvs, normals, colors = get_mesh_information(mesh)
    weights = dict(get_weights(mesh))
            
    bone_names = []
    for m in mesh.modifiers:
        if m.type == "ARMATURE":
            bone_names = list(get_bone_names(m.object))
    
    return xmpr.write(mesh.name_full, indices, vertices, uvs, normals, colors, weights, bone_names, library_name, template)


##########################################
# Register class
##########################################     
    
class ExportPRM(bpy.types.Operator, ExportHelper):
    bl_idname = "export.prm"
    bl_label = "Export to prm"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".prm"
    filter_glob: StringProperty(default="*.prm", options={'HIDDEN'})
    
    def item_callback(self, context):
        items = []
        for o in bpy.context.scene.objects:
            if o.type == "MESH":
                items.append((o.name, o.name, ""))
        return items
        
    def template_items_callback(self, context):
        my_templates = templates.get_templates()
        items = [(template.name, template.name, "") for template in my_templates]
        return items        
        
    mesh_name: EnumProperty(
        name="Meshes",
        description="Choose mesh",
        items=item_callback,
        default=0,
    )
    
    template_name: EnumProperty(
        name="Templates",
        description="Choose a template",
        items=template_items_callback,
        default=0,
    )
    
    library_name: StringProperty(
        name="Library",
        description="Write a library name",
        default="",
    )    

    def execute(self, context):
        if (self.mesh_name == ""):
            self.report({'ERROR'}, "No mesh found")
            return {'FINISHED'}
            
        if (self.template_name == ""):
            self.report({'ERROR'}, "No template found")
            return {'FINISHED'}
            
        if (self.library_name == ""):
            self.report({'ERROR'}, "Library name cannot be null")
            return {'FINISHED'}               
            
        with open(self.filepath, "wb") as f:
            f.write(fileio_write_xmpr(context, self.mesh_name, self.library_name, templates.get_template_by_name(self.template_name)))
            return {'FINISHED'}  