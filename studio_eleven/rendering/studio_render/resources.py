import os
import json

from ...formats import atr, cmb, lut
from .. import game_manager, render_defaults

_cache = {}

GLSL_EXTENSIONS = {"VTX": ".vert", "FRG": ".frag", "GEO": ".geom"}


def resource_file_name(name):
    # engine.json keeps the '#' of the shipped names, the extracted files drop it
    return name[1:] if name.startswith("#") else name


def _path(engine_id, *parts):
    return os.path.join(game_manager.data_directory(engine_id), *parts)


def _cached(engine_id, key, build):
    # The default game answers for every engine that isn't installed, so the cache is keyed on the data folder
    full_key = (game_manager.data_engine_id(engine_id),) + key
    if full_key not in _cache:
        _cache[full_key] = build()
    return _cache[full_key]


def clear_cache():
    _cache.clear()


def engine_info(engine_id):
    return render_defaults.get_engine_data(engine_id).info


def load_combiner(engine_id, name):
    """Returns the CombinerStage list of a shipped combiner, or None when the engine has no such combiner."""
    def build():
        path = _path(engine_id, "combiners", resource_file_name(name) + ".json")
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as combiner_file:
            data = json.load(combiner_file)
        return [cmb.CombinerStage.from_dict(stage) for stage in data["stages"]]

    return _cached(engine_id, ("combiner", name), build)


def load_lut(engine_id, name):
    """Returns the Lut of a shipped fragment lighting table, or None."""
    def build():
        path = _path(engine_id, "luts", resource_file_name(name) + ".json")
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as lut_file:
            return lut.Lut.from_dict(json.load(lut_file))

    return _cached(engine_id, ("lut", name), build)


def load_atr(engine_id, name):
    """Returns the state dict of a shipped render state preset, or None."""
    def build():
        path = _path(engine_id, "atr", resource_file_name(name) + ".json")
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as atr_file:
            data = json.load(atr_file)
        state = atr.new_state(data.get("file_version"))
        for field, value in data["state"].items():
            if field in state:
                state[field] = value
        return state

    return _cached(engine_id, ("atr", name), build)


def load_vertex_programs(engine_id):
    def build():
        with open(_path(engine_id, "vertex_programs.json"), "r", encoding="utf-8") as programs_file:
            return json.load(programs_file)

    return _cached(engine_id, ("vertex_programs",), build)


def find_vertex_program(engine_id, name):
    return load_vertex_programs(engine_id).get(name)


def is_skinned(engine_id, name):
    program = find_vertex_program(engine_id, name)
    return bool(program and program.get("skinned"))


def load_gls(engine_id, name):
    """Reads one shipped GLSL source by its name, VTX000 / FRG001 / GEO000, None when the game has none."""
    def build():
        path = _path(engine_id, "gls", name + GLSL_EXTENSIONS.get(name[:3], ""))
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as gls_file:
            return gls_file.read()

    return _cached(engine_id, ("gls", name), build)


def combiner_names(engine_id):
    directory = _path(engine_id, "combiners")
    if not os.path.isdir(directory):
        return []
    return sorted(name[:-len(".json")] for name in os.listdir(directory) if name.endswith(".json"))


def engine_lut_names(engine_id):
    return list(engine_info(engine_id).get("luts", []))


def engine_atr_names(engine_id):
    return list(engine_info(engine_id).get("atr_presets", []))
