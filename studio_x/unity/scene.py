"""GameObject / Transform hierarchy helpers built on top of deserialized objects."""

from .class_ids import CLASS_IDS

CLASS_TRANSFORM = CLASS_IDS["Transform"]
CLASS_RECT_TRANSFORM = CLASS_IDS["RectTransform"]


class SceneNode:
    __slots__ = ("obj", "game_object", "name", "parent", "children", "position", "rotation",
                 "scale", "components", "active")

    def __init__(self, obj, transform, game_object):
        self.obj = obj
        self.game_object = game_object
        self.name = game_object.get("m_Name", "") if game_object else ""
        self.active = bool(game_object.get("m_IsActive", True)) if game_object else True
        self.parent = None
        self.children = []
        p = transform["m_LocalPosition"]
        r = transform["m_LocalRotation"]
        s = transform["m_LocalScale"]
        self.position = (p["x"], p["y"], p["z"])
        self.rotation = (r["x"], r["y"], r["z"], r["w"])
        self.scale = (s["x"], s["y"], s["z"])
        # class name -> list of ObjectInfo
        self.components = {}

    @property
    def path(self):
        names = []
        node = self
        while node is not None:
            names.append(node.name)
            node = node.parent
        return "/".join(reversed(names))

    def relative_path(self, ancestor):
        """Path used by AnimationClip bindings: relative to the Animator's GameObject."""
        names = []
        node = self
        while node is not None and node is not ancestor:
            names.append(node.name)
            node = node.parent
        return "/".join(reversed(names))

    def get_component(self, type_name):
        items = self.components.get(type_name)
        return items[0] if items else None

    def walk(self):
        yield self
        for child in self.children:
            for node in child.walk():
                yield node

    def find(self, relative_path):
        node = self
        for part in relative_path.split("/") if relative_path else []:
            node = next((c for c in node.children if c.name == part), None)
            if node is None:
                return None
        return node

    def __repr__(self):
        return "SceneNode(%r)" % self.path


class Scene:
    """All Transform hierarchies found in a SerializedFile."""

    def __init__(self, sfile):
        self.sfile = sfile
        self.nodes = {}
        for obj in sfile.objects.values():
            if obj.class_id not in (CLASS_TRANSFORM, CLASS_RECT_TRANSFORM):
                continue
            transform = obj.read()
            go_info = sfile.get_object(transform["m_GameObject"])
            game_object = go_info.read() if go_info else None
            node = SceneNode(obj, transform, game_object)
            if game_object:
                for component in game_object["m_Component"]:
                    info = sfile.get_object(component["component"])
                    if info is not None:
                        node.components.setdefault(info.type_name, []).append(info)
            self.nodes[obj.path_id] = node

        self.roots = []
        for path_id, node in self.nodes.items():
            transform = node.obj.read()
            father = transform["m_Father"]
            parent = self.nodes.get(father["m_PathID"]) if father["m_FileID"] == 0 else None
            if parent is None:
                self.roots.append(node)
        # Keep children in the serialized order
        for node in self.nodes.values():
            for child_ptr in node.obj.read()["m_Children"]:
                child = self.nodes.get(child_ptr["m_PathID"])
                if child is not None:
                    child.parent = node
                    node.children.append(child)

    def all_nodes(self):
        for root in self.roots:
            for node in root.walk():
                yield node
