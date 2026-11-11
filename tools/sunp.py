#!/usr/bin/env python3
"""Shared zero-dependency parser for the instax mini Evo FPUPDATE.DAT
(Sunplus "SUNP BURN FILE" format family).

Physical layout verified on stock v1.09 (97328468 bytes):

    0x000000  file header   "SUNP BURN FILE" + offset table (0x200 bytes,
                            then sysboot/preloader MIPS code up to hdr1)
    off_hdr1  burn header 1 "SUNP BURN HDR 1" (mostly-zero descriptor block)
    off_hdr2  burn header 2 "SUNP BURN HDR 2" (count + count*128B entries,
                            XOR-obfuscated with 0x7A)
    A image   FAT16 "ICATCH" filesystem (72 MB on v1.09) - RO resources,
                            fonts, UI assets, calibration
    B image   FAT16 "ICATCH" filesystem (15 MB on v1.09) - user resources
                            incl. PRINTER.BIN (research notes said FAT12;
                            the v1.09 BPB says FAT16)
    off_code  main firmware - MIPS32/ThreadX code
    off_hdr3  burn header 3 "SUNP BURN HDR 3" (count + count*0x70 filenames
                            backed up during update)
    file_size field marks the start of a ~0x500 byte trailing block of
    high-entropy data (signature/checksum; contents unknown, kept verbatim).

All multi-byte fields are little-endian.
"""

import struct

MAG_FILE = b"SUNP BURN FILE"
MAG_HDR1 = b"SUNP BURN HDR 1"
MAG_HDR2 = b"SUNP BURN HDR 2"
MAG_HDR3 = b"SUNP BURN HDR 3"

HDR2_ENTRY = 128   # bytes per obfuscated HDR2 entry
HDR3_ENTRY = 0x70  # bytes per backup filename entry
HDR_PREAMBLE = 32  # magic(16) + count/field(4) + pad(12)


class SunpError(Exception):
    pass


def u32(data, off):
    return struct.unpack_from("<I", data, off)[0]


def u16(data, off):
    return struct.unpack_from("<H", data, off)[0]


def parse_header(data):
    """Parse the top-level SUNP BURN FILE header. Returns a dict."""
    if data[:14] != MAG_FILE:
        raise SunpError("missing 'SUNP BURN FILE' magic at offset 0")
    h = {
        "file_size": u32(data, 0x10),
        "off_hdr1": u32(data, 0x14),
        "off_hdr2": u32(data, 0x18),
        "off_code": u32(data, 0x1C),
        "unk_zero": u32(data, 0x20),
        "off_hdr3": u32(data, 0x24),
        "trailer": u32(data, 0x1FC),  # nonzero; checksum per V50 prior art
    }
    for name in ("off_hdr1", "off_hdr2", "off_code", "off_hdr3"):
        if not (0 < h[name] < len(data)):
            raise SunpError(f"header field {name}=0x{h[name]:x} out of range")
    for name, mag in (("off_hdr1", MAG_HDR1), ("off_hdr2", MAG_HDR2),
                      ("off_hdr3", MAG_HDR3)):
        if data[h[name]:h[name] + 15] != mag:
            raise SunpError(f"bad magic at {name} (0x{h[name]:x})")
    return h


def fat_size(data, off):
    """Size of a FAT12/16 image from its BPB. Returns total bytes."""
    if data[off] not in (0xE8, 0xE9, 0xEB):
        raise SunpError(f"no FAT jump instruction at 0x{off:x}")
    bps = u16(data, off + 11)
    if bps == 0:
        raise SunpError(f"bad BPB at 0x{off:x}: bytes/sector is 0")
    total = u16(data, off + 19) or u32(data, off + 32)
    return total * bps


def bpb_info(data, off):
    """Human-readable BPB summary for a FAT image at `off`."""
    return {
        "oem": data[off + 3:off + 11].decode("ascii", "replace").strip(),
        "bytes_per_sector": u16(data, off + 11),
        "sectors_per_cluster": data[off + 13],
        "fats": data[off + 16],
        "root_entries": u16(data, off + 17),
        "total_sectors": u16(data, off + 19) or u32(data, off + 32),
        "fat_type": data[off + 54:off + 62].decode("ascii", "replace").strip(),
    }


def parts(data):
    """Split the file into named contiguous parts.

    Returns a list of (name, offset, size) covering the whole file.
    Order is significant: repack concatenates in this order.
    """
    h = parse_header(data)
    n = len(data)

    hdr2_entries = u32(data, h["off_hdr2"] + 16)
    a_start = h["off_hdr2"] + HDR_PREAMBLE + hdr2_entries * HDR2_ENTRY
    a_size = fat_size(data, a_start)
    b_start = a_start + a_size
    b_size = fat_size(data, b_start)
    if b_start + b_size != h["off_code"]:
        raise SunpError(
            f"B image ends at 0x{b_start + b_size:x}, code starts at "
            f"0x{h['off_code']:x} - layout not understood")

    return [
        ("head", 0, h["off_hdr1"]),               # file header + sysboot
        ("hdr1", h["off_hdr1"], h["off_hdr2"] - h["off_hdr1"]),
        ("hdr2", h["off_hdr2"], a_start - h["off_hdr2"]),
        ("A.img", a_start, a_size),               # FAT16 resources
        ("B.img", b_start, b_size),               # FAT16 user data
        ("code", h["off_code"], h["off_hdr3"] - h["off_code"]),
        ("tail", h["off_hdr3"], n - h["off_hdr3"]),  # hdr3 + sig trailer
    ]


def build(part_blobs, manifest_order=None):
    """Concatenate part blobs, then rewrite header offsets + file_size.

    part_blobs: list of (name, bytes) in file order (as produced by parts()).
    The last part ('tail') keeps its internal structure; the signature
    trailer inside it is preserved verbatim and will be STALE after any
    modification. On the sibling iCatch V50 the updater did not enforce
    checksumming; whether the mini Evo enforces this trailer is UNKNOWN.
    """
    out = bytearray()
    offsets = {}
    for name, blob in part_blobs:
        offsets[name] = len(out)
        out += blob

    hdr = bytearray(out[:0x200])
    struct.pack_into("<I", hdr, 0x14, offsets["hdr1"])
    struct.pack_into("<I", hdr, 0x18, offsets["hdr2"])
    struct.pack_into("<I", hdr, 0x1C, offsets["code"])
    struct.pack_into("<I", hdr, 0x24, offsets["tail"])
    # file_size points at the signature trailer inside 'tail'. Locate it by
    # re-parsing hdr3 in the tail blob (preamble + count*0x70, 0x20-aligned).
    tail = dict(part_blobs)["tail"]
    count = struct.unpack_from("<I", tail, 16)[0]
    sig_rel = HDR_PREAMBLE + count * HDR3_ENTRY
    struct.pack_into("<I", hdr, 0x10, offsets["tail"] + sig_rel)
    out[:0x200] = hdr
    return bytes(out)
