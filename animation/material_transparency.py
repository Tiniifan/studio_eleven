import struct

class Transparency:
    def __init__(self, transparency):
        self.transparency = transparency
    
    def __str__(self):
        return f"({self.transparency})"
    
    def __eq__(self, obj):
        return self.transparency == obj.transparency
    
    def ToBytes(self):
        return struct.pack("<f", float(self.transparency))