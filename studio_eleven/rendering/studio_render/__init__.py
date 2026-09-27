"""StudioRender, the render engine of the addon driven by the data the games ship in fix.xr.

The gpu module is only touched from inside the draw calls, so importing and registering the package
works in background mode.
"""

from . import billboard, combiner, draw, engine, lighting, material, resources, shaders, state

ENGINE_ID = engine.ENGINE_ID


def register():
    engine.register()


def unregister():
    engine.unregister()
