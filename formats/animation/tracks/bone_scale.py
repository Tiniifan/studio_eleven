import struct

class BoneScale:
    def __init__(self, X, Y, Z):
        self.X = X
        self.Y = Y
        self.Z = Z
    
    def __str__(self):
        return f"({self.X}, {self.Y}, {self.Z})"
    
    def __eq__(self, obj):
        return (self.X, self.Y, self.Z) == (obj.X, obj.Y, obj.Z)
    
    def ToBytes(self):
        return struct.pack("<fff", float(self.X), float(self.Y), float(self.Z))