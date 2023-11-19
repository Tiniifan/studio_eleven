class Template:
    def __init__(self, name, material):
        self.name = name
        self.material =material
        
    def __str__(self):
        return self.name
        
    def __repr__(self):
        return self.name        

templates = [
        Template("CS/Galaxy", "09ED78C5E33CD4DD6002000000000000800A9D3C6E0F7741005900BEE6083A40C2281E4012BBFD3F000400000100000001000000"),
        Template("YKW1", "E093029A0000000000000000000000000000000000000000000000000000000000000000000000000000000001000000"),
        Template("YKW2", "E093029ABCABD179F601000000000000000000007B649740A041153D9F1E004031D5F13F499FDD3F00000000010000000D0000000000000001010000"),
        Template("YKW3", "E093029A06FAD8E0670200000000000000000000EF3DC33FA45CD9BF26551C405A2DC13F8A843E4000000000010000001300000000000000000000000000000000000000")
    ]

def get_templates():
    return templates
    
def get_template_by_name(name):
    for template in templates:
        if template.name == name:
            return template
    return None    