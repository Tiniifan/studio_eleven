"""Extract the GLSL ES 3 sources of the Inazuma Eleven Cross shaders into data/unity_shaders.zip.

The game keeps its shaders in an Addressables bundle shipped inside the APK asset pack:
    <APK>/UnityDataAssetPack/assets/aa/Android/app_shaders_assets_all.bundle
(serialized file CAB-12ec70e4e3e31653e4f80978f3841e82, referenced by every effect material).
The materials of the move bundles only point to it (m_Shader), so the shader code is read here once
and stored in studio_x: nobody has to load that bundle at import time.

Every Shader object holds one LZ4 blob per graphics API (9 = GLES3, 18 = Vulkan SPIR-V); the GLES3 blob
contains the variants as plain text programs starting with "#ifdef VERTEX" / "#ifdef FRAGMENT".
Only distinct programs are kept. The text is ~150 MB (URP and background shaders have hundreds of
variants) but ~1 MB once LZMA-zipped: one <shader name>.glsl per shader plus index.json (path IDs,
property names). Shaders stripped from the build (Soccer/Effect/DifferenceFlow) have no program.

python tools/extract_shaders.py <app_shaders_assets_all.bundle | APK/XAPK/zip | folder> [--out FILE.zip]

Usage from the studio_x folder, with plain Python (no Blender needed).
"""

import io
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from unity import Environment  # noqa: E402
from unity.compression import decompress_lz4  # noqa: E402

BUNDLE_NAME = "app_shaders_assets_all.bundle"
PLATFORM_GLES3 = 9
SHADER_CLASS_ID = 48
DEFAULT_OUT = os.path.join(os.path.dirname(HERE), "data", "unity_shaders.zip")
STAGE = re.compile(rb"#ifdef (VERTEX|FRAGMENT)\n")


def find_bundle(path):
    """Return (name, bytes) of the shader bundle from a bundle file, a folder, or an APK/XAPK/zip."""
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for name in files:
                if name == BUNDLE_NAME:
                    return name, open(os.path.join(root, name), "rb").read()
                if name.lower().endswith((".apk", ".xapk", ".zip")):
                    found = find_bundle(os.path.join(root, name))
                    if found:
                        return found
        return None
    if zipfile.is_zipfile(path):
        return _find_in_zip(zipfile.ZipFile(path))
    return os.path.basename(path), open(path, "rb").read()


def _find_in_zip(archive):
    # XAPK files hold the asset pack as a nested APK
    for info in archive.infolist():
        if info.filename.endswith("/" + BUNDLE_NAME) or info.filename == BUNDLE_NAME:
            return BUNDLE_NAME, archive.read(info)
    for info in archive.infolist():
        if info.filename.lower().endswith((".apk", ".zip")):
            found = _find_in_zip(zipfile.ZipFile(io.BytesIO(archive.read(info))))
            if found:
                return found
    return None


def gles3_programs(shader):
    """Distinct GLES3 programs of a Shader object, as (stage, source) in blob order."""
    if PLATFORM_GLES3 not in shader["platforms"]:
        return []
    index = shader["platforms"].index(PLATFORM_GLES3)
    blob = bytes(shader["compressedBlob"])
    data = b"".join(decompress_lz4(blob[offset:offset + size], length)
                    for offset, size, length in zip(shader["offsets"][index],
                                                    shader["compressedLengths"][index],
                                                    shader["decompressedLengths"][index]))
    programs, seen = [], set()
    for match in STAGE.finditer(data):
        end = data.find(b"\0", match.end())
        source = data[match.start():end if end >= 0 else len(data)]
        if source not in seen:
            seen.add(source)
            programs.append((match.group(1).decode(), source.decode("utf-8", "replace")))
    return programs


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = os.path.abspath(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else DEFAULT_OUT
    if "--out" in sys.argv:
        args.remove(sys.argv[sys.argv.index("--out") + 1])
    if not args:
        sys.exit(__doc__)
    found = find_bundle(args[0])
    if not found:
        sys.exit("%s not found in %s" % (BUNDLE_NAME, args[0]))
    environment = Environment()
    environment.load_bytes(found[1], found[0])

    archive = zipfile.ZipFile(out + ".tmp", "w", zipfile.ZIP_LZMA)
    index = {}
    for obj in environment.objects:
        if obj.class_id != SHADER_CLASS_ID:
            continue
        shader = obj.read()
        form = shader["m_ParsedForm"]
        name = form["m_Name"]
        programs = gles3_programs(shader)
        file_name = safe_name(name) + ".glsl"
        text = ["// %s (Shader path ID %d, %s)\n" % (name, obj.path_id, obj.sfile.name)]
        for number, (stage, source) in enumerate(programs):
            text.append("\n// ===== program %d: %s =====\n%s\n" % (number, stage, source))
        archive.writestr(file_name, "".join(text))
        properties = form.get("m_PropInfo", {}).get("m_Props", [])
        index[name] = {
            "path_id": str(obj.path_id),
            "file": file_name,
            "programs": len(programs),
            "properties": [p.get("m_Name") for p in properties],
        }
        print("%-50s %3d programs" % (name, len(programs)))
    archive.writestr("index.json", json.dumps({"source": found[0],
                                               "cab": [s.name for s in environment.serialized_files.values()],
                                               "shaders": index}, indent=1, sort_keys=True))
    archive.close()
    os.replace(out + ".tmp", out)
    print("%d shaders -> %s (%.1f MB)" % (len(index), out, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
