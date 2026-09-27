class RGB8:
    name = "RGB8"
    
    def encode(self, color):
        return bytes([((color) & 0xFF), ((color >> 8) & 0xFF), ((color >> 16) & 0xFF)])
