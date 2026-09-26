import io
import zlib
import struct

from ...compression import lz10, compressor

##########################################
# XCMA Header Class
##########################################

class Header:
    header_format = '12I1f1I'
    
    def __init__(self, *args):
        self.magic = args[0]
        self.data_offset = args[1]
        self.data_skip_offset = args[2]
        self.enable_location = args[3]
        self.enable_target = args[4]
        self.enable_focal_length = args[5]
        self.enable_roll = args[6]
        self.enable_unk = args[7]
        self.animation_hash = args[8]
        self.empty_block1 = args[9]
        self.frame_count = args[10]
        self.unk1 = args[11]
        self.cam_speed = args[12]
        self.unk1 = args[13]
        
class CameraSettingHeader:
    header_format = '4I'
    
    def __init__(self, *args):
        self.track_length = args[0]
        self.track_offset = args[1]
        self.block_length = args[2]
        self.empty_block = args[3]

##########################################
# CONST
##########################################

cam_types = ["location", "aim", "focal_length", "roll", "unk"]

##########################################
# XCMA Function
##########################################

def get_frame_count(cam_values):
    max_key = 0

    if cam_values:
        for item in cam_values.values():
            if max(item.keys(), default=0) > max_key:
                max_key = max(item.keys())

    return max_key

def is_hash_name(animation_name):
    if len(animation_name) != 10 or animation_name[:2].lower() != "0x":
        return False

    for c in animation_name[2:]:
        if c not in "0123456789abcdefABCDEF":
            return False

    return True

def get_animation_hash(animation_name):
    # Imported cameras only have the hash of their name, written as 0xXXXXXXXX
    if is_hash_name(animation_name):
        return int(animation_name, 16)

    return zlib.crc32(animation_name.encode("shift-jis"))

def fill_ghost_frames(frames_indexes, size):
    # For each frame, the index of the last key at or before it
    result = [0] * size

    for i in range(len(frames_indexes)):
        if i != len(frames_indexes) - 1:
            next_value = frames_indexes[i + 1]
        else:
            next_value = size

        for j in range(frames_indexes[i], min(next_value, size)):
            result[j] = i

    return result

def write_alignment(stream, alignment=4):
    remainder = len(stream) % alignment
    if remainder > 0:
        stream += bytes(alignment - remainder)

##########################################
# XCMA V1
##########################################

def write_v1(animation_name, camera_speed, cam_values):
    out = bytes()

    frame_count = get_frame_count(cam_values)

    tracks = []
    for cam_type in cam_types[:4]:
        tracks.append(cam_values.get(cam_type, {}))

    out += b"XCMA"
    out += int(0x20).to_bytes(4, 'little')
    out += int(0x14).to_bytes(4, 'little')

    for track in tracks:
        out += int(len(track) > 0).to_bytes(4, 'little')

    out += int(0).to_bytes(4, 'little')

    out += int(get_animation_hash(animation_name)).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    out += struct.pack("<i", frame_count)
    out += int(0x02).to_bytes(4, 'little')
    out += struct.pack("<f", camera_speed)

    for track in tracks:
        if len(track) == 0:
            continue

        frames_indexes = list(track.keys())

        component_count = 1
        if not isinstance(track[frames_indexes[0]], (int, float)):
            component_count = len(track[frames_indexes[0]])

        # Motion header (0x30 bytes)
        motion = bytearray()
        motion += int(0xC55BEBD1).to_bytes(4, 'little')
        motion += bytes([0x01, 0x02])
        motion += struct.pack("<h", 0x01)
        motion += struct.pack("<i", 0x00)
        motion += struct.pack("<i", frame_count)
        motion += struct.pack("<i", len(frames_indexes))
        motion += struct.pack("<i", frame_count + 1)
        motion += struct.pack("<i", 0x04)
        motion += struct.pack("<i", component_count)
        motion += struct.pack("<i", component_count * 4)
        motion += struct.pack("<i", (frame_count + 1) * 2)
        motion += struct.pack("<i", len(frames_indexes) * 2)
        motion += struct.pack("<i", len(frames_indexes) * component_count * 4)

        for ghost_frame in fill_ghost_frames(frames_indexes, frame_count + 1):
            motion += struct.pack("<h", ghost_frame)

        write_alignment(motion)

        frame_offset = len(motion)

        for frame in frames_indexes:
            motion += struct.pack("<h", frame)

        write_alignment(motion)

        value_offset = len(motion)

        for key in frames_indexes:
            if component_count == 1:
                motion += struct.pack("<f", float(track[key]))
            else:
                for value in track[key]:
                    motion += struct.pack("<f", value)

        compressed_motion = bytearray(compressor.compress(bytes(motion)))
        write_alignment(compressed_motion)

        out += struct.pack("<i", 0x14)
        out += struct.pack("<i", 0x30)
        out += struct.pack("<i", frame_offset)
        out += struct.pack("<i", value_offset)
        out += struct.pack("<i", 0x14 + len(compressed_motion))
        out += bytes(compressed_motion)

    return out

def read_v1(data):
    cam_values = {}

    reader = io.BytesIO(data)

    xcma_magic = struct.unpack("<I", reader.read(4))[0]
    data_offset = struct.unpack("<I", reader.read(4))[0]
    data_skip_offset = struct.unpack("<I", reader.read(4))[0]

    track_counts = []
    for i in range(5):
        track_counts.append(struct.unpack("<I", reader.read(4))[0])

    reader.seek(data_offset)
    animation_hash = struct.unpack("<I", reader.read(4))[0]
    empty_block = struct.unpack("<i", reader.read(4))[0]
    frame_count = struct.unpack("<i", reader.read(4))[0]
    unk = struct.unpack("<I", reader.read(4))[0]
    cam_speed = struct.unpack("<f", reader.read(4))[0]

    block_offset = data_offset + data_skip_offset

    for i in range(5):
        for j in range(track_counts[i]):
            reader.seek(block_offset)
            compressed_offset = struct.unpack("<I", reader.read(4))[0]
            ghost_frame_offset = struct.unpack("<I", reader.read(4))[0]
            frame_offset = struct.unpack("<I", reader.read(4))[0]
            value_offset = struct.unpack("<I", reader.read(4))[0]
            block_length = struct.unpack("<I", reader.read(4))[0]

            motion = io.BytesIO(compressor.decompress(data[block_offset + compressed_offset:block_offset + block_length]))

            # Motion header (0x30 bytes): hash, flags, frame count, key count, ghost frame count, value size, component count...
            motion.seek(0x10)
            key_count = struct.unpack("<i", motion.read(4))[0]
            ghost_frame_count = struct.unpack("<i", motion.read(4))[0]
            value_size = struct.unpack("<i", motion.read(4))[0]
            component_count = struct.unpack("<i", motion.read(4))[0]

            if value_size != 4:
                raise NotImplementedError(f"Camera value size {value_size} not implemented")

            motion.seek(frame_offset)

            frames_indexes = []
            for k in range(key_count):
                frames_indexes.append(struct.unpack("<h", motion.read(2))[0])

            if cam_types[i] not in cam_values:
                cam_values[cam_types[i]] = {}

            motion.seek(value_offset)

            for k in range(key_count):
                anim_data = []
                for c in range(component_count):
                    anim_data.append(struct.unpack("<f", motion.read(4))[0])

                if len(anim_data) == 1:
                    anim_data = anim_data[0]

                cam_values[cam_types[i]][frames_indexes[k]] = anim_data

            motion.close()

            block_offset += block_length

    reader.close()

    return {
        'hash': animation_hash,
        'speed': cam_speed,
        'frame_count': frame_count,
        'version': 'V1',
        'values': cam_values,
    }

##########################################
# XCMA V2
##########################################

def write_v2(animation_name, camera_speed, cam_values):
    file_bytes = io.BytesIO()

    hash_name_uint = get_animation_hash(animation_name)
    header1 = struct.pack('IiiiIIII', 0x414D4358, 0x20, 0x18, 0x01, 0x01, 0x01, 0x01, 0x00)
    header2 = struct.pack('Iiiifiiiii', hash_name_uint, 0x0, get_frame_count(cam_values), 0x02, camera_speed, 0x00, 0x0C, 0x1C, 0x50, 0x00)
    pattern1 = struct.pack('hhhh', 0x0201, 0x0300, 0x00, get_frame_count(cam_values))
    pattern2 = struct.pack('hhhh', 0x0201, 0x0100, 0x00, get_frame_count(cam_values))
    pattern1_octets = struct.unpack('4h', pattern1)
    pattern2_octets = struct.unpack('4h', pattern2)
    header3 = struct.pack('III6h4h4h4h4h8B',
                      0xC55BEBD1, 0xC55BEBD1, 0xC55BEBD1,
                      0x28, 0x30, 0x38, 0x40, 0x48,
                      0x00,
                      pattern1_octets[0], pattern1_octets[1], pattern1_octets[2], pattern1_octets[3],
                      pattern1_octets[0], pattern1_octets[1], pattern1_octets[2], pattern1_octets[3],
                      pattern2_octets[0], pattern2_octets[1], pattern2_octets[2], pattern2_octets[3],
                      pattern2_octets[0], pattern2_octets[1], pattern2_octets[2], pattern2_octets[3],
                      0, 0, 0, 0, 0, 0, 0, 0)

    file_bytes.write(header1)
    file_bytes.write(header2)
    file_bytes.write(header3)

    for cam_value in list(cam_values.values()):
        cam_data_stream = bytearray()
        cam_data_start_offset = 0

        cam_data_stream += b'\xFF\xFF'
        if (len(cam_value) < 255):
            cam_data_stream += struct.pack("<BB", len(cam_value), 0x00)
        else:
            lowFrameCount = len(cam_value) & 0xFF
            highFrameCount = 32 + (len(cam_value) >> 8) & 0xFF
            cam_data_stream += struct.pack("<BB", lowFrameCount, highFrameCount)

        frames_indexes = [key for key in cam_value.keys()]
        cam_data_stream += struct.pack(f'{len(frames_indexes)}h', *frames_indexes)

        # Write alignment
        alignment = 4 - (len(cam_data_stream) % 4)
        cam_data_stream += bytes(alignment)

        cam_data_start_offset = len(cam_data_stream)

        for key in frames_indexes:
            if isinstance(cam_value[key], float):
                cam_data_stream += struct.pack('f', cam_value[key])
            elif isinstance(cam_value[key], int):
                cam_data_stream += struct.pack('f', float(cam_value[key]))
            else:
                cam_data_stream += struct.pack(f'{len(cam_value[key])}f', *cam_value[key])

        compressed_cam_data = bytearray(compressor.compress(bytes(cam_data_stream)))
        write_alignment(compressed_cam_data)

        file_bytes.write(struct.pack('4i', 0x10, 0x04, cam_data_start_offset, len(compressed_cam_data) + 0x10))
        file_bytes.write(compressed_cam_data)

    return file_bytes.getvalue()

def read_v2(data):
    # Initialize a stream from the data
    data_stream = io.BytesIO(data)
    
    # Initialize a dictionary to store camera values
    cam_values = {}
    
    # Read the header
    header = Header(*struct.unpack(Header.header_format, data_stream.read(56)))
    
    # Calculate the number of tracks
    track_count = header.enable_location + header.enable_target + header.enable_focal_length + header.enable_roll + header.enable_unk
    
    # Read the camera setting header
    setting_start = data_stream.tell()
    setting = CameraSettingHeader(*struct.unpack(CameraSettingHeader.header_format, data_stream.read(16)))
    
    # Get tracks
    tracks = []
    for i in range(5):
        # Read track offset
        data_stream.seek(setting_start + setting.track_offset + i * 2)
        track_offset = struct.unpack('H', data_stream.read(2))[0]
        
        # Read track data
        data_stream.seek(setting_start + track_offset)
        track = {}
        track["type"] = struct.unpack("<B", data_stream.read(1))[0]
        track["data_type"] = struct.unpack("<B", data_stream.read(1))[0]
        track["unk"] = struct.unpack("<B", data_stream.read(1))[0]
        track["data_count"] = struct.unpack("<B", data_stream.read(1))[0]
        track["start"] = struct.unpack("<H", data_stream.read(2))[0]
        track["end"] = struct.unpack("<H", data_stream.read(2))[0]
        tracks.append(track)

    # Get to data offset
    data_stream.seek(setting_start + setting.block_length)

    # Iterate over tracks
    for i in range(track_count):
        track = tracks[i]
        block_offset = data_stream.tell()
        
        # Read block metadata
        decomp_offset = struct.unpack('I', data_stream.read(4))[0]
        frame_offset = struct.unpack('I', data_stream.read(4))[0]
        data_offset = struct.unpack('I', data_stream.read(4))[0]
        block_length = struct.unpack('I', data_stream.read(4))[0]
        
        # Decompress block data
        with io.BytesIO(compressor.decompress(data_stream.read(block_length - decomp_offset))) as cam_data_stream:
            values = {}
            frames_count = 0
            
            # Read header
            bone_index = struct.unpack("<h", cam_data_stream.read(2))[0]
            low_frame_count = struct.unpack("<B", cam_data_stream.read(1))[0]
            high_frame_count = struct.unpack("<B", cam_data_stream.read(1))[0]
            if high_frame_count == 0:
                frames_count = low_frame_count
            else:
                high_frame_count -= 32
                frames_count = (high_frame_count << 8) | low_frame_count
            
            # Read frame indexes
            frames_indexes = struct.unpack(f'{frames_count}h', cam_data_stream.read(2 * frames_count))
            
            # Read data
            cam_data_stream.seek(data_offset)
            for k in range(frames_count):
                frame_index = frames_indexes[k]
                
                anim_data = [0] * track["data_count"]
                for j in range(track["data_count"]):
                    if track["data_type"] == 1:
                        anim_data[j] = struct.unpack("<h", cam_data_stream.read(2))[0] / float(0x7FFF)
                    elif track["data_type"] == 2:
                        anim_data[j] = struct.unpack("<f", cam_data_stream.read(4))[0]
                    elif track["data_type"] == 4:
                        anim_data[j] = struct.unpack("<h", cam_data_stream.read(2))[0]
                    else:
                        raise NotImplementedError(f"Data Type {track['data_type']} not implemented")
               
                if len(anim_data) == 1:
                    anim_data = anim_data[0]
                    
                values[frame_index] = anim_data
            
            # Store values in cam_values dictionary
            cam_values[cam_types[i]] = values

    return {
        'hash': header.animation_hash,
        'speed': header.cam_speed,
        'frame_count': header.frame_count,
        'version': 'V2',
        'values': cam_values,
    }

##########################################
# XCMA Write Function
##########################################

def write(animation_name, camera_speed, cam_values, version="V2"):
    if version == "V1":
        return write_v1(animation_name, camera_speed, cam_values)
    else:
        return write_v2(animation_name, camera_speed, cam_values)

##########################################
# XCMA Open Function
##########################################

def is_v1(data):
    # V1 has its track blocks right after a 0x14 bytes animation header
    return struct.unpack_from('<I', data, 8)[0] == 0x14

def read(data):
    if is_v1(data):
        return read_v1(data)
    else:
        return read_v2(data)

def open(data):
    camera = read(data)

    return camera['hash'], camera['values']
