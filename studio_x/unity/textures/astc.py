"""Pure Python ASTC LDR decoder.

Port of astc.cpp from texture2ddecoder (https://github.com/K0lb3/texture2ddecoder),
itself based on Ishotihadus' mikunyan decoder. Trit/quint tables are generated from the
ARM ASTC specification instead of being hardcoded. HDR endpoint modes are not supported
(Unity's ASTC_HDR formats are rarely used) and decode as magenta like void-extent errors.
"""

WEIGHT_PREC_A = (0, 0, 0, 3, 0, 5, 3, 0, 0, 0, 5, 3, 0, 5, 3, 0)
WEIGHT_PREC_B = (0, 0, 1, 0, 2, 0, 1, 3, 0, 0, 1, 2, 4, 2, 3, 5)
CEM_A = (0, 3, 5, 0, 3, 5, 0, 3, 5, 0, 3, 5, 0, 3, 5, 0, 3, 0, 0)
CEM_B = (8, 6, 5, 7, 5, 4, 6, 4, 3, 5, 3, 2, 4, 2, 1, 3, 1, 2, 1)
TRIT_C = (0, 204, 93, 44, 22, 11, 5)
QUINT_C = (0, 113, 54, 26, 13, 6)
HDR_MODES = {2, 3, 7, 11, 14, 15}
MAGENTA = (255, 0, 255, 255)


def _bit(value, index):
    return (value >> index) & 1


def _build_trits():
    table = []
    for t in range(256):
        if (t >> 2) & 7 == 7:
            c = ((t >> 5) & 7) << 2 | (t & 3)
            t4 = t3 = 2
        else:
            c = t & 0x1F
            if (t >> 5) & 3 == 3:
                t4 = 2
                t3 = _bit(t, 7)
            else:
                t4 = _bit(t, 7)
                t3 = (t >> 5) & 3
        if c & 3 == 3:
            t2 = 2
            t1 = _bit(c, 4)
            t0 = _bit(c, 3) << 1 | (_bit(c, 2) & (1 - _bit(c, 3)))
        elif (c >> 2) & 3 == 3:
            t2 = t1 = 2
            t0 = c & 3
        else:
            t2 = _bit(c, 4)
            t1 = (c >> 2) & 3
            t0 = _bit(c, 1) << 1 | (_bit(c, 0) & (1 - _bit(c, 1)))
        table.append((t0, t1, t2, t3, t4))
    return table


def _build_quints():
    table = []
    for q in range(128):
        if (q >> 1) & 3 == 3 and (q >> 5) & 3 == 0:
            q2 = _bit(q, 0) << 2 | (_bit(q, 4) & (1 - _bit(q, 0))) << 1 | (_bit(q, 3) & (1 - _bit(q, 0)))
            q1 = q0 = 4
        else:
            if (q >> 1) & 3 == 3:
                q2 = 4
                c = ((q >> 3) & 3) << 3 | ((~(q >> 5)) & 3) << 1 | _bit(q, 0)
            else:
                q2 = (q >> 5) & 3
                c = q & 0x1F
            if c & 7 == 5:
                q1 = 4
                q0 = (c >> 3) & 3
            else:
                q1 = (c >> 3) & 3
                q0 = c & 7
        table.append((q0, q1, q2))
    return table


TRITS = _build_trits()
QUINTS = _build_quints()


def _decode_intseq(bits, offset, a, b, count):
    """Return a list of (bits, trit_or_quint) read forward from `bits` starting at `offset`."""
    out = []
    mask = (1 << b) - 1
    if a == 3:
        remaining = _sequence_bits(a, b, count)
        while len(out) < count:
            size = min(8 + 5 * b, remaining)
            # Bits past the end of the sequence must read as zero
            d = (bits >> offset) & ((1 << size) - 1)
            x = (d >> b & 3) | (d >> (b * 2) & 0xC) | (d >> (b * 3) & 0x10) | (d >> (b * 4) & 0x60) | (d >> (b * 5) & 0x80)
            trits = TRITS[x]
            for j in range(min(5, count - len(out))):
                out.append(((d >> ((0, 2, 4, 5, 7)[j] + b * j)) & mask, trits[j]))
            offset += size
            remaining -= size
    elif a == 5:
        remaining = _sequence_bits(a, b, count)
        while len(out) < count:
            size = min(7 + 3 * b, remaining)
            d = (bits >> offset) & ((1 << size) - 1)
            x = (d >> b & 7) | (d >> (b * 2) & 0x18) | (d >> (b * 3) & 0x60)
            quints = QUINTS[x]
            for j in range(min(3, count - len(out))):
                out.append(((d >> ((0, 3, 5)[j] + b * j)) & mask, quints[j]))
            offset += size
            remaining -= size
    else:
        for _ in range(count):
            out.append(((bits >> offset) & mask, 0))
            offset += b
    return out


def _sequence_bits(a, b, count):
    if a == 3:
        return count * b + (count * 8 + 4) // 5
    if a == 5:
        return count * b + (count * 7 + 2) // 3
    return count * b


def _reverse128(value):
    return int(format(value, "0128b")[::-1], 2)


def _clamp(value):
    return 0 if value < 0 else 255 if value > 255 else value


def _bit_transfer_signed(a, b):
    b = (b >> 1) | (a & 0x80)
    a = (a >> 1) & 0x3F
    if a & 0x20:
        a -= 0x40
    return a, b


def _blue_contract(r1, g1, b1, a1, r2, g2, b2, a2):
    return ((r1 + b1) >> 1, (g1 + b1) >> 1, b1, a1, (r2 + b2) >> 1, (g2 + b2) >> 1, b2, a2)


def _decode_endpoint(cem, v):
    if cem == 0:
        return (v[0], v[0], v[0], 255, v[1], v[1], v[1], 255)
    if cem == 1:
        l0 = (v[0] >> 2) | (v[1] & 0xC0)
        l1 = _clamp(l0 + (v[1] & 0x3F))
        return (l0, l0, l0, 255, l1, l1, l1, 255)
    if cem == 4:
        return (v[0], v[0], v[0], v[2], v[1], v[1], v[1], v[3])
    if cem == 5:
        v1, v0 = _bit_transfer_signed(v[1], v[0])
        v3, v2 = _bit_transfer_signed(v[3], v[2])
        v1 += v0
        return tuple(_clamp(x) for x in (v0, v0, v0, v2, v1, v1, v1, v2 + v3))
    if cem == 6:
        return (v[0] * v[3] >> 8, v[1] * v[3] >> 8, v[2] * v[3] >> 8, 255, v[0], v[1], v[2], 255)
    if cem == 8:
        if v[0] + v[2] + v[4] <= v[1] + v[3] + v[5]:
            return (v[0], v[2], v[4], 255, v[1], v[3], v[5], 255)
        return _blue_contract(v[1], v[3], v[5], 255, v[0], v[2], v[4], 255)
    if cem == 9:
        v1, v0 = _bit_transfer_signed(v[1], v[0])
        v3, v2 = _bit_transfer_signed(v[3], v[2])
        v5, v4 = _bit_transfer_signed(v[5], v[4])
        if v1 + v3 + v5 >= 0:
            return tuple(_clamp(x) for x in (v0, v2, v4, 255, v0 + v1, v2 + v3, v4 + v5, 255))
        return tuple(_clamp(x) for x in _blue_contract(v0 + v1, v2 + v3, v4 + v5, 255, v0, v2, v4, 255))
    if cem == 10:
        return (v[0] * v[3] >> 8, v[1] * v[3] >> 8, v[2] * v[3] >> 8, v[4], v[0], v[1], v[2], v[5])
    if cem == 12:
        if v[0] + v[2] + v[4] <= v[1] + v[3] + v[5]:
            return (v[0], v[2], v[4], v[6], v[1], v[3], v[5], v[7])
        return _blue_contract(v[1], v[3], v[5], v[7], v[0], v[2], v[4], v[6])
    if cem == 13:
        v1, v0 = _bit_transfer_signed(v[1], v[0])
        v3, v2 = _bit_transfer_signed(v[3], v[2])
        v5, v4 = _bit_transfer_signed(v[5], v[4])
        v7, v6 = _bit_transfer_signed(v[7], v[6])
        if v1 + v3 + v5 >= 0:
            return tuple(_clamp(x) for x in (v0, v2, v4, v6, v0 + v1, v2 + v3, v4 + v5, v6 + v7))
        return tuple(_clamp(x) for x in _blue_contract(v0 + v1, v2 + v3, v4 + v5, v6 + v7, v0, v2, v4, v6))
    return None


def _unquantize_endpoints(seq, a, b):
    values = []
    if a == 3:
        c = TRIT_C[b]
        for bits, trit in seq:
            mask = (bits & 1) * 0x1FF
            x = bits >> 1
            base = (0, 0, 0b100010110 * x, x << 7 | x << 2 | x, x << 6 | x, x << 5 | x >> 2, x << 4 | x >> 4)[b]
            values.append((mask & 0x80) | ((trit * c + base) ^ mask) >> 2)
    elif a == 5:
        c = QUINT_C[b]
        for bits, quint in seq:
            mask = (bits & 1) * 0x1FF
            x = bits >> 1
            base = (0, 0, 0b100001100 * x, x << 7 | x << 1 | x >> 1, x << 6 | x >> 1, x << 5 | x >> 3)[b]
            values.append((mask & 0x80) | ((quint * c + base) ^ mask) >> 2)
    else:
        for bits, _ in seq:
            if b == 1:
                values.append(bits * 0xFF)
            elif b == 2:
                values.append(bits * 0x55)
            elif b == 3:
                values.append(bits << 5 | bits << 2 | bits >> 1)
            elif b == 4:
                values.append(bits << 4 | bits)
            elif b == 5:
                values.append(bits << 3 | bits >> 2)
            elif b == 6:
                values.append(bits << 2 | bits >> 4)
            elif b == 7:
                values.append(bits << 1 | bits >> 6)
            else:
                values.append(bits)
    return values


def _unquantize_weights(seq, a, b):
    weights = []
    if a == 0:
        for bits, _ in seq:
            if b == 1:
                w = 63 if bits else 0
            elif b == 2:
                w = bits << 4 | bits << 2 | bits
            elif b == 3:
                w = bits << 3 | bits
            elif b == 4:
                w = bits << 2 | bits >> 2
            else:
                w = bits << 1 | bits >> 4
            weights.append(w + 1 if w > 32 else w)
        return weights
    if b == 0:
        scale = 32 if a == 3 else 16
        return [tq * scale for _, tq in seq]
    for bits, tq in seq:
        if a == 3:
            if b == 1:
                w = tq * 50
            elif b == 2:
                w = tq * 23 + (0b1000101 if bits & 2 else 0)
            else:
                w = tq * 11 + ((bits << 4 | bits >> 1) & 0b1100011)
        else:
            if b == 1:
                w = tq * 28
            else:
                w = tq * 13 + (0b1000010 if bits & 2 else 0)
        mask = (bits & 1) * 0x7F
        w = (mask & 0x20) | ((w ^ mask) >> 2)
        weights.append(w + 1 if w > 32 else w)
    return weights


_INFILL_CACHE = {}
_PARTITION_CACHE = {}


def _infill_table(bw, bh, width, height):
    key = (bw, bh, width, height)
    table = _INFILL_CACHE.get(key)
    if table is None:
        table = []
        ds = (1024 + bw // 2) // (bw - 1)
        dt = (1024 + bh // 2) // (bh - 1)
        for t in range(bh):
            for s in range(bw):
                gs = (ds * s * (width - 1) + 32) >> 6
                gt = (dt * t * (height - 1) + 32) >> 6
                fs = gs & 0xF
                ft = gt & 0xF
                v = (gs >> 4) + (gt >> 4) * width
                w11 = (fs * ft + 8) >> 4
                table.append((v, 16 - fs - ft + w11, fs - w11, ft - w11, w11))
        _INFILL_CACHE[key] = table
    return table


def _partition_table(seed, part_num, bw, bh):
    key = (seed, bw, bh)
    table = _PARTITION_CACHE.get(key)
    if table is not None:
        return table
    rnum = seed
    rnum ^= rnum >> 15
    rnum = (rnum - (rnum << 17)) & 0xFFFFFFFF
    rnum = (rnum + (rnum << 7)) & 0xFFFFFFFF
    rnum = (rnum + (rnum << 4)) & 0xFFFFFFFF
    rnum ^= rnum >> 5
    rnum = (rnum + (rnum << 16)) & 0xFFFFFFFF
    rnum ^= rnum >> 7
    rnum ^= rnum >> 3
    rnum = (rnum ^ (rnum << 6)) & 0xFFFFFFFF
    rnum ^= rnum >> 17

    seeds = [((rnum >> (i * 4)) & 0xF) ** 2 for i in range(8)]
    sh = (4 if seed & 2 else 5, 6 if part_num == 3 else 5)
    if seed & 1:
        seeds = [s >> sh[i % 2] for i, s in enumerate(seeds)]
    else:
        seeds = [s >> sh[1 - i % 2] for i, s in enumerate(seeds)]

    small = bw * bh < 31
    table = []
    for y in range(bh):
        for x in range(bw):
            px, py = (x << 1, y << 1) if small else (x, y)
            a = (seeds[0] * px + seeds[1] * py + (rnum >> 14)) & 0x3F
            b = (seeds[2] * px + seeds[3] * py + (rnum >> 10)) & 0x3F
            c = (seeds[4] * px + seeds[5] * py + (rnum >> 6)) & 0x3F if part_num >= 3 else 0
            d = (seeds[6] * px + seeds[7] * py + (rnum >> 2)) & 0x3F if part_num >= 4 else 0
            if a >= b and a >= c and a >= d:
                table.append(0)
            elif b >= c and b >= d:
                table.append(1)
            elif c >= d:
                table.append(2)
            else:
                table.append(3)
    _PARTITION_CACHE[key] = table
    return table


def _decode_block(block, bw, bh):
    """Return a flat list of RGBA byte values for one 16 byte block."""
    b0 = block[0]
    b1 = block[1]
    texels = bw * bh

    if b0 == 0xFC and b1 & 1:
        if b1 & 2:
            return list(MAGENTA) * texels  # HDR void extent
        return [block[9], block[11], block[13], block[15]] * texels
    if ((b0 & 0xC3) == 0xC0 and b1 & 1) or (b0 & 0xF) == 0:
        return list(MAGENTA) * texels

    bits = int.from_bytes(block, "little")
    dual_plane = bool(b1 & 4)
    weight_range = (b0 >> 4 & 1) | (b1 << 2 & 8)
    head16 = b0 | b1 << 8

    if b0 & 3:
        weight_range |= b0 << 1 & 6
        mode = b0 & 0xC
        if mode == 0:
            width, height = (head16 >> 7 & 3) + 4, (b0 >> 5 & 3) + 2
        elif mode == 4:
            width, height = (head16 >> 7 & 3) + 8, (b0 >> 5 & 3) + 2
        elif mode == 8:
            width, height = (b0 >> 5 & 3) + 2, (head16 >> 7 & 3) + 8
        elif b1 & 1:
            width, height = (b0 >> 7 & 1) + 2, (b0 >> 5 & 3) + 2
        else:
            width, height = (b0 >> 5 & 3) + 2, (b0 >> 7 & 1) + 6
    else:
        weight_range |= b0 >> 1 & 6
        mode = head16 & 0x180
        if mode == 0:
            width, height = 12, (b0 >> 5 & 3) + 2
        elif mode == 0x80:
            width, height = (b0 >> 5 & 3) + 2, 12
        elif mode == 0x100:
            width, height = (b0 >> 5 & 3) + 6, (b1 >> 1 & 3) + 6
            dual_plane = False
            weight_range &= 7
        else:
            width, height = (10, 6) if b0 & 0x20 else (6, 10)

    if width > bw or height > bh:
        return list(MAGENTA) * texels

    part_num = (b1 >> 3 & 3) + 1
    weight_num = width * height * (2 if dual_plane else 1)
    wa = WEIGHT_PREC_A[weight_range]
    wb = WEIGHT_PREC_B[weight_range]
    weight_bits = _sequence_bits(wa, wb, weight_num)
    # Blocks outside the spec limits are error blocks
    if weight_num > 64 or not 24 <= weight_bits <= 96:
        return list(MAGENTA) * texels

    cems = [0] * part_num
    cem_base = 0
    if part_num == 1:
        cems[0] = (bits >> 13) & 0xF
        config_bits = 17
    else:
        cem_base = (bits >> 23) & 3
        if cem_base == 0:
            cem = (bits >> 25) & 0xF
            cems = [cem] * part_num
            config_bits = 29
        else:
            b3 = block[3]
            cems = [((b3 >> (i + 1) & 1) + cem_base - 1) << 2 for i in range(part_num)]
            if part_num == 2:
                cems[0] |= b3 >> 3 & 3
                cems[1] |= (bits >> (126 - weight_bits)) & 3
            elif part_num == 3:
                cems[0] |= b3 >> 4 & 1
                cems[0] |= (bits >> (122 - weight_bits)) & 2
                cems[1] |= (bits >> (124 - weight_bits)) & 3
                cems[2] |= (bits >> (126 - weight_bits)) & 3
            else:
                for i in range(4):
                    cems[i] |= (bits >> (120 + i * 2 - weight_bits)) & 3
            config_bits = 25 + part_num * 3

    if any(cem in HDR_MODES for cem in cems):
        return list(MAGENTA) * texels

    plane_selector = 0
    if dual_plane:
        config_bits += 2
        plane_selector = (bits >> (130 - weight_bits - part_num * 3 if cem_base else 126 - weight_bits)) & 3

    remain_bits = 128 - config_bits - weight_bits
    endpoint_value_num = sum((cem >> 1 & 6) + 2 for cem in cems)
    cem_range = None
    for i in range(len(CEM_A)):
        if _sequence_bits(CEM_A[i], CEM_B[i], endpoint_value_num) <= remain_bits:
            cem_range = i
            break
    if cem_range is None or endpoint_value_num > 18:
        return list(MAGENTA) * texels

    # Endpoints
    seq = _decode_intseq(bits, 17 if part_num == 1 else 29, CEM_A[cem_range], CEM_B[cem_range], endpoint_value_num)
    values = _unquantize_endpoints(seq, CEM_A[cem_range], CEM_B[cem_range])
    endpoints = []
    position = 0
    for cem in cems:
        count = (cem // 4 + 1) * 2
        endpoint = _decode_endpoint(cem, values[position:position + count])
        if endpoint is None:
            return list(MAGENTA) * texels
        endpoints.append(endpoint)
        position += count

    # Weights are stored bit-reversed from the top of the block
    weight_seq = _decode_intseq(_reverse128(bits), 0, wa, wb, weight_num)
    weights = _unquantize_weights(weight_seq, wa, wb)
    planes = 2 if dual_plane else 1
    infill = _infill_table(bw, bh, width, height)
    grid_size = width * height
    # Pad so bilinear sampling on the last row/column stays in range
    weights += [0] * ((grid_size + width + 1) * planes - len(weights))

    partition = _partition_table(((bits >> 13) & 0x3FF) | (part_num - 1) << 10, part_num, bw, bh) if part_num > 1 else None

    out = [0] * (texels * 4)
    for i in range(texels):
        v, w00, w01, w10, w11 = infill[i]
        ep = endpoints[partition[i]] if partition else endpoints[0]
        if planes == 1:
            w = (weights[v] * w00 + weights[v + 1] * w01 + weights[v + width] * w10 + weights[v + width + 1] * w11 + 8) >> 4
            plane_weights = (w, w, w, w)
        else:
            p0 = (weights[v * 2] * w00 + weights[(v + 1) * 2] * w01 + weights[(v + width) * 2] * w10
                  + weights[(v + width + 1) * 2] * w11 + 8) >> 4
            p1 = (weights[v * 2 + 1] * w00 + weights[(v + 1) * 2 + 1] * w01 + weights[(v + width) * 2 + 1] * w10
                  + weights[(v + width + 1) * 2 + 1] * w11 + 8) >> 4
            plane_weights = [p0, p0, p0, p0]
            plane_weights[plane_selector] = p1
        base = i * 4
        for channel in range(4):
            c0 = ep[channel]
            c1 = ep[channel + 4]
            w = plane_weights[channel]
            out[base + channel] = ((((c0 << 8 | c0) * (64 - w) + (c1 << 8 | c1) * w + 32) >> 6) * 255 + 32768) // 65536
    return out


def decode_astc(data, width, height, block_width, block_height):
    """Decode ASTC data to RGBA8 bytes, rows in stored order (Unity: bottom row first)."""
    blocks_x = (width + block_width - 1) // block_width
    blocks_y = (height + block_height - 1) // block_height
    image = bytearray(width * height * 4)
    view = memoryview(data)
    offset = 0
    cache = {}
    for by in range(blocks_y):
        for bx in range(blocks_x):
            block = bytes(view[offset:offset + 16])
            offset += 16
            texels = cache.get(block)
            if texels is None:
                texels = bytes(_decode_block(block, block_width, block_height))
                if len(cache) < 4096:
                    cache[block] = texels
            x0 = bx * block_width
            y0 = by * block_height
            copy_w = min(block_width, width - x0)
            for row in range(min(block_height, height - y0)):
                dst = ((y0 + row) * width + x0) * 4
                src = row * block_width * 4
                image[dst:dst + copy_w * 4] = texels[src:src + copy_w * 4]
    return bytes(image)
