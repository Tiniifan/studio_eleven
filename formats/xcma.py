import io
import zlib
import struct

from ..compression import lz10, compressor

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
# XCMA Open Function
##########################################

def open(data):
    # Initialize a stream from the data
    data_stream = io.BytesIO(data)
    
    # Initialize a dictionary to store camera values
    cam_values = {}
    
    # List of camera types
    cam_types = ["location", "aim", "focal_length", "roll", "unk"]
    
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

    return header.animation_hash, cam_values
    
##########################################
# XCMA Save Function
##########################################

def get_frame_count(cam_values):
    max_key = 0

    if cam_values:
        for item in cam_values.values():
            if max(item.keys(), default=0) > max_key:
                max_key = max(item.keys())

    return max_key

def write(animation_name, camera_speed, cam_values):
    file_bytes = io.BytesIO()

    hash_name = zlib.crc32(animation_name.encode("shift-jis")).to_bytes(4, 'little')
    hash_name_uint = int.from_bytes(hash_name, byteorder='little', signed=False)
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

        compressed_cam_data = lz10.compress(bytes(cam_data_stream))

        file_bytes.write(struct.pack('4i', 0x10, 0x04, cam_data_start_offset, len(compressed_cam_data) + 0x10))
        file_bytes.write(compressed_cam_data)

    return file_bytes.getvalue()
