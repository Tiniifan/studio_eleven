import io
import zlib
import struct

from ..compression import *

def write(name, meshes, thickness, visibility, outline_mesh_data, cmb1, cmb2):
    header = {
        "magic": 0x4C534358,
        "outline_offset": 0x20,
        "mesh_offset": 0x0,
        "mesh_length": 0x0,
        "cmb_offset1": 0x0,
        "cmb_length1": 0x0,
        "cmb_offset2": 0x0,
        "cmb_length2": 0x0,
    }
    
    # Update outline_mesh_data
    outline_mesh_data[20] = thickness
    outline_mesh_data[21] = visibility

    stream = io.BytesIO()

    # Write outlineMeshDataOffset
    stream.seek(0x20)
    
    outline_mesh_data_stream = io.BytesIO()
    outline_mesh_data_stream.write(zlib.crc32(name.encode("shift-jis")).to_bytes(4, 'little'))
    outline_mesh_data_stream.write(int(0).to_bytes(4, 'little'))
    outline_mesh_data_stream.write(int(len(meshes)).to_bytes(4, 'little'))
    
    for value in outline_mesh_data:
        if isinstance(value, int) or isinstance(value, int):
            outline_mesh_data_stream.write(struct.pack('<i', value))
        elif isinstance(value, float) or isinstance(value, float):
            outline_mesh_data_stream.write(struct.pack('<f', value))
        
    header['mesh_offset'] = (len(outline_mesh_data) + 3) * 4
    header['mesh_length'] = len(meshes) * 4
    
    for i in range(len(meshes)):
        outline_mesh_data_stream.write(zlib.crc32(meshes[i].encode("shift-jis")).to_bytes(4, 'little'))
        
    outline_mesh_data_compress = compress(outline_mesh_data_stream.getvalue())
    stream.write(outline_mesh_data_compress)

    # Write CMB1 header
    header['cmb_offset1'] = stream.tell()
    stream.write(struct.pack('<QI', 0x0000303043424D43, 0x0001000C))

    # Write CMB1 data
    cmb1_data_stream = io.BytesIO()
    cmb1_data_stream.write(bytes(cmb1))
    cmb1_data_compress = compress(cmb1_data_stream.getvalue())
    stream.write(cmb1_data_compress)
    header['cmb_length1'] = len(cmb1_data_compress) + 12

    # Write CMB2 header
    header['cmb_offset2'] = stream.tell()
    stream.write(struct.pack('<QI', 0x0000303043424D43, 0x0001000C))

    # Write CMB2 data
    cmb2_data_stream = io.BytesIO()
    cmb2_data_stream.write(bytes(cmb2))
    cmb2_data_compress = compress(cmb2_data_stream.getvalue())
    stream.write(cmb2_data_compress)
    header['cmb_length2'] = len(cmb2_data_compress) + 12

    # Write header
    stream.seek(0)
    stream.write(struct.pack('<Iiiiiiii', *header.values()))

    # Return bytesarray
    return stream.getvalue()