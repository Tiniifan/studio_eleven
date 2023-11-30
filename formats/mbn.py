import io
import math
import zlib
import struct
from mathutils import Quaternion, Matrix

def matrix_to_bytes(matrix):
    out = bytes()
    
    # Location
    location = matrix.to_translation()
    for i in range(3):
        out += bytearray(struct.pack("f", location[i]))
    
    # Rotation
    rotation = matrix.to_quaternion()
    matrix_rotation = rotation.to_matrix().to_3x3()
    for i in range(3):
        for j in range(3):
            out += bytearray(struct.pack("f", matrix_rotation[i][j]))
     
    # Scale 
    scale = matrix.to_scale()
    for i in range(3):
        out += bytearray(struct.pack("f", scale[i]))
        
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

def write(bone):
    out = bytes()
    
    out += zlib.crc32(bone.name.encode("utf-8")).to_bytes(4, 'little')
    if (bone.parent is not None):
        out +=  zlib.crc32(bone.parent.name.encode("utf-8")).to_bytes(4, 'little')
    else:
        out += int(0).to_bytes(4, 'little')
        
    out += int(4).to_bytes(4, 'little')
    
    # get bone matrix relative to bone_parent           
    parent = bone.parent	
    while parent:
        if parent.bone.use_deform:
            break
        parent = parent.parent   
                        
    pose_matrix = bone.matrix
    if parent:
        parent_matrix = parent.matrix
        pose_matrix = parent_matrix.inverted() @ pose_matrix
    
    out += matrix_to_bytes(pose_matrix)
    
    tail = bone.tail
    head = bone.head
    relative_transform = Matrix.Translation(head - tail)
    head_transform = pose_matrix @ relative_transform
    tail_transform = Matrix.Translation(tail)
    tail_to_head_transform = tail_transform.inverted() @ head_transform

    out += b''.join([struct.pack('f', item) for sublist in head_transform.to_3x3() for item in sublist])
    out += struct.pack('fff', *[-x for x in head])
    out += b''.join([struct.pack('f', item) for sublist in head_transform.to_3x3() for item in sublist])
    out += struct.pack('fff', *head)
    
    return out