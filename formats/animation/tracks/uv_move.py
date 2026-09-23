import struct

class UVMove:
    def __init__(self, X, Y):
        self.X = X
        self.Y = Y
    
    def __str__(self):
        return f"({self.X}, {self.Y})"
    
    def __eq__(self, obj):
        return (self.X, self.Y) == (obj.X, obj.Y)
    
    def ToBytes(self):
        return struct.pack("<ff", float(self.X), float(self.Y))