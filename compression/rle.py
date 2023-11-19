def decompress(instream):
    inLength = len(instream)
    ReadBytes = 0
    p = 0

    p += 1

    decompressed_size = (instream[p] & 0xFF) | ((instream[p + 1] & 0xFF) << 8) | ((instream[p + 2] & 0xFF) << 16)
    p += 3
    ReadBytes += 4;

    if decompressed_size == 0:
        decompressed_size = decompressed_size | ((instream[p + 3] & 0xFF) << 24)
        ReadBytes += 4

    outstream = bytearray()

    while p < inLength:

        flag = instream[p]
        p += 1
        ReadBytes += 1

        compressed = (flag & 0x80) > 0
        length = flag & 0x7F
        
        if compressed:
            length += 3
        else:
            length += 1
            
        if compressed:
            data = instream[p]
            p += 1
            ReadBytes += 1
            
            for i in range(length):
                outstream.append(data)
        else:
            tryReadLength = length
            if ReadBytes + length > inLength:
                tryReadLength = int(inLength - ReadBytes)
                
            ReadBytes += tryReadLength
            
            for i in range(tryReadLength):
                outstream.append(instream[p] & 0xFF)
                p += 1

    if ReadBytes < inLength:
        pass

    return bytes(outstream)

# Example usage:
# result = decompress(byte_array_input)
