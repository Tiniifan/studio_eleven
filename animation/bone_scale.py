import struct
class BoneScale:
    def __init__(self, X, Y, Z):
        self.X = X
        self.Y = Y
        self.Z = Z
    
    def __str__(self):
        return f"({self.X}, {self.Y}, {self.Z})"
    
    def __eq__(self, obj):
        same_x = self.X == obj.X
        same_y = self.Y == obj.Y
        same_z = self.Z == obj.Z
        if (same_x == False or same_y == False or same_z == False):
            return False
        else:
            return True
    
    def ToBytes(self):
        return struct.pack("<fff", float(self.X), float(self.Y), float(self.Z))