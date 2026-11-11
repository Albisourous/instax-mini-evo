#!/usr/bin/env python3
"""Pure-Python Snappy *raw* format codec (no external deps).

The iCatch SFN/SST resource files store a Snappy raw stream after a 4-byte
"SNAP" marker: decompress(data[4:]) / "SNAP" + compress(data).

compress() emits a literal-only stream. That is still valid Snappy - the
format permits uncompressed literals - just larger than optimal. Files in
the A:/B: images grow when recompressed; the FAT layer handles growth.
"""

LITERAL_CHUNK = 0x10000  # emit literals in <=64KB chunks


def decompress(data):
    """Decompress a Snappy raw stream (varint preamble + elements)."""
    pos = 0
    shift = 0
    length = 0
    while True:  # varint: uncompressed length
        b = data[pos]
        pos += 1
        length |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7

    out = bytearray()
    while pos < len(data):
        tag = data[pos]
        pos += 1
        kind = tag & 3
        if kind == 0:  # literal
            n = tag >> 2
            if n < 60:
                n += 1
            else:
                nbytes = n - 59
                n = int.from_bytes(data[pos:pos + nbytes], "little") + 1
                pos += nbytes
            out += data[pos:pos + n]
            pos += n
        else:
            if kind == 1:
                n = ((tag >> 2) & 0x7) + 4
                off = ((tag >> 5) << 8) | data[pos]
                pos += 1
            elif kind == 2:
                n = (tag >> 2) + 1
                off = int.from_bytes(data[pos:pos + 2], "little")
                pos += 2
            else:
                n = (tag >> 2) + 1
                off = int.from_bytes(data[pos:pos + 4], "little")
                pos += 4
            if off == 0 or off > len(out):
                raise ValueError("snappy: bad copy offset")
            for _ in range(n):
                out.append(out[-off])
    if len(out) != length:
        raise ValueError(
            f"snappy: got {len(out)} bytes, expected {length}")
    return bytes(out)


def _emit_literal(out, blob):
    n = len(blob)
    if n - 1 < 60:
        out.append((n - 1) << 2)
    else:
        k = (n - 1).bit_length() // 8 + 1
        out.append((59 + k) << 2)
        out += (n - 1).to_bytes(k, "little")
    out += blob


def compress(data):
    """Compress to a Snappy raw stream (literal-only, still valid)."""
    out = bytearray()
    n = len(data)  # varint preamble
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            break
    for i in range(0, len(data), LITERAL_CHUNK):
        _emit_literal(out, data[i:i + LITERAL_CHUNK])
    return bytes(out)
