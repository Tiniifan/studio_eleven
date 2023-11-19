import io
import struct
from ..compression import lz10, compressor

##########################################
# XCMA Open Function
##########################################

def open_file(filepath):
    with open(filepath, 'rb') as file:
        cam_values = {
            'location': {},
            'rotation': {},
            'focal_length': {},
            'panning': {}
        }

        # Read headers
        header1 = read_struct(file, 'IiiiIIII')
        header2 = read_struct(file, 'Iiiiiiiiii')
        header3 = read_struct(file, 'III6h16h8B')

        hash_name = header2[0]

        cam_values['location'] = read_cam_data(file, 3)
        cam_values['rotation'] = read_cam_data(file, 3)
        cam_values['focal_length'] = read_cam_data(file, 1)
        cam_values['panning'] = read_cam_data(file, 1)

    return hash_name, cam_values

def read_cam_data(file, values_count):
    cam_values = {}

    cam_header = read_struct(file, 'iiii')

    with io.BytesIO(compressor.decompress(bytes(file.read(cam_header[3] - cam_header[0])))) as cam_data_stream:
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


def read_struct(file, format):
    size = struct.calcsize(format)
    data = file.read(size)
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

def save(file_name, hash_name, cam_values):
    with open(file_name, 'wb') as stream:
        header1 = struct.pack('IiiiIIII', 0x414D4358, 0x20, 0x18, 0x01, 0x01, 0x01, 0x01, 0x00)
        header2 = struct.pack('Iiiiiiiii', hash_name, 0x0, get_frame_count(cam_values), 0x02, 0x3F000000, 0x00, 0x0C, 0x1C, 0x50, 0x00)
        pattern1 = struct.pack('hhhh', 0x0201, 0x0300, 0x00, get_frame_count(cam_values))
        pattern2 = struct.pack('hhhh', 0x0201, 0x0100, 0x00, get_frame_count(cam_values))
        header3 = struct.pack('IIIhhhhhhhhh8B', 0xC55BEBD1, 0xC55BEBD1, 0xC55BEBD1, 0x28, 0x30, 0x38, 0x40, 0x48, 0x00, *([pattern1] * 2 + [pattern2] * 2), bytes(8))

        stream.write(header1)
        stream.write(header2)
        stream.write(header3)

        for i in range(4):
            cam_data_stream = bytearray()
            cam_data_start_offset = 0

            cam_data_stream += b'\xFF\xFF' + struct.pack('BBBx', len(cam_values[i]), 0x20)

            frames_indexes = [key for key in cam_values[i].keys()]
            cam_data_stream += struct.pack(f'{len(frames_indexes)}h', *frames_indexes)

            # Write alignment
            alignment = 4 - (len(cam_data_stream) % 4)
            cam_data_stream += bytes(alignment)

            cam_data_start_offset = len(cam_data_stream)

            for key in frames_indexes:
                cam_data_stream += struct.pack(f'{len(cam_values[i][key])}f', *cam_values[i][key])

            compressed_cam_data = lz10.compress(bytes(cam_data_stream))

            stream.write(struct.pack('IIBI', 0x10, 0x04, cam_data_start_offset, len(compressed_cam_data) + 0x10))
            stream.write(compressed_cam_data)
