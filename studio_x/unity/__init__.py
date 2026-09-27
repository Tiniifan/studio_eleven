"""Standalone Unity asset/bundle reader (no UnityPy, no bpy).

Usage:
    from studio_x.unity import Environment
    env = Environment("character.bundle")
    for obj in env.objects:
        print(obj.type_name, obj.path_id, obj.peek_name())
"""

from .environment import Environment
from .bundle_file import BundleFile
from .serialized_file import SerializedFile, ObjectInfo
from .class_ids import CLASS_IDS, CLASS_NAMES, class_name
