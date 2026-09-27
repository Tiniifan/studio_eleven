r"""Find the UnityFS bundle files that hold given serialized files (CAB-...), reading only each
bundle's directory (header + LZ4 block info), so thousands of files are scanned in seconds.

python tools/find_cab.py CAB-xxxx [CAB-yyyy ...] [DIR ...]
Without DIR, scans E:\InazumaCross\1.3.2\content\files\UnityCache\Shared. A material's m_Shader
PPtr gives the CAB through its m_FileID (entry m_FileID - 1 of the serialized file externals).
Needs the lz4 package (system Python, not Blender).
"""
import glob
import os
import struct
import sys

import lz4.block


def cstring(f):
    out = b""
    while True:
        c = f.read(1)
        if not c or c == b"\0":
            return out.decode("utf-8", "replace")
        out += c


def directory(path):
    with open(path, "rb") as f:
        if cstring(f) != "UnityFS":
            return []
        version = struct.unpack(">I", f.read(4))[0]
        cstring(f), cstring(f)
        size, csize, usize, flags = struct.unpack(">qIII", f.read(20))
        if version >= 7:
            f.seek((f.tell() + 15) & ~15)
        if flags & 0x80:
            f.seek(os.path.getsize(path) - csize)
        raw = f.read(csize)
    kind = flags & 0x3F
    info = raw if kind == 0 else lz4.block.decompress(raw, uncompressed_size=usize)
    pos = 16
    blocks = struct.unpack_from(">i", info, pos)[0]
    pos += 4 + blocks * 10
    count = struct.unpack_from(">i", info, pos)[0]
    pos += 4
    names = []
    for _ in range(count):
        pos += 20
        end = info.index(b"\0", pos)
        names.append(info[pos:end].decode())
        pos = end + 1
    return names


roots = [a for a in sys.argv[1:] if os.path.isdir(a)]
want = [a for a in sys.argv[1:] if a not in roots]
paths = ([os.path.join(d, n) for r in roots for d, _, fs in os.walk(r) for n in fs] if roots
         else glob.glob(r"E:\InazumaCross\1.3.2\content\files\UnityCache\Shared\*\*\__data"))
for path in paths:
    try:
        names = directory(path)
    except Exception:
        continue
    if any(w in n for n in names for w in want):
        print(path, os.path.getsize(path), names)

