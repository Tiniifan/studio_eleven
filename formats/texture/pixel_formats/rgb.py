class RGB:
    def __init__(self, r, g, b):
        self.R = r
        self.G = g
        self.B = b
        self.padding = 0  # Padding for speed reasons

    # Operator overloading for addition
    def __add__(self, mod):
        return RGB(self._clamp(self.R + mod), self._clamp(self.G + mod), self._clamp(self.B + mod))

    # Operator overloading for subtraction
    def __sub__(self, other):
        return self._error_rgb(self.R - other.R, self.G - other.G, self.B - other.B)

    # Static method to calculate the average color from a list of colors
    @staticmethod
    def average(src):
        return RGB(
            int(sum(c.R for c in src) / len(src)),
            int(sum(c.G for c in src) / len(src)),
            int(sum(c.B for c in src) / len(src))
        )

    # Method to scale the RGB values
    def scale(self, limit):
        return RGB(self.R * 17, self.G * 17, self.B * 17) if limit == 16 else RGB(
            (self.R << 3) | (self.R >> 2),
            (self.G << 3) | (self.G >> 2),
            (self.B << 3) | (self.B >> 2)
        )

    # Method to unscale the RGB values
    def unscale(self, limit):
        return RGB(self.R * limit // 256, self.G * limit // 256, self.B * limit // 256)

    # Method to calculate the hash value of the RGB instance
    def __hash__(self):
        return self.R | (self.G << 8) | (self.B << 16)

    # Method to check equality of two RGB instances
    def __eq__(self, other):
        return isinstance(other, RGB) and self.__hash__() == other.__hash__()

    # Method to check inequality of two RGB instances
    def __ne__(self, other):
        return not self.__eq__(other)

    # Static method to clamp a value between 0 and 255
    @staticmethod
    def _clamp(n):
        return max(0, min(n, 255))

    # Static method to calculate a signed value between -4 and 3
    @staticmethod
    def sign3(n):
        return (n + 4) % 8 - 4

    # Static method to calculate error in RGB values based on human perception
    @staticmethod
    def _error_rgb(r, g, b):
        return 2 * r * r + 4 * g * g + 3 * b * b  # human perception
