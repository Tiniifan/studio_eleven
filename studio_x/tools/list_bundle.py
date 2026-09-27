"""List the files and objects contained in Unity asset bundles / serialized files.

Runs with a plain Python interpreter (no Blender, no UnityPy):
    python tools/list_bundle.py path/to/file.bundle [--type Mesh] [--dump PATH_ID]
"""

import argparse
import json
import os
import sys

# Import the reader package directly so the Blender addon (and bpy) is not loaded
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unity import Environment  # noqa: E402


def to_json(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "<%d bytes>" % len(value)
    if isinstance(value, dict):
        return {key: to_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        if len(value) > 64:
            return [to_json(item) for item in value[:64]] + ["... %d more" % (len(value) - 64)]
        return [to_json(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--type", help="only list objects of this class (e.g. Mesh, Texture2D)")
    parser.add_argument("--dump", type=int, help="print the deserialized object with this path id")
    args = parser.parse_args()

    env = Environment(*args.paths)

    for name, bundle in env.bundles:
        print("Bundle %s (%s, Unity %s)" % (name, bundle.signature, bundle.engine_version))
        for entry in bundle.entries:
            print("  %-60s %10d bytes" % (entry.path, entry.size))

    for sfile in env.serialized_files.values():
        print("\nSerializedFile %s (format %d, Unity %s, platform %d, %d objects)" % (
            sfile.name, sfile.format_version, sfile.unity_version, sfile.target_platform, len(sfile.objects)))
        for obj in sorted(sfile.objects.values(), key=lambda o: (o.type_name, o.path_id)):
            if args.type and obj.type_name != args.type:
                continue
            if args.dump is not None:
                if obj.path_id == args.dump:
                    print(json.dumps(to_json(obj.read()), indent=2, ensure_ascii=False))
                continue
            print("  %-24s %22d  %s" % (obj.type_name, obj.path_id, obj.peek_name() or ""))


if __name__ == "__main__":
    main()
