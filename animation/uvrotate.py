import struct
class UVRotate:
    def __init__(self, X):
        self.X = X
        
    def __str__(self):
        return f"({self.X})"
    
    def __eq__(self, obj):
        same_x = self.X == obj.X
        if (same_x == False):
            return False
        else:
            return True
    
    def ToBytes(self):
        return struct.pack("<f", float(self.X))