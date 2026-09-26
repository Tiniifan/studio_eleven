from collections import namedtuple

GameEngine = namedtuple("GameEngine", ("id", "name", "file_version"))

# file_version comes from the shipped fix.xr: IE4 stores ATRC00/XCMB (V1), every other game ATRC01/CMBC00 (V2)
GAME_ENGINES = (
    GameEngine("IE4", "Inazuma Eleven Go", 1),
    GameEngine("IE5", "Inazuma Eleven Go Chrono Stone", 2),
    GameEngine("IE6", "Inazuma Eleven Go Galaxy", 2),
    GameEngine("PL5", "Professor Layton 5", 2),
    GameEngine("PL6", "Professor Layton 6", 2),
    GameEngine("PLvsPW", "Professor Layton vs Phoenix Wright", 2),
    GameEngine("YW1", "Yo-kai Watch", 2),
    GameEngine("YW2", "Yo-kai Watch 2", 2),
    GameEngine("YW3", "Yo-kai Watch 3", 2),
    GameEngine("YWB1", "Yo-kai Watch Blaster", 2),
    GameEngine("YWB2", "Yo-kai Watch Busters 2", 2),
    GameEngine("SW", "Snack World", 2),
)

# What the project uses while no game is registered, a configuration that suits every game without being tuned for one
DEFAULT_ENGINE_V2 = GameEngine("DEFAULT_V2", "No game registered (V2)", 2)
DEFAULT_ENGINE_V1 = GameEngine("DEFAULT_V1", "No game registered (V1)", 1)

DEFAULT_ENGINES = (DEFAULT_ENGINE_V2, DEFAULT_ENGINE_V1)

DEFAULT_ENGINE_ID = DEFAULT_ENGINE_V2.id

ALL_ENGINES = DEFAULT_ENGINES + GAME_ENGINES

_BY_ID = {engine.id: engine for engine in ALL_ENGINES}


def get_engine(engine_id):
    return _BY_ID.get(engine_id) or DEFAULT_ENGINE_V2


def is_default_engine(engine_id):
    return engine_id in (engine.id for engine in DEFAULT_ENGINES)


def default_engine_for(engine_id):
    """The generic engine that writes the same file version as the given one."""
    return DEFAULT_ENGINE_V1 if get_engine(engine_id).file_version == 1 else DEFAULT_ENGINE_V2


def engine_items(games_only=False):
    engines = GAME_ENGINES if games_only else ALL_ENGINES
    return [
        (engine.id, engine.name, f"A configuration that works for every game but isn't tuned for one, it writes V{engine.file_version} files" if is_default_engine(engine.id) else "")
        for engine in engines
    ]
