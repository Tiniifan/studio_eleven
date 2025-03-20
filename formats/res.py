import io
from zlib import crc32
from struct import pack, unpack, unpack_from, Struct

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
    MESH_GROUP = 210
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
# RES
##########################################

class ResHeader:
    def __init__(self, data):
        strct = Struct("<HhHHHH")
        _stringOffset, self.Unk1, _materialTableOffset, self.MaterialTableCount, _nodeOffset, self.NodeCount = \
            strct.unpack_from(data, 0)
        self.StringOffset = _stringOffset << 2
        self.MaterialTableOffset = _materialTableOffset << 2
        self.NodeOffset = _nodeOffset << 2

class ResHeaderTable:
    def __init__(self, data, offset):
        strct = Struct("<HHHH")
        _dataOffset, self.Count, self.Type, self.Length = \
            strct.unpack_from(data, offset)
        self.DataOffset = _dataOffset << 2

def read_string_table(data):
    string_table = {}
    text = b""
    for i in range(len(data)):
        char = data[i].to_bytes(1, "little")
        if char == b"\x00":
            text = text.decode("shift-jis")
            if text != "":
                if text not in string_table:
                    string_table[crc32(text.encode("shift-jis"))] = text
                
                splitting = [".", "_"]
                for j in splitting:
                    splitted = text.split(j)
                    for k in splitted:
                        if k not in string_table:
                            string_table[crc32(k.encode("shift-jis"))] = k
            text = b""
        else:
            text += char
    return string_table

def open_res(data):
    data = compressor.decompress(data)
    
    magic = data[:4]
    if magic == b"XRES":
        return open_xres(data)
    
    items = {}
    
    header = ResHeader(data[8:])
    
    text_section = data[header.StringOffset:len(data)]
    string_table = read_string_table(text_section)
    
    def read_section_table(data, tableOffset, tableCount):
        for i in range(tableCount):
            pos = tableOffset + i * 8
            
            headerTable = ResHeaderTable(data, pos)
            pos += 8
            
            if RESType(headerTable.Type) == RESType.NULL:       continue
            if RESType(headerTable.Type) == RESType.MESH_GROUP: continue
            if RESType(headerTable.Type) not in items:
                items[RESType(headerTable.Type)] = {}
            
            for j in range(headerTable.Count):
                pos = headerTable.DataOffset + j * headerTable.Length
                section = data[pos:pos+headerTable.Length]
                
                pos = 0
                obj_hash = unpack_from("<I", section, pos)[0]
                obj_name = string_table[obj_hash]
                
                if headerTable.Length == 8:
                    items[RESType(headerTable.Type)][obj_hash] = obj_name
                
                elif RESType(headerTable.Type) == RESType.TEXTURE_DATA:
                    pos = 8
                    
                    items[RESType(headerTable.Type)][obj_hash] = \
                        {"name": obj_name,
                         "unk1": unpack_from("<b", section, pos),
                         "unk2": unpack_from("<b", section, pos+1)}
                
                elif RESType(headerTable.Type) == RESType.MATERIAL_DATA:
                    pos = 16
                    linked_textures = []
                    max_texture = (headerTable.Length - 16) // 52
                    for k in range(max_texture):
                        texture_hash = unpack_from("<I", section, pos)[0]
                        pos += 4
                        
                        if texture_hash != 0:
                            linked_textures.append(texture_hash)
                        
                        pos += 48
                    
                    items[RESType(headerTable.Type)][obj_hash] = {"name": obj_name, "textures": linked_textures}
    
    read_section_table(data, header.MaterialTableOffset, header.MaterialTableCount)
    read_section_table(data, header.NodeOffset, header.NodeCount)
    
    return items

##########################################
# XRES
##########################################

class XRESHeader:
    def __init__(self, data):
        self.StringOffset, unk = unpack_from("<HH", data[1])
        self.MATERIAL_TYPE_UNK1 = HeaderTable(data[5])
        self.MATERIAL_1 =         HeaderTable(data[6])
        self.MATERIAL_2 =         HeaderTable(data[7])
        self.TEXTURE_DATA =       HeaderTable(data[8])
        self.MATERIAL_TYPE_UNK2 = HeaderTable(data[9])
        self.MATERIAL_DATA =      HeaderTable(data[11])
        self.MESH_NAME =          HeaderTable(data[13])
        self.BONE =               HeaderTable(data[14])
        self.ANIMATION_MTN2 =     HeaderTable(data[15])
        self.ANIMATION_IMM2 =     HeaderTable(data[16])
        self.ANIMATION_MTM2 =     HeaderTable(data[17])
        self.SHADING =            HeaderTable(data[18])
        self.NODE_TYPE_UNK2 =     HeaderTable(data[19])
        self.PROPERTIES =         HeaderTable(data[20])
        self.MTNINF =             HeaderTable(data[21])
        self.IMMINF =             HeaderTable(data[22])
        self.MTMINF =             HeaderTable(data[23])
        self.TEXPROJ =            HeaderTable(data[24])

class HeaderTable:
    def __init__(self, data):
        self.DataOffset, self.Count = unpack_from("<HH", data)

type_length = {
    RESType.BONE: 8,
    RESType.TEXPROJ: 8,
    RESType.PROPERTIES: 8,
    RESType.SHADING: 8,
    RESType.MATERIAL_1: 8,
    RESType.MATERIAL_2: 8,
    RESType.MESH_NAME: 8,
    RESType.TEXTURE_DATA: 32,
    RESType.MATERIAL_DATA: 224,
    RESType.ANIMATION_MTN2: 8,
    RESType.ANIMATION_IMM2: 8,
    RESType.ANIMATION_MTM2: 8,
    RESType.MTNINF: 8,
    RESType.IMMINF: 8,
    RESType.MTMINF: 8,
}

def open_xres(data):
    items = {}
    
    header = XRESHeader([data[i:i+4] for i in range(0, len(data), 4)])
    
    text_section = data[header.StringOffset:len(data)]
    string_table = read_string_table(text_section)
    
    def read_type(data, headerTable, Type):
        if Type not in items:
            items[Type] = {}
        
        for i in range(headerTable.Count):
            pos = headerTable.DataOffset + i * type_length[Type]
            section = data[pos:pos+type_length[Type]]
            
            pos = 0
            obj_hash = unpack_from("<I", section, pos)[0]
            obj_name = string_table[obj_hash]
            
            if Type == RESType.TEXTURE_DATA:
                pos = 8
                items[Type][obj_hash] = \
                    {"name": obj_name,
                     "unk1": unpack_from("<b", section, pos),
                     "unk2": unpack_from("<b", section, pos+1)}
            
            elif Type == RESType.MATERIAL_DATA:
                pos = 16
                linked_textures = []
                max_texture = (type_length[Type] - 16) // 52
                for k in range(max_texture):
                    texture_hash = unpack_from("<I", section, pos)[0]
                    pos += 4
                    
                    if texture_hash != 0:
                        linked_textures.append(texture_hash)
                    
                    pos += 48
                
                items[Type][obj_hash] = {"name": obj_name, "textures": linked_textures}
            
            else:
                items[Type][obj_hash] = obj_name
    
    read_type(data, header.BONE,           RESType.BONE)
    read_type(data, header.TEXPROJ,        RESType.TEXPROJ)
    read_type(data, header.PROPERTIES,     RESType.PROPERTIES)
    read_type(data, header.SHADING,        RESType.SHADING)
    read_type(data, header.MATERIAL_1,     RESType.MATERIAL_1)
    read_type(data, header.MATERIAL_2,     RESType.MATERIAL_2)
    read_type(data, header.MESH_NAME,      RESType.MESH_NAME)
    read_type(data, header.TEXTURE_DATA,   RESType.TEXTURE_DATA)
    read_type(data, header.MATERIAL_DATA,  RESType.MATERIAL_DATA)
    read_type(data, header.ANIMATION_MTN2, RESType.ANIMATION_MTN2)
    read_type(data, header.ANIMATION_IMM2, RESType.ANIMATION_IMM2)
    read_type(data, header.ANIMATION_MTM2, RESType.ANIMATION_MTM2)
    read_type(data, header.MTNINF,         RESType.MTNINF)
    read_type(data, header.IMMINF,         RESType.IMMINF)
    read_type(data, header.MTMINF,         RESType.MTMINF)
    
    return items

def make_library(meshes = [], armature = None, textures = {}, animations = {}, outline_name = "", properties=[], texprojs=[]):
    items = {}
    string_table = bytes()
    materials_offset = {}
    
    if meshes:
        # Add material name (twice time no idea why)
        materials_name = []
        
        for mesh in meshes:
            material_name = mesh.material_name.encode("shift-jis")
            materials_name.append(crc32(material_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little')) 
            materials_offset[material_name] = len(string_table)           
            string_table += material_name + int(0).to_bytes(1, 'little')
        
        items[RESType.MATERIAL_1] = materials_name
        items[RESType.MATERIAL_2] = materials_name
        
        # Add mesh name
        meshes_name = []
        
        for mesh in meshes:
            mesh_name = mesh.name.encode("shift-jis")
            meshes_name.append(crc32(mesh_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))   
            string_table += mesh_name + int(0).to_bytes(1, 'little')
                
        items[RESType.MESH_NAME] = meshes_name

    if textures:
        # Add texture data (texture name and texture mode)
        textures_data = [] 
        
        for texture_name, texture_data in textures.items():
            texture_name_encoded = texture_name.encode("shift-jis")
            textures_data.append(crc32(texture_name_encoded).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little') + bytes.fromhex("030A00000000000000000000"))
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
            material_name_crc32 = crc32(material_name_encoded).to_bytes(4, 'little')
            
            if material_name in materials_offset:
                material_data = material_name_crc32 + int(materials_offset[material_name]).to_bytes(4, 'little') + material_name_crc32 + material_name_crc32
            else:
                material_data = material_name_crc32 + int(0).to_bytes(4, 'little') + material_name_crc32 + material_name_crc32
            
            for i in range(4):
                if i < len(material_info):
                    texture_name = material_info[i].encode("shift-jis")
                    material_data += crc32(texture_name).to_bytes(4, 'little') + bytes.fromhex("010000000000803F0000803F00000000000000000000803F00000000000000000000803F00000000000000000000803F")
                else:
                    material_data += bytes.fromhex("00000000000000000000803F0000803F00000000000000000000803F00000000000000000000803F00000000000000000000803F")
                    
            materials_data.append(material_data)
        
        items[RESType.MATERIAL_DATA] = materials_data
        
    if armature:
        bones_name = []
        
        for bone in armature.pose.bones:
            bone_name = bone.name.encode("shift-jis")
            bones_name.append(crc32(bone_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))    
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
                string_table += animation_name_encoded + int(0).to_bytes(1, 'little')
            
            animation_bytes = crc32(animation_name_encoded).to_bytes(4, 'little') + int(animations_offset[animation_name]).to_bytes(4, 'little')

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
                    string_table += animation_split_name_encoded + int(0).to_bytes(1, 'little')
                
                animation_split_bytes = crc32(animation_split_name_encoded).to_bytes(4, 'little') + int(animations_split_offset[animation_split_name]).to_bytes(4, 'little')

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
            properties_name.append(crc32(property_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))
            string_table += property_name + int(0).to_bytes(1, 'little')
            
        items[RESType.PROPERTIES] = properties_name
        
    if texprojs:
        texprojs_name = []
        
        for texproj in texprojs:
            texproj_name = texproj[0].encode("shift-jis")
            texprojs_name.append(crc32(texproj_name).to_bytes(4, 'little') + int(len(string_table)).to_bytes(4, 'little'))
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
                        res_value_length = 0
                        
                        if len(res_value) > 0:
                            res_value_length = len(res_value[0])
                            
                        material_header_table = {
                            '_dataOffset': data_pos >> 2,
                            'Count': len(res_value),
                            'Type': res_type.value,
                            'Length': res_value_length,
                        }

                        header_pos += 8
                        data_pos += sum(len(byte_array) for byte_array in res_value)

                        writer_table.write(pack('<hhhh', *material_header_table.values()))
                        writer_data.write(b''.join(res_value))

                # Node - Header table
                if nodes:
                    header['_nodeOffset'] = header_pos >> 2

                    for res_type, res_value in nodes.items():
                        res_value_length = 0
                        
                        if len(res_value) > 0:
                            res_value_length = len(res_value[0])
                        
                        node_header_table = {
                            '_dataOffset': data_pos >> 2,
                            'Count': len(res_value),
                            'Type': res_type.value,
                            'Length': res_value_length,
                        }

                        header_pos += 8
                        data_pos += sum(len(byte_array) for byte_array in res_value)

                        writer_table.write(pack('<hhhh', *node_header_table.values()))
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
                writer_res.write(pack('<qhhhhhh', *header.values()))
                writer_res.write(writer_table.getvalue())
                writer_res.write(writer_data.getvalue())
                
                return compress(writer_res.getvalue())
