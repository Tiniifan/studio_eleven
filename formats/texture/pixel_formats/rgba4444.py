class RGBA4444:
    name = "RGBA4444"
    has_alpha = True
    
    def encode(self, color):
        val = (((color >> 24) & 0xFF) / 0x11)
        val += ((((color) & 0xFF) / 0x11) << 4)
        val += ((((color >> 8) & 0xFF) / 0x11) << 8)
        val += ((((color >> 16) & 0xFF) / 0x11) << 12)
        return bytes([(val & 0xFF), (byte)(val >> 8)])
