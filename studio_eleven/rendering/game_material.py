import json

from ..formats import mtr
from . import render_defaults

_defaults = {}
_parsed = {}


def engine_material(engine_id):
    """The default lighting material of a game engine."""
    key = (engine_id, render_defaults.get_engine_data(engine_id).info["version"])
    if key not in _defaults:
        _defaults[key] = mtr.read_mtr(bytes.fromhex(render_defaults.get_engine_data(engine_id).info["default_material"]["mtr"]))

    return _defaults[key]


def material_of(blender_material, engine_id):
    """The lighting material of a Blender material: the one read from the model, the game engine default otherwise."""
    data = blender_material.level5_mtr.data if blender_material is not None and hasattr(blender_material, "level5_mtr") else ""
    if not data:
        return engine_material(engine_id)

    if data not in _parsed:
        if len(_parsed) > 256:
            _parsed.clear()
        _parsed[data] = mtr.Material.from_dict(json.loads(data))

    return _parsed[data]
