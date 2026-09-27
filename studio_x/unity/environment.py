"""Entry point to load Unity files and browse their objects.

The Environment keeps every loaded SerializedFile and resource blob (.resS, .resource)
by name so PPtr and StreamingInfo references can be resolved across files, like
UnityPy's Environment (https://github.com/K0lb3/UnityPy/blob/master/UnityPy/environment.py).
"""

import os

from .bundle_file import BundleFile
from .serialized_file import SerializedFile


class Environment:
    def __init__(self, *paths):
        self.serialized_files = {}
        self.resources = {}
        self.bundles = []
        self.directories = set()
        for path in paths:
            self.load(path)

    def load(self, path):
        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                for file_name in files:
                    self.load_file(os.path.join(root, file_name))
        else:
            self.load_file(path)

    def load_file(self, path):
        self.directories.add(os.path.dirname(os.path.abspath(path)))
        with open(path, "rb") as stream:
            data = stream.read()
        return self.load_bytes(data, os.path.basename(path))

    def load_bytes(self, data, name):
        if BundleFile.is_bundle(data):
            bundle = BundleFile(data)
            self.bundles.append((name, bundle))
            for entry in bundle.entries:
                self._register(bundle.read_entry(entry), os.path.basename(entry.path), bundle)
            return bundle
        return self._register(memoryview(data), name, None)

    def _register(self, data, name, parent):
        if SerializedFile.is_serialized_file(data):
            sfile = SerializedFile(data, name, self, parent)
            self.serialized_files[name.lower()] = sfile
            return sfile
        self.resources[name.lower()] = data
        return data

    def find_serialized_file(self, name):
        return self.serialized_files.get(os.path.basename(name).lower())

    @property
    def objects(self):
        for sfile in self.serialized_files.values():
            for obj in sfile.objects.values():
                yield obj

    def get_resource(self, path, offset, size):
        """Read a StreamingInfo blob (texture/mesh data stored outside the SerializedFile)."""
        name = os.path.basename(path.replace("archive:", "")).lower()
        data = self.resources.get(name)
        if data is None:
            for directory in self.directories:
                candidate = os.path.join(directory, os.path.basename(path))
                if os.path.isfile(candidate):
                    with open(candidate, "rb") as stream:
                        data = memoryview(stream.read())
                    self.resources[name] = data
                    break
        if data is None:
            raise FileNotFoundError("Resource not found: %s" % path)
        return bytes(data[offset:offset + size])
