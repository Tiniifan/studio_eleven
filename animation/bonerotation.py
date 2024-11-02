from math import sin, cos, atan2, asin
import struct

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
        return [qx, qy, qz, qw]

    def __str__(self):
        return f"({self.X}, {self.Y}, {self.Z}, {self.W})"
    
    def __eq__(self, obj):
        same_x = self.X == obj.X
        same_y = self.Y == obj.Y
        same_z = self.Z == obj.Z
        same_w = self.W == obj.W
        if (same_x == False or same_y == False or same_z == False or same_w == False):
            return False
        else:
            return True
    
    def ToBytes(self):
        return struct.pack("<ffff", float(self.X), float(self.Y), float(self.Z), float(W))
