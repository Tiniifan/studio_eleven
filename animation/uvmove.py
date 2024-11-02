import struct
class UVMove:
    def __init__(self, X, Y):
        self.X = X
        self.Y = Y
    
    def __str__(self):
        return f"({self.X}, {self.Y})"
    
    def __eq__(self, obj):
        same_x = self.X == obj.X
        same_y = self.Y == obj.Y
        if (same_x == False or same_y == False):
            return False
        else:
            return True
    
    def ToBytes(self):
        return struct.pack("<ff", float(self.X), float(self.Y))