class Location:      
    def __init__(self, location_x, location_y, location_z):
        self.location_x = location_x
        self.location_y = location_y
        self.location_z = location_z
        
    def __repr__(self):
        return "x:%s, y:%s, z:%s" % (self.get_x(), self.get_y(), self.get_z())
        
    def __str__(self):
        return "x:%s, y:%s, z:%s" % (self.get_x(), self.get_y(), self.get_z())

    def __eq__(self, location2):
        same_x = self.get_x() == location2.get_x()
        same_y = self.get_y() == location2.get_y()
        same_z = self.get_z() == location2.get_z()
        if (same_x == False or same_y == False or same_z == False):
            return False
        else:
            return True
        
    def get_x(self):
        return "{:.6f}".format(float(self.location_x))

    def get_y(self):
        return "{:.6f}".format(float(self.location_y))
        
    def get_z(self):
        return "{:.6f}".format(float(self.location_z))           