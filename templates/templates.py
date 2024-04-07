class Template:
    def __init__(self, name, material, atr, mtr):
        self.name = name
        self.material = material
        self.atr = atr
        self.mtr = mtr
        
    def __str__(self):
        return self.name
        
    def __repr__(self):
        return self.name        

templates = [
        Template(
            "Inazuma Eleven", 
            "09ED78C5E33CD4DD6002000000000000800A9D3C6E0F7741005900BEE6083A40C2281E4012BBFD3F000400000100000001000000",
            "41545243303100000C000000E3010000054080FF0000C0C13C80BF0137F72F406005FFFFF0FFFF56",
            "4D545243303000001800000000000000000000000000000041070000350000F001501301801C0340037E04800B5013F043F055F0673079F819FEFE3E5003B08B803F5003F0F023F0B5F0C770D9E8891DA70000004C555443"
        ),
    ]

def get_templates():
    return templates
    
def get_template_by_name(name):
    for template in templates:
        if template.name == name:
            return template
    return None    
