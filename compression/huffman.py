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

##########################################
# Huffman Compress Function
##########################################

# Same tree building and node labelling as Kuriimu2 (https://github.com/FanTranslatorsInternational/Kuriimu2)

def get_symbols(data, bit_depth):
    if bit_depth == 8:
        return data

    symbols = bytearray(len(data) * 2)
    symbols[0::2] = bytes(b & 0xF for b in data)
    symbols[1::2] = bytes(b >> 4 for b in data)

    return bytes(symbols)

def build_tree(frequencies):
    queue = []

    for symbol in range(len(frequencies)):
        if frequencies[symbol] > 0:
            queue.append({"frequency": frequencies[symbol], "value": symbol, "children": None})

    # The tree needs at least two leaves
    while len(queue) < 2:
        queue.append({"frequency": 1, "value": 0, "children": None})

    while len(queue) > 1:
        queue.sort(key=lambda node: node["frequency"])

        left = queue.pop(0)
        right = queue.pop(0)

        queue.append({"frequency": left["frequency"] + right["frequency"], "value": 0, "children": [left, right]})

    return queue[0]

def label_tree(root):
    labels = []
    pending = [root]
    root["code"] = 0

    while len(pending) > 0:
        best_index = 0

        for i in range(len(pending)):
            if pending[i]["code"] - i < pending[best_index]["code"] - best_index:
                best_index = i

        node = pending.pop(best_index)
        node["code"] = len(labels) - node["code"]
        labels.append(node)

        if node["children"] is None:
            continue

        for child in reversed(node["children"]):
            if child["children"] is not None:
                child["code"] = len(labels)
                pending.append(child)

    return labels

def get_codes(node, prefix, codes):
    if node["children"] is None:
        if prefix == "":
            codes[node["value"]] = "0"
        else:
            codes[node["value"]] = prefix
    else:
        get_codes(node["children"][0], prefix + "0", codes)
        get_codes(node["children"][1], prefix + "1", codes)

    return codes

def write_tree(labels):
    out = bytearray()
    out.append(len(labels))

    nodes = [labels[0]]

    for label in labels:
        if label["children"] is not None:
            nodes += label["children"]

    for node in nodes:
        if node["children"] is None:
            out.append(node["value"])
        else:
            # A node can only point 63 pairs further
            if node["code"] > 0x3F:
                raise Exception("Huffman tree too deep")

            code = node["code"]

            if node["children"][0]["children"] is None:
                code |= 0x80

            if node["children"][1]["children"] is None:
                code |= 0x40

            out.append(code)

    return bytes(out)

def compress(data, bit_depth):
    symbols = get_symbols(data, bit_depth)

    frequencies = [0] * (1 << bit_depth)

    for symbol in range(len(frequencies)):
        frequencies[symbol] = symbols.count(symbol)

    root = build_tree(frequencies)
    labels = label_tree(root)
    codes = get_codes(root, "", {})

    out = bytes()

    if bit_depth == 4:
        out += struct.pack('<I', len(data) << 3 | 0x2)
    else:
        out += struct.pack('<I', len(data) << 3 | 0x3)

    out += write_tree(labels)

    # The bits are read from the highest bit of little endian ints
    bits = "".join([codes[symbol] for symbol in symbols])
    bits += "0" * (-len(bits) % 32)

    words = bytearray(len(bits) // 8)

    for i in range(0, len(bits), 32):
        words[i // 8:i // 8 + 4] = int(bits[i:i + 32], 2).to_bytes(4, 'little')

    out += bytes(words)

    return out
