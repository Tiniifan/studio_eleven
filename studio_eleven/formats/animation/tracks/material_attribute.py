import struct

class MaterialAttribute:
    def __init__(self, hue, saturation, value):
        self.hue = hue
        self.saturation = saturation
        self.value = value
    
    def __str__(self):
        return f"({self.hue}, {self.saturation}, {self.value})"
    
    def __eq__(self, obj):
        return (self.hue, self.saturation, self.value) == (obj.hue, obj.saturation, obj.value)
    
    def ToBytes(self):
        return struct.pack("<fff", float(self.hue), float(self.saturation), float(self.value))