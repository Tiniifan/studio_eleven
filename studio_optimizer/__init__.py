"""Studio Optimizer: optimize meshes for the 3DS games (triangles only, 24 bones per skinned mesh) without
breaking their skinning, shape keys, UV and material animations."""

bl_info = {
    "name": "Studio Optimizer",
    "category": "Mesh",
    "description": "Reduce mesh faces with quadric error edge collapses and split the meshes that use too many bones, keeping animations",
    "author": "Tinifan",
    "version": (1, 3, 0),
    "blender": (2, 80, 2),
    "location": "3D View > Object > Optimize the model for studio_eleven",
    "warning": "",
    "doc_url": "",
    "support": "COMMUNITY",
}

from . import blender_mesh

def register():
    blender_mesh.register()

def unregister():
    blender_mesh.unregister()
