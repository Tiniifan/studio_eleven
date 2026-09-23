class Color:
    def __init__(self, color):
        self.r = color[0]
        self.g = color[1]
        self.b = color[2]
        self.a = 0

        if (len(color) == 4):
            self.a = color[3]
