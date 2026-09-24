import io

def decompress(input_bytes):
    input_stream = io.BytesIO(input_bytes)
    compression_header = input_stream.read(4)
    
    if compression_header[0] & 0x7 != 0x4:
        raise Exception("Not Level5 Rle")

    decompressed_size = (compression_header[0] >> 3) | (compression_header[1] << 5) | \
                        (compression_header[2] << 13) | (compression_header[3] << 21)

    output_stream = bytearray()
    while len(output_stream) < decompressed_size:
        flag = input_stream.read(1)[0]
        if flag & 0x80:
            repetitions = (flag & 0x7F) + 3
            output_stream.extend(bytes([input_stream.read(1)[0]]) * repetitions)
        else:
            length = flag + 1
            uncompressed_data = input_stream.read(length)
            output_stream.extend(uncompressed_data)

    return bytes(output_stream)

def compress(data):
    out = bytearray()
    out += int(len(data) << 3 | 0x4).to_bytes(4, 'little')

    raw_start = 0
    i = 0

    while i < len(data):
        run = 1

        # A run holds 3 to 130 bytes
        while i + run < len(data) and data[i + run] == data[i] and run < 130:
            run += 1

        if run < 3:
            i += 1

            # Raw blocks hold 1 to 128 bytes
            if i - raw_start == 128:
                out.append(127)
                out += data[raw_start:i]
                raw_start = i

            continue

        if i > raw_start:
            out.append(i - raw_start - 1)
            out += data[raw_start:i]

        out.append(0x80 | (run - 3))
        out.append(data[i])

        i += run
        raw_start = i

    if len(data) > raw_start:
        out.append(len(data) - raw_start - 1)
        out += data[raw_start:]

    return bytes(out)
