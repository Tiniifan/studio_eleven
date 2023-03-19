import bpy
import struct
import zlib
import mathutils
import zlib
import struct
from ..animation import *
from ..compression import *

def table_offset(frame_offset, frame_transform):
    out = bytes()
    out += int(frame_offset).to_bytes(4, 'little')
    out += int(frame_offset + 4).to_bytes(4, 'little')
    out += int(frame_offset + 4 + len(frame_transform) * 2).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    return out

def node_modified(node, frames):
    out = bytes()
    out += int(node).to_bytes(2, 'little')
    out += int(len(frames)).to_bytes(1, 'little')
    out += int(32).to_bytes(1, 'little')
    return out

def frame_modified(frame_key):
    return int(frame_key).to_bytes(2, 'little')

def to_euler_angles(q):
    x = -q[0]
    y = -q[1]
    z = -q[2]
    w = q[3]

    ysqr = y * y

    t0 = 2.0 * (w * x + y * z)
    t1 = 1.0 - 2.0 * (x * x + ysqr)
    X = math.atan2(t0, t1)

    t2 = 2.0 * (w * y - z * x)
    t2 = 1.0 if t2 > 1.0 else t2
    t2 = -1.0 if t2 < -1.0 else t2
    Y = math.asin(t2)

    t3 = 2.0 * (w * z + x * y)
    t4 = 1.0 - 2.0 * (ysqr + z * z)
    Z = math.atan2(t3, t4)

    return X, Y, Z

def create_bone(bone_name):
    armature = bpy.context.active_object.data
    bone = armature.edit_bones.new(bone_name)
    bone.head = (0, 0, 0)
    bone.tail = (0, 0, 1)
    return bone

def open_xmtn(file_path):
    with open(file_path, "rb") as f:
        # read header
        f.seek(0x08)
        decom_size = struct.unpack("<i", f.read(4))[0]
        name_offset = struct.unpack("<I", f.read(4))[0]
        comp_data_offset = struct.unpack("<I", f.read(4))[0]
        position_count = struct.unpack("<i", f.read(4))[0]
        rotation_count = struct.unpack("<i", f.read(4))[0]
        scale_count = struct.unpack("<i", f.read(4))[0]
        unknown_count = struct.unpack("<i", f.read(4))[0]
        bone_count = struct.unpack("<i", f.read(4))[0]

        f.seek(0x54)
        frame_count = struct.unpack("<i", f.read(4))[0]

        anim_name_hash = struct.unpack("<I", f.read(4))[0]
		
        f.seek(name_offset)
        anim_name = f.read(comp_data_offset - name_offset).decode("utf-8")

        # read compressed data
        f.seek(comp_data_offset)
        data = lz10.decompress(f.read())

        # read decompressed data
        bone_hash_table_offset = struct.unpack("<I", data.read(4))[0]
        track_info_offset = struct.unpack("<I", data.read(4))[0]
        data_offset = struct.unpack("<I", data.read(4))[0]

        # read bone hashes
        bone_name_hashes = []
        for i in range((track_info_offset - bone_hash_table_offset) // 4):
            bone_name_hashes.append(struct.unpack("<I", data.read(4))[0])

        # create bones
        armature = bpy.data.armatures.new(name=anim_name)
        armature_obj = bpy.data.objects.new(name=anim_name, object_data=armature)
        bpy.context.scene.collection.objects.link(armature_obj)
        bpy.context.view_layer.objects.active = armature_obj
        bpy.ops.object.mode_set(mode="EDIT")

        bones = {}
        for i in range(bone_count):
            f.seek(bone_hash_table_offset + struct.unpack("<I", data.read(4))[0] - data_offset)
            bone_name = f.read(0x100).decode("utf-8")
            bone = create_bone(bone_name)
            bones[bone_name] = bone

        # read keyframes
        for i in range(frame_count):
            for j in range(bone_count):
                fcurves = []
                bone_name_hash = struct.unpack("<I", data.read(4))[0]
                bone_name = None
                for k in range(len(bone_name_hashes)):
                    if bone_name_hashes[k] == bone_name_hash:
                        f.seek(bone_hash_table_offset + k * 4 - data_offset)
                        bone_name = f.read(0x100).decode("utf-8")
                        break

                if bone_name is None:
                    continue

                if bone_name not in bones:
                    bone = create_bone(bone_name)
                    bones[bone_name] = bone
                else:
                    bone = bones[bone_name]

                position_keys = []
                rotation_keys = []
                scale_keys = []
                for k in range(position_count):
                    position_keys.append((struct.unpack("<f", data.read(4))[0], struct.unpack("<f", data.read(4))[0], struct.unpack("<f", data.read(4))[0]))
                for k in range(rotation_count):
                    rotation_keys.append((struct.unpack("<f", data.read(4))[0], struct.unpack("<f", data.read(4))[0], struct.unpack("<f", data.read(4))[0], struct.unpack("<f", data.read(4))[0]))
                for k in range(scale_count):
                    scale_keys.append((struct.unpack("<f", data.read(4))[0], struct.unpack("<f", data.read(4))[0], struct.unpack("<f", data.read(4))[0]))

                # create fcurves for position keys
                if position_count > 0:
                    fcurves.append(bone.pose.bones[bone_name].location_x.animation_data_create().action.fcurves[0])
                    fcurves.append(bone.pose.bones[bone_name].location_y.animation_data_create().action.fcurves[1])
                    fcurves.append(bone.pose.bones[bone_name].location_z.animation_data_create().action.fcurves[2])

                    for k in range(position_count):
                        for l in range(3):
                            fcurves[l].keyframe_points.insert(frame=i, value=position_keys[k][l], options={"FAST"})

                # create fcurves for rotation keys
                if rotation_count > 0:
                    fcurves.append(bone.pose.bones[bone_name].rotation_euler_x.animation_data_create().action.fcurves[0])
                    fcurves.append(bone.pose.bones[bone_name].rotation_euler_y.animation_data_create().action.fcurves[1])
                    fcurves.append(bone.pose.bones[bone_name].rotation_euler_z.animation_data_create().action.fcurves[2])

                    for k in range(rotation_count):
                        q = rotation_keys[k]
                        euler_angles = to_euler_angles(q)
                        for l in range(3):
                            fcurves[l + 3].keyframe_points.insert(frame=i, value=euler_angles[l], options={"FAST"})

                # create fcurves for scale keys
                if scale_count > 0:
                    fcurves.append(bone.pose.bones[bone_name].scale.animation_data_create().action.fcurves[0])
                    fcurves.append(bone.pose.bones[bone_name].scale.animation_data_create().action.fcurves[1])
                    fcurves.append(bone.pose.bones[bone_name].scale.animation_data_create().action.fcurves[2])

                    for k in range(scale_count):
                        for l in range(3):
                            fcurves[l].keyframe_points.insert(k, k + i * scale_count, scale_keys[k][l])

        bpy.ops.object.mode_set(mode="OBJECT")

def write(name, nodes, frame_location, frame_rotation, frame_scale, frame_end):
    out = bytes()

    # for each node write the crc32 of node name
    table_node = bytes()
    for node in nodes:
        crc32 = zlib.crc32(node.encode("utf-8"))
        table_node += crc32.to_bytes(4, 'little')

    # write [table_node offset, transform offset, frames offset and table_node]
    out += int(12).to_bytes(4, 'little')
    out += int(12 + len(table_node)).to_bytes(4, 'little')
    out += int(52 + len(table_node)).to_bytes(4, 'little')
    out += table_node

    # write location, rotation, size offset
    type_offset = len(out)
    for i in range(1, 5):
        out += (type_offset + 8 * i).to_bytes(2, 'little')

    # write transform specify and the number of frame 
    for i in range(3):
        if i == 0:
            out += int("0x03000201", 16).to_bytes(4, 'little')
        elif i == 1:
            out += int("0x04000102", 16).to_bytes(4, 'little')
        elif i == 2: 
            out += int("0x03000203", 16).to_bytes(4, 'little')            
        out += int(0).to_bytes(2, 'little')
        out += frame_end.to_bytes(2, 'little')
    
    # write empty block
    out += int(0).to_bytes(8, 'little')
    
    # initialise bytes object to save frame data and frame_offset to save each offset of frame
    data_location = bytes()
    data_rotation = bytes()
    data_scale = bytes()
    frame_offset = len(out) + (len(frame_location) + len(frame_rotation) + len(frame_scale)) * 16
    
    # write data_location for each frame
    for node, frames in frame_location.items():
        # table
        out += table_offset(frame_offset, frames)
        frame_offset += len(frames) * 14 + 4;
        # node data
        data_location += node_modified(node, frames)
        # frame edited
        data_transform = bytes()
        for frame_key, frame_transform in frames.items():
            data_location += frame_modified(frame_key)
            data_transform += bytearray(struct.pack("f", frame_transform.location_x))
            data_transform += bytearray(struct.pack("f", frame_transform.location_y))
            data_transform += bytearray(struct.pack("f", frame_transform.location_z))
        data_location += data_transform

    # write data_rotation for each frame
    for node, frames in frame_rotation.items():
        # table
        out += table_offset(frame_offset, frames)
        frame_offset += len(frames) * 10 + 4;
        # node data
        data_rotation += node_modified(node, frames)
        # frame edited
        data_transform = bytes()
        for frame_key, frame_transform in frames.items():
            data_rotation += frame_modified(frame_key)
            quaternion = frame_transform.to_quaternion()
            for i in range(4):
                data_transform += int(quaternion[i] * 32767).to_bytes(2, 'little', signed=True)
        data_rotation += data_transform

    # write data_scale for each frame
    for node, frames in frame_scale.items():
        # table
        out += table_offset(frame_offset, frames)
        frame_offset += len(frames) * 14 + 4;
        # node data
        data_scale += node_modified(node, frames)
        # frame edited
        data_transform = bytes()
        for frame_key, frame_transform in frames.items():
            data_scale += frame_modified(frame_key)
            data_transform += bytearray(struct.pack("f", frame_transform.scale_x))
            data_transform += bytearray(struct.pack("f", frame_transform.scale_y))
            data_transform += bytearray(struct.pack("f", frame_transform.scale_z))
        data_scale += data_transform    

    # compress
    out += data_location + data_rotation + data_scale
    data_uncompress = len(out)
    data_compress = compress(out)    

    # create mtn
    out = int("0x4e544d58", 16).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    out += int(data_uncompress + 8316).to_bytes(4, 'little')
    out += int(40).to_bytes(4, 'little')
    name_bytes = name.encode("utf-8")
    name_bytes = zlib.crc32(name_bytes).to_bytes(4, 'little') + name_bytes
    out += int(88).to_bytes(4, 'little')
    out += int(len(frame_location)).to_bytes(4, 'little')
    out += int(len(frame_rotation)).to_bytes(4, 'little')
    out += int(len(frame_scale)).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    out += int(len(frame_location)).to_bytes(4, 'little')
    out += name_bytes
    out += int(0).to_bytes(40-len(name), 'little')
    out += int(frame_end).to_bytes(4, 'little')
    out += data_compress
    
    return out
