import struct

class BoneLocation:
    def __init__(self, X, Y, Z):
        self.X = round(X, 4)
        self.Y = round(Y, 4)
        self.Z = round(Z, 4)
    
    def __str__(self):
        return f"({self.X:.4f}, {self.Y:.4f}, {self.Z:.4f})"
    
    def __eq__(self, obj):
        return (self.X, self.Y, self.Z) == (obj.X, obj.Y, obj.Z)
    
    def ToBytes(self):
        return struct.pack("<fff", self.X, self.Y, self.Z)