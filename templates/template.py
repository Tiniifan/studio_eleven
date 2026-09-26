import os
import json
import zlib

##########################################
# CONST
##########################################

TEMPLATES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates.json")

DEFAULT_TEMPLATE_ID = "YKW"

##########################################
# Template Function
##########################################

# A template gives the game engine of the blend (V1 or V2) and what a new mesh gets: the render program,
# the render state and the lighting material of its "Object (Transparent)" mode, a single bind mesh uses the program of its "Map" mode
def load_templates():
    with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    templates = {}

    for template in data["templates"]:
        template["render_program_hash"] = zlib.crc32(template["render_program"].encode("shift-jis"))
        template["map_render_program_hash"] = zlib.crc32(template["map_render_program"].encode("shift-jis"))
        templates[template["id"]] = template

    return templates

def get_template_items(templates):
    items = []

    for template in templates.values():
        version = "V2"
        if template["engine"] == "DEFAULT_V1":
            version = "V1"

        items.append((template["id"], template["name"], f"Writes {version} files, a new mesh uses {template['render_program']}"))

    return items

TEMPLATES = load_templates()

TEMPLATE_ITEMS = get_template_items(TEMPLATES)

def get_template(template_id):
    if template_id in TEMPLATES:
        return TEMPLATES[template_id]

    return TEMPLATES[DEFAULT_TEMPLATE_ID]
