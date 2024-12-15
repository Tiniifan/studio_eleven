import io
import zlib
import struct

from enum import Enum
from ..compression import *

##########################################
# RESType
##########################################

class RESType(Enum):
    BONE = 110
    TEXPROJ = 140
    PROPERTIES = 200
    SHADING = 120
    MATERIAL_1 = 220
    MATERIAL_2 = 230
    MESH_NAME = 100
    TEXTURE_DATA = 240
    MATERIAL_DATA = 290
    ANIMATION_MTN2 = 300
    ANIMATION_MTN3 = 301
    ANIMATION_IMM2 = 310
    ANIMATION_MTM2 = 320
    MTNINF = 400
    MTNINF2 = 401
    IMMINF = 410
    MTMINF = 420
    NULL = 9999
    MATERIAL_TYPE_UNK1 = 0
    MATERIAL_TYPE_UNK2 = 1
    NODE_TYPE_UNK1 = 2
    NODE_TYPE_UNK2 = 3
    NODE_TYPE_UNK3 = 4
    NODE_TYPE_UNK4 = 460
    NODE_TYPE_UNK5 = 320
    NODE_TYPE_UNK6 = 420
    NODE_TYPE_UNK7 = 20
    
materials_ordered = [
    RESType.MATERIAL_TYPE_UNK1,
    RESType.MATERIAL_1,
    RESType.MATERIAL_2,
    RESType.TEXTURE_DATA,
    RESType.MATERIAL_TYPE_UNK2,
    RESType.MATERIAL_DATA,
]

nodes_ordered = [
    RESType.MESH_NAME,
    RESType.BONE,
    RESType.ANIMATION_MTN2,
    RESType.ANIMATION_MTN3,
    RESType.ANIMATION_IMM2,
    RESType.ANIMATION_MTM2,
    RESType.SHADING,
    RESType.NODE_TYPE_UNK2,
    RESType.PROPERTIES,
    RESType.MTNINF,
    RESType.MTNINF2,
    RESType.IMMINF,
    RESType.MTMINF,
    RESType.TEXPROJ,
]

##########################################
# Read String
##########################################
    
def read_string(byte_io):
    bytes_list = []
    
    while True:
        byte = byte_io.read(1)
        if byte == b'\x00':
            break
        bytes_list.append(byte)
    
    name = b''.join(bytes_list).decode('shift-jis')
    return name    

##########################################
# RES
##########################################

def open_res(stream=None, data=None, string_table=None, items=None):
    string_table = string_table or {}
    items = items or {}

    if stream:
        with io.BytesIO(compressor.decompress(stream.read())) as reader:
            read_data(reader, string_table, items)

    elif data:
        with io.BytesIO(compressor.decompress(data)) as reader:
            read_data(reader, string_table, items)

    elif string_table and items:
        pass  # Already provided, no need to read data

    return items

def read_data(reader, string_table, items):
    header = struct.unpack("<qhhhhhh", reader.read(20))
    string_offset = header[1] << 2
    material_table_offset = header[3] << 2
    material_table_count = header[4]
    node_offset = header[5] << 2
    node_count = header[6]

    reader.seek(string_offset)
    text_reader = io.BytesIO(reader.read())
    text_section = text_reader.read().decode("shift-jis").split("\x00")
    for text in text_section:
        if text == "":
            continue
        
        crc32text = zlib.crc32(text.encode("shift-jis"))
        if crc32text not in string_table:
            string_table[crc32text] = text
        
        text_split = text.split(".")
        for t in text_split:
            crc32text_split = zlib.crc32(t.encode("shift-jis"))
            if crc32text_split not in string_table:
                string_table[crc32text_split] = t
        
        text_split = text.split("_")
        for t in text_split:
            crc32text_split = zlib.crc32(t.encode("shift-jis"))
            if crc32text_split not in string_table:
                string_table[crc32text_split] = t
    
    read_section_table(reader, material_table_offset, material_table_count, items, string_table, text_reader)
    read_section_table(reader, node_offset, node_count, items, string_table, text_reader)
    
def get_object_name(type_reader, text_reader, string_table):
    material_crc32 = struct.unpack("<I", type_reader.read(4))[0]
                
    if material_crc32 in string_table:
        return string_table[material_crc32]
    else:
        text_reader.seek(struct.unpack("<I", type_reader.read(4))[0])
        name = read_string(text_reader)
        return name    

def read_section_table(reader, table_offset, table_count, items, string_table, text_reader):
    for i in range(table_count):
        reader.seek(table_offset + i * 8)
        header_table = struct.unpack("<hhhh", reader.read(8))

        data_offset = header_table[0] << 2
        count = header_table[1]
        _type = header_table[2]
        length = header_table[3]
        
        if RESType(_type) == RESType.Null:
            continue

        if RESType(_type) not in items:
            items[RESType(_type)] = {}

        for j in range(count):
            reader.seek(data_offset + j * length)
            type_reader = io.BytesIO(reader.read(length))
            
            object_name = get_object_name(type_reader, text_reader, string_table)
            object_crc32 = zlib.crc32(object_name.encode("shift-jis"))
            
            if length == 8:
                items[RESType(_type)][object_crc32] = object_name
            elif RESType(_type) == RESType.Texture:
                type_reader.seek(8)
                texture_unk = struct.unpack("<b", type_reader.read(1))[0]
                next_facial_expression = struct.unpack("<b", type_reader.read(1))[0]
                
                texture_dict = {}
                texture_dict['name'] = object_name
                texture_dict['texture_unk'] = texture_unk
                texture_dict['next_facial_expression'] = next_facial_expression
                
                items[RESType(_type)][object_crc32] = texture_dict
            elif RESType(_type) == RESType.MaterialData:
                type_reader.seek(16)
                linked_textures = []
                
                max_texture = (length-16) // 52
                for k in range(max_texture):
                    texture_crc32 = struct.unpack("<I", type_reader.read(4))[0]
                    
                    if texture_crc32 != 0:    
                        linked_textures.append(hex(texture_crc32))
                                        
                    type_reader.seek(type_reader.tell() + 48)        
                
                material_dict = {}
                material_dict['name'] = object_name
                material_dict['textures'] = linked_textures
                
                items[RESType(_type)][object_crc32] = material_dict               

def make_library(meshes = [], armature = None, textures = {}, animations = {}, outline_name = "", properties=[], texprojs=[]):
    items = {}
    string_table = bytes()
    materials_offset = {}
    
    if meshes:
        # Add material name (twice time no idea why)
        materials_name = []
        
        for mesh in meshes:
            material_name = mesh.material_name.encode("shift-jis")
            materials_name.append(zlib.crc32(material_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little')) 
            materials_offset[material_name] = len(string_table)           
            string_table += material_name + int(0).to_bytes(1, 'little')
        
        items[RESType.MATERIAL_1] = materials_name
        items[RESType.MATERIAL_2] = materials_name
        
        # Add mesh name
        meshes_name = []
        
        for mesh in meshes:
            mesh_name = mesh.name.encode("shift-jis")
            meshes_name.append(zlib.crc32(mesh_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))   
            string_table += mesh_name + int(0).to_bytes(1, 'little')
                
        items[RESType.MESH_NAME] = meshes_name

    if textures:
        # Add texture data (texture name and texture mode)
        textures_data = [] 
        
        for texture_name, texture_data in textures.items():
            texture_name_encoded = texture_name.encode("shift-jis")
            textures_data.append(zlib.crc32(texture_name_encoded).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little') + bytes.fromhex("030A00000000000000000000"))
            string_table += texture_name_encoded + int(0).to_bytes(1, 'little')
            
        items[RESType.TEXTURE_DATA] = textures_data

        # Add material data (texture used by the material)
        materials_info = {}
        
        for texture_name, texture_data in textures.items():
            for material_name in texture_data['linked_material']:
                if material_name not in materials_info:
                    materials_info[material_name] = []
                
                if texture_name not in materials_info[material_name]:
                    materials_info[material_name].append(texture_name)

        materials_data = []
        for material_name, material_info in materials_info.items():
            material_name_encoded = material_name.encode("shift-jis")
            material_name_crc32 = zlib.crc32(material_name_encoded).to_bytes(4, 'little')
            
            if material_name in materials_offset:
                material_data = material_name_crc32 + int(materials_offset[material_name]).to_bytes(4, 'little') + material_name_crc32 + material_name_crc32
            else:
                material_data = material_name_crc32 + int(0).to_bytes(4, 'little') + material_name_crc32 + material_name_crc32
            
            for i in range(4):
                if i < len(material_info):
                    texture_name = material_info[i].encode("shift-jis")
                    material_data += zlib.crc32(texture_name).to_bytes(4, 'little') + bytes.fromhex("010000000000803F0000803F00000000000000000000803F00000000000000000000803F00000000000000000000803F")
                else:
                    material_data += bytes.fromhex("00000000000000000000803F0000803F00000000000000000000803F00000000000000000000803F00000000000000000000803F")
                    
            materials_data.append(material_data)
        
        items[RESType.MATERIAL_DATA] = materials_data
        
    if armature:
        bones_name = []
        
        for bone in armature.pose.bones:
            bone_name = bone.name.encode("shift-jis")
            bones_name.append(zlib.crc32(bone_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))    
            string_table += bone_name + int(0).to_bytes(1, 'little')

        items[RESType.BONE] = bones_name
        
    if animations:
        # Add animation name
        animations_mtn2 = []
        animations_imm2 = []
        animations_mtm2 = []
        animations_offset = {}
        
        for animation_type, animation_data in animations.items():
            animation_name = animation_data['name']
            animation_name_encoded = animation_name.encode("shift-jis")
            
            if animation_name not in animations_offset:
                animations_offset[animation_name] = len(string_table)
                string_table += animation_name + int(0).to_bytes(1, 'little')
            
            animation_bytes = zlib.crc32(animation_name_encoded).to_bytes(4, 'little') + int(animations_offset[animation_name]).to_bytes(4, 'little')

            if animation_type == 'armature':
               animations_mtn2.append(animation_bytes) 
            elif animation_type == 'uv':
                animations_imm2.append(animation_bytes) 
            elif animation_type == 'material':
                animations_mtm2.append(animation_bytes) 
        
        items[RESType.ANIMATION_MTN2] = animations_mtn2
        items[RESType.ANIMATION_IMM2] = animations_imm2
        items[RESType.ANIMATION_MTM2] = animations_mtm2        

        # Add animation split name
        mtninfs = []
        immninfs = []
        mtminfs = []
        animations_split_offset = {}
        
        for animation_type, animation_data in animations.items():
            for split_animation in animation_data['split_animation']['split']:
                animation_split_name = split_animation.name
                animation_split_name_encoded = animation_split_name.encode("shift-jis")
                
                if animation_split_name not in animations_split_offset:
                    animations_split_offset[animation_split_name] = len(string_table)
                    string_table += animation_split_name + int(0).to_bytes(1, 'little')
                
                animation_split_bytes = zlib.crc32(animation_split_name_encoded).to_bytes(4, 'little') + int(animations_split_offset[animation_split_name]).to_bytes(4, 'little')

                if animation_type == 'armature':
                   mtninfs.append(animation_split_bytes) 
                elif animation_type == 'uv':
                    immninfs.append(animation_split_bytes) 
                elif animation_type == 'material':
                    mtminfs.append(animation_split_bytes) 
                
        items[RESType.MTNINF] = mtninfs
        items[RESType.IMMINF] = immninfs
        items[RESType.MTMINF] = mtminfs          

    if outline_name:
        name = outline_name.encode("shift-jis")
        string_table += name + int(0).to_bytes(1, 'little')
        items[RESType.SHADING] = [name]
        
    if properties:
        properties_name = []
        
        for archive_property in properties:
            property_name = archive_property[0].encode("shift-jis")
            properties_name.append(zlib.crc32(property_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))
            string_table += property_name + int(0).to_bytes(1, 'little')
            
        items[RESType.PROPERTIES] = properties_name
        
    if texprojs:
        texprojs_name = []
        
        for texproj in texprojs:
            texproj_name = texproj[0].encode("shift-jis")
            texprojs_name.append(zlib.crc32(texproj_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))
            string_table += texproj_name + int(0).to_bytes(1, 'little')
            
        items[RESType.TEXPROJ] = texprojs_name
        
    return items, string_table
                
def write_res(magic, items, string_table):
    materials = {key: value for key, value in items.items() if key in materials_ordered}
    nodes = {key: value for key, value in items.items() if key in nodes_ordered}

    header = {
        'Magic': int.from_bytes(magic, byteorder='little'),
        '_stringOffset': 0,  # Placeholder for string offset
        'Unk1': 1,
        '_materialTableOffset': 0,  # Placeholder for material table offset
        'MaterialTableCount': len(materials),
        '_nodeOffset': 0,  # Placeholder for node offset
        'NodeCount': len(nodes),
    }

    header_pos = 20
    data_pos = header_pos + len(items) * 8

    with io.BytesIO() as writer_res:
        with io.BytesIO() as writer_table:
            with io.BytesIO() as writer_data:
                # Material - Header table
                if materials:
                    header['_materialTableOffset'] = header_pos >> 2

                    for res_type, res_value in materials.items():
                        material_header_table = {
                            '_dataOffset': data_pos >> 2,
                            'Count': len(res_value),
                            'Type': res_type.value,
                            'Length': len(res_value[0]),
                        }

                        header_pos += 8
                        data_pos += sum(len(byte_array) for byte_array in res_value)

                        writer_table.write(struct.pack('<hhhh', *material_header_table.values()))
                        writer_data.write(b''.join(res_value))

                # Node - Header table
                if nodes:
                    header['_nodeOffset'] = header_pos >> 2

                    for res_type, res_value in nodes.items():
                        node_header_table = {
                            '_dataOffset': data_pos >> 2,
                            'Count': len(res_value),
                            'Type': res_type.value,
                            'Length': len(res_value[0]),
                        }

                        header_pos += 8
                        data_pos += sum(len(byte_array) for byte_array in res_value)

                        writer_table.write(struct.pack('<hhhh', *node_header_table.values()))
                        writer_data.write(b''.join(res_value))

                # String table
                header['_stringOffset'] = writer_data.tell() + 20 + len(items) * 8 >> 2
                writer_data.write(string_table)
                        
                # Calculate padding for alignment
                remaining_bytes = 4 - (writer_res.tell() % 4)
                if remaining_bytes != 4:
                    padding = bytes([0] * remaining_bytes)
                    writer_res.write(padding)                        

                writer_res.seek(0)
                writer_res.write(struct.pack('<qhhhhhh', *header.values()))
                writer_res.write(writer_table.getvalue())
                writer_res.write(writer_data.getvalue())
                
                return compress(writer_res.getvalue())

##########################################
# XRES
##########################################

