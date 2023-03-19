from .img_format import *

zorder = [  0, 2, 8, 10, 32, 34, 40, 42,
            1, 3, 9, 11, 33, 35, 41, 43,
            4, 6, 12, 14, 36, 38, 44, 46,
            5, 7, 13, 15, 37, 39, 45, 47,
            16, 18, 24, 26, 48, 50, 56, 58,
            17, 19, 25, 27, 49, 51, 57, 59,
            20, 22, 28, 30, 52, 54, 60, 62,
            21, 23, 29, 31, 53, 55, 61, 63 ]   

def encode_image(px, height, width, img_format):
    out = bytes()
    tiles = []
    

    for h in range(0, height, 8):
        for w in range(0, width, 8):
            tile = []

            for bh in range(8):
                for bw in range(8):
                    tile.append(px[(w+bw) + (h+bh) * width])

            if tile not in tiles:
                tiles.append(tile)
                
                for bh in range(8):
                    for bw in range(8):
                        pos = bw + bh * 8
                        for i in range(len(zorder)):
                            if zorder[i] == pos:
                                color = Color(tile[i])
                                out += img_format.encode(color)
                                break
    return out

def image_to_tile(px, height, width):
    out = bytes()
    tiles = []
    
    for h in range(0, height, 8):
        for w in range(0, width, 8):
            tile = []

            for bh in range(8):
                for bw in range(8):
                    tile.append(px[(w+bw) + (h+bh) * width])
            
            if tile not in tiles:
                tiles.append(tile)
                out += int(len(tiles)-1).to_bytes(2, 'little')
            else:
                out += int(tiles.index(tile)).to_bytes(2, 'little')
                
    return out