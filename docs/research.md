# instax mini Evo — reverse engineering notes

## Hardware / software facts

| Thing | Value | Evidence |
|---|---|---|
| Model | Fujifilm instax mini Evo (FI019, USB-C rev: FI038) | manual |
| SoC | **Sunplus iCatch CA5310A / CA5000A** | strings in FPUPDATE.DAT |
| CPU | **MIPS32 4Kx** (little-endian; tools use `mipsel-linux-gnu`) | ThreadX version string |
| OS | **Express Logic ThreadX** (G4.0c.4.0) | version string in image |
| Firmware file | `FPUPDATE.DAT`, v1.09, 0x5cd1d54 bytes | instax.com download |
| Update path | file on microSD root → `FIRMWARE UPGRADE` menu | manual |
| USB port | charge-only per spec; no data enumeration observed | spec + `ioreg` check |
| Bootloader | `$unp_0.7.14_sysboot` — serial shell w/ `dump/fill/search`, `read <file> <addr>`, `nanderase` | strings |

Firmware download URL (serves raw .DAT despite .html name):
`https://www.instax.com/mini_evo/en/support/firmware/firmware.html`

## FPUPDATE.DAT structure (v1.09) — fully mapped

Top-level header at 0x0 (little-endian u32s after 16-byte magic+pad):

```
0x10 file_size   0x05cd1850 — offset of the signature trailer, NOT the
                 whole file (trailer = 0x504 bytes of high-entropy data
                 at EOF; likely a signature/checksum, contents unknown)
0x14 off_hdr1    0x000b1a00   SUNP BURN HDR 1 — mostly zeros; field[3]=
                 0xffffffff, field[6]=0x04800000/0x00f00000 (matches the
                 A:/B: image sizes — probably a burn descriptor)
0x18 off_hdr2    0x000b2a00   SUNP BURN HDR 2 — 2 x 128B entries XOR 0x7A
                 ("060916:build<sign>a?", "060916:build<sign>b?")
0x1c off_code    0x057b2b20   main firmware (MIPS32, ThreadX)
0x20 unk_zero    0
0x24 off_hdr3    0x05ccf920   SUNP BURN HDR 3 — 71 x 0x70 backup filenames
0x1fc            nonzero      checksum word (per V50 prior art; unverified)
```

Physical layout (verified; `tools/carve.py` reproduces it):

| Part | Offset | Size | Contents |
|---|---|---|---|
| head | 0x0 | 0xb1a00 | file header (0x200) + sysboot/ISP MIPS code ("DRAM CODE" @0x290) |
| hdr1 | 0xb1a00 | 0x1000 | burn header 1 |
| hdr2 | 0xb2a00 | 0x120 | burn header 2 |
| A.img | 0xb2b20 | 0x4800000 (72MB) | **FAT16** OEM "ICATCH", 4K clusters, RO_RES tree |
| B.img | 0x48b2b20 | 0xf00000 (15MB) | **FAT16** OEM "ICATCH", 1K clusters, USER_RES + PRT_HIS |
| code | 0x57b2b20 | 0x51ce00 | main firmware, linked at **vaddr 0x80000000** |
| tail | 0x5ccf920 | 0x2434 | burn header 3 + filename list + signature trailer |

Corrections to earlier guesses: B: is **FAT16** (BPB says so), not FAT12.
The "nested SUNP BURN FILE/HDR" magics are false-positive strings inside
code, not nested images. carve→repack round-trips byte-identically.

## Filesystem contents

- A:\RO_RES — ~517 files: sensor calibration (COLD.BIN, DEFPIX*, SHDTBL,
  CLBRANK*, LSC), IQ tables, fonts (*.SFN — RIFF/SPFN, stored
  UNCOMPRESSED in v1.09; no SNAP streams found), 295 UI PNGs, WAVs,
  pattern data (incl. LZ4 dir)
- B:\ — USER_RES\PRINTER.BIN (192B "FIF0" index → ERRORLOG.BIN,
  UIPRINT0.BIN), UIDATA.BIN (272B index → UIBOOT00/UIOPEN/UISETUPO),
  LOGDATA.BIN, UIBTRES.BIN, PRT_HIS\PRTCHK.LST

## Main firmware (code part, base 0x80000000)

- 8092 string xrefs confirm link base 0x80000000 (kseg0).
- Boot: appInit chain @0x80006994-ish creates threads incl.
  `PowerOnCtrlThread` (entry 0x8015fe44) → staged `PreBoot(1|2|3)`
  dispatcher at 0x8015f394.
- PreBoot 1 (0x8015f410): registers change-detect handlers, loads
  `B:\USER_RES\UIBOOT00.BIN` via fn 0x80223164, then — gated by flag
  byte 0x805817b4 — polls GPIO 0xb0001038 bit3 (film/door sensor),
  ~500ms timeout → "*** Timeout, Need to Film Out" → sets
  NeedToFilmOut flag (state+0xc bit 0x200000) → ColdData recovery /
  auto-eject path at 0x8015f8f4.
- `printer-boot-skip` mod (tools/mods.py) makes the flag check at
  0x8015f5e0 unconditional — skips the entire film-mech boot block.
- Printer errors are named enum strings registered by a table function
  at ~0x249484 (DPS_PAPER_JAM, DPS_HARDWARE_COVER_OPEN, ...). Runtime
  print-job path untouched by the mod.
- "SunpPIP_Init" = LCD picture-in-picture init, NOT printer. The
  "printer go!" strings sit in the print-job path at ~0x21ee1c.

## SUNP BURN FILE format (from prior art)

Format documented by mheistermann's spca-fun (SPCA6350/EKEN H9) and
Linouth's iCatch-V50-Playground (SPCA6500/Akaso V50):

- Header magic `SUNP BURN FILE`, then offsets to HDR1/HDR2/code/HDR3.
- HDR 1: nine 16-byte fields — partition/segment descriptors (mostly first 4B used).
- HDR 2: `count` then `count` × 128-byte entries XOR-obfuscated with 0x7A. Contains build date.
- HDR 3: `num_filenames` then that many 0x70-byte strings — files to back up during update.
- Sibling products carve into ~7 parts: bootloader (ISP bin), FAT16 resource
  image "A" (configs, fonts, UI assets, Snappy-compressed SFN/SST files),
  FAT12 image "B" (wifi config), main firmware, calib data, drampara.
- On V50, checksum at file offset 0x1FC is NOT enforced — modified images flash anyway.
- Memory map on V50: bootloader 0x40040000, firmware 0x40000000, drampara 0x47ff0000.

## Reference projects (cloned to ~/Documents/ref/, not committed)

- `mheistermann/spca-fun` — sunp.py parser, sunp.bt 010 template, sunp_to_elf.py,
  MIPS softmod loader (run code from SD without flashing), EKEN FTP exploit.
- `Linouth/iCatch-V50-Playground` — sptool (carve/combine/Snappy compress),
  icatchV50M datasheet, iCatch PC drivers + Reflash_V2.6 (FRM flasher),
  reversing notes, Ghidra file.
- `tiredboffin.github.io` + `github.com/fujihack/fujihack` — Fujifilm X-series RE
  (different firmware family; useful methodology, wrong format).

## Entry points for code execution (untested on this device)

1. **iCatch ISP/debug mode**: on V50-family cams, hold shutter → plug USB → tap
   power → enumerates as "Icatch(X) KX Series Bulk Camera Device" → FRM tool
   flashes/dumps. Needs testing on mini Evo despite "charge-only" USB.
2. **UART**: sysboot has a serial command shell (memory dump/fill, file load to
   DRAM at e.g. 0xa1000000). Needs teardown to find pads.
3. **Modified FPUPDATE.DAT**: if checksum/signature unenforced (as on V50),
   repacked image flashes via SD card menu. Highest brick risk, no confirmed
   recovery path on this model.
4. **Softmod path**: spca-fun ran code via the camera's own `mapExe`/loader
   commands — needs equivalent on-device mechanism identified.

## Open questions

- Does the updater verify the signature trailer at `file_size`..EOF, or
  the 0x1FC checksum word, or neither? (V50 ignores its checksum;
  unverified here — repacked images are produced but NOT flash-tested.)
- Does the ISP button combo exist on the mini Evo, and which button?
- Which runtime paths still check printer status (print-job gating)?
- Printer board: separate MCU almost certainly (DPS_* status names are
  protocol-side error labels); where does the boot-time cover check
  read its state besides GPIO 0xb0001038?
- HDR1 field[6] = A:/B: image sizes — is field[3]=0xffffffff a "burn
  everything" marker?
