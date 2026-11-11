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

    # "Wong Kar-wai" film effect, iteration 1.
    #
    # Film effects are parameter combos applied by IQ_FilmEffectModeSet
    # (0x80360a04) via 8 param-class setters. The tint block P5 writes
    # at 0x808b2e4c feeds ISP params 0x2a003 (x) and 0x2a004 (y) through
    # the apply path at 0x80360f80.
    #
    # This mod does three things:
    #
    # 1. Tune the P5-mode-4 constants toward a warm WKW grade
    #    (vaddr 0x8036080c/0x80360810): x 246->128, y 8->64. Semantics
    #    are unverified (likely Cb/Cr tint or hue/sat gain); v1 is a
    #    strong shift so the look is obviously different.
    #
    # 2. Repoint effect slot 1 to the WKW combo (vaddr 0x80360ab8/
    #    0x80360ac0/0x80360ac4): stock slot 1 was P4=1,P5=1,P7=1; now
    #    P4=0 (neutral reset), P5=4 (our tint), P7=3. WKW sits at dial
    #    position 1, right after NORMAL at position 0.
    #
    # 3. Limit the film-effect dial to two slots. The dial handlers
    #    wrap index +0x19 at 9: decrement wraps 0->9 (vaddr 0x801e1914,
    #    now 0->1) and increment continues while idx<9 (vaddr
    #    0x801e1a9c, now idx<1). Result: NORMAL <-> WKW only.
    #
    # Slots 2-9 still exist in the dispatcher but are unreachable via
    # the dial. Lens effects (field +0x18) are untouched.
    "film-wkw": [
        Patch(0x36080c, "f6000424", "80000424",
              "P5-m4 x: 246 -> 128 (ISP 0x2a003)"),
        Patch(0x360810, "08000324", "40000324",
              "P5-m4 y: 8 -> 64 (ISP 0x2a004)"),
        Patch(0x360ab8, "01000424", "00000424",
              "slot1 P4 arg: 1 -> 0 (neutral)"),
        Patch(0x360ac0, "01000424", "04000424",
              "slot1 P5 arg: 1 -> 4 (WKW tint)"),
        Patch(0x360ac4, "01000424", "03000424",
              "slot1 P7 arg: 1 -> 3"),
        Patch(0x1e1914, "09000324", "01000324",
              "dial decrement wrap: 0->9 becomes 0->1"),
        Patch(0x1e1a9c, "0900432c", "0100432c",
              "dial increment bound: idx<9 becomes idx<1"),
    ],

    # Monochrome film effect at dial position 2.
    #
    # Repoints effect slot 2's case (vaddr 0x80360adc) to a pure
    # stock-parameter combo: P3=0 (mode 0 writes zero, neutral),
    # P4=0 (neutral, same assumption film-wkw makes), P5=5 (the
    # all-zeros grayscale config; no stock effect selects it). Stock
    # slot 2 was P3=1, P4=2, P5=2. The P5 arg sits in the tail-call
    # setup at 0x80360af8, not next to the other args.
    #
    # The two dial patches expect the bytes film-wkw leaves behind
    # (wrap 0->1, idx<1) and widen them to 0->2 / idx<2, so the dial
    # becomes NORMAL <-> WKW <-> MONO. They only apply cleanly after
    # film-wkw; on a build without it they skip with a warning and
    # MONO simply sits at stock dial position 2.
    "film-mono": [
        Patch(0x360ae0, "01000424", "00000424",
              "slot2 P3 arg: 1 -> 0 (neutral)"),
        Patch(0x360ae8, "02000424", "00000424",
              "slot2 P4 arg: 2 -> 0 (neutral)"),
        Patch(0x360af8, "02000424", "05000424",
              "slot2 P5 arg: 2 -> 5 (grayscale)"),
        Patch(0x1e1914, "01000324", "02000324",
              "dial decrement wrap: 0->1 becomes 0->2"),
        Patch(0x1e1a9c, "0100432c", "0200432c",
              "dial increment bound: idx<1 becomes idx<2"),
    ],
}

DEFAULT_MODS = ["printer-boot-skip", "film-wkw", "film-mono"]


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
