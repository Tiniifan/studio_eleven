import io
import struct

class NibbleOrder:
    LowNibbleFirst = 0
    HighNibbleFirst = 1

def decompress(data, bit_depth):
    def decode_headerless(input_stream, output_stream, decompressed_size):
        nibble_order = NibbleOrder.LowNibbleFirst 
        result = bytearray(decompressed_size * 8 // bit_depth)

        with io.BytesIO(input_stream.read()) as br:
            tree_size = br.read(1)[0]
            tree_root = br.read(1)[0]
            tree_buffer = br.read(tree_size * 2)

            i = 0
            code = 0
            next_val = 0
            pos = tree_root
            result_pos = 0

            while result_pos < len(result):
                if i % 32 == 0:
                    code = struct.unpack("I", br.read(4))[0]

                next_val += ((pos & 0x3F) << 1) + 2
                direction = 2 if (code >> (31 - i) % 32) % 2 == 0 else 1
                leaf = (pos >> 5 >> direction) % 2 != 0

                pos = tree_buffer[next_val - direction]

                if leaf:
                    result[result_pos] = pos
                    result_pos += 1
                    pos = tree_root
                    next_val = 0
                    
                i += 1

        if bit_depth == 8:
            output_stream.write(result)
        else:
            combined_data = [
                (result[2 * j] | (result[2 * j + 1] << 4))
                if nibble_order == NibbleOrder.LowNibbleFirst
                else ((result[2 * j] << 4) | result[2 * j + 1])
                for j in range(decompressed_size)
            ]

            output_stream.write(bytes(combined_data))

    with io.BytesIO(data) as input_stream, io.BytesIO() as output_stream:
        compression_header = input_stream.read(4)

        huffman_mode = 2 if bit_depth == 4 else 3
        if (compression_header[0] & 0x7) != huffman_mode:
            raise ValueError(f"Level5 Huffman{bit_depth}")

        decompressed_size = (
            (compression_header[0] >> 3)
            | (compression_header[1] << 5)
            | (compression_header[2] << 13)
            | (compression_header[3] << 21)
        )
        
        decode_headerless(input_stream, output_stream, decompressed_size)

        return output_stream.getvalue()
