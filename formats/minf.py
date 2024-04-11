import io
import zlib
import struct

##########################################
# MINF1
##########################################

def open_minf1(data):
    reader = io.BytesIO(data)
    size = len(reader.getbuffer())
    
    reader.seek(0x0C)
    crc32_offset = struct.unpack('<I', reader.read(4))[0]
    
    reader.seek(crc32_offset)
    split_anim_crc32 = struct.unpack('<I', reader.read(4))[0]
    
    split_anim_name = reader.read(0x24).decode("shift-jis").rstrip('\0')
    
    anim_crc32 = struct.unpack('<I', reader.read(4))[0]
    reader.read(4)
    
    frame_start = struct.unpack('<I', reader.read(4))[0]
    frame_end = struct.unpack('<I', reader.read(4))[0]
    
    return split_anim_crc32, split_anim_name, anim_crc32, frame_start, frame_end

def write_minf1(animation_name, split_animation_name, frame_start, frame_end):
    out = bytes()
    
    out += bytes([int(x,0) for x in ["0x4D", "0x49", "0x4E", "0x46"] ])
    out += int(0).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    out += int(28).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    out += int(96).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    
    if len(split_animation_name) > 36:
        split_animation_name = split_animation_name[:36]    
    
    out += zlib.crc32(split_animation_name.encode("shift-jis")).to_bytes(4, 'little')
    
    split_animation_name_encode = split_animation_name.encode('shift-jis')
    out += split_animation_name_encode.ljust(36, b'\x00')
    
    out += zlib.crc32(animation_name.encode("shift-jis")).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    
    out += int(frame_start).to_bytes(4, 'little')
    out += int(frame_end).to_bytes(4, 'little')
    
    out += struct.pack('<f', 1.0)
    out += int(0).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    
    return out
    
##########################################
# MINF2
##########################################

def open_minf2(data):
    reader = io.BytesIO(data)
    size = len(reader.getbuffer())
    
    reader.seek(0)

    offsets = []
    sub_animations = []

    while True:
        try_name = reader.read(4).decode("utf-8", errors="ignore")

        if try_name == "MINF":
            reader.read(0x04)
            minf_data_offset = struct.unpack('<i', reader.read(4))[0]
            offsets.append(minf_data_offset)
            reader.read(0x0C)
        else:
            reader.seek(reader.tell() - 4)
            break

    minf_data_reader = io.BytesIO(reader.read(size -  reader.tell()))
    for offset in offsets:
        minf_data_reader.seek(offset)
        hash_value = struct.unpack('<I', minf_data_reader.read(4))[0]
        name = minf_data_reader.read(0x24).decode("shift-jis").rstrip('\0')

        minf_data_reader.seek(offset + 0x28)

        new_sub_animation = {}
        new_sub_animation['split_anim_crc32'] = hash_value
        new_sub_animation['split_anim_name'] = name
        new_sub_animation['anim_crc32'] = struct.unpack('<I', minf_data_reader.read(4))[0]
        minf_data_reader.read(0x04)
        new_sub_animation['frame_start'] = struct.unpack('<i', minf_data_reader.read(4))[0]
        new_sub_animation['frame_end'] = struct.unpack('<i', minf_data_reader.read(4))[0]

        sub_animations.append(new_sub_animation)

    return sub_animations