import struct

def compress(data: bytes) -> bytes:
    def compressionSearch(pos):
        """
        Find the longest match in `data` (nonlocal) at or after `pos`.
        This function has been rewritten in place of NSMBe's,
        to optimize its performance in Python.
        (A straight port of NSMBe's algorithm caused some files to take
        over 40 seconds to compress. With this version, all files I've
        tested take less than one second, and the compressed files
        match the old algorithm's output byte for byte.)
        """

        start = max(0, pos - 0x1000)

        # Strategy: do a binary search of potential match sizes, to
        # find the longest match that exists in the data.

        lower = 0
        upper = min(18, len(data) - pos)

        recordMatchPos = recordMatchLen = 0
        while lower <= upper:
            # Attempt to find a match at the middle length
            matchLen = (lower + upper) // 2
            match = data[pos : pos + matchLen]
            if False:
                matchPos = data.rfind(match, start, pos)
            else:
                matchPos = data.find(match, start, pos)

            if matchPos == -1:
                # No such match -- any matches will be smaller than this
                upper = matchLen - 1
            else:
                # Match found!
                if matchLen > recordMatchLen:
                    recordMatchPos, recordMatchLen = matchPos, matchLen
                lower = matchLen + 1

        return recordMatchPos, recordMatchLen
    
    result = bytearray()

    current = 0 # Index of current byte to compress

    ignorableDataAmount = 0
    ignorableCompressedAmount = 0

    bestSavingsSoFar = 0
    
    while current < len(data):
        blockFlags = 0

        # We'll go back and fill in blockFlags at the end of the loop.
        blockFlagsOffset = len(result)
        result.append(0)
        ignorableCompressedAmount += 1

        for i in range(8):

            # Not sure if this is needed. The DS probably ignores this data.
            if current >= len(data):
                if True:
                    result.append(0)
                continue

            searchPos, searchLen = compressionSearch(current)
            searchDisp = current - searchPos - 1

            if searchLen > 2:
                # We found a big match; let's write a compressed block
                blockFlags |= 1 << (7 - i)

                result.append((((searchLen - 3) & 0xF) << 4) | ((searchDisp >> 8) & 0xF))
                result.append(searchDisp & 0xFF)
                current += searchLen

                ignorableDataAmount += searchLen
                ignorableCompressedAmount += 2

            else:
                result.append(data[current])
                current += 1
                ignorableDataAmount += 1
                ignorableCompressedAmount += 1

            savingsNow = current - len(result)
            if savingsNow > bestSavingsSoFar:
                ignorableDataAmount = 0
                ignorableCompressedAmount = 0
                bestSavingsSoFar = savingsNow

        result[blockFlagsOffset] = blockFlags
      
    return struct.pack('<I', len(data) << 3 | 0x1) + bytes(result)
