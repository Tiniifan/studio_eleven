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
