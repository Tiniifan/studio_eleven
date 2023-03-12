class Scale:
    def __init__(self, scale_x, scale_y, scale_z):
        self.scale_x = float(scale_x)
        self.scale_y = float(scale_y)
        self.scale_z = float(scale_z)

    def __repr__(self):
        return "x:%s, y:%s, z:%s" % (self.get_x(), self.get_y(), self.get_z())
        
    def __str__(self):
        return "x:%s, y:%s, z:%s" % (self.get_x(), self.get_y(), self.get_z())
        
    def __eq__(self, scale2):
        same_x = self.get_x() == scale2.get_x()
        same_y = self.get_y() == scale2.get_y()
        same_z = self.get_z() == scale2.get_z()
        if (same_x == False or same_y == False or same_z == False):
            return False
        else:
            return True
        
    def get_x(self):
        return "{:.6f}".format(float(self.scale_x))

    def get_y(self):
        return "{:.6f}".format(float(self.scale_y))
        
    def get_z(self):
        return "{:.6f}".format(float(self.scale_z))