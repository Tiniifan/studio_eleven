import os
import json

class Template:
    def __init__(self, name, modes, atr, mtr, outline_mesh_data, cmb1, cmb2):
        self.name = name
        self.modes = modes
        self.atr = atr
        self.mtr = mtr
        self.outline_mesh_data = outline_mesh_data
        self.cmb1 = cmb1
        self.cmb2 = cmb2
        self.visible = True
        
    def __str__(self):
        return self.name
        
    def __repr__(self):
        return self.name

templates = []
all_templates = []
template_order = []

script_dir = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(script_dir, "templates.json")

def get_templates():
    return [t for t in all_templates if t.visible]
    
def get_template_by_name(name):
    for template in all_templates:
        if template.name == name:
            return template
    return None    

def template_from_dict(d):
    t = Template(
        d["name"],
        d["modes"],
        d["atr"],
        d["mtr"],
        d["outline_mesh_data"],
        d["cmb1"],
        d["cmb2"]
    )
    
    t.visible = d.get("visible", True)
    
    return t

def load_templates_from_json():
    global templates, all_templates, template_order
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Load ALL templates
        all_templates = [template_from_dict(t) for t in data.get("templates", [])]
        
        # Order concerns all templates, not just visible ones
        order = data.get("template_order", [])
        if order and len(order) == len(all_templates):
            # Reorganize according to saved order
            ordered_templates = [all_templates[idx] for idx in order if 0 <= idx < len(all_templates)]
            all_templates = ordered_templates
            template_order = order
        else:
            # Default order
            template_order = list(range(len(all_templates)))
        
        # templates contains only visible ones for compatibility
        templates = [t for t in all_templates if t.visible]
            
    except Exception as e:
        print(f"Warning: Failed to load templates.json ({e}). Using default template.")
        
        default_template_dict = {
            "name": "Default Template",
            "modes": {"Model": ["759FE5F3", 1]},
            "atr": "41545243303100000C000000E3010000054080FF0000C0C13C80BF0137F72F406005FFFFF0FFFF56",
            "mtr": "4D545243303000001800000000000000000000000000000041070000350000F001501301801C0340037E04800B5013F043F055F0673079F819FEFE3E5003B08B803F5003F0F023F0B5F0C770D9E8891DA70000004C555443",
            "outline_mesh_data": [0.0249999985,5.0,1,1.0,1.0,1.0,1.0,1,0.0,1.0,1.0,1.0,1.0,100.0,60.0,96000.0,0.5,0.0,1,1,0.0025,0.5,0.4,10.0,60.0,0.0,0.0,1],
            "cmb1": [1,2,1,0,0,0,1,1,0,0,0,0,1,2,1,0,0,0,1,1,0,0,0,0,255,255,255,255,0,0,0,0],
            "cmb2": [3,2,1,0,0,0,1,1,0,0,0,0,3,2,1,0,0,0,1,1,0,0,0,0,255,255,255,255,0,0,0,0],
            "visible": True
        }
        
        t = template_from_dict(default_template_dict)
        all_templates = [t]
        templates = [t]
        template_order = [0]

def save_templates_to_json():
    global templates, all_templates, template_order
    
    data = {"templates": [], "template_order": []}
    
    for t in all_templates:
        data["templates"].append({
            "name": t.name,
            "modes": t.modes,
            "atr": t.atr,
            "mtr": t.mtr,
            "outline_mesh_data": t.outline_mesh_data,
            "cmb1": t.cmb1,
            "cmb2": t.cmb2,
            "visible": t.visible  # Can be True or False
        })
    
    data["template_order"] = list(range(len(all_templates)))
    template_order = data["template_order"]
    
    templates = [t for t in all_templates if t.visible]
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

load_templates_from_json()