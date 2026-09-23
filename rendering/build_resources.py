"""Extracts the rendering resources of every game engine from the fix.xr archives.

Run outside Blender: python build_resources.py <fix directory>

The default render default and the default material of an engine can't be read from the archives: they are
kept from the previous engine.json, or taken from a legacy templates.json passed as second argument.
"""
import os
import sys
import json
import zlib
import struct
import types
import hashlib
import shutil
import zipfile
import importlib
import collections
from unittest import mock

ROOT = os.path.dirname(os.path.abspath(__file__))
ADDON_ROOT = os.path.dirname(ROOT)
GAMES_ROOT = os.path.join(ROOT, "games")
PACKAGE = os.path.basename(ADDON_ROOT)

# (engine id, fix archive, legacy template it replaces)
ENGINE_SOURCES = (
    ("IE4", "fix_go.xr", "IEGO"),
    ("IE5", "fix_cs.xr", "IEGOCS/GALAXY"),
    ("IE6", "fix_galaxy.xr", "IEGOCS/GALAXY"),
    ("PL5", "fix_layton5.xr", "PLvsPW"),
    ("PL6", "fix_layton6.xr", "PLvsPW"),
    ("PLvsPW", "fix_laytonVSphoenix.xr", "PLvsPW"),
    ("YW1", "fix_ykw1.xr", "YKW"),
    ("YW2", "fix_ykw2.xr", "YKW"),
    ("YW3", "fix_ykw3.xr", "YKW"),
    ("YWB1", "fix_ykwblaster.xr", "YKW"),
    ("YWB2", "fix_ykwblaster2.xr", "YKW"),
    ("SW", "fix_snackworld.xr", "Snack World"),
)

# Version of the data of the engines, it goes up when a game folder changes
ENGINE_VERSION = 2

# The engine lacks the silhouette variant of the legacy default, its skinned program with the same combiner replaces it
FALLBACK_DEFAULT = {"PL5": "#FIX_TON_12"}

SKIN_UNIFORMS = ("unf_vtx_bone", "unf_vtx_lin_mtx", "unf_vtx_sprite_bone", "unf_vtx_srt_clr")

GLSL_EXTENSIONS = {"VTX": ".vert", "FRG": ".frag", "GEO": ".geom"}

# Share of the games that must agree on a combiner for the default game to keep it
AGREEMENT = 2 / 3

# Section types of RES.bin: the loader takes NNN.ext as the N-th entry of the table
TYPE_SHADER_BINARY, TYPE_VERTEX_PROGRAM, TYPE_COMBINER, TYPE_RENDER_PROGRAM, TYPE_LUT, TYPE_ATR = 100, 110, 120, 190, 200, 230


def game_directory(engine_id):
    return os.path.join(GAMES_ROOT, engine_id.lower())


def load_addon():
    for name in ("bpy", "bmesh", "mathutils", "bpy_extras", "bpy.types", "bpy.props", "gpu", "bgl", "blf"):
        sys.modules.setdefault(name, mock.MagicMock())

    if PACKAGE not in sys.modules:
        package = types.ModuleType(PACKAGE)
        package.__path__ = [ADDON_ROOT]
        sys.modules[PACKAGE] = package

    names = ("compression.compressor", "formats.archive.xpck", "formats.material.atr", "formats.material.cmb", "formats.material.lut", "rendering.glsl_format")
    return [importlib.import_module(f"{PACKAGE}.{name}") for name in names]


def parse_strings(data, offset):
    table = {}
    for name in data[offset:].split(b"\0"):
        if name:
            table[zlib.crc32(name)] = name.decode("shift-jis")
    return table


def parse_res(data):
    """Returns ({type: [entry bytes]}, {hash: name})."""
    if data[:4] == b"XRES":
        slots = struct.unpack_from("<60H", data, 4)
        pairs = [(slots[i], slots[i + 1]) for i in range(0, 60, 2)]
        layout = {1: (TYPE_SHADER_BINARY, 12), 2: (TYPE_VERTEX_PROGRAM, 20), 3: (TYPE_COMBINER, 8), 4: (TYPE_LUT, 8),
                  6: (TYPE_ATR, 8), 9: (TYPE_RENDER_PROGRAM, 16)}
        sections = {}
        for slot, (section_type, length) in layout.items():
            offset, count = pairs[slot]
            sections[section_type] = [data[offset + i * length:offset + (i + 1) * length] for i in range(count)]
        return sections, parse_strings(data, pairs[0][0])

    string_offset, _, section_table, section_count = struct.unpack_from("<HhHH", data, 8)
    sections = {}
    for i in range(section_count):
        offset, count, section_type, length = struct.unpack_from("<HHHH", data, (section_table << 2) + i * 8)
        if section_type != 9999:
            sections[section_type] = [data[(offset << 2) + j * length:(offset << 2) + (j + 1) * length] for j in range(count)]
    return sections, parse_strings(data, string_offset << 2)


def parse_dvlb(data):
    """Returns the DVLE list as [{type, uniforms}] in file order."""
    count = struct.unpack_from("<I", data, 4)[0]
    result = []
    for offset in struct.unpack_from(f"<{count}I", data, 8):
        header = struct.unpack_from("<4sHBBIIHHBBBBIIIIIIIIII", data, offset)
        shader_type, uniform_offset, uniform_count, symbol_offset = header[2], header[18], header[19], header[20]
        symbols = offset + symbol_offset
        uniforms = []
        for k in range(uniform_count):
            name_offset = struct.unpack_from("<I", data, offset + uniform_offset + k * 8)[0]
            end = data.index(b"\0", symbols + name_offset)
            uniforms.append(data[symbols + name_offset:end].decode("ascii").split(".")[0])
        result.append({"type": shader_type, "uniforms": uniforms})
    return result


def safe_name(name):
    return name.lstrip("#")


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def gls_filename(name):
    stem = os.path.splitext(name)[0]
    return stem + GLSL_EXTENSIONS[stem[:3]]


def build_engine(engine_id, archive_path, template, templates, tools):
    compressor, xpck, atr, cmb, lut, glsl_format = tools[:6]
    files = xpck.open_file(archive_path)
    sections, names = parse_res(compressor.decompress(files["RES.bin"]))

    def name_of(entry_hash):
        # The archive doesn't always keep the string of a hash that comes from the parent library
        if entry_hash not in names:
            print(f"{engine_id}: no name for {entry_hash:08X}")
        return names.get(entry_hash, f"0x{entry_hash:08X}")

    out = game_directory(engine_id)
    previous = None
    for candidate in (os.path.join(out, "engine.json"), os.path.join(ROOT, engine_id, "engine.json")):
        if os.path.isfile(candidate):
            previous = read_json(candidate)
            break

    for stale in (out, os.path.join(ROOT, engine_id)):
        if os.path.isdir(stale):
            shutil.rmtree(stale)

    # Vertex programs: the DVLB of SHD%03d.shdc holds the vertex DVLEs then the geometry ones
    dvlbs = [parse_dvlb(compressor.decompress(files[f"SHD{i:03d}.shdc"])) for i in range(len(sections[TYPE_SHADER_BINARY]))]
    vertex_programs = {}
    vertex_counts = {}
    for entry in sections[TYPE_VERTEX_PROGRAM]:
        binary = struct.unpack_from("<H", entry, 14)[0]
        vertex_counts[binary] = max(vertex_counts.get(binary, 0), entry[11] + 1)

    for entry in sections[TYPE_VERTEX_PROGRAM]:
        program_hash = struct.unpack_from("<I", entry, 0)[0]
        name = name_of(program_hash)
        binary = struct.unpack_from("<H", entry, 14)[0]
        vertex_dvle = entry[11]
        geometry = None if entry[12] == 0xFF else entry[12] + vertex_counts[binary]
        uniforms = dvlbs[binary][vertex_dvle]["uniforms"]
        vertex_programs[name] = {
            "shader_binary": binary,
            "vertex_dvle": vertex_dvle,
            "geometry_dvle": geometry,
            "skin_uniforms": [u for u in SKIN_UNIFORMS if u in uniforms],
            "skinned": "unf_vtx_bone" in uniforms,
            "gls_vertex": entry[8],
            "gls_geometry": None if entry[9] == 0xFF else entry[9],
        }
    write_json(os.path.join(out, "vertex_programs.json"), vertex_programs)

    # Combiners: NNN.cmb is the N-th type 120 entry
    combiners = {}
    for index, entry in enumerate(sections[TYPE_COMBINER]):
        name = name_of(struct.unpack_from("<I", entry, 0)[0])
        version, stages = cmb.read_cmb(files[f"{index:03d}.cmb"])
        combiners[name] = stages
        write_json(os.path.join(out, "combiners", safe_name(name) + ".json"), {
            "name": name,
            "file_version": version,
            "stages": [stage.to_dict() for stage in stages],
        })

    # LUTs and ATR presets share the same numbering
    lut_names = []
    for index, entry in enumerate(sections[TYPE_LUT]):
        name = name_of(struct.unpack_from("<I", entry, 0)[0])
        lut_names.append(name)
        table = lut.read_lut(files[f"{index:03d}.lut"])
        assert lut.Lut.from_dict(table.to_dict(name)) == table
        write_json(os.path.join(out, "luts", safe_name(name) + ".json"), table.to_dict(name))

    atr_names = []
    for index, entry in enumerate(sections[TYPE_ATR]):
        name = name_of(struct.unpack_from("<I", entry, 0)[0])
        atr_names.append(name)
        state = atr.read_atr(files[f"{index:03d}.atr"])
        write_json(os.path.join(out, "atr", safe_name(name) + ".json"), {
            "name": name,
            "file_version": state.file_version,
            "state": state.to_dict(),
        })

    # GLSL of the desktop GL path, only the whitespace is changed
    for name, data in xpck.open_file(compressor.decompress(files["SHD.shdw"])).items():
        source = data.decode("utf-8")
        formatted = glsl_format.format_glsl(source)
        assert glsl_format.same_tokens(source, formatted), name
        write_text(os.path.join(out, "gls", gls_filename(name)), formatted)

    # Render defaults: one per render program
    render_program_names = []
    for entry in sections[TYPE_RENDER_PROGRAM]:
        program_hash, _, vertex_hash, combiner_hash = struct.unpack("<4I", entry)
        name = name_of(program_hash)
        render_program_names.append(name)
        vertex_name, combiner_name = name_of(vertex_hash), name_of(combiner_hash)
        write_json(os.path.join(out, "render_defaults", safe_name(name) + ".json"), {
            "name": name,
            "vertex_program": vertex_name,
            "combiner": combiner_name,
            # Some programs name a vertex program that fix.xr doesn't define, the engine then asks the parent library
            "skinned": vertex_programs[vertex_name]["skinned"] if vertex_name in vertex_programs else None,
            "fragment_lighting": any(stage.uses_fragment_lighting for stage in combiners[combiner_name]) if combiner_name in combiners else None,
        })

    if previous is not None:
        default_program, default_mtr = previous["default_render_default"], previous["default_material"]["mtr"]
    else:
        legacy = templates[template]
        legacy_hash = int.from_bytes(bytes.fromhex(legacy["modes"]["Object (Transparent)"][0]), "little")
        default_program = next((name for name in render_program_names if zlib.crc32(name.encode("shift-jis")) == legacy_hash), None)
        default_program = default_program or FALLBACK_DEFAULT.get(engine_id)
        default_mtr = legacy["mtr"]

    if default_program not in render_program_names:
        raise RuntimeError(f"{engine_id}: default render default {default_program} is not a render program of the engine")

    write_json(os.path.join(out, "engine.json"), {
        "id": engine_id,
        "version": ENGINE_VERSION,
        "file_version": 1 if files["000.atr"][:6] == b"ATRC00" else 2,
        "default_render_default": default_program,
        "default_material": {"mtr": default_mtr},
        "luts": lut_names,
        "atr_presets": atr_names,
    })
    return len(render_program_names)

##########################################
# Default game
##########################################

def load_game(engine_id, tools):
    _, _, atr, cmb, lut, _ = tools[:6]
    directory = game_directory(engine_id)
    game = {"info": read_json(os.path.join(directory, "engine.json")), "vertex_programs": read_json(os.path.join(directory, "vertex_programs.json"))}

    for kind in ("render_defaults", "combiners", "atr", "luts"):
        game[kind] = {}
        for filename in sorted(os.listdir(os.path.join(directory, kind))):
            data = read_json(os.path.join(directory, kind, filename))
            game[kind][data["name"]] = data

    game["gls"] = {}
    for filename in sorted(os.listdir(os.path.join(directory, "gls"))):
        with open(os.path.join(directory, "gls", filename), "r", encoding="utf-8") as f:
            game["gls"][filename] = f.read()

    return game


def majority(variants):
    """The most frequent value of a list of JSON values, the first one wins a tie."""
    counts = collections.Counter(json.dumps(variant, sort_keys=True) for variant in variants)
    best = max(counts.values())
    for variant in variants:
        if counts[json.dumps(variant, sort_keys=True)] == best:
            return variant, best


def build_default(engine_ids, tools):
    """A game with what every engine agrees on: the render programs whose vertex program and combiner are the same
    everywhere. Where the engines differ the variant used by most of them is kept."""
    games = {engine_id: load_game(engine_id, tools) for engine_id in engine_ids}
    count = len(games)
    out = game_directory("DEFAULT_V2")
    for stale in (game_directory("default"), out, game_directory("DEFAULT_V1")):
        if os.path.isdir(stale):
            shutil.rmtree(stale)

    report = collections.OrderedDict()
    common = set.intersection(*[set(game["render_defaults"]) for game in games.values()])
    shared = []
    for name in sorted(common):
        definitions = [game["render_defaults"][name] for game in games.values()]
        combiner = definitions[0]["combiner"]
        vertex = definitions[0]["vertex_program"]
        same_names = all(d["vertex_program"] == vertex and d["combiner"] == combiner for d in definitions)
        reference = games[engine_ids[0]]
        stage_lists = [g["combiners"][combiner]["stages"] for g in games.values() if combiner in g["combiners"]]
        stages, votes = majority(stage_lists) if stage_lists else (None, 0)
        same_stages = votes >= AGREEMENT * count
        if same_stages and votes < count:
            odd = [engine_id for engine_id, g in games.items() if g["combiners"].get(combiner, {}).get("stages") != stages]
            report[f"combiner {combiner}"] = f"{votes}/{count} games, differs in {', '.join(odd)}"
        same_skin = vertex in reference["vertex_programs"] and all(
            vertex in g["vertex_programs"] and g["vertex_programs"][vertex]["skin_uniforms"] == reference["vertex_programs"][vertex]["skin_uniforms"]
            for g in games.values())
        if same_names and same_stages and same_skin:
            shared.append(name)

    report["render_defaults"] = f"{len(shared)} kept ({len(common)} exist in the {count} games)"

    for name in shared:
        write_json(os.path.join(out, "render_defaults", safe_name(name) + ".json"), games[engine_ids[0]]["render_defaults"][name])

    combiners = sorted({games[engine_ids[0]]["render_defaults"][name]["combiner"] for name in shared})
    for name in combiners:
        stages, _ = majority([g["combiners"][name]["stages"] for g in games.values() if name in g["combiners"]])
        write_json(os.path.join(out, "combiners", safe_name(name) + ".json"), {"name": name, "file_version": 2, "stages": stages})
    report["combiners"] = f"{len(combiners)}"

    # The 3DS binaries are game specific, only what the engines agree on is kept of a vertex program
    gls_variants = collections.defaultdict(list)
    vertex_programs = {}
    for name in sorted({games[engine_ids[0]]["render_defaults"][n]["vertex_program"] for n in shared}):
        reference = games[engine_ids[0]]["vertex_programs"][name]
        variants = [g["gls"][f"VTX{g['vertex_programs'][name]['gls_vertex']:03d}.vert"] for g in games.values()]
        source, votes = majority(variants)
        gls_variants[source].append(name)
        vertex_programs[name] = {
            "shader_binary": None, "vertex_dvle": None, "geometry_dvle": None,
            "skin_uniforms": reference["skin_uniforms"], "skinned": reference["skinned"],
            "gls_vertex": None, "gls_geometry": None, "gls_votes": votes,
        }

    for index, (source, users) in enumerate(gls_variants.items()):
        write_text(os.path.join(out, "gls", f"VTX{index:03d}.vert"), source)
        for name in users:
            vertex_programs[name]["gls_vertex"] = index

    for entry in vertex_programs.values():
        del entry["gls_votes"]
    write_json(os.path.join(out, "vertex_programs.json"), vertex_programs)
    report["vertex_programs"] = f"{len(vertex_programs)}, {len(gls_variants)} distinct vertex shaders"

    # Fragment shaders can't be tied to a combiner, the ones found in most games are kept
    fragment_votes = collections.Counter()
    for game in games.values():
        for source in {text for filename, text in game["gls"].items() if filename.endswith(".frag")}:
            fragment_votes[source] += 1
    kept = [source for source, votes in fragment_votes.most_common() if votes * 2 > count]
    for index, source in enumerate(kept):
        write_text(os.path.join(out, "gls", f"FRG{index:03d}.frag"), source)
    report["fragment_shaders"] = f"{len(kept)} kept ({len(fragment_votes)} distinct in the games)"

    atr_names = sorted(set.intersection(*[set(game["atr"]) for game in games.values()]))
    for name in atr_names:
        variants = [{key: value for key, value in game["atr"][name]["state"].items()} for game in games.values()]
        state, votes = majority(variants)
        write_json(os.path.join(out, "atr", safe_name(name) + ".json"), {"name": name, "file_version": 2, "state": state})
    report["atr"] = f"{len(atr_names)} presets in every game"

    lut_names = sorted(set.intersection(*[set(game["luts"]) for game in games.values()]))
    for name in lut_names:
        variants = [{key: value for key, value in game["luts"][name].items() if key != "name"} for game in games.values()]
        data, votes = majority(variants)
        write_json(os.path.join(out, "luts", safe_name(name) + ".json"), dict({"name": name}, **data))
        report[f"lut {name}"] = f"{votes}/{count} games"

    preferred = ["#FIX_TON_12", "#FIX_MDS", "#FIX_IMG"]
    default_program = next((name for name in preferred if name in shared), shared[0])
    write_json(os.path.join(out, "engine.json"), {
        "id": "DEFAULT_V2",
        "version": ENGINE_VERSION,
        "file_version": 2,
        "default_render_default": default_program,
        "default_material": {"mtr": majority([game["info"]["default_material"]["mtr"] for game in games.values() if game["info"]["file_version"] == 2])[0]},
        "luts": lut_names,
        "atr_presets": atr_names,
    })
    report["default render default"] = default_program

    for key, value in report.items():
        print(f"default: {key}: {value}")

    derive_default_v1(games, tools)


def derive_default_v1(games, tools):
    """The same configuration written the way a V1 game stores it: V1 combiners, the render state a V1 file can hold."""
    atr = tools[2]
    source, out = game_directory("DEFAULT_V2"), game_directory("DEFAULT_V1")
    shutil.copytree(source, out)

    info = read_json(os.path.join(out, "engine.json"))
    info["id"], info["file_version"] = "DEFAULT_V1", 1
    info["default_material"] = {"mtr": next(game["info"]["default_material"]["mtr"] for game in games.values() if game["info"]["file_version"] == 1)}
    write_json(os.path.join(out, "engine.json"), info)

    for filename in os.listdir(os.path.join(out, "combiners")):
        path = os.path.join(out, "combiners", filename)
        data = read_json(path)
        data["file_version"] = 1
        write_json(path, data)

    for filename in os.listdir(os.path.join(out, "atr")):
        path = os.path.join(out, "atr", filename)
        data = read_json(path)
        data["state"] = atr.read_atr(atr.write_atr(atr.AtrState(**data["state"]), 1)).to_dict()
        data["file_version"] = 1
        write_json(path, data)

##########################################
# Zip
##########################################

def zip_directory(directory, zip_path):
    """A zip that only depends on the files: fixed dates, sorted names."""
    entries = []
    for folder, _, filenames in os.walk(directory):
        for filename in filenames:
            path = os.path.join(folder, filename)
            entries.append((os.path.relpath(path, directory).replace(os.sep, "/"), path))

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, path in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(path, "rb") as f:
                archive.writestr(info, f.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    with open(zip_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    fix_directory = sys.argv[1]
    templates = {}
    if len(sys.argv) > 2:
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            templates = {t["name"]: t for t in json.load(f)["templates"]}

    tools = load_addon()
    os.makedirs(GAMES_ROOT, exist_ok=True)

    for engine_id, archive, template in ENGINE_SOURCES:
        count = build_engine(engine_id, os.path.join(fix_directory, archive), template, templates, tools)
        print(f"{engine_id}: {count} render defaults")

    build_default([engine_id for engine_id, _, _ in ENGINE_SOURCES], tools)

    for engine_id, _, _ in ENGINE_SOURCES:
        digest = zip_directory(game_directory(engine_id), game_directory(engine_id) + ".zip")
        print(f"{engine_id.lower()}.zip sha256 {digest[:16]}")


if __name__ == "__main__":
    main()
