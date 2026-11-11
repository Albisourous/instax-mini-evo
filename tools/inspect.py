#!/usr/bin/env python3
"""Inspect a Fujifilm instax mini Evo FPUPDATE.DAT (Sunplus SUNP BURN FILE).

Zero-dependency. Reports the top-level header fields and every embedded
SUNP structure it can find.

Usage:
    python3 tools/inspect.py firmware/FPUPDATE.DAT
"""

import struct
import sys

MAG_FILE = b"SUNP BURN FILE"
MAG_HDR = b"SUNP BURN HDR"


def u32(data, off):
    return struct.unpack_from("<I", data, off)[0]


def scan(data, needle):
    out = []
    off = 0
    while True:
        i = data.find(needle, off)
        if i < 0:
            return out
        out.append(i)
        off = i + 1


def hdr_kind(data, off):
    # "SUNP BURN HDR " then a single digit
    try:
        return int(data[off + 14 : off + 15])
    except ValueError:
        return "?"


def main(path):
    data = open(path, "rb").read()
    print(f"file: {path}")
    print(f"size: {len(data)} bytes (0x{len(data):x})\n")

    if data[:14] != MAG_FILE:
        print("ERROR: missing 'SUNP BURN FILE' magic at offset 0")
        sys.exit(1)

    file_size = u32(data, 0x10)
    off_hdr1 = u32(data, 0x14)
    off_hdr2 = u32(data, 0x18)
    off_code = u32(data, 0x1C)
    unk_zero = u32(data, 0x20)
    off_hdr3 = u32(data, 0x24)

    print("top-level header:")
    print(f"  file_size   = 0x{file_size:08x} (actual file is 0x{len(data):x})")
    print(f"  off_hdr1    = 0x{off_hdr1:08x}")
    print(f"  off_hdr2    = 0x{off_hdr2:08x}")
    print(f"  off_code    = 0x{off_code:08x}")
    print(f"  unk_zero    = 0x{unk_zero:08x}")
    print(f"  off_hdr3    = 0x{off_hdr3:08x}")
    if off_code and off_hdr3 and off_hdr3 > off_code:
        print(f"  code len    = 0x{off_hdr3 - off_code:x}")

    print("\nembedded 'SUNP BURN FILE' magics (nested burn images?):")
    for off in scan(data, MAG_FILE):
        print(f"  0x{off:08x}")

    print("\nembedded 'SUNP BURN HDR' entries:")
    for off in scan(data, MAG_HDR):
        kind = hdr_kind(data, off)
        count = u32(data, off + 16) if off + 20 <= len(data) else 0
        print(f"  0x{off:08x}  HDR {kind}  count/field = {count}")

    # burnhdr2 mystery strings (XOR 0x7A obfuscated, 128-byte entries)
    if off_hdr2 and data[off_hdr2 : off_hdr2 + len(MAG_HDR)] == MAG_HDR:
        count = u32(data, off_hdr2 + 16)
        print(f"\nburnhdr2 entries ({count}, XOR 0x7A decoded, first 5):")
        base = off_hdr2 + 32
        for i in range(min(count, 5)):
            entry = bytes(b ^ 0x7A for b in data[base + i * 128 : base + (i + 1) * 128])
            printable = entry.split(b"\x00")[0]
            print(f"  [{i}] {printable!r}")

    # burnhdr3 filename list
    if off_hdr3 and data[off_hdr3 : off_hdr3 + len(MAG_HDR)] == MAG_HDR:
        count = u32(data, off_hdr3 + 16)
        print(f"\nburnhdr3 filenames ({count}, backup list, first 20):")
        base = off_hdr3 + 32
        for i in range(min(count, 20)):
            name = data[base + i * 0x70 : base + i * 0x70 + 0x70].split(b"\x00")[0]
            print(f"  {name.decode('ascii', 'replace')}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1])
