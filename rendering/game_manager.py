import os
import json
import shutil
import zipfile
import hashlib
import tempfile

from .engines import GAME_ENGINES, get_engine, is_default_engine, default_engine_for

ROOT = os.path.dirname(os.path.abspath(__file__))
GAMES_ROOT = os.path.join(ROOT, "games")
STATE_PATH = os.path.join(GAMES_ROOT, "installed.json")

# Updates the user refused are not proposed again before the next session
_ignored_updates = set()


def folder_name(engine_id):
    return engine_id.lower()


def game_directory(engine_id):
    return os.path.join(GAMES_ROOT, folder_name(engine_id))


def zip_path(engine_id):
    return game_directory(engine_id) + ".zip"


def read_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}

    state.setdefault("setup_done", False)
    state.setdefault("games", {})
    return state


def write_state(state):
    try:
        with open(STATE_PATH, "w", encoding="utf-8", newline="\n") as f:
            json.dump(state, f, indent=2)
            f.write("\n")
    except OSError as error:
        print(f"[Studio Eleven] Couldn't save {STATE_PATH}: {error}")


def file_sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def is_bundled(engine_id):
    """The zip of the game is part of the addon."""
    return not is_default_engine(engine_id) and os.path.isfile(zip_path(engine_id))


def bundled_version(engine_id):
    if not is_bundled(engine_id):
        return None

    with zipfile.ZipFile(zip_path(engine_id)) as archive:
        return json.loads(archive.read("engine.json").decode("utf-8"))["version"]


def installed_entry(engine_id):
    if is_default_engine(engine_id):
        return {}

    entry = read_state()["games"].get(engine_id)
    if entry is not None and os.path.isfile(os.path.join(game_directory(engine_id), "engine.json")):
        return entry

    return None


def is_installed(engine_id):
    return installed_entry(engine_id) is not None


def installed_version(engine_id):
    entry = installed_entry(engine_id)
    return entry.get("version") if entry else None


def is_usable(engine_id):
    return is_default_engine(engine_id) or is_installed(engine_id)


def data_engine_id(engine_id):
    """The engine whose folder holds the data of the requested one: the default game of its file version while it isn't installed."""
    return engine_id if is_usable(engine_id) else default_engine_for(engine_id).id


def data_directory(engine_id):
    return game_directory(data_engine_id(engine_id))


def update_available(engine_id):
    """The zip of the addon is newer than the installed folder."""
    entry = installed_entry(engine_id)
    return bool(entry) and is_bundled(engine_id) and entry.get("zip_sha256") != file_sha256(zip_path(engine_id))


def pending_update(engine_id):
    return update_available(engine_id) and engine_id not in _ignored_updates


def ignore_update(engine_id):
    _ignored_updates.add(engine_id)


def status(engine_id):
    if is_default_engine(engine_id):
        return "ready"
    if not is_bundled(engine_id):
        return "missing"
    if not is_installed(engine_id):
        return "not installed"
    return "update available" if update_available(engine_id) else "installed"


def install(engine_id):
    """Unpacks the zip of the game and remembers its sha, it replaces the previous version."""
    if not is_bundled(engine_id):
        raise FileNotFoundError(f"No zip for the game engine {engine_id}")

    destination = game_directory(engine_id)
    staging = tempfile.mkdtemp(prefix=folder_name(engine_id) + "_", dir=GAMES_ROOT)

    try:
        with zipfile.ZipFile(zip_path(engine_id)) as archive:
            for name in archive.namelist():
                target = os.path.normpath(os.path.join(staging, name))
                if os.path.commonpath([staging, target]) != staging:
                    raise ValueError(f"Unsafe path in {zip_path(engine_id)}: {name}")
            archive.extractall(staging)

        if os.path.isdir(destination):
            shutil.rmtree(destination)
        os.replace(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    with open(os.path.join(destination, "engine.json"), "r", encoding="utf-8") as f:
        version = json.load(f)["version"]

    state = read_state()
    state["games"][engine_id] = {"zip_sha256": file_sha256(zip_path(engine_id)), "version": version}
    write_state(state)
    _ignored_updates.discard(engine_id)

    from . import render_defaults
    render_defaults.invalidate()

    return version


def install_all():
    return {engine.id: install(engine.id) for engine in GAME_ENGINES if is_bundled(engine.id)}


def is_setup_done():
    return read_state()["setup_done"]


def set_setup_done(done=True):
    state = read_state()
    state["setup_done"] = done
    write_state(state)


def describe(engine_id):
    engine = get_engine(engine_id)
    state = status(engine_id)
    version = installed_version(engine_id)
    return engine.name if is_default_engine(engine_id) else f"{engine.name}: {state}" + (f" (v{version})" if version else "")
