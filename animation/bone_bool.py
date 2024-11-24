import struct

class BoneBool:
    def __init__(self, X):
        self.X = X
        
    def __str__(self):
        return f"({self.X})"
    
    def __eq__(self, obj):
        return self.X == obj.X
    
    def ToBytes(self):
        return struct.pack("<B", float(self.X))