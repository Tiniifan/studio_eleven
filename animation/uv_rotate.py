import struct

class UVRotate:
    def __init__(self, X):
        self.X = X
        
    def __str__(self):
        return f"({self.X})"
    
    def __eq__(self, obj):
        return (self.X, self.Y) == (obj.X, obj.Y)
    
    def ToBytes(self):
        return struct.pack("<f", float(self.X))