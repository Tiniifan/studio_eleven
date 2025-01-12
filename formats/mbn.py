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

def matrix_to_bytes(matrix, head, tail, local_matrix):
    out = bytes()
    
    # Location
    location = matrix.to_translation()
    for i in range(3):
        out += bytearray(struct.pack("f", scientific_float_to_float(location[i])))
    
    # Rotation
    rotation = matrix.to_quaternion()
    matrix_rotation = rotation.to_matrix().to_3x3()
    for i in range(3):
        for j in range(3):
            out += bytearray(struct.pack("f", float(matrix_rotation[j][i])))
     
    # Scale 
    scale = matrix.to_scale()
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
    rotated_head = matrix_vector_multiply(local_matrix_rotation_ordered, head)
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
        bone_id, parent_index = struct.unpack('<II', stream.read(8))
        stream.seek(4)

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

        bone['crc32'] = bone_id
        bone['parent_crc32'] = parent_index
        bone['location'] = location
        bone['quaternion_rotation'] = quaternion_rotation
        bone['scale'] = scale
        bone['quaternion_local_rotation'] = quaternion_local_rotation
        bone['head'] = head
        bone['tail'] = tail

    return bone

def write(armature, pose_bone):
    out = bytes()  
        
    # get bone matrix relative to bone_parent           
    parent = pose_bone.parent	
    while parent:
        if parent.bone.use_deform:
            break
        parent = parent.parent   

    pose_matrix = pose_bone.matrix
    local_matrix = pose_matrix
    if parent:
        parent_matrix = parent.matrix
        pose_matrix = parent_matrix.inverted() @ pose_matrix

    out += zlib.crc32(pose_bone.name.encode("utf-8")).to_bytes(4, 'little')
    if (parent is not None):
        out +=  zlib.crc32(parent.name.encode("utf-8")).to_bytes(4, 'little')
    else:
        out += int(0).to_bytes(4, 'little')
        
    if pose_bone.name == "billboard" or pose_bone.name == "cam_rot":
        out += int(5).to_bytes(4, "little")
    else:
        out += int(4).to_bytes(4, 'little')
    
    out += matrix_to_bytes(pose_matrix, pose_bone.head, pose_bone.tail, local_matrix)
    
    return out
