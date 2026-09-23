import io
import zlib
import struct

from ...compression import *
from . import cmb

def to_float32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]

def align_to_4(offset):
    return (offset + 3) & ~3

def write_padding(stream, target_offset):
    current_pos = stream.tell()
    aligned_offset = align_to_4(current_pos)
    if target_offset < aligned_offset:
        target_offset = aligned_offset
    padding_needed = target_offset - current_pos
    if padding_needed > 0:
        stream.write(b'\x00' * padding_needed)
    return target_offset

# Fixed slots of the outline data, they never differ between the shipped files
ENGINE_CONSTANTS = {
    2: 1, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0, 7: 1, 8: 0, 9: 1.0, 10: 1.0, 11: 1.0, 12: 1.0,
    15: 96000.0, 17: 0, 19: 1, 25: 0, 26: 0, 27: 1,
}

# Slots that are integers in the file
INTEGER_SLOTS = {2, 7, 8, 17, 18, 19, 25, 26, 27}

SLOT_COUNT = 28


def make_outline_data(width0, width1, scale, depth_min, depth_max, open_width):
    """The 28 slots of an outline, the game keeps a few of them as scaled copies of the others."""
    data = [ENGINE_CONSTANTS.get(index, 0) for index in range(SLOT_COUNT)]

    unit = to_float32(to_float32(scale) * 10)

    data[0] = to_float32(to_float32(width0) * 10)
    data[1] = to_float32(to_float32(width1) * 10)
    data[2] = int(open_width)
    data[13] = to_float32(400 / unit)
    data[14] = to_float32(240 / unit)
    data[16] = to_float32(2 / unit)
    data[18] = int(open_width)
    data[20] = width0
    data[21] = width1
    data[22] = scale
    data[23] = depth_min
    data[24] = depth_max

    return data


def make_outline_combiner(color, textured, file_version):
    """Constant (or texture) times primary color, the constant is the color of the outline."""
    stage = cmb.CombinerStage(
        source_rgb=(3 if textured else 1, 2, 1), source_alpha=(3 if textured else 1, 2, 1),
        combine_rgb=1, combine_alpha=1, scale_rgb=1, scale_alpha=1,
        constant_color=color,
    )

    return cmb.write_cmb([stage], file_version)


def write(name, meshes, width0, width1, scale, depth_min, depth_max, open_width, color, file_version):
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

    outline_mesh_data = make_outline_data(width0, width1, scale, depth_min, depth_max, open_width)
    stream = io.BytesIO()

    # Write outlineMeshDataOffset
    stream.seek(0x20)

    outline_mesh_data_stream = io.BytesIO()
    outline_mesh_data_stream.write(zlib.crc32(name.encode("shift-jis")).to_bytes(4, 'little'))
    outline_mesh_data_stream.write(int(0).to_bytes(4, 'little'))
    outline_mesh_data_stream.write(int(len(meshes)).to_bytes(4, 'little'))

    for index, value in enumerate(outline_mesh_data):
        if index in INTEGER_SLOTS:
            outline_mesh_data_stream.write(struct.pack('<i', value))
        else:
            outline_mesh_data_stream.write(struct.pack('<f', value))

    # Calculate mesh_offset aligned to 4
    base_mesh_offset = (len(outline_mesh_data) + 3) * 4
    header['mesh_offset'] = align_to_4(base_mesh_offset)
    header['mesh_length'] = len(meshes) * 4

    for i in range(len(meshes)):
        outline_mesh_data_stream.write(zlib.crc32(meshes[i].encode("shift-jis")).to_bytes(4, 'little'))

    outline_mesh_data_compress = compress(outline_mesh_data_stream.getvalue())
    stream.write(outline_mesh_data_compress)

    # The first combiner is the plain outline, the second one the textured outline
    for index, textured in enumerate((False, True), start=1):
        write_padding(stream, align_to_4(stream.tell()))
        header[f'cmb_offset{index}'] = stream.tell()

        combiner = make_outline_combiner(color, textured, file_version)
        stream.write(combiner)
        header[f'cmb_length{index}'] = len(combiner)

    # Write header
    stream.seek(0)
    stream.write(struct.pack('<Iiiiiiii', *header.values()))

    # Return bytesarray
    return stream.getvalue()


def read(data):
    """The outline of a .sil file, the combiners only carry the outline color."""
    magic, outline_offset, mesh_offset, mesh_length, cmb_offset1, cmb_length1, _, _ = struct.unpack_from('<Iiiiiiii', data)
    if magic != 0x4C534358:
        raise ValueError(f"Unknown outline magic: {magic:#x}")

    block = compressor.decompress(data[outline_offset:])
    name_hash, render_program_hash, mesh_count = struct.unpack_from('<3I', block)
    slots = [struct.unpack_from('<i' if index in INTEGER_SLOTS else '<f', block, 12 + index * 4)[0] for index in range(SLOT_COUNT)]

    # A .sil may come without combiners, the outline is then white like the ones this addon used to write
    color = (255, 255, 255, 255)
    if cmb_length1 > 0:
        color = cmb.read_cmb(data[cmb_offset1:cmb_offset1 + cmb_length1])[1][0].constant_color

    return {
        "name_hash": name_hash,
        "render_program_hash": render_program_hash,
        "thickness": slots[20],
        "visibility": slots[21],
        "scale": slots[22],
        "depth_min": slots[23],
        "depth_max": slots[24],
        "open_width": bool(slots[2]),
        "color": color,
        "mesh_hashes": list(struct.unpack_from(f'<{mesh_length // 4}I', block, mesh_offset)),
    }
