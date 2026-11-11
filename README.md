# instax-mini-evo

Open-source tooling to repurpose the **Fujifilm instax mini Evo** as a
standalone digital camera running modified software. It unpacks the stock
firmware, applies camera-centric mods, and repacks a flashable image —
one command, no dependencies beyond Python 3.

> **BRICK RISK.** Flashing modified firmware can permanently brick the
> camera. There is no confirmed recovery path on this model. The build
> output is **not tested on hardware**. You proceed entirely at your own
> risk. See `docs/research.md`.

## Requirements

- macOS or Linux, Python 3.8+ (no pip installs needed)
- a microSD card (FAT32, as the camera expects)
- an instax mini Evo you're willing to risk

## One-line usage

```sh
./instax-evo build
```

That downloads the stock v1.09 firmware if missing (~93MB), carves it
into parts, applies the default mods, and writes
`out/FPUPDATE_MOD.DAT`.

## Installing the result

1. Copy `out/FPUPDATE_MOD.DAT` to the **root** of a FAT32 microSD card.
2. Rename it to `FPUPDATE.DAT`.
3. Insert the card, power the camera on, open **MENU → FIRMWARE UPGRADE**.
4. Cross your fingers — see the brick warning above.

## What the default mod does

`printer-boot-skip` — the instax printer mechanism does a self-check
during boot (film-door GPIO poll, "Need to Film Out" recovery,
auto-eject). If the mechanism is jammed, missing, or you simply never
want the printer in the boot path, this mod skips that whole block with
a single-instruction patch in the PreBoot-1 stage. Runtime printing is
untouched. Full details in `tools/mods.py` and `docs/research.md`.

## Other commands

```sh
./instax-evo inspect    # SUNP BURN FILE headers + physical layout
./instax-evo unpack     # carve firmware into out/carved/ parts
./instax-evo catalog    # extract all A:/B: partition files to out/
```

Individual tools (all zero-dependency Python 3):

```sh
python3 tools/inspect.py firmware/FPUPDATE.DAT
python3 tools/carve.py  firmware/FPUPDATE.DAT out/carved
python3 tools/repack.py out/carved out/FPUPDATE_MOD.DAT
python3 tools/fat.py    ls out/carved/A.img
python3 tools/fat.py    get out/carved/B.img USER_RES/PRINTER.BIN out.bin
python3 tools/fat.py    put out/carved/B.img USER_RES/PRINTER.BIN new.bin
```

- `tools/sunp.py` — SUNP BURN FILE parser + repack logic
- `tools/fatfs.py` / `tools/fat.py` — FAT16 read/write inside the images
- `tools/snappy.py` — Snappy codec for SNAP-compressed SFN/SST resources
- `tools/mods.py` — the mod table (add your own patches here)

## Verified

On stock v1.09: carve → repack produces a **byte-identical** file; both
FAT16 images mount on macOS/Linux; the default mod changes exactly one
byte and disassembles sanely. Nothing has been flashed to a device.

## Layout

- `instax-evo` — the one-command entry point
- `firmware/` — stock `FPUPDATE.DAT` (gitignored, auto-downloaded)
- `tools/` — unpack/inspect/mod/repack utilities
- `docs/research.md` — full reverse-engineering notes
- `out/` — carved parts, extracted files, build output (gitignored)

## Credit / prior art

Format family documented by
[mheistermann/spca-fun](https://github.com/mheistermann/spca-fun)
(SPCA6350) and
[Linouth/iCatch-V50-Playground](https://github.com/Linouth/iCatch-V50-Playground)
(SPCA6500). This repo reimplements the pieces needed for the mini Evo
with zero dependencies.
