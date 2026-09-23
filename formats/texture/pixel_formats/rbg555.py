from struct import pack

class RBG555:
    name = "RGB565"
    
    def encode(self, color):
        r = int(color.r / 8)
        g = int((color.g /8)) << 5
        b = int((color.b /8)) << 10
        return pack('H', r+g+b);
