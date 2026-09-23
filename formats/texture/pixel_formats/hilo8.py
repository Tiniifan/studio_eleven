class HILO8:
    name = "HILO8"
    
    def encode(self, color):
        bytes([((color) & 0xFF), (byte)((color >> 8) & 0xFF)])
