import io
import zlib
import struct

def write(animation_name, split_animation_name, frame_start, frame_end):
    out = bytes()
    
    out += bytes([int(x,0) for x in ["0x4D", "0x49", "0x4E", "0x46"] ])
    out += int(0).to_bytes(4, 'little')
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
    
    out += int(frame_start).to_bytes(4, 'little')
    out += int(frame_end).to_bytes(4, 'little')
    
    out += struct.pack('<f', 1.0)
    out += int(0).to_bytes(4, 'little')
    out += int(0).to_bytes(4, 'little')
    
    return out