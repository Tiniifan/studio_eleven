import struct

def lzss_decompress(data):
    output = []
    p = 4
    op = 0

    mask = 0
    flag = 0

    while p < len(data):
        if mask == 0:
            flag = data[p]
            p += 1
            mask = 0x80

        if (flag & mask) == 0:
            if p + 1 > len(data):
                break
            output.append(data[p])
            p += 1
            op += 1
        else:
            if p + 2 > len(data):
                break
            dat = (data[p] << 8) | data[p + 1]
            p += 2
            pos = (dat & 0x0FFF) + 1
            length = (dat >> 12) + 3

            for i in range(length):
                if op - pos >= 0:
                    output.append(output[op - pos] if op - pos < len(output) else 0)
                    op += 1

        mask >>= 1
        
    return bytes(output)

def lzss_compress(data):
    window = []
    output = []
    flags = 0
    flag_index = 0

    for i in range(len(data)):
        search_index = max(0, len(window) - 4096)
        offset = 0
        length = 0
        for j in range(search_index, len(window)):
            if window[j:j + i - search_index] == data[search_index:i]:
                offset = len(window) - j
                length = i - search_index
                break
        if length >= 3:
            length_dist = (length - 3) * 4096 + (offset - 1)
            output.append(length_dist & 0xff)
            output.append((length_dist >> 8) & 0xff)
            flags |= (1 << (7 - flag_index))
            flag_index += 1
        else:
            output.append(data[i])
            flags |= (0 << (7 - flag_index))
            flag_index += 1
        if flag_index == 8:
            output.append(flags)
            flag_index = 0
            flags = 0
        window.append(data[i])
    if flag_index > 0:
        while flag_index < 8:
            flags |= (0 << (7 - flag_index))
            flag_index += 1
        output.append(flags)
      
    return struct.pack('<I', len(data) << 3 | 0x1) + bytes(output)
