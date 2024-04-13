import io
import zlib
import struct

from ..compression import lz10, compressor

##########################################
# XCMA Open Function
##########################################

def open(data):
    data_stream = io.BytesIO(data)
    
    cam_values = {
        'location': {},
        'aim': {},
        'focal_length': {},
        'roll': {}
    }

    # Read headers
    header1 = read_struct(data_stream, 'IiiiIIII')
    header2 = read_struct(data_stream, 'Iiiiiiiiii')
    header3 = read_struct(data_stream, 'III6h16h8B')

    hash_name = header2[0]

    cam_values['location'] = read_cam_data(data_stream, 3)
    cam_values['aim'] = read_cam_data(data_stream, 3)
    cam_values['focal_length'] = read_cam_data(data_stream, 1)
    cam_values['roll'] = read_cam_data(data_stream, 1)

    return hash_name, cam_values

def read_cam_data(data_stream, values_count):
    cam_values = {}

    cam_header = read_struct(data_stream, 'iiii')

    with io.BytesIO(compressor.decompress(data_stream.read(cam_header[3] - cam_header[0]))) as cam_data_stream:
        unk1 = struct.unpack('B', cam_data_stream.read(1))[0]
        unk2 = struct.unpack('B', cam_data_stream.read(1))[0]
        frames_count = struct.unpack('B', cam_data_stream.read(1))[0]
        unk3 = struct.unpack('B', cam_data_stream.read(1))[0]

        frames_indexes = struct.unpack(f'{frames_count}h', cam_data_stream.read(2 * frames_count))

        cam_data_stream.seek(cam_header[2])

        for k in range(frames_count):
            frame_index = frames_indexes[k]
            values = struct.unpack(f'{values_count}f', cam_data_stream.read(4 * values_count))
            
            if values_count == 1:
                cam_values[frame_index] = values[0]
            else:
                cam_values[frame_index] = list(values)
            
    return cam_values

def read_struct(data_stream, format):
    size = struct.calcsize(format)
    data = data_stream.read(size)
    return struct.unpack(format, data)
    
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

def write(animation_name, cam_values):
    file_bytes = io.BytesIO()

    hash_name = zlib.crc32(animation_name.encode("shift-jis")).to_bytes(4, 'little')
    hash_name_uint = int.from_bytes(hash_name, byteorder='little', signed=False)
    header1 = struct.pack('IiiiIIII', 0x414D4358, 0x20, 0x18, 0x01, 0x01, 0x01, 0x01, 0x00)
    header2 = struct.pack('Iiiiiiiiii', hash_name_uint, 0x0, get_frame_count(cam_values), 0x02, 0x3F000000, 0x00, 0x0C, 0x1C, 0x50, 0x00)
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

        cam_data_stream += b'\xFF\xFF' + struct.pack('BB', len(cam_value), 0x20)

        frames_indexes = [key for key in cam_value.keys()]
        cam_data_stream += struct.pack(f'{len(frames_indexes)}h', *frames_indexes)

        # Write alignment
        alignment = 4 - (len(cam_data_stream) % 4)
        cam_data_stream += bytes(alignment)

        cam_data_start_offset = len(cam_data_stream)

        for key in frames_indexes:
            if isinstance(cam_value[key], float):
                cam_data_stream += struct.pack('f', cam_value[key])
            else:
                cam_data_stream += struct.pack(f'{len(cam_value[key])}f', *cam_value[key])

        compressed_cam_data = lz10.compress(bytes(cam_data_stream))

        file_bytes.write(struct.pack('4i', 0x10, 0x04, cam_data_start_offset, len(compressed_cam_data) + 0x10))
        file_bytes.write(compressed_cam_data)

    return file_bytes.getvalue()
