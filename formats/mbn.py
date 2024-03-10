import io
import math
import zlib
import struct

from math import radians
from mathutils import Matrix, Quaternion, Vector

def matrix_vector_multiply(matrix, vector):
    result = [0, 0, 0]
    for i in range(3):
        for j in range(3):
            result[i] += matrix[i][j] * vector[j]
    return result

def matrix_to_bytes(matrix, head, tail):
    out = bytes()
    
    # Location
    location = matrix.to_translation()
    for i in range(3):
        out += bytearray(struct.pack("f", location[i]))
    
    # Rotation
    rotation = matrix.to_quaternion()
    matrix_rotation = rotation.to_matrix().to_3x3()
    matrix_rotation_ordered = [[0,0,0], [0,0,0], [0,0,0]]
    for i in range(3):
        for j in range(3):
            out += bytearray(struct.pack("f", matrix_rotation[j][i]))
            matrix_rotation_ordered[i][j] = matrix_rotation[j][i]
     
    # Scale 
    scale = matrix.to_scale()
    for i in range(3):
        out += bytearray(struct.pack("f", scale[i]))

    # Rotation 2
    rotation = matrix.to_quaternion()
    matrix_rotation = rotation.to_matrix().to_3x3()
    for i in range(3):
        for j in range(3):
            out += bytearray(struct.pack("f", matrix_rotation[i][j]))

    rotated_head = matrix_vector_multiply(matrix_rotation_ordered, head)
    for i in range(3):
        out += bytearray(struct.pack("f", rotated_head[i]*-1))

    for j in range(3):
        out += bytearray(struct.pack("f", matrix_rotation[j][0]))

    for i in range(3):
        out += bytearray(struct.pack("f", tail[i]-head[i]))

    for j in range(3):
        out += bytearray(struct.pack("f", matrix_rotation[j][2]))

    for i in range(3):
        out += bytearray(struct.pack("f", head[i]))
  
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

        # Remplissage du dictionnaire bone
        bone['crc32'] = bone_id
        bone['parent_crc32'] = parent_index
        bone['location'] = location
        bone['quaternion_rotation'] = quaternion_rotation
        bone['scale'] = scale

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
    if parent:
        parent_matrix = parent.matrix
        pose_matrix = parent_matrix.inverted() @ pose_matrix

    out += zlib.crc32(pose_bone.name.encode("utf-8")).to_bytes(4, 'little')
    if (parent is not None):
        out +=  zlib.crc32(parent.name.encode("utf-8")).to_bytes(4, 'little')
    else:
        out += int(0).to_bytes(4, 'little')
        
    out += int(4).to_bytes(4, 'little')
    
    out += matrix_to_bytes(pose_matrix, pose_bone.head, pose_bone.tail)
    
    return out