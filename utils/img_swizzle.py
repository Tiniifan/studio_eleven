from collections import namedtuple
from functools import reduce
from operator import xor

# Define a named tuple for representing a 2D point
Point = namedtuple('Point', ['X', 'Y'])

class MasterSwizzle:
    def __init__(self, image_stride, init, bit_field_coords, init_point_transform_on_y=None):
        self._bit_field_coords = bit_field_coords
        self._init_point_transform_on_y = init_point_transform_on_y or []
        self._init = init
        self.MacroTileWidth = reduce(xor, (p[0] for p in bit_field_coords), 0) + 1
        self.MacroTileHeight = reduce(xor, (p[1] for p in bit_field_coords), 0) + 1
        self._width_in_tiles = (image_stride + self.MacroTileWidth - 1) // self.MacroTileWidth

    def Get(self, point_count):
        # Calculate the macro tile coordinates
        macro_tile_count = point_count // self.MacroTileWidth // self.MacroTileHeight
        macroX, macroY = macro_tile_count % self._width_in_tiles, macro_tile_count // self._width_in_tiles
        
        # Calculate the final point using XOR operations
        return reduce(lambda a, b: Point(a.X ^ b[0], a.Y ^ b[1]),
                      [(macroX * self.MacroTileWidth, macroY * self.MacroTileHeight)] +
                      [v for v, j in zip(self._bit_field_coords, range(len(self._bit_field_coords))) if (point_count >> j) % 2 == 1] +
                      [v for v, j in zip(self._init_point_transform_on_y, range(len(self._init_point_transform_on_y))) if (macroY >> j) % 2 == 1],
                      self._init)

class IMGCSwizzle:
    def __init__(self, width, height):
        self.Width = (width + 0x7) & ~0x7
        self.Height = (height + 0x7) & ~0x7
        self._zorderTrans = MasterSwizzle(self.Width, Point(0, 0), [(0, 1), (1, 0), (0, 2), (2, 0), (0, 4), (4, 0)])

    def Get(self, point):
        return self._zorderTrans.Get(point.Y * self.Width + point.X)

    def get_point_sequence(self):
        stride_width = self.Width
        stride_height = self.Height

        for i in range(stride_width * stride_height):
            point = Point(i % stride_width, i // stride_width)
            if self._zorderTrans is not None:
                point_index = point.Y * self.Width + point.X
                point = self._zorderTrans.Get(point_index)

            yield point