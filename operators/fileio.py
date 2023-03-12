import os
import bpy
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, EnumProperty

from ..animation import *
from ..formats import *

##########################################
# .mtn2 Class
##########################################

def write_mtn2(context, filepath, armature_name, animation_name):   
    scene = context.scene
    armature = bpy.data.objects[armature_name]
    bpy.ops.object.mode_set(mode='POSE')

    # initialise transform data
    node_name = []
    transform_location = {}
    transform_rotation = {}
    transform_scale = {}
    
    # for each bone
    for bone in armature.pose.bones:
        node_name.append(bone.name)
        
    # for each frame
    for frame in range(scene.frame_end):
        scene.frame_set(frame)
        for bone in armature.pose.bones:
            # get pose_bone matrix relative to bone_parent
            bone_index = armature.pose.bones.values().index(bone)
            pose_bone = armature.pose.bones[bone_index]
            
            if not pose_bone.bone.use_deform: 
                continue
		
            parent = pose_bone.parent	
            while parent:
                if parent.bone.use_deform:
                    break
                parent = parent.parent   
                        
            pose_matrix = pose_bone.matrix
            if parent:
                parent_matrix = parent.matrix
                pose_matrix = parent_matrix.inverted() @ pose_matrix
            
            # append location in transform_location
            location = pose_matrix.to_translation()
            location = Location(float(location[0]), float(location[1]), float(location[2]))
            if bone_index not in transform_location:
                transform_location[bone_index] = {}
            transform_location[bone_index][frame] = location

            # append rotation in transform_rotation
            rotation = pose_matrix.to_euler()
            rotation = Rotation(float(rotation[0]), float(rotation[1]), float(rotation[2]))          
            if bone_index not in transform_rotation:
                transform_rotation[bone_index] = {}
            transform_rotation[bone_index][frame] = rotation

            # append scale in transform_scale
            scale = pose_matrix.to_scale()
            scale = Scale(float(scale[0]), float(scale[1]), float(scale[2]))            
            if bone_index not in transform_scale:
                transform_scale[bone_index] = {}
            transform_scale[bone_index][frame] = scale             
    
    # Save file
    new_xmtn = xmtn.write(animation_name, node_name, transform_location, transform_rotation, transform_scale, scene.frame_end)  
    f = open(filepath, 'wb')
    f.write(new_xmtn)
    f.close()
    
    return {'FINISHED'}

class ExportMTN2(bpy.types.Operator, ExportHelper):
    bl_idname = "export.mtn2"
    bl_label = "Export to mtn2"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".mtn2"
    filter_glob: StringProperty(default="*.mtn2", options={'HIDDEN'})

    def item_callback(self, context):
        items = []
        for o in bpy.context.scene.objects:
            if o.type == "ARMATURE":
                items.append((o.name, o.name, ""))
        return items
        
    armature_name: EnumProperty(
        name="Animation Armature",
        description="Choose animation armature",
        items=item_callback,
        default=0,
    )

    animation_name: StringProperty(
        name="Animation Name",
        description="Set your animation name",
        default='my_animation',
        maxlen=40,
    )    

    def execute(self, context):
        if (self.armature_name == ""):
            self.report({'ERROR'}, "No animation armature found")
            return {'FINISHED'}
        else:
            return write_mtn2(context, self.filepath, self.armature_name, self.animation_name)


##########################################
# .prm Class
##########################################
           
def get_bone_names(armature):
    for bone in armature.pose.bones:
        yield(bone.name)

def get_indices(polygons):
    for face in polygons:
        yield (face.vertices[:])
                
def get_normals(vertices):
    for x in range(len(vertices)):
        yield (x, vertices[x].normal)   
            
def get_vertices(vertices):
    for x in range(len(vertices)):
        yield (x, vertices[x].co.xyz)   
            
def get_uvs(uv_layers):
    for uv_layer in uv_layers:
        for x in range(len(uv_layer.data)):
            yield (x, uv_layer.data[x].uv)            

def get_colours(vertex_colors):
    for vertex_color in vertex_colors:
        for x in range(len(vertex_color.data)):
            r, g, b, a = vertex_color.data[x].color
            yield (x, [r, g, b, a]) 

def get_weights(ob):
    for i, v in enumerate(ob.data.vertices):
        weight = {}
        for g in v.groups:
            if g.weight != 0:
                weight[g.group] = g.weight       
        yield(i, weight)

def create_files_dict(extension, data_list):
    output = {}
    
    for i in range(len(data_list)):
        output[str(i).rjust(3,'0') + extension] = data_list[i]
        
    return output

def write_xpck(context, filepath):
    armatures = []
    meshes = []
    
    # Get armature and meshes
    for obj in bpy.data.objects:
        if obj.type == "ARMATURE":
            armatures.append(obj)
        elif obj.type == "MESH":
            meshes.append(obj)
    
    # Try to generate bones
    bones = {}
    if armatures is not []:
        for armature in armatures:
            for bone in armature.pose.bones:
                bones[bone.name] = mbn.write(bone)
    
    # Try to generate images
    images = {}
    materials = {}
    if meshes is not []:
        for mesh in meshes:
            for mat_slot in mesh.material_slots:
                if mat_slot.material:
                    materials[mat_slot.name] = []
                    if mat_slot.material.node_tree:             
                        for x in mat_slot.material.node_tree.nodes:
                            if x.type=='TEX_IMAGE':
                                materials[mat_slot.name].append(x.image.name[:-4])
                                if x.image.name[:-4] not in images:
                                    images[x.image.name[:-4]] = imgc.write(x.image, RGB565)
    
    # Try to generate .prm
    xmprs = []
    if meshes is not []:
        for mesh in meshes:
            indices = list(get_indices(mesh.data.polygons))
            vertices = dict(get_vertices(mesh.data.vertices))
            uvs = dict(get_uvs(mesh.data.uv_layers))
            normals = dict(get_normals(mesh.data.vertices))
            colors = dict(get_colours(mesh.data.vertex_colors))
            weights = dict(get_weights(mesh))
            
            material_name = ""
            for mat_slot in mesh.material_slots:
                if mat_slot.material:
                    material_name = mat_slot.name
            
            bone_names = []
            for m in mesh.modifiers:
                if (m.type == "ARMATURE"):
                    bone_names = list(get_bone_names(m.object))
                xmprs.append(xmpr.write(mesh.name_full, indices, vertices, uvs, normals, colors, weights, bone_names, material_name))
    
    # Create res
    library = {}
    library["material"] = materials
    library["material2"] = materials
    library["texture"] = list(images.keys())
    library["materialconfig"] = materials
    library["mesh"] = [mesh.name for mesh in meshes]
    library["bone"] = list(bones.keys())
    my_res = res.write(library)
    
    # Create files dict
    files = {}
    files.update(create_files_dict(".mbn", list(bones.values()) ))
    files.update(create_files_dict(".xi", list(images.values()) ))
    files.update(create_files_dict(".prm", xmprs))
    files["RES.bin"] = my_res
    files["000.atr"] = bytes.fromhex("41545243303100000C000000E3010000054080FF0000C0C13C80BF0137F72F406005FFFFF0FFFF56")
    files["000.mtr"] = bytes.fromhex("4D545243303000001800000000000000000000000000000041070000350000F001501301801C0340037E04800B5013F043F055F0673079F819FEFE3E5003B08B803F5003F0F023F0B5F0C770D9E8891DA70000004C555443")
    
    # create xpck
    xpck.pack(files, filepath)
     
    return {'FINISHED'}

class ExportPRM(bpy.types.Operator, ExportHelper):
    bl_idname = "export.prm"
    bl_label = "Export to xc"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".xc"
    filter_glob: StringProperty(default="*.xc", options={'HIDDEN'})

    def execute(self, context):
        return write_xpck(context, self.filepath)
            
            
##########################################
# Register class
##########################################

def register():
    bpy.utils.register_class(ExportMTN2)
    bpy.utils.register_class(ExportPRM)

def unregister():
    bpy.utils.unregister_class(ExportMTN2)
    bpy.utils.unregister_class(ExportPRM)

if __name__ == "__main__":
    register()        