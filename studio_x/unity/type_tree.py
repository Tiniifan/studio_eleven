"""TypeTree parsing and generic object deserialization.

A TypeTree describes the binary layout of each serialized class. Reading objects
through it avoids hardcoding structures for every Unity version.

Based on UnityPy's TypeTreeNode.py / TypeTreeHelper.py (https://github.com/K0lb3/UnityPy)
and AssetStudio's TypeTreeNode.cs / CommonString.cs (https://github.com/aelurum/AssetStudioMod).
"""

import struct

from .binary_reader import BinaryReader

ALIGN_FLAG = 0x4000

# Strings shared by all type trees, referenced by offset | 0x80000000 (AssetStudio CommonString.cs)
COMMON_STRINGS = {
    0: "AABB", 5: "AnimationClip", 19: "AnimationCurve", 34: "AnimationState", 49: "Array",
    55: "Base", 60: "BitField", 69: "bitset", 76: "bool", 81: "char", 86: "ColorRGBA",
    96: "Component", 106: "data", 111: "deque", 117: "double", 124: "dynamic_array",
    138: "FastPropertyName", 155: "first", 161: "float", 167: "Font", 172: "GameObject",
    183: "Generic Mono", 196: "GradientNEW", 208: "GUID", 213: "GUIStyle", 222: "int",
    226: "list", 231: "long long", 241: "map", 245: "Matrix4x4f", 256: "MdFour",
    263: "MonoBehaviour", 277: "MonoScript", 288: "m_ByteSize", 299: "m_Curve",
    307: "m_EditorClassIdentifier", 331: "m_EditorHideFlags", 349: "m_Enabled",
    359: "m_ExtensionPtr", 374: "m_GameObject", 387: "m_Index", 395: "m_IsArray",
    405: "m_IsStatic", 416: "m_MetaFlag", 427: "m_Name", 434: "m_ObjectHideFlags",
    452: "m_PrefabInternal", 469: "m_PrefabParentObject", 490: "m_Script",
    499: "m_StaticEditorFlags", 519: "m_Type", 526: "m_Version", 536: "Object", 543: "pair",
    548: "PPtr<Component>", 564: "PPtr<GameObject>", 581: "PPtr<Material>",
    596: "PPtr<MonoBehaviour>", 616: "PPtr<MonoScript>", 633: "PPtr<Object>",
    646: "PPtr<Prefab>", 659: "PPtr<Sprite>", 672: "PPtr<TextAsset>", 688: "PPtr<Texture>",
    702: "PPtr<Texture2D>", 718: "PPtr<Transform>", 734: "Prefab", 741: "Quaternionf",
    753: "Rectf", 759: "RectInt", 767: "RectOffset", 778: "second", 785: "set", 789: "short",
    795: "size", 800: "SInt16", 807: "SInt32", 814: "SInt64", 821: "SInt8", 827: "staticvector",
    840: "string", 847: "TextAsset", 857: "TextMesh", 866: "Texture", 874: "Texture2D",
    884: "Transform", 894: "TypelessData", 907: "UInt16", 914: "UInt32", 921: "UInt64",
    928: "UInt8", 934: "unsigned int", 947: "unsigned long long", 966: "unsigned short",
    981: "vector", 988: "Vector2f", 997: "Vector3f", 1006: "Vector4f",
    1015: "m_ScriptingClassIdentifier", 1042: "Gradient", 1051: "Type*", 1057: "int2_storage",
    1070: "int3_storage", 1083: "BoundsInt", 1093: "m_CorrespondingSourceObject",
    1121: "m_PrefabInstance", 1138: "m_PrefabAsset", 1152: "FileSize", 1161: "Hash128",
    1169: "RenderingLayerMask", 1188: "fixed_array", 1200: "EntityId",
}

# Primitive type name -> struct format
PRIMITIVE_FORMATS = {
    "SInt8": "b", "UInt8": "B", "char": "B", "short": "h", "SInt16": "h",
    "unsigned short": "H", "UInt16": "H", "int": "i", "SInt32": "i", "unsigned int": "I",
    "UInt32": "I", "Type*": "I", "long long": "q", "SInt64": "q", "unsigned long long": "Q",
    "UInt64": "Q", "FileSize": "Q", "float": "f", "double": "d", "bool": "?",
}


PRIMITIVE_SIZES = {fmt: struct.calcsize(fmt) for fmt in set(PRIMITIVE_FORMATS.values())}


class TypeTreeNode:
    __slots__ = ("type", "name", "byte_size", "index", "flags", "version", "meta_flag",
                 "level", "ref_type_hash", "children")

    def __init__(self, type_name="", name="", level=0):
        self.type = type_name
        self.name = name
        self.level = level
        self.byte_size = 0
        self.index = 0
        self.flags = 0
        self.version = 0
        self.meta_flag = 0
        self.ref_type_hash = 0
        self.children = []

    def __repr__(self):
        return "TypeTreeNode(%s %s)" % (self.type, self.name)


def _build_tree(nodes):
    root = nodes[0]
    stack = [root]
    for node in nodes[1:]:
        while len(stack) > node.level:
            stack.pop()
        stack[-1].children.append(node)
        stack.append(node)
    return root


def parse_blob(reader, format_version):
    """Parse the compact type tree format (SerializedFile version >= 12 or == 10)."""
    node_count = reader.read_i32()
    string_size = reader.read_i32()
    node_size = 32 if format_version >= 19 else 24
    node_data = reader.read_view(node_size * node_count)
    strings = bytes(reader.read_view(string_size))

    def get_string(offset):
        if offset & 0x80000000:
            return COMMON_STRINGS.get(offset & 0x7FFFFFFF, str(offset & 0x7FFFFFFF))
        end = strings.find(b"\x00", offset)
        return strings[offset:end].decode("utf-8", "replace")

    fmt = reader.endian + "hBBIIiii" + ("Q" if format_version >= 19 else "")
    nodes = []
    for values in struct.iter_unpack(fmt, node_data):
        node = TypeTreeNode(get_string(values[3]), get_string(values[4]), values[1])
        node.version = values[0]
        node.flags = values[2]
        node.byte_size = values[5]
        node.index = values[6]
        node.meta_flag = values[7]
        if format_version >= 19:
            node.ref_type_hash = values[8]
        nodes.append(node)
    return _build_tree(nodes)


def parse_legacy(reader, format_version, level=0):
    """Parse the old recursive type tree format (SerializedFile version < 12)."""
    node = TypeTreeNode(level=level)
    node.type = reader.read_cstring()
    node.name = reader.read_cstring()
    node.byte_size = reader.read_i32()
    if format_version == 2:
        reader.read_i32()  # variable count
    if format_version != 3:
        node.index = reader.read_i32()
    node.flags = reader.read_i32()
    node.version = reader.read_i32()
    if format_version != 3:
        node.meta_flag = reader.read_i32()
    child_count = reader.read_i32()
    for _ in range(child_count):
        node.children.append(parse_legacy(reader, format_version, level + 1))
    return node


class TypeTreeReader:
    """Deserialize an object's bytes into nested dicts/lists following its TypeTree."""

    def __init__(self, serialized_file=None):
        self.serialized_file = serialized_file

    def read(self, root, reader):
        return self._read_value(root, reader, False)

    def _find_ref_type(self, ref_object):
        type_info = ref_object.get("type") or {}
        class_name = type_info.get("class", "")
        if not class_name or self.serialized_file is None:
            return None
        for ref_type in self.serialized_file.ref_types:
            if (ref_type.class_name == class_name and ref_type.namespace == type_info.get("ns")
                    and ref_type.assembly_name == type_info.get("asm")):
                return ref_type.node
        return None

    def _read_value(self, node, reader, has_registry):
        align = node.meta_flag & ALIGN_FLAG
        node_type = node.type
        fmt = PRIMITIVE_FORMATS.get(node_type)

        if fmt is not None:
            value = reader._unpack(fmt, PRIMITIVE_SIZES[fmt])
        elif node_type == "string":
            value = reader.read_aligned_string()
        elif node_type == "TypelessData":
            value = reader.read_bytes(reader.read_i32())
        elif node_type == "pair":
            value = (self._read_value(node.children[0], reader, has_registry),
                     self._read_value(node.children[1], reader, has_registry))
        elif node_type == "ReferencedObject":
            value = {}
            for child in node.children:
                if child.type == "ReferencedObjectData":
                    ref_node = self._find_ref_type(value)
                    value[child.name] = self._read_value(ref_node, reader, has_registry) if ref_node else None
                else:
                    value[child.name] = self._read_value(child, reader, has_registry)
        elif node.children and node.children[0].type == "Array":
            array_node = node.children[0]
            if array_node.meta_flag & ALIGN_FLAG:
                align = True
            size = reader.read_i32()
            if size < 0:
                raise ValueError("Negative array size in %s" % node.name)
            value = self._read_array(array_node.children[1], reader, size, has_registry)
        else:
            value = {}
            for child in node.children:
                if child.type == "ManagedReferencesRegistry":
                    if has_registry:
                        continue
                    has_registry = True
                value[child.name] = self._read_value(child, reader, has_registry)

        if align:
            reader.align(4)
        return value

    def _read_array(self, item_node, reader, size, has_registry):
        fmt = PRIMITIVE_FORMATS.get(item_node.type)
        if fmt is not None and not (item_node.meta_flag & ALIGN_FLAG):
            if fmt in ("B", "b") and item_node.type != "SInt8":
                # Byte buffers (vertex data, image data...) stay as bytes for speed
                return reader.read_bytes(size)
            return list(reader.read_array(fmt, size))
        return [self._read_value(item_node, reader, has_registry) for _ in range(size)]


def read_object(root, data, endian="<", serialized_file=None):
    reader = BinaryReader(data, endian)
    return TypeTreeReader(serialized_file).read(root, reader)
