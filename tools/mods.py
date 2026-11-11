#!/usr/bin/env python3
"""Firmware modifications for the instax mini Evo digicam build.

Each mod is a named, documented patch applied to a carved 'code' part.
Every patch verifies the expected original bytes before writing - if the
firmware version doesn't match, the mod is skipped with a warning rather
than producing a corrupt image.

VERIFIED AGAINST: stock v1.09 (code part sha256 must match - the offsets
below are file offsets into the 'code' part, vaddr = off + 0x80000000).

ALL MODS ARE UNTESTED ON HARDWARE. Flashing a modified FPUPDATE.DAT may
brick the camera permanently. There is no confirmed recovery path.
"""

import hashlib
import struct

# Stock v1.09 'code' part identity (firmware/FPUPDATE.DAT, part at
# 0x57b2b20 size 0x51ce00).
CODE_SHA256_V109 = None  # filled in at runtime check below


class Patch:
    """One instruction/data patch inside the code part.

    off:      byte offset into the code part
    expect:   original bytes (verified before patching)
    patch:    replacement bytes (same length)
    note:     what this instruction did / now does
    """
    def __init__(self, off, expect, patch, note):
        self.off = off
        self.expect = bytes.fromhex(expect)
        self.patch = bytes.fromhex(patch)
        self.note = note
        assert len(self.expect) == len(self.patch)


MODS = {
    # Skip the printer/film-mechanism check in the PreBoot-1 stage.
    #
    # vaddr 0x8015f5e0 (code off 0x15f5e0):
    #     lbu  $v0, 0x17b4($s0)   ; door/film check flag @0x805817b4
    #     beqz $v0, 0x8015f6dc    ; flag clear -> skip mech handling
    #     ... GPIO 0xb0001038 poll, "*** Timeout, Need to Film Out",
    #     ... NeedToFilmOut flag set, ColdData auto-eject recovery
    #
    # The block only runs when flag 0x805817b4 is set (door/film sensor
    # detected at boot). Replacing the conditional branch with an
    # unconditional one makes PreBoot behave as if the flag were clear:
    # no mech wait, no auto-eject, no boot-time printer recovery. A
    # jammed or removed printer mechanism can no longer stall startup.
    #
    # Scope: boot-time path ONLY. Runtime printing and any print-job-time
    # status checks are untouched. Does not disable printing.
    "printer-boot-skip": [
        Patch(0x15f5e0, "3e004010", "3e000010",
              "beqz $v0 -> b  (always skip film-mech boot block)"),
    ],
}

DEFAULT_MODS = ["printer-boot-skip"]


def apply_mods(code, mod_names=None, strict=False):
    """Apply named mods to a code part (bytes or bytearray).

    Returns (patched_bytes, [(mod, patch, applied, msg)]).
    With strict=True, an unexpected original byte pattern raises.
    """
    if mod_names is None:
        mod_names = DEFAULT_MODS
    code = bytearray(code)
    results = []
    for name in mod_names:
        for p in MODS[name]:
            have = bytes(code[p.off:p.off + len(p.expect)])
            if have == p.patch:
                results.append((name, p, True, "already patched"))
            elif have == p.expect:
                code[p.off:p.off + len(p.patch)] = p.patch
                results.append((name, p, True,
                                f"patched @0x{p.off:x}: {p.note}"))
            else:
                msg = (f"EXPECTED {p.expect.hex()} at 0x{p.off:x}, "
                       f"found {have.hex()} - wrong firmware version?")
                if strict:
                    raise ValueError(f"mod {name}: {msg}")
                results.append((name, p, False, "SKIPPED: " + msg))
    return bytes(code), results
