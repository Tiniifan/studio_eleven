from math import sin, cos

class Rotation:
    def __init__(self, rotation_x, rotation_y, rotation_z, rotation_w=0):
        self.rotation_x = rotation_x
        self.rotation_y = rotation_y
        self.rotation_z = rotation_z
        self.rotation_w = rotation_w
        
    def to_quaternion(self):
        qx = sin(self.rotation_x / 2) * cos(self.rotation_y / 2) * cos(self.rotation_z / 2) - cos(self.rotation_x / 2) * sin(self.rotation_y / 2) * sin(self.rotation_z / 2);
        qy = cos(self.rotation_x / 2) * sin(self.rotation_y / 2) * cos(self.rotation_z / 2) + sin(self.rotation_x / 2) * cos(self.rotation_y / 2) * sin(self.rotation_z / 2);
        qz = cos(self.rotation_x / 2) * cos(self.rotation_y / 2) * sin(self.rotation_z / 2) - sin(self.rotation_x / 2) * sin(self.rotation_y / 2) * cos(self.rotation_z / 2);
        qw = cos(self.rotation_x / 2) * cos(self.rotation_y / 2) * cos(self.rotation_z / 2) + sin(self.rotation_x / 2) * sin(self.rotation_y / 2) * sin(self.rotation_z / 2); 
        return [qx, qy, qz, qw]

    def __repr__(self):
        return "x:%s, y:%s, z:%s" % (self.get_x(), self.get_y(), self.get_z())
        
    def __str__(self):
        return "x:%s, y:%s, z:%s" % (self.get_x(), self.get_y(), self.get_z())

    def __eq__(self, rotation2):
        same_x = self.get_x() == rotation2.get_x()
        same_y = self.get_y() == rotation2.get_y()
        same_z = self.get_z() == rotation2.get_z()
        if (same_x == False or same_y == False or same_z == False):
            return False
        else:
            return True

    def get_x(self):
        return "{:.6f}".format(float(self.rotation_x))

    def get_y(self):
        return "{:.6f}".format(float(self.rotation_y))
        
    def get_z(self):
        return "{:.6f}".format(float(self.rotation_z))        