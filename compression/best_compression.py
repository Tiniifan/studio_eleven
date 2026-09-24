import heapq

import numpy as np

##########################################
# About this file
##########################################

# find_best_compression(data, methods) tells which Level-5 compression gives the smallest block, without running any
# compressor. Compressing a block with the 5 methods to keep the smallest one is what Level-5's own tool seems to do
# (the shipped files use every method, block by block), but it is slow in Python: the LZ10 and Huffman encoders loop
# over every byte. Here the size of every method is computed (or estimated) with a few numpy passes over the data:
#
#   - no compression: the size is known, 4 + len(data).
#   - Huffman 4 / 8 bit: the size is EXACT. A Huffman code only depends on the symbol frequencies, so the histogram
#     gives the length of every code, then the size of the bit stream (sum of frequency * code length).
#     The tree takes 2 bytes per symbol in the Nintendo / Level-5 layout.
#   - RLE: the size is EXACT. The runs of equal bytes are found with numpy, then counted the way the encoder cuts them.
#   - LZ10: the size is ESTIMATED, with the same greedy parse as the encoder but with a few match candidates per
#     position instead of the whole 4 KB window (see get_lz_parse). The estimate is almost never below the real size:
#     a missed candidate can only make a match shorter.
#   - zlib: the size is ESTIMATED from the same parse (32 KB window, matches up to 258 bytes) plus an entropy cost for
#     the literals. The V1 and V2 games refuse zlib, it is only here so the function works with any list of methods.
#
# The blocks of the games are small: on 73 596 blocks of the shipped files (maps, models and animations of a V2 game)
# the median block is 180 bytes, 95% are under 32 KB and the largest one is 661 560 bytes (a bone animation), see
# MAX_BLOCK_SIZE. Above SAMPLE_SIZE the LZ estimate only looks at spread samples of the data (Harnik et al.).
#
# Sources:
#   - Level-5 compression header and methods: Kuriimu2, https://github.com/FanTranslatorsInternational/Kuriimu2
#     (Level5 compression), and the decompressor of the V1 / V2 games (methods 0 to 4, anything else is refused).
#   - Size of an optimal code from the frequencies: D. A. Huffman, "A Method for the Construction of
#     Minimum-Redundancy Codes" (1952), https://en.wikipedia.org/wiki/Huffman_coding
#   - Nintendo Huffman / LZ77 (LZ10) / RLE layouts, that Level-5 reuses: GBATEK, "BIOS Decompression Functions",
#     https://problemkaputt.de/gbatek.htm
#   - LZSS, a match is only written when it is shorter than the literals (3 bytes and more here):
#     https://en.wikipedia.org/wiki/Lempel%E2%80%93Ziv%E2%80%93Storer%E2%80%93Szymanski
#   - Match candidates found with the previous occurrences of the same 3 byte string, recent ones first:
#     zlib, "algorithm.txt", https://github.com/madler/zlib/blob/master/doc/algorithm.txt
#   - Estimating the compressibility on samples instead of compressing everything: D. Harnik, R. Kat, O. Margalit,
#     D. Sotnikov, A. Traeger, "To Zip or Not to Zip: Effective Resource Usage for Real-Time Compression", FAST 2013,
#     https://www.usenix.org/conference/fast13/technical-sessions/presentation/harnik

##########################################
# CONST
##########################################

NO_COMPRESSION = 0
LZ10 = 1
HUFFMAN_4 = 2
HUFFMAN_8 = 3
RLE = 4
ZLIB = 5

COMPRESSION_NAMES = {
    NO_COMPRESSION: "No compression",
    LZ10: "LZ10",
    HUFFMAN_4: "Huffman 4 bit",
    HUFFMAN_8: "Huffman 8 bit",
    RLE: "RLE",
    ZLIB: "zlib",
}

# Methods the decompressor of the V1 and V2 games accepts (every block of every format goes through it)
LEVEL5_COMPRESSIONS = [NO_COMPRESSION, LZ10, HUFFMAN_4, HUFFMAN_8, RLE]

# Largest decompressed block of the shipped files (661 560 bytes) rounded up: no real block is bigger, the heavy data
# find_best_compression was tested on stops there
MAX_BLOCK_SIZE = 0x100000

# Above this size, the LZ estimate looks at SAMPLE_COUNT spread samples of SAMPLE_LENGTH bytes
SAMPLE_SIZE = 0x10000
SAMPLE_COUNT = 8
SAMPLE_LENGTH = 0x2000

# LZ10: 12 bit distance (1 to 4096), 4 bit length (3 to 18)
LZ10_WINDOW = 0x1000
LZ10_MAX_LENGTH = 18

# Deflate: 32 KB window, matches of 3 to 258 bytes
ZLIB_WINDOW = 0x8000
ZLIB_MAX_LENGTH = 258

# Lengths of the strings used to find match candidates (see get_lz_parse)
KEY_LENGTHS = [3, 6, 12]

# RLE: a run holds 3 to 130 bytes (2 bytes in the file), a raw block 1 to 128 bytes (1 flag byte + the bytes)
RLE_MAX_RUN = 130
RLE_MAX_RAW = 128

##########################################
# Exact Size Function
##########################################

def get_stored_size(array):
    # 4 bytes of header then the data as it is
    return 4 + len(array)

def get_huffman_bit_count(frequencies):
    # Build the Huffman tree on the frequencies only: every time the two lightest nodes are merged, every symbol under
    # them gets one more bit, so the total number of bits is the sum of the weights of all the merged nodes.
    # The encoder gets the same total (any optimal tree has the same total, whatever the ties).
    weights = [int(frequency) for frequency in frequencies if frequency > 0]

    # The encoder always builds a tree of 2 leaves at least: a single symbol still costs 1 bit
    if len(weights) < 2:
        return sum(weights), 2

    leaf_count = len(weights)
    heapq.heapify(weights)

    bit_count = 0

    while len(weights) > 1:
        merged = heapq.heappop(weights) + heapq.heappop(weights)
        bit_count += merged
        heapq.heappush(weights, merged)

    return bit_count, leaf_count

def get_huffman_size(array, bit_depth):
    if bit_depth == 8:
        # One symbol per byte
        frequencies = np.bincount(array, minlength=256)
    else:
        # Two symbols per byte, the low nibble and the high nibble
        frequencies = np.bincount(array & 0xF, minlength=16) + np.bincount(array >> 4, minlength=16)

    bit_count, leaf_count = get_huffman_bit_count(frequencies)

    # Header (4) + tree (1 size byte, the root, then 2 bytes per internal node = 2 bytes per leaf)
    # + the bit stream, written as whole little endian ints
    return 4 + 2 * leaf_count + 4 * ((bit_count + 31) // 32)

def get_rle_size(array):
    size = len(array)

    if size == 0:
        return 4

    # Start of every run of equal bytes, and its length
    starts = np.flatnonzero(np.concatenate(([True], array[1:] != array[:-1])))
    lengths = np.diff(np.append(starts, size))

    # A run of 3 bytes or more becomes run blocks of up to 130 bytes; what is left (0 to 2 bytes after the last full
    # block, or a whole run shorter than 3) is written as raw bytes
    is_run = lengths >= 3
    full_blocks = lengths // RLE_MAX_RUN
    left = lengths % RLE_MAX_RUN

    run_blocks = np.where(is_run, full_blocks + (left >= 3), 0)
    raw_bytes = np.where(is_run, np.where(left >= 3, 0, left), lengths)

    # The raw bytes between two run blocks make one raw segment, cut in blocks of 128 bytes with one flag byte each.
    # A new segment starts after every run that wrote run blocks (its leftover raw bytes start the segment).
    segment_ids = np.cumsum(run_blocks > 0)
    segment_bytes = np.bincount(segment_ids, weights=raw_bytes).astype(np.int64)
    raw_flags = int(np.sum((segment_bytes + RLE_MAX_RAW - 1) // RLE_MAX_RAW))

    return 4 + 2 * int(np.sum(run_blocks)) + int(np.sum(raw_bytes)) + raw_flags

##########################################
# LZ Estimate Function
##########################################

def get_words(array, count):
    # words[i] holds the 8 bytes from position i as a little endian int, the first byte in the lowest bits.
    # The data is padded with zeros so every position has its 8 bytes (and a few more words for the long matches).
    padded = np.concatenate((array, np.zeros(count * 8 + 8, dtype=np.uint8))).astype(np.uint64)
    words = np.zeros(len(array) + count * 8, dtype=np.uint64)

    for i in range(8):
        words |= padded[i:i + len(words)] << np.uint64(8 * i)

    return words

def get_equal_bytes(x):
    # Number of equal leading bytes of two words from x = word1 ^ word2: the first byte of x that is not 0
    # (the words are little endian, the first byte of the data is the first byte in memory). 8 when the words are equal.
    different = x.view(np.uint8).reshape(-1, 8) != 0

    return np.where(different.any(axis=1), different.argmax(axis=1), 8)

def get_key_hashes(array, key_length):
    # Hash of the key_length bytes from every position (a polynomial hash, the ints wrap around). A collision can only
    # give a bad candidate, and a bad candidate gets a short length when its bytes are compared.
    count = len(array) - key_length + 1
    hashes = np.zeros(count, dtype=np.uint64)

    with np.errstate(over='ignore'):
        for i in range(key_length):
            hashes = hashes * np.uint64(0x100000001B3) + array[i:i + count].astype(np.uint64)

    return hashes

def get_candidates(hashes, window):
    # For every position, two previous positions that start with the same bytes (-1 when there is none):
    #   - the nearest one: sort the positions by hash (stable, so the positions of a hash stay in order), then every
    #     position follows its previous one;
    #   - the oldest one still in the window.
    count = len(hashes)
    positions = np.arange(count, dtype=np.int64)

    order = np.argsort(hashes, kind='stable')
    sorted_hashes = hashes[order]
    same = sorted_hashes[1:] == sorted_hashes[:-1]

    nearest = np.full(count, -1, dtype=np.int64)
    nearest[order[1:][same]] = order[:-1][same]

    # The first position of every hash, and the rank of the hash in the sorted list
    ranks = np.zeros(count, dtype=np.int64)
    ranks[1:] = np.cumsum(~same)
    group_starts = np.flatnonzero(np.concatenate(([True], ~same)))

    hash_ranks = np.zeros(count, dtype=np.int64)
    hash_ranks[order] = ranks
    oldest = order[group_starts[hash_ranks]]

    # When the first position of the hash left the window, search (hash, position - window) in the list sorted by
    # (hash, position), the rank replaces the hash so the pair fits in one int. Only for those positions.
    too_old = np.flatnonzero(positions - oldest > window)

    if len(too_old) > 0:
        combined = ranks * (count + window + 1) + order
        targets = hash_ranks[too_old] * (count + window + 1) + too_old - window
        found = np.searchsorted(combined, targets)
        oldest[too_old] = order[np.minimum(found, count - 1)]

    # The first position of a hash has no previous one
    oldest = np.where(oldest < positions, oldest, -1)

    return nearest, oldest

def get_match_lengths(words, positions, candidates, size, window, max_length):
    # Length of the match between every position and its candidate, compared 8 bytes at a time.
    # Only the positions whose match is still growing are compared again.
    distances = positions - candidates
    lengths = np.zeros(len(candidates), dtype=np.int64)

    alive = np.flatnonzero((candidates >= 0) & (distances <= window))

    for offset in range(0, max_length, 8):
        if len(alive) == 0:
            break

        equal = get_equal_bytes(words[positions[alive] + offset] ^ words[candidates[alive] + offset])
        lengths[alive] += equal
        alive = alive[equal == 8]

    # The match stops at the end of the data, at the maximum length, and it can not overlap the current position
    lengths = np.minimum(lengths, size - positions)
    lengths = np.minimum(lengths, max_length)
    lengths = np.minimum(lengths, distances)

    return np.where(lengths >= 3, lengths, 0), distances

def follow_greedy_parse(lengths, size, costs = None):
    # The encoder is greedy: at each position it writes the match if there is one (and skips its length), otherwise
    # a literal. Instead of walking the data token by token, the path from position 0 is followed with pointer
    # jumping: after round k, next_positions[i] is the position reached from i after 2^k tokens, and the counts
    # hold the tokens, the matches and the cost (in bits, costs[i] is the cost of the token written at i) met on the
    # way. The end of the data (position size) loops on itself with 0 counts.
    is_match = lengths >= 3
    steps = np.minimum(np.arange(size, dtype=np.int64) + np.where(is_match, lengths, 1), size)

    if costs is None:
        costs = np.zeros(size)

    next_positions = np.append(steps, size)
    token_counts = np.append(np.ones(size, dtype=np.int64), 0)
    match_counts = np.append(is_match.astype(np.int64), 0)
    cost_counts = np.append(costs, 0)

    jumps = 1

    while jumps < size:
        token_counts = token_counts + token_counts[next_positions]
        match_counts = match_counts + match_counts[next_positions]
        cost_counts = cost_counts + cost_counts[next_positions]
        next_positions = next_positions[next_positions]
        jumps *= 2

    return int(token_counts[0]), int(match_counts[0]), float(cost_counts[0])

def get_lz10_cost(token_count, match_count):
    literal_count = token_count - match_count

    # Tokens are grouped by 8 behind a flag byte, the last group is filled with 0 bytes
    group_count = (token_count + 7) // 8
    padding = group_count * 8 - token_count

    # A literal is 1 byte, a match 2 bytes
    return 4 + group_count + literal_count + 2 * match_count + padding

def get_lz_parse(array, window, max_length, stop_below = None):
    # The encoder looks for the longest match in the whole window, at every position. Here every position only gets
    # 2 candidates for every length of KEY_LENGTHS:
    #   - the nearest previous position that starts with the same bytes. If the longest match of the window is 14 bytes
    #     long, the nearest position with the same 12 bytes gives at least 12 of them. The long keys find the aligned
    #     repeats of the structured data (vertices, keyframes, pixels) that the nearest 3 byte repeat misses;
    #   - the oldest position of the window that starts with the same bytes, it is the one the encoder finds (it searches
    #     from the start of the window) and on the runs of equal bytes (zeros, padding) it is the only one that gives a
    #     long match, the nearest ones are too close to the current position.
    # More candidates can only give longer matches, so a smaller size: with stop_below (LZ10 only), the search stops
    # as soon as the size is below it, LZ10 has already won.
    size = len(array)

    # Too short for any match: only literals
    if size < 4:
        return np.zeros(size, dtype=np.int64), np.zeros(size, dtype=np.int64), size, 0

    words = get_words(array, (max_length + 7) // 8)
    lengths = np.zeros(size, dtype=np.int64)
    distances = np.zeros(size, dtype=np.int64)

    for key_length in KEY_LENGTHS:
        if size < key_length:
            break

        nearest, oldest = get_candidates(get_key_hashes(array, key_length), window)
        count = len(nearest)

        # Both candidates are measured in one pass, one after the other
        positions = np.arange(count, dtype=np.int64)
        candidate_lengths, candidate_distances = get_match_lengths(words, np.concatenate((positions, positions)), np.concatenate((nearest, oldest)), size, window, max_length)
        candidate_lengths = candidate_lengths.reshape(2, count)
        candidate_distances = candidate_distances.reshape(2, count)

        # Keep the longest match, the nearest one on a tie
        for i in range(2):
            longer = candidate_lengths[i] > lengths[:count]
            lengths[:count] = np.where(longer, candidate_lengths[i], lengths[:count])
            distances[:count] = np.where(longer, candidate_distances[i], distances[:count])

        if stop_below is not None and key_length != KEY_LENGTHS[-1]:
            token_count, match_count, cost = follow_greedy_parse(lengths, size)

            if get_lz10_cost(token_count, match_count) < stop_below:
                return lengths, distances, token_count, match_count

    token_count, match_count, cost = follow_greedy_parse(lengths, size)

    return lengths, distances, token_count, match_count

def get_lz10_size(array, stop_below = None):
    lengths, distances, token_count, match_count = get_lz_parse(array, LZ10_WINDOW, LZ10_MAX_LENGTH, stop_below)

    return get_lz10_cost(token_count, match_count)

def get_zlib_size(array):
    # Rough deflate cost, token by token on the same greedy parse:
    #   - a literal costs its order 0 entropy, -log2(frequency of the byte), what a Huffman code gives at best;
    #   - a match costs its length code (about 7 bits + 1 extra bit) and its distance code (5 bits + log2(distance) - 1
    #     extra bits, deflate splits the distances in 30 codes of doubling ranges).
    size = len(array)
    lengths, distances, token_count, match_count = get_lz_parse(array, ZLIB_WINDOW, ZLIB_MAX_LENGTH)

    frequencies = np.bincount(array, minlength=256)
    literal_bits = -np.log2(frequencies[array] / size)
    match_bits = 8 + 5 + np.maximum(np.floor(np.log2(np.maximum(distances, 1))) - 1, 0)

    token_count, match_count, bit_count = follow_greedy_parse(lengths, size, np.where(lengths >= 3, match_bits, literal_bits))

    # Deflate can also use its fixed codes, without tables: a literal costs 8 bits (0 to 143) or 9 bits (144 to 255)
    fixed_literal_bits = np.where(array < 144, 8, 9)
    token_count, match_count, fixed_bit_count = follow_greedy_parse(lengths, size, np.where(lengths >= 3, match_bits, fixed_literal_bits))

    # Header (4) + zlib header and checksum (6) + the Huffman tables of a dynamic block (about 64 bytes)
    return int(4 + 6 + min(64 + bit_count / 8, fixed_bit_count / 8))

def get_samples(array):
    # SAMPLE_COUNT windows spread evenly over the data (Harnik et al.: spread samples give the ratio of the whole data).
    # A sample is two LZ10 windows long, so most of its matches find their source inside the sample.
    step = len(array) // SAMPLE_COUNT
    samples = []

    for i in range(SAMPLE_COUNT):
        start = i * step
        samples.append(array[start:start + SAMPLE_LENGTH])

    return samples

def get_lz_size(array, method, stop_below = None):
    size = len(array)

    if size <= SAMPLE_SIZE:
        if method == LZ10:
            return get_lz10_size(array, stop_below)
        else:
            return get_zlib_size(array)

    # Big data: the estimate runs on each sample alone (a sample does not see the bytes before it, as if the data was
    # cut there), then the total is scaled to the whole data
    sample_size = 0
    compressed_size = 0

    for sample in get_samples(array):
        sample_size += len(sample)

        if method == LZ10:
            compressed_size += get_lz10_size(sample) - 4
        else:
            compressed_size += get_zlib_size(sample) - 4

    return 4 + compressed_size * size // sample_size

##########################################
# Best Compression Function
##########################################

def get_compressed_sizes(data, methods):
    """Give the size of data for every method of methods, exact or estimated (LZ10 and zlib)."""
    array = np.frombuffer(bytes(data), dtype=np.uint8)
    sizes = {}

    for method in methods:
        if method == NO_COMPRESSION:
            sizes[method] = get_stored_size(array)
        elif method == HUFFMAN_4:
            sizes[method] = get_huffman_size(array, 4)
        elif method == HUFFMAN_8:
            sizes[method] = get_huffman_size(array, 8)
        elif method == RLE:
            sizes[method] = get_rle_size(array)
        elif method in (LZ10, ZLIB):
            sizes[method] = get_lz_size(array, method)
        else:
            raise Exception(f"Unknown compression method: {method}")

    return sizes

def get_smallest(sizes, methods):
    # The first method of the list wins a tie
    best_method = None

    for method in methods:
        if method in sizes:
            if best_method is None or sizes[method] < sizes[best_method]:
                best_method = method

    return best_method

def find_best_compression(data, methods = LEVEL5_COMPRESSIONS):
    """Give the compression method of methods that makes data the smallest, without compressing it."""
    if len(methods) == 0:
        raise Exception("No compression method to choose from")

    if len(methods) == 1:
        return methods[0]

    # Nothing to compress
    if len(data) == 0:
        if NO_COMPRESSION in methods:
            return NO_COMPRESSION

        return methods[0]

    array = np.frombuffer(bytes(data), dtype=np.uint8)

    # 1. The exact sizes (stored, Huffman, RLE), a few numpy passes each
    exact_methods = [method for method in methods if method not in (LZ10, ZLIB)]
    sizes = get_compressed_sizes(array, exact_methods)

    if ZLIB in methods:
        sizes[ZLIB] = get_lz_size(array, ZLIB)

    # 2. The LZ10 estimate, it stops early once it is smaller than every other size
    if LZ10 in methods:
        best_other = get_smallest(sizes, methods)
        stop_below = None

        if best_other is not None:
            stop_below = sizes[best_other]

        sizes[LZ10] = get_lz_size(array, LZ10, stop_below)

    return get_smallest(sizes, methods)
