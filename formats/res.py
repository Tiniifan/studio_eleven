import zlib
import struct
from ..compression import lz10

def write(library):
    out = bytes()
    
    library_data = write_library(library)
    
    # Header
    out += struct.pack("6s", "CHRC00".encode('utf-8'))
    out += struct.pack("<H", 0)
    out += struct.pack("<H", (len(library_data) + 20) // 4)
    out += struct.pack("<H", 1)
    out += struct.pack("<H", 5)
    out += struct.pack("<H", 4)
    out += struct.pack("<H", 13)
    out += struct.pack("<H", 2)
    out += library_data
    
    # Write the name of each element of library
    for key, value in library.items():
        if key is not "materialconfig":
            for name in value:
                out += name.encode("utf-8")
                out += struct.pack("B", 0)

    return lz10.compress(out)
    
def write_library(library):
    size = 0
    
    table = bytes()
    data = bytes()
    
    material_offset = {}
    element_type = {"material": 220, "material2": 230, "texture": 240, "materialconfig": 290, "mesh": 100, "bone": 110}
    element_size = {"material": 8, "material2": 8, "texture": 20, "materialconfig": 224, "mesh": 8, "bone": 8}
    
    for key, value in library.items(): 
        # header 
        table += struct.pack("<H", (20 + len(library) * 8 + len(data))//4)
        table += struct.pack("<H", len(value))
        table += struct.pack("<H", element_type[key])
        table += struct.pack("<H", element_size[key])
        
        # data
        for v in value:
            if key is "material":
                material_offset[v] = size
            
            # crc32 name
            data += zlib.crc32(v.encode("utf-8")).to_bytes(4, 'little')
            
            # String table offset
            if key is "material2":
                data += int(material_offset[v]).to_bytes(4, 'little')
            elif key is "materialconfig":
                data += int(material_offset[v]).to_bytes(4, 'little')
            elif key is not "bone":
                data += size.to_bytes(4, 'little')
            else:
                data += int(0).to_bytes(4, 'little')
            
            # Extend data
            if key == "texture":
                data += bytes.fromhex("030500000000000000000000")
            elif key == "materialconfig":
                data += zlib.crc32(v.encode("utf-8")).to_bytes(4, 'little')
                data += zlib.crc32(v.encode("utf-8")).to_bytes(4, 'little')
                
                texture_linked = library[key][v]
                
                # One mesh can have a maximum of 4 textures linked
                for i in range(4):
                    if len(texture_linked) > i:
                        data += zlib.crc32(texture_linked[i].encode("utf-8")).to_bytes(4, 'little')
                        data += int(1).to_bytes(4, 'little')
                    else:
                        data += int(0).to_bytes(4, 'little')
                        data += int(0).to_bytes(4, 'little')     
                    data += bytes.fromhex("0000803F0000803F00000000000000000000803F00000000000000000000803F00000000000000000000803F")      
            
            if key is not "materialconfig":
                size += len(v) + 1
    
    return table + data
        