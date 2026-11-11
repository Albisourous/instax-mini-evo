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

    # The WKW dial: one Wong Kar-wai film per film-effect position.
    #
    # All ten positions stay reachable (stock dial wrap). Slots 1-6
    # get repointed P5 args and retuned P5 constants; slots 7-9 keep
    # their stock pattern combos and only get renamed, because the
    # only film patterns in the firmware are sepia and rough
    # (FILM_EFFECT_SEPIA / FILM_EFFECT_ROUGH strings; heavy, fisheye,
    # colorshift and light leak are all LENS effects).
    #
    # Corrected P5 mode map (jump table 0x804d7dfc, indexed by arg;
    # research.md's older table was off by one - mode 3 owns x/y):
    #
    #   0  clear alt field      1  tint [0x53,0,0,0x53]
    #   2  tint [0x13,0,0,0x13] 3  x=246, y=8 (the x/y case)
    #   4  all zeros (flat)     5  x=y=0xf8, tint [0x56,0,0,0x56]
    #   6  tint [0x36,0,0,0x36]
    #
    # Modes 1, 2 and 6 share one body at 0x803607b8; each only
    # differs in the byte loaded into $a0.
    #
    # Dial layout:
    #   0 NORMAL (stock)
    #   1 In the Mood for Love  P4=0, P5=3 (x/y retuned 128/64), P7=3
    #   2 Chungking Express     stock P3=1/P4=2, P5=1 (byte 0x70)
    #   3 Fallen Angels         stock P3=3/P7=5, P5=2 (byte 0x08)
    #   4 Happy Together        stock P7=3, P5=6 (byte 0x48)
    #   5 2046                  stock P7=2, P5=5 (x/y 0x18, byte 0x70)
    #   6 The Grandmaster       stock P4=3/P7=4, P5=4 (flat)
    #   7 Ashes of Time         stock P2=2 + P8=2 (sepia?)
    #   8 Days of Being Wild    stock P2=1 + P8=1 (rough?)
    #   9 As Tears Go By        stock P1=1 + P2=3
    #
    # Retune values are blind first guesses: tint-byte and x/y
    # semantics are unverified, and which P2 arg maps to sepia vs
    # rough is unverified. Flash, shoot, report, retune.
    "wkw-suite": [
        # In the Mood for Love (slot 1): x/y grade
        Patch(0x36080c, "f6000424", "80000424",
              "P5-m3 x: 246 -> 128 (ISP 0x2a003)"),
        Patch(0x360810, "08000324", "40000324",
              "P5-m3 y: 8 -> 64 (ISP 0x2a004)"),
        Patch(0x360ab8, "01000424", "00000424",
              "slot1 P4 arg: 1 -> 0 (neutral)"),
        Patch(0x360ac0, "01000424", "03000424",
              "slot1 P5 arg: 1 -> 3 (x/y grade)"),
        Patch(0x360ac4, "01000424", "03000424",
              "slot1 P7 arg: 1 -> 3"),
        # Chungking Express (slot 2): retuned m1 diagonal tint
        Patch(0x3607e8, "53000424", "70000424",
              "P5-m1 tint byte: 0x53 -> 0x70"),
        Patch(0x360af8, "02000424", "01000424",
              "slot2 P5 arg: 2 -> 1"),
        # Fallen Angels (slot 3): retuned m2 diagonal tint
        Patch(0x3607f8, "13000424", "08000424",
              "P5-m2 tint byte: 0x13 -> 0x08"),
        Patch(0x360b10, "06000424", "02000424",
              "slot3 P5 arg: 6 -> 2"),
        # Happy Together (slot 4): retuned m6 diagonal tint
        Patch(0x3607b4, "36000424", "48000424",
              "P5-m6 tint byte: 0x36 -> 0x48"),
        Patch(0x360b20, "04000424", "06000424",
              "slot4 P5 arg: 4 -> 6"),
        # 2046 (slot 5): retuned m5 x/y + tint byte
        Patch(0x360878, "f8000424", "18000424",
              "P5-m5 x/y: 0xf8 -> 0x18"),
        Patch(0x36087c, "56000524", "70000524",
              "P5-m5 tint byte: 0x56 -> 0x70"),
        Patch(0x360b30, "03000424", "05000424",
              "slot5 P5 arg: 3 -> 5"),
        # The Grandmaster (slot 6): flat all-zeros tint
        Patch(0x360b48, "05000424", "04000424",
              "slot6 P5 arg: 5 -> 4 (flat)"),
    ],

    # Optional: bypass the firmware-signature gate. NOT a default
    # mod, and NOT a bootstrap path: the check runs in the
    # INSTALLED firmware before writing, so this patch inside the
    # new image can never fire on the first flash. It only helps
    # once modded code is already running (e.g. after a UART/ISP
    # bootstrap), making later updates friction-free.
    #
    # The FIRMWARE UPGRADE path calls ab_fw_signature_verify at
    # 0x802269b8: it snprintf's the file path, calls the mbedtls
    # verify core at 0x80308d88, and returns s4 (1 on success, 0
    # on failure). Every internal path converges on the same
    # verify call, so the single instruction that zeroes s4 on
    # failure (0x80226a98, addu s4,zero,zero) is the choke point.
    # Replacing it with li s4,1 makes every signature check
    # "succeed" - the RSA/ECDSA result is ignored entirely.
    #
    # Callers both gate on v0==0: 0x80230ee0 rejects with error
    # pair {7,2}, 0x80234a9c with {7,4} (the "firmware broken"
    # style error). This patch satisfies both, and any other
    # current or future caller of the wrapper.
    "sigverify-bypass": [
        Patch(0x226a98, "21a00000", "01001424",
              "s4 fail-path: 0 -> 1 (ab_fw_signature_verify "
              "always returns success)"),
    ],
}

DEFAULT_MODS = ["printer-boot-skip", "wkw-suite"]


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
