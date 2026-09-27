"""Unity SerializedFile (the "CAB-xxxx" / .assets files holding objects).

Header, type table and object table parsing ported from UnityPy's SerializedFile.py /
ObjectReader.py (https://github.com/K0lb3/UnityPy) and AssetStudio's SerializedFile.cs
(https://github.com/aelurum/AssetStudioMod).
"""

import re

from .binary_reader import BinaryReader
from . import type_tree
from .class_ids import class_name


class SerializedType:
    __slots__ = ("class_id", "is_stripped", "script_type_index", "script_id", "old_type_hash",
                 "node", "class_name", "namespace", "assembly_name", "type_dependencies")

    def __init__(self, reader, sfile, is_ref_type):
        version = sfile.format_version
        self.class_id = reader.read_i32()
        self.is_stripped = False
        self.script_type_index = -1
        self.script_id = None
        self.old_type_hash = None
        self.node = None
        self.class_name = self.namespace = self.assembly_name = ""
        self.type_dependencies = ()

        if version >= 16:
            self.is_stripped = reader.read_bool()
        if version >= 17:
            self.script_type_index = reader.read_i16()
        if version >= 13:
            if ((is_ref_type and self.script_type_index >= 0)
                    or (version < 16 and self.class_id < 0)
                    or (version >= 16 and self.class_id == 114)):
                self.script_id = reader.read_bytes(16)
            self.old_type_hash = reader.read_bytes(16)

        if sfile.enable_type_tree:
            if version >= 12 or version == 10:
                self.node = type_tree.parse_blob(reader, version)
            else:
                self.node = type_tree.parse_legacy(reader, version)
            if version >= 21:
                if is_ref_type:
                    self.class_name = reader.read_cstring()
                    self.namespace = reader.read_cstring()
                    self.assembly_name = reader.read_cstring()
                else:
                    self.type_dependencies = reader.read_array("i", reader.read_i32())


class ExternalReference:
    __slots__ = ("path", "guid", "type")

    def __init__(self, reader, version):
        if version >= 6:
            reader.read_cstring()
        self.guid = None
        self.type = 0
        if version >= 5:
            self.guid = reader.read_bytes(16)
            self.type = reader.read_i32()
        self.path = reader.read_cstring()

    @property
    def name(self):
        return self.path.replace("\\", "/").split("/")[-1]


class ObjectInfo:
    """Entry of the object table. Call `read()` to deserialize it through its TypeTree."""

    __slots__ = ("sfile", "path_id", "byte_start", "byte_size", "type_id", "class_id",
                 "serialized_type", "_cache")

    def __init__(self, sfile, path_id, byte_start, byte_size, type_id, class_id, serialized_type):
        self.sfile = sfile
        self.path_id = path_id
        self.byte_start = byte_start
        self.byte_size = byte_size
        self.type_id = type_id
        self.class_id = class_id
        self.serialized_type = serialized_type
        self._cache = None

    @property
    def type_name(self):
        return class_name(self.class_id)

    @property
    def raw_data(self):
        return self.sfile.data[self.byte_start:self.byte_start + self.byte_size]

    def read(self):
        if self._cache is None:
            node = self.serialized_type.node if self.serialized_type else None
            if node is None:
                raise NotImplementedError(
                    "Object %d (%s) has no TypeTree; stripped files are not supported"
                    % (self.path_id, self.type_name))
            self._cache = type_tree.read_object(node, self.raw_data, self.sfile.endian, self.sfile)
        return self._cache

    def peek_name(self):
        """Return the object's m_Name without failing on unreadable objects."""
        node = self.serialized_type.node if self.serialized_type else None
        if node is None or not node.children:
            return None
        try:
            if node.children[0].name == "m_Name":
                reader = BinaryReader(self.raw_data, self.sfile.endian)
                return reader.read_aligned_string()
            if any(child.name == "m_Name" for child in node.children):
                return self.read().get("m_Name")
        except Exception:
            pass
        return None

    def __repr__(self):
        return "<%s path_id=%d>" % (self.type_name, self.path_id)


class SerializedFile:
    def __init__(self, data, name="", environment=None, parent=None):
        self.name = name
        self.environment = environment
        self.parent = parent
        self.data = memoryview(data)
        reader = BinaryReader(self.data, ">")

        metadata_size = reader.read_u32()
        file_size = reader.read_u32()
        self.format_version = reader.read_u32()
        data_offset = reader.read_u32()

        if self.format_version >= 9:
            self.endian = ">" if reader.read_bool() else "<"
            reader.skip(3)
            if self.format_version >= 22:
                metadata_size = reader.read_u32()
                file_size = reader.read_i64()
                data_offset = reader.read_i64()
                reader.read_i64()
        else:
            reader.seek(file_size - metadata_size)
            self.endian = ">" if reader.read_bool() else "<"
        reader.endian = self.endian

        self.unity_version = ""
        if self.format_version >= 7:
            self.unity_version = reader.read_cstring()
        self.target_platform = -1
        if self.format_version >= 8:
            self.target_platform = reader.read_i32()
        self.enable_type_tree = True
        if self.format_version >= 13:
            self.enable_type_tree = reader.read_bool()

        self.types = [SerializedType(reader, self, False) for _ in range(reader.read_i32())]

        big_id_enabled = 0
        if 7 <= self.format_version < 14:
            big_id_enabled = reader.read_i32()

        self.objects = {}
        for _ in range(reader.read_i32()):
            if big_id_enabled:
                path_id = reader.read_i64()
            elif self.format_version < 14:
                path_id = reader.read_i32()
            else:
                reader.align(4)
                path_id = reader.read_i64()

            byte_start = reader.read_i64() if self.format_version >= 22 else reader.read_u32()
            byte_start += data_offset
            byte_size = reader.read_u32()
            type_id = reader.read_i32()

            if self.format_version < 16:
                class_id = reader.read_u16()
                serialized_type = next((t for t in self.types if t.class_id == type_id), None)
            else:
                serialized_type = self.types[type_id]
                class_id = serialized_type.class_id
            if self.format_version < 11:
                reader.read_u16()  # is destroyed
            if 11 <= self.format_version < 17:
                script_type_index = reader.read_i16()
                if serialized_type:
                    serialized_type.script_type_index = script_type_index
            if self.format_version in (15, 16):
                reader.read_u8()  # stripped

            self.objects[path_id] = ObjectInfo(self, path_id, byte_start, byte_size, type_id,
                                               class_id, serialized_type)

        if self.format_version >= 11:
            for _ in range(reader.read_i32()):
                reader.read_i32()
                if self.format_version < 14:
                    reader.read_i32()
                else:
                    reader.align(4)
                    reader.read_i64()

        self.externals = [ExternalReference(reader, self.format_version) for _ in range(reader.read_i32())]

        self.ref_types = []
        if self.format_version >= 20:
            self.ref_types = [SerializedType(reader, self, True) for _ in range(reader.read_i32())]

    @property
    def version_tuple(self):
        match = re.match(r"(\d+)\.(\d+)\.(\d+)", self.unity_version)
        return tuple(int(x) for x in match.groups()) if match else (0, 0, 0)

    @staticmethod
    def is_serialized_file(data):
        """Heuristic check used to tell SerializedFiles apart from resource blobs."""
        if len(data) < 20:
            return False
        reader = BinaryReader(data, ">")
        metadata_size = reader.read_u32()
        file_size = reader.read_u32()
        version = reader.read_u32()
        data_offset = reader.read_u32()
        if version >= 22:
            if len(data) < 48:
                return False
            reader.skip(4)
            metadata_size = reader.read_u32()
            file_size = reader.read_i64()
            data_offset = reader.read_i64()
        if not (0 < version < 100):
            return False
        return file_size == len(data) and data_offset <= file_size and metadata_size < file_size

    def resolve_external(self, file_id):
        """Return the SerializedFile referenced by a PPtr m_FileID, or None when unavailable."""
        if file_id == 0:
            return self
        index = file_id - 1
        if index < 0 or index >= len(self.externals) or self.environment is None:
            return None
        return self.environment.find_serialized_file(self.externals[index].name)

    def get_object(self, pptr):
        """Resolve a PPtr dict {"m_FileID", "m_PathID"} to an ObjectInfo."""
        if not pptr or pptr.get("m_PathID", 0) == 0:
            return None
        target = self.resolve_external(pptr.get("m_FileID", 0))
        if target is None:
            return None
        return target.objects.get(pptr["m_PathID"])
