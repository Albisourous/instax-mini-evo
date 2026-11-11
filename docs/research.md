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

## FPUPDATE.DAT structure (v1.09)

Top-level header at 0x0 (little-endian u32s after 16-byte magic+pad):

```
0x10 file_size   (0x05cd1850 — differs from actual size by 0x504, unknown why)
0x14 off_hdr1    0x000b1a00   SUNP BURN HDR 1 — partition table?
0x18 off_hdr2    0x000b2a00   SUNP BURN HDR 2 — 128B entries XOR-obfuscated w/ 0x7A
0x1c off_code    0x057b2b20   near "DRAM CODE" string at 0x57b2bb0
0x20 unk_zero    0
0x24 off_hdr3    0x05ccf920   SUNP BURN HDR 3 — filename backup list
```

Other magics found: nested `SUNP BURN FILE` at 0xa4400, 0x5c4be28, 0x5ca07dc;
`SUNP BURN HDR` at 0xa4410, 0xa4574, 0xa460c; `ThreadX` string at 0xb1579;
`$unp` version strings clustered 0x5cc8xxx–0x5ccfxxx.

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

- Is HDR1 the partition table for the 7-ish carved parts, and do our offsets
  match the V50 layout (bootloader / FAT-A / FAT-B / firmware / drampara)?
- Does the updater verify any signature, or just the 0x1FC checksum (or neither)?
- Does the ISP button combo exist on the mini Evo, and which button?
- Which ThreadX entry is the main firmware, and where is it mapped?
- Printer board: separate MCU? If jam blocks boot, where does init fail?
