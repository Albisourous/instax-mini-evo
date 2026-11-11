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

## FPUPDATE.DAT structure (v1.09), fully mapped

Top-level header at 0x0 (little-endian u32s after 16-byte magic+pad):

```
0x10 file_size   0x05cd1850 = offset of a 256-byte block that looks like
                 an RSA-2048 signature, followed by a 0x20..0x01 countdown
                 marker, version string "0.001.000", meta, and a final
                 checksum word (0x504 bytes total to EOF)
0x14 off_hdr1    0x000b1a00   SUNP BURN HDR 1: mostly zeros; field[3]=
                 0xffffffff, field[6]=0x04800000/0x00f00000 (matches the
                 A:/B: image sizes, probably a burn descriptor)
0x18 off_hdr2    0x000b2a00   SUNP BURN HDR 2: 2 x 128B entries XOR 0x7A
                 ("060916:build<sign>a?", "060916:build<sign>b?")
0x1c off_code    0x057b2b20   main firmware (MIPS32, ThreadX)
0x20 unk_zero    0
0x24 off_hdr3    0x05ccf920   SUNP BURN HDR 3: 71 x 0x70 backup filenames
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

- A:\RO_RES: ~517 files: sensor calibration (COLD.BIN, DEFPIX*, SHDTBL,
  CLBRANK*, LSC), IQ tables, fonts (*.SFN, RIFF/SPFN, stored
  UNCOMPRESSED in v1.09; no SNAP streams found), 295 UI PNGs, WAVs,
  pattern data (incl. LZ4 dir)
- B:\: USER_RES\PRINTER.BIN (192B "FIF0" index pointing at ERRORLOG.BIN,
  UIPRINT0.BIN), UIDATA.BIN (272B index pointing at UIBOOT00/UIOPEN/
  UISETUPO), LOGDATA.BIN, UIBTRES.BIN, PRT_HIS\PRTCHK.LST

## Main firmware (code part, base 0x80000000)

- 8092 string xrefs confirm link base 0x80000000 (kseg0).
- Boot: appInit chain @0x80006994-ish creates threads incl.
  `PowerOnCtrlThread` (entry 0x8015fe44) → staged `PreBoot(1|2|3)`
  dispatcher at 0x8015f394.
- PreBoot 1 (0x8015f410): registers change-detect handlers, loads
  `B:\USER_RES\UIBOOT00.BIN` via fn 0x80223164, then (gated by flag
  byte 0x805817b4) polls GPIO 0xb0001038 bit3 (film/door sensor),
  ~500ms timeout → "*** Timeout, Need to Film Out" → sets
  NeedToFilmOut flag (state+0xc bit 0x200000) → ColdData recovery /
  auto-eject path at 0x8015f8f4.
- `printer-boot-skip` mod (tools/mods.py) makes the flag check at
  0x8015f5e0 unconditional, skipping the entire film-mech boot block.
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

## Entry points for code execution

1. **iCatch FRM over USB** (primary): hold shutter → plug USB → tap
   power → V50 cams enumerate as "Icatch(X) KX Series Bulk Camera
   Device" → FRM tool flashes/dumps unsigned. The ISP dispatcher
   (`ispDoFunction`, ~21 NAND/FW opcodes) is statically confirmed
   present in this firmware. Untested: whether the mini Evo combo
   exists and whether its USB stack answers vendor requests.
2. **UART sysboot shell**: debug commands only (mem dump/fill,
   file read/write, raw NAND/SPI). `isp`/`boot` are dead code -
   not registered. `fill` enables RAM patching but nothing in the
   shell jumps to loaded code. Needs teardown to find pads.
3. **Modified FPUPDATE.DAT via menu**: DEAD. Signature covers the
   whole image, verified by installed firmware before writing.
   A bypass inside the image cannot help the first flash.
4. **Softmod loader path**: spca-fun ran code via the camera's own
   loader commands - no equivalent found here (`boot` is
   unregistered); FRM or UART must come first.

## Open questions

- CONFIRMED: the updater enforces integrity (camera rejected an
  8-byte-modified image with a "firmware is broken" style error and
  powered off safely - it checks BEFORE writing). Checksum scheme
  decoded: u32 word-sum of fw[:file_size] == 0 (0x1FC field balances
  it, same offset as V50's sumpatch CRC) and u32 word-sum of the
  ENTIRE file == 0 (final word balances the trailer). repack now
  recomputes both. Still open: whether the 256-byte signature block
  is independently verified - it looks like RSA-2048 and is kept
  verbatim. If the camera still rejects the fixed image, the sig is
  real and unforgeable, and the remaining path is patching the
  verifier in the sysboot (head, loaded at 0x80040000).
- Does the ISP button combo exist on the mini Evo, and which button?
- Which runtime paths still check printer status (print-job gating)?
- Printer board: separate MCU almost certainly (DPS_* status names are
  protocol-side error labels); where does the boot-time cover check
  read its state besides GPIO 0xb0001038?
- HDR1 field[6] = A:/B: image sizes. Is field[3]=0xffffffff a "burn
  everything" marker?

## Bluetooth / FujiFile protocol map (FI019, v1.09)

The camera is a BLE GATT server + classic SPP device named `INSTAX-%s`
(CN variant `INSTAX-CN-%s`). The phone app speaks a custom "FujiFile"
command protocol over GATT writes/notifies.

### Message flow (all addresses = vaddr, code base 0x80000000)

- GATT write -> recv path -> wrapper @0x802f9cfc/0x802f9d44:
  `a0 = lw(frame)` (first u32 of the received buffer = wire opcode),
  then `jal 0x802f8474`.
- 0x802f8474: wire-opcode -> internal-msgid translator. Wire opcodes
  are `0x0100xxxx` (little-endian u32, first 4 bytes of the write).
- Dispatcher @0x802f6ee8: `a0` = internal msgid. Top nibble class:
  `0x1xxx` = app commands, `0xexxx` = internal BT events.
  `0x19xx` -> jump table @0x804b38c4 (0x2a entries, GET_*),
  `0x1bxx` -> jump table @0x804b3838 (0x23 entries, CMD_*).
- Handlers live in `BTInterface_*` (~0x802cxxxx-0x802dxxxx).
  Call shape per case: `a0 = lw(ctx+8)`, `a1 = lw(msg+0xc)` (payload ptr).

### Internal msg IDs (from the two jump tables)

GET group (0x19xx):
  0x1917 GET_DEVICE_SUPP_INFORMATION   0x1918 GET_DEVICE_INFORMATION
  0x1919 GET_PRINT_IMG_INFO            0x191a GET_BARRTERY_INFO (sic)
  0x191b GET_PRINTER_CAP_INFO          0x191c GET_PRINTER_OP_INFO
  0x191d GET_CAMERA_CAP_INFO           0x191e GET_CAMERA_OP_INFO
  0x191f GET_IDENTIFY_INFO             0x1920 GET_UPLOAD_INFO
  0x1921 GET_PRINT_COMPLETE_TIME       0x1922 GET_SUBTOTAL_NUM
  0x1923 GET_DATE_NUM                  0x1924 GET_SUBTOTAL_DATA
  0x1925 GET_DATE_DATA                 0x1926 GET_FILTER_NUM
  0x1927 GET_FILTER_DATA               0x1928 GET_CAMERA_FAVORITE_SETTING_HISTORY
  0x1929 GET_CAMERA_CURRENT_FAVORITE_SETTING

CMD group (0x1bxx):
  0x1b00 PRINT_DOWNLOAD_START   0x1b02 PRINT_DOWNLOAD_END
  0x1b03 PRINT_DOWNLOAD_CANCEL  0x1b04 PRINT_REJECT_FILMCOVER
  0x1b05 UPLOAD_PIC_START       0x1b06 UPLOAD_PIC_DATA
  0x1b07 UPLOAD_PIC_END         0x1b08-0x1b0a UPLOAD_AUDIO_*
  0x1b0b UPLOAD_URL_ADDR        0x1b0c UPLOAD_DATA_COMPLETE
  0x1b0d LIVEVIEW_START         0x1b0f LIVEVIEW_STOP
  0x1b10 LIVEVIEW_TAKE_PIC      0x1b11-0x1b14 LIVEVIEW_POST_UPLOAD_*
  0x1b15/0x1b17 FRAME_PIC_DOWNLOAD_START/END
  0x1b18-0x1b1a CLEAR_SUBTOTAL/DATE/FILTER
  0x1b1b-0x1b21 FW_DOWNLOAD_* / FW_BACKUP / FW_PROGRAM_*
  0x1b22 COMMON_SHUTDOWN

Known wire opcodes (0x0100xxxx -> msgid, from translator; partial):
  0x01006012 -> 0x1b05 UPLOAD_PIC_START   0x01006013 -> 0x1b06 UPLOAD_PIC_DATA
  0x0100600c -> 0x1b02 PRINT_DOWNLOAD_END 0x0100600d -> 0x1b03 PRINT_DL_CANCEL
  0x0100600f -> 0x1b04                    0x01006019 -> 0x1b0c
  0x0100601a -> 0x1b0d LIVEVIEW_START     0x0100601c -> 0x1b0f LIVEVIEW_STOP
  0x01006020 -> 0x1b13                    0x01006029 -> 0x1b12
  0x0100602a -> 0x1b19                    0x0100602d -> 0x1b1a
  0x01006034 -> 0x1b20                    0x01006035 -> 0x1b21
  0x01006001 -> 0x1918                    0x01006005 -> 0x191c
  0x01006014 -> 0x1919?? (verify)         0x0100602f -> 0x191e
  0x01006036 -> 0x191b                    0x0100602e -> 0x1928
  0x01000100 -> 0x17c1                    0x01000300 -> 0x17c3 BREDR_LOST
  0x0100a001 -> 0x1843 BLE_DEVICE_LOST    0x01007000 -> 0xec00
  (full dump in tools/dev/fujifile_opcodes.txt if regenerated)

### UPLOAD_PIC_START handler (0x802ceb94)

- Request payload: u32 picture index (bounds check `< 0x63`).
- Resolves index -> file info (0x802d4a24), snprintf filename via
  0x8006bb78, reads pic-type/size fields, builds ~0x1cc-byte response
  block (sp+0x1e8). So the app can pull arbitrary stored photos by
  index -- NOT limited to print renders. Index enumeration likely via
  GET_DATE_*/GET_SUBTOTAL_* (photo lists grouped by date) and/or
  GET_UPLOAD_INFO.

### Pairing

Uses numeric comparison (MSG_UI_WIFI_BT_DEVICE_NUMERIC_INFO,
HCI_CMD_PASSKEY_ENTRY_RSP, PairingReply handler): app shows code,
user confirms on camera with OK (per official FAQ). Standard
OS-level BLE pairing should suffice for a custom client.

### Still unknown (need a live probe)

- GATT service/characteristic UUIDs (client can just enumerate).
- Exact response frame layout (header fields, notify chunking, MTU).
- Whether the GATT write is raw [u32 opcode][payload] or has a
  header (len/seq/flags) before the opcode.
- Endianness/packing of larger payloads and image chunk format.

## Film effect system (v1.09)

Film effects are parameter combos, not LUT files. `View_SetFilmEffect(i)`
calls `IQ_FilmEffectModeSet` at 0x80360a04, which resets the param
block and dispatches mode 0..9 through a jump table at 0x804d7e30.
Mode 0 is NORMAL (no params, everything stays at reset defaults).

Each case calls some of eight param-class setters:

| setter | addr        | writes struct | semantics (partial)                    |
|--------|-------------|---------------|----------------------------------------|
| P1     | 0x803604d8  | 0x808b2e14    | small mode flag                        |
| P2     | 0x80360510  | 0x808b2e1c    | pattern overlay (calls 0x801e3c00)     |
| P3     | 0x80360614  | 0x808b2e24    | one signed byte param, contrast-like   |
| P4     | 0x803606a0  | 0x808b2e34    | multi-field gain block                 |
| P5     | 0x80360770  | 0x808b2e4c    | color tint, feeds ISP 0x2a003/4/6      |
| P7     | 0x803608e8  | 0x808b2e9c    | small mode + byte param                |
| P8     | 0x803609ac  | 0x808b2eac    | two u32 params                         |

Effect modes (param values per setter):

| mode | params                    |
|------|---------------------------|
| 0    | none (NORMAL)             |
| 1    | P4=1, P5=1, P7=1          |
| 2    | P3=1, P4=2, P5=2          |
| 3    | P3=3, P5=6, P7=5          |
| 4    | P5=4, P7=3                |
| 5    | P5=3, P7=2                |
| 6    | P4=3, P5=5, P7=4          |
| 7    | P2=2, P8=2                |
| 8    | P2=1, P8=1                |
| 9    | P1=1, P2=3                |

P5 is the color-grading knob. Its sub-cases write a tint block:
flag at +0x10, x at +0x14, y at +0x18, four tint bytes at +0x1c..0x1f.
The apply path at 0x80360f80 pushes x to ISP param 0x2a003, y to
0x2a004, and the byte array pointer to 0x2a006. Modes 1, 2 and 6
share one body at 0x803607b8 and differ only in the byte loaded
into $a0: tint [v,0,0,v] with v = 0x53 / 0x13 / 0x36. Mode 3 is
the x/y case (stock x=246, y=8). Mode 4 writes all zeros (flat).
Mode 5 combines x=y=0xf8 with tint [0x56,0,0,0x56]. Mode 0 clears
an alternate-layout field. Tint-byte and x/y semantics are
unverified.

Custom effects: repurpose a stock slot, do not add modes. The UI
shows 10 fixed effect icons. `wkw-suite` retunes per-mode P5
constants and repoints each slot's P5 arg; the P5 arg selects the
shared tint case, so each retuned mode is a global constant shared
by every slot that references it.

Pattern-overlay resources (P2 modes) live in A:/RO_RES/PATTERN/ as
.yuv + .y weight pairs (sepia, rough, colors, fisheye, heavy, LIGHT
variants) at 320x240 and 800x608, some LZ4-compressed.

### wkw-suite implementation

One Wong Kar-wai film per dial position; the dial keeps its stock
0-9 wrap so all ten positions stay reachable. Only arg immediates
and per-mode constants are patched.

| pos | film | change |
|-----|------|--------|
| 0 | NORMAL | stock |
| 1 | In the Mood for Love | P4 arg->0, P5 arg->3, P7 arg->3; m3 x/y 246/8 -> 128/64 |
| 2 | Chungking Express | P5 arg->1; m1 byte 0x53 -> 0x70 |
| 3 | Fallen Angels | P5 arg->2; m2 byte 0x13 -> 0x08 |
| 4 | Happy Together | P5 arg->6; m6 byte 0x36 -> 0x48 |
| 5 | 2046 | P5 arg->5; m5 x/y 0xf8 -> 0x18, byte 0x56 -> 0x70 |
| 6 | The Grandmaster | P5 arg->4 (flat) |
| 7 | Ashes of Time | stock P2=2 + P8=2 (sepia pattern, unverified) |
| 8 | Days of Being Wild | stock P2=1 + P8=1 (rough pattern, unverified) |
| 9 | As Tears Go By | stock P1=1 + P2=3 |

Only two film patterns exist (FILM_EFFECT_SEPIA, FILM_EFFECT_ROUGH
strings; heavy/fisheye/colorshift/light leak are lens effects), so
positions 7-9 keep stock combos. Positions 8 and 9 may end up
sharing the rough pattern, distinguished only by the unknown P8/P1
args. P2 arg -> pattern-file mapping is unverified; fix by cycling
args after a flash.

### Film-effect internals, addresses worth keeping

Dispatcher `IQ_FilmEffectModeSet` at 0x80360a04:

- jump table at 0x804d7e30, 10 entries, bound check `a0 < 10`
- case addresses: mode0 0x80360a84, mode1 0x80360ab4,
  mode2 0x80360adc, mode3 0x80360b04, mode4 0x80360b1c,
  mode5 0x80360b2c, mode6 0x80360b3c, mode7 0x80360b54,
  mode8 0x80360b74, mode9 0x80360a94
- callers (jal sites): 0x801bf3f0 (combined lens+film setter,
  writes struct +0x18/+0x19 then calls 0x803603d0 + 0x80360a04),
  0x801bf674 (film-only setter, writes +0x19 then calls
  0x80360a04), 0x80361930

P5 (0x80360770) sub-dispatch: bound `a0 < 7`, jump table
0x804d7dfc. Tint block at 0x808b2e4c: u32 mode @+0, u32 @+4/+8
(alt layout), bytes @+0xc..0xf (alt layout), u32 flag @+0x10,
u32 x @+0x14, u32 y @+0x18, 4 tint bytes @+0x1c..0x1f. Per-mode
values (corrected; an earlier table was off by one):

| P5 arg | case | written values                             |
|--------|------|--------------------------------------------|
| 0      | 0x803607a0 | clears alt field @0x2e5c               |
| 1      | 0x803607dc | flag=1, x=0, y=0, tint=[0x53,0,0,0x53]     |
| 2      | 0x803607ec | flag=1, x=0, y=0, tint=[0x13,0,0,0x13]     |
| 3      | 0x803607fc | flag=1, x=246, y=8, tint=[0,0,0,0]         |
| 4      | 0x80360830 | flag=1, x=0, y=0, tint=[0,0,0,0] (loop)    |
| 5      | 0x80360870 | flag=1, x=y=0xf8, tint=[0x56,0,0,0x56]     |
| 6      | 0x803607ac | flag=1, x=0, y=0, tint=[0x36,0,0,0x36]     |

Modes 1/2/6 jump into a shared body at 0x803607b8 with the byte
preloaded into $a0; only the `li $a0,v` immediate differs.

P7 (0x803608e8) sub-dispatch: bound `a0 < 6`, jump table
0x804d7e18. Writes {u32 mode @0x2e9c, byte param @+4}: observed
bytes 6, 3, ... (small enum, likely processing-type selector).

P3 (0x80360614): writes {u32 mode @0x2e24, sbyte @+4} with param
values 0x50 (mode 3), -0x74 (mode 2), 0x78 (mode 1); mode 0
writes zero. Contrast-like single signed value.

P4 (0x803606a0): writes block at 0x2e34 with fields
{u32 @0, u32 @4, u32 @8, u32 @0xc, u32 @0x10, byte @0x14};
mode 3 writes {1,4,8,3,arg,arg}, mode 2 writes {1,4,8,3..,arg}.

P8 (0x803609ac): writes {u32 @0x2eac+8, u32 @+0xc}; modes 1/2
store 0x1e in +0xc, else copies a global.

P1 (0x803604d8): writes {u32 @0x2ddc, mode @0x2e14, bytes +4/+5}.

Apply path 0x80360f80 reads the 0x2e4c block and pushes params
to the ISP through 0x803c0f6c(id, val) / 0x803c13a4:
x -> id 0x2a003, y -> id 0x2a004, pointer to the 4-byte tint
array -> id 0x2a006. A second layout branch at 0x80361064 uses
fields +4/+8 and the byte array at 0x2e58 (= block +0xc). A
second writer around 0x80360180 fills the alternate layout,
so the same struct serves two param encodings.

UI state struct: `lw -0x67a0(0x8051)` = pointer at 0x80509860.
Field +0x18 = lens-effect index, +0x19 = film-effect index,
+0x29 read by the dial handler path. Dial decrement handler at
0x801e18fc (wraps idx 0->9 via `addiu $v1,$zero,9` at
0x801e1914); dial increment handler at 0x801e1a8c (continues
while idx<9 via `sltiu $v1,$v0,9` at 0x801e1a9c). Parallel
handlers for the lens index (+0x18) sit at 0x801e19b8 and
0x801e1b7c with the same wrap pattern; wkw-suite leaves them
alone so lens effects keep all 10 positions.

### Digital zoom internals (mapped 2026-11-10)

Capture/preview digital zoom uses a 10-stop table, not motor
stops: `ZoomLevelToFactor` at 0x801ba170 indexes a u16 table at
0x80489774 (code 0x489774) and returns entry/10. Stock values
x100: 1000,1140,1290,1470,1680,1910,2170,2470,2810,3200 =
geometric 1.00x -> 3.20x (~x1.138/step). Nine call sites. The
u16 table at 0x804f8270 indexed by a <31 bound is mechanical
zoom-motor step deltas (shared codebase; mini Evo has a fixed
lens) and is unrelated. Playback zoom ("DZoom 1-4") is a
separate path. `zoom-6x` rewrites table entries 1-9 to a
geometric 1.00 -> 6.40x curve; level 0 stays 1.00x. Zooming
below 1x is impossible (digital crop only).

### Updater / integrity (v1.09, decoded 2026-11-10)

- sysboot ("head" part, 0x0..0xB1A00) loads at 0x80040000; its MIPS
  code starts at file offset 0x200. It contains the SD-card update
  routine (large function at VA 0x8004d348) and verify/verify-err
  strings, but NO md5/sha/rsa/crypto strings.
- Integrity anchors, both verified to hold on stock v1.09:
  * u32 @0x1FC: u32 word-sum of fw[0:file_size] == 0
  * u32 @EOF-4: u32 word-sum of entire file == 0
  sunp.build() recomputes both via _fix_sums().
- Trailer at file_size (0x5CD1850): 256-byte high-entropy block
  (RSA-2048 shape), 32-byte 0x20..0x01 countdown, "0.001.000"
  version string, meta fields, final checksum word.
- HDR2 (XOR 0x7A) holds two records named "060916:build<sign>a?"
  and "060916:build<sign>b?" carrying {offset, size} pairs that
  exactly describe the A: and B: images - signature-coverage
  descriptors.
- hdr3 region lists backup filenames (A:\RO_RES\*.BIN,
  B:\PRT_HIS\PIMG*.JPG) restored during update.
- The camera's "broken firmware" rejection happened before any
  write: the check is a gate, not a verify-after-write.

### Signature verify path (mapped 2026-11-10, code part)

The gate lives in the main firmware, not sysboot. The update menu
calls `ab_fw_signature_verify` at 0x802269b8:

- snprintf's the file path into a stack buffer (paths via
  0x8006bb78, prints via 0x8006bd38).
- prints `ab_fw_signature_verify S [%d]` at 0x80226a5c.
- calls the verify core `jal 0x80308d88` at 0x80226a6c with
  a0 = path buffer, a1 = 4.
- prints `ab_fw_signature_verify E [%d] [%d]` at 0x80226a80.
- `beq s0,zero` at 0x80226a90 selects the return: s4 stays 1 on
  success; on failure `addu s4,zero,zero` at 0x80226a98 clears it.
  Every internal path (long-name truncation branches at
  0x80226ac0/0x80226b14/0x80226b44/0x80226b6c) reconverges on the
  same verify call, so 0x80226a98 is a single choke point.
- Callers: 0x80230ee0 and 0x80234a9c (jal 0x802269b8), both test
  v0==0 and reject with error pairs {7,2} / {7,4} - the observed
  "firmware broken" rejection.

Verify core at 0x80308d88 is a real mbedtls RSA/ECDSA check:

- Seeks to EOF-1028 (the byte after the 256-byte signature) and
  reads the 1024-byte post-signature block.
- memcmp's its first 32 bytes against the 0x20..0x01 countdown
  pattern (error 7, "Magic number is wrong." if mismatched).
- sscanf("%u.%u.%u") parses "0.001.000" at +0x20; the second
  component must be nonzero or it bails with "OTA version is
  lower then Signature verify tool version." (return code 2).
- The u32 at +0x58 indexes a jump table of hash/crypto types
  (stock value 1).
- Reads {offset,size} from +0x30/+0x34 and streams that region
  through the mbedtls SHA path (0x80334500) in <=1MB chunks.
  Stock values: {0, 0x05cd1850} = fw[0:file_size).
- Then hashes the same 1024-byte post-signature block again
  (fw[file_size+0x100 : EOF-4)), finalizes the digest and runs
  mbedtls_pk_verify (ECDSA or RSA per type) against the 256-byte
  signature.

Coverage conclusion (verified against stock values): the
signature covers fw[0:file_size) plus the post-signature block
minus its last word - i.e. EVERYTHING except the signature
itself and the final checksum word. Head, HDR1/2/3, A:, B: and
code are all inside the signed region. The two word-sums are
necessary but never sufficient; any content change fails
signature verification.

Hard consequence: the check runs in the INSTALLED firmware
before anything is written. Patching ab_fw_signature_verify
inside the new image is inert for the first flash - the running
stock verifier still fails the image. `sigverify-bypass` only
becomes useful after code execution is achieved another way
(it would then make subsequent updates friction-free). The SD
menu path alone cannot bootstrap a modified image.

### ISP paths in sysboot (mapped 2026-11-10, head part)

The shell command table is `{name_ptr, handler, help_ptr, 0}`,
16-byte entries starting near file 0x9e51c. Registered commands
are a debug set only: memory `dump`/`fill`/`search`, `regdump`,
`os`/`task`/`mem` info, file `read`/`write`/`cp`/`ren`/`fmt`/`info`,
raw NAND (`nanddetect`, `nanderase*`, `nandpr`/`nandpw`/`nandlr`/
`nandrr`, rsv read/write/erase) and the SPI mirror set.
`isp` and `boot` strings exist but NO table entry or code ref
points at them - dead code in this build, not typed commands.

The live path is the USB vendor ISP protocol (iCatch FRM):
- `ispDoFunction` dispatcher at ~0x80047b30 reads an opcode from
  a request struct, bounds-checks < 21, and jump-tables at
  0x800e33f0. Strings name the ops: `NAND_DETECT`,
  `NAND_RSV_ALLOCATE`, `NAND_RSV_A_FORMAT`, `NAND_RSV_B_FORMAT`,
  `NAND_LOGICAL_FORMAT`, `NAND_PHYSICAL_FORMAT`,
  `NAND_TOTAL_ERASE`, `FwWrite start/end`, `FW%d write %u/%u KB`.
- `usbVNDR*` strings (`usbVNDRISPJump`, `usbVNDRReqNandDetect`)
  tie it to USB vendor requests.
- `Card ISP` strings (`Card ISP Version`, `isp file :%s`,
  `***** Card ISP complete!*****`) mark the SD burn path that
  the app reboots into after its own signature check passes.

Signature status in head: NONE. The burn function (~0x80051xxx)
validates `SUNP BURN FILE`/HDR 1/2/3 structure and HDR2
`060916:build<sign>a?/b?` record names (structural checks,
not crypto), then does write + readback compare
(`verify err at ofs=0x%x`, `FW verified`, `RawC verified`).
No RSA/SHA/mbedtls strings exist in head.

Consequence: any route that reaches the USB ISP dispatcher or
Card ISP burns unsigned images. The V50 family exposed FRM over
USB without soldering. Fallback remains UART (`fill` can
RAM-patch, but no `go`/`jump`/`isp`/`boot` command exists, so
exec via the shell alone is limited).

Tested 2026-11-10, hardware:

- Checksummed wkw-suite image via SD menu update: REJECTED with
  the "firmware is broken" style error, safe power-off, nothing
  written. Confirms the signature check is real and covers
  modified content; the two additive sums are not sufficient.
- USB FRM combos tried with zero enumeration: shutter held +
  power-on over USB, shutter held while plugging USB on a
  powered-on camera, playback held + power-on over USB. The
  port appears charge-only at the hardware level on this model -
  no iCatch device ever appeared on the host bus.

No-solder entry paths are exhausted. UART teardown is the only
confirmed-viable door left.

`iab_generate_signature_check_data` (~0x80309100) strings:
`iab_signature_verify`, `iab_get_public_key`,
`ECDSA verify failed. mbedtls_pk_verify returned -0x%04x`,
`RSA verify failed ...`, `hash ctx init fail.`,
`Unsupported hash type`, `Unsupported crypto type.`,
`Public key read fail.`
