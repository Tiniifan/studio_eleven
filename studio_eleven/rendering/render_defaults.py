import os
import json
import zlib

from . import game_manager

_cache = {}


class RenderDefault:
    def __init__(self, engine_id, data):
        self.engine_id = engine_id
        self.data = data
        self.name = data["name"]
        self.render_program_hash = zlib.crc32(self.name.encode("shift-jis"))

    def __repr__(self):
        return f"RenderDefault({self.engine_id}, {self.name})"


class EngineRenderData:
    def __init__(self, engine_id):
        self.engine_id = engine_id
        directory = game_manager.game_directory(engine_id)

        with open(os.path.join(directory, "engine.json"), "r", encoding="utf-8") as f:
            self.info = json.load(f)

        self.defaults = {}
        defaults_directory = os.path.join(directory, "render_defaults")
        for filename in sorted(os.listdir(defaults_directory)):
            if filename.endswith(".json"):
                with open(os.path.join(defaults_directory, filename), "r", encoding="utf-8") as f:
                    render_default = RenderDefault(engine_id, json.load(f))
                self.defaults[render_default.name] = render_default

        self.by_hash = {render_default.render_program_hash: render_default for render_default in self.defaults.values()}
        self.default_name = self.info["default_render_default"]


def invalidate():
    _cache.clear()


def get_engine_data(engine_id):
    """The data of the engine, the ones of the default game while the engine isn't installed."""
    key = game_manager.data_engine_id(engine_id)
    if key not in _cache:
        _cache[key] = EngineRenderData(key)
    return _cache[key]


def get_render_defaults(engine_id):
    return list(get_engine_data(engine_id).defaults.values())


def get_default_render_default(engine_id):
    data = get_engine_data(engine_id)
    return data.defaults[data.default_name]


def find_render_default(engine_id, name):
    return get_engine_data(engine_id).defaults.get(name)


def find_render_default_by_hash(engine_id, render_program_hash):
    return get_engine_data(engine_id).by_hash.get(render_program_hash)


def resolve_render_default(engine_id, current_name):
    """Keep the render default when the engine has it, otherwise fall back on the engine default."""
    found = find_render_default(engine_id, current_name) if current_name else None
    return found or get_default_render_default(engine_id)
