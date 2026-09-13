import numpy as np

modifiers = [
    [2, 8, -2, -8],
    [5, 17, -5, -17],
    [9, 29, -9, -29],
    [13, 42, -13, -42],
    [18, 60, -18, -60],
    [24, 80, -24, -80],
    [33, 106, -33, -106],
    [47, 183, -47, -183]
]

pixel_order = [0, 4, 1, 5, 8, 12, 9, 13, 2, 6, 3, 7, 10, 14, 11, 15]

# ETC1 class for compressing and decompressing ETC1 image data
class ETC1:
    def __init__(self, has_alpha_channel, width, height):
        self.has_alpha_channel = has_alpha_channel
        self.Width = width
        self.Height = height

    # Method for compressing data (Not Implemented)
    def compress(self, data):
        return None

    # Method for decompressing ETC1a4 data
    def decompress(self, data):
        return ETC1Decoder.decompress_etc1a4(data, self.Width, self.Height, self.has_alpha_channel)

class ETC1Decoder:
    @staticmethod
    def decompress_etc1a4(data, width, height, has_alpha_channel):
        """Decode every 4x4 block at once; pixels of a block are written in pixel_order."""
        block_count = ((height + 3) // 4) * ((width + 3) // 4)
        block_length = 16 if has_alpha_channel else 8
        
        source = np.frombuffer(bytes(data), dtype=np.uint8)[:block_count * block_length]
        blocks = np.zeros(block_count * block_length, dtype=np.uint8)
        blocks[:len(source)] = source
        blocks = blocks.reshape(block_count, block_length).astype(np.int64)
        
        alpha_bytes = blocks[:, :8] if has_alpha_channel else None
        color_bytes = blocks[:, 8:] if has_alpha_channel else blocks
        
        lsb = color_bytes[:, 0] | (color_bytes[:, 1] << 8)
        msb = color_bytes[:, 2] | (color_bytes[:, 3] << 8)
        flags = color_bytes[:, 4]
        
        flip_bit = (flags & 1) == 1
        diff_bit = (flags & 2) == 2
        table0 = (flags >> 5) & 7
        table1 = (flags >> 2) & 7
        
        # Channels in R, G, B order
        channels = np.stack([color_bytes[:, 7], color_bytes[:, 6], color_bytes[:, 5]], axis=1)
        diff = diff_bit[:, None]
        
        color0 = np.where(diff, channels >> 3, channels >> 4)
        sign3 = (channels % 8 + 4) % 8 - 4
        color1 = np.where(diff, color0 + sign3, channels % 16)
        
        # 16 levels are scaled with * 17, 32 levels with bit replication
        color0 = np.where(diff, (color0 << 3) | (color0 >> 2), color0 * 17)
        color1 = np.where(diff, (color1 << 3) | (color1 >> 2), color1 * 17)
        
        modifier_table = np.array(modifiers, dtype=np.int64)
        flip_bit_mask = np.where(flip_bit, 2, 8)
        
        channel_count = 4 if has_alpha_channel else 3
        result = np.zeros((block_count, 16, channel_count), dtype=np.uint8)
        
        for t, i in enumerate(pixel_order):
            use_color0 = (i & flip_bit_mask) == 0
            base = np.where(use_color0[:, None], color0, color1)
            table = np.where(use_color0, table0, table1)
            modifier = modifier_table[table, ((msb >> i) & 1) * 2 + ((lsb >> i) & 1)]
            result[:, t, :3] = np.clip(base + modifier[:, None], 0, 255)
            
            if has_alpha_channel:
                result[:, t, 3] = ((alpha_bytes[:, i // 2] >> ((i & 1) * 4)) & 0x0F) * 17
        
        return result.tobytes()
