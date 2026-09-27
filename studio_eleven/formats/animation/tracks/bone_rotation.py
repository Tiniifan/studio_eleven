import struct
from math import sin, cos, atan2, asin

class BoneRotation:
    def __init__(self, X, Y, Z, W=None):
        self.X = X
        self.Y = Y
        self.Z = Z
        self.W = W
    
    def ToQuaternion(self):
        qx = sin(self.X / 2) * cos(self.Y / 2) * cos(self.Z / 2) - cos(self.X / 2) * sin(self.Y / 2) * sin(self.Z / 2)
        qy = cos(self.X / 2) * sin(self.Y / 2) * cos(self.Z / 2) + sin(self.X / 2) * cos(self.Y / 2) * sin(self.Z / 2)
        qz = cos(self.X / 2) * cos(self.Y / 2) * sin(self.Z / 2) - sin(self.X / 2) * sin(self.Y / 2) * cos(self.Z / 2)
        qw = cos(self.X / 2) * cos(self.Y / 2) * cos(self.Z / 2) + sin(self.X / 2) * sin(self.Y / 2) * sin(self.Z / 2) 
        self.X = qx
        self.Y = qy
        self.Z = qz
        self.W = qw

    def __str__(self):
        return f"({self.X}, {self.Y}, {self.Z}, {self.W})"
    
    def __eq__(self, obj):
        return (self.X, self.Y, self.Z, self.W) == (obj.X, obj.Y, obj.Z, obj.W)
    
    def ToBytes(self):
        return struct.pack("<hhhh", int(self.X * 32767), int(self.Y * 32767), int(self.Z * 32767), int(self.W * 32767))
