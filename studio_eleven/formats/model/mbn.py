import io
import math
import zlib
import struct

from math import radians
from mathutils import Matrix, Quaternion, Vector

def scientific_float_to_float(float_scientifique):
    return float("{:.4f}".format(float_scientifique))

def matrix_vector_multiply(matrix, vector):
    result = [0, 0, 0]
    for i in range(3):
        for j in range(3):
            result[i] += matrix[i][j] * vector[j]
    return result

def matrix_to_bytes(location, rotation, scale, head, tail, local_matrix, bind_head):
    out = bytes()
    
    # Location
    for i in range(3):
        out += bytearray(struct.pack("f", scientific_float_to_float(location[i])))
    
    # Rotation
    matrix_rotation = rotation.to_matrix().to_3x3()
    for i in range(3):
        for j in range(3):
            out += bytearray(struct.pack("f", float(matrix_rotation[j][i])))
     
    # Scale 
    for i in range(3):
        out += bytearray(struct.pack("f", float(scale[i])))

    # Local rotation
    local_rotation = local_matrix.to_quaternion()
    local_matrix_rotation = local_rotation.to_matrix().to_3x3()
    local_matrix_rotation_ordered = [[0,0,0], [0,0,0], [0,0,0]]
    for i in range(3):
        for j in range(3):
            out += bytearray(struct.pack("f", scientific_float_to_float(local_matrix_rotation[i][j])))
            local_matrix_rotation_ordered[i][j] = local_matrix_rotation[j][i]                    

    # Location rotation * head
    rotated_head = matrix_vector_multiply(local_matrix_rotation_ordered, bind_head)
    for i in range(3):
        out += bytearray(struct.pack("f", float(rotated_head[i]*-1)))

    # First column of local matrix rotation
    for j in range(3):
        out += bytearray(struct.pack("f", float(local_matrix_rotation[j][0])))

    # Tail - head
    for i in range(3):
        out += bytearray(struct.pack("f", float(tail[i]-head[i])))

    # Last column of local matrix rotation
    for j in range(3):
        out += bytearray(struct.pack("f", float(local_matrix_rotation[j][2])))

    # Head
    for i in range(3):
        out += bytearray(struct.pack("f", float(head[i])))
  
    return out    
    
def open(data):
    if len(data) == 0:
        return None

    bone = {}
    with io.BytesIO(data) as stream:
        bone_id, parent_index, flag = struct.unpack('<III', stream.read(12))

        stream.seek(0xC)
        location = struct.unpack('<fff', stream.read(12))

        rotation_matrix = [
            struct.unpack('<fff', stream.read(12)),
            struct.unpack('<fff', stream.read(12)),
            struct.unpack('<fff', stream.read(12))
        ]
        rotation_matrix = Matrix(rotation_matrix)
        quaternion_rotation = rotation_matrix.to_quaternion().inverted()

        scale = struct.unpack('<fff', stream.read(12))
        
        local_rotation_matrix = [
            struct.unpack('<fff', stream.read(12)),
            struct.unpack('<fff', stream.read(12)),
            struct.unpack('<fff', stream.read(12))
        ]
        local_rotation_matrix = Matrix(local_rotation_matrix)
        quaternion_local_rotation = local_rotation_matrix.to_quaternion().inverted()
        
        rotation_time_head = struct.unpack('<fff', stream.read(12))
        first_column_local_matrix_rotation = struct.unpack('<fff', stream.read(12))
        tail_min_head = struct.unpack('<fff', stream.read(12))
        last_column_local_matrix_rotation = struct.unpack('<fff', stream.read(12))
        head = struct.unpack('<fff', stream.read(12))
        tail = tuple(tmh + h for tmh, h in zip(tail_min_head, head))

        # The game skins with the inverse bind of the file: the local rotation transposed, then the rotated head
        inverse_bind = local_rotation_matrix.transposed().to_4x4()
        inverse_bind.translation = Vector(rotation_time_head)

        bone['crc32'] = bone_id
        bone['parent_crc32'] = parent_index
        bone['flag'] = flag
        bone['inverse_bind'] = inverse_bind
        bone['location'] = location
        bone['quaternion_rotation'] = quaternion_rotation
        bone['scale'] = scale
        bone['quaternion_local_rotation'] = quaternion_local_rotation
        bone['head'] = head
        bone['tail'] = tail

    return bone

def write(armature, pose_bone, transform, flag=None):
    out = bytes()  
        
    # get bone parent
    parent = pose_bone.parent	
    while parent:
        if parent.bone.use_deform:
            break
        parent = parent.parent   

    # Location, rotation and scale relative to the parent, a matrix loses the rotation of a node of scale 0
    location, rotation, scale = transform

    out += zlib.crc32(pose_bone.name.encode("utf-8")).to_bytes(4, 'little')
    if (parent is not None):
        out +=  zlib.crc32(parent.name.encode("utf-8")).to_bytes(4, 'little')
    else:
        out += int(0).to_bytes(4, 'little')
        
    # An imported node keeps its flag, a new one is a billboard (5) or a node (4)
    if flag is None:
        flag = 4
        if pose_bone.name == "billboard" or pose_bone.name == "cam_rot":
            flag = 5

    out += int(flag).to_bytes(4, 'little')
    
    # The inverse bind and the bone are the rest pose the vertices are in, the pose holds the rest scale of the node
    bone = pose_bone.bone
    out += matrix_to_bytes(location, rotation, scale, bone.head_local, bone.tail_local, bone.matrix_local, bone.head_local)
    
    return out
