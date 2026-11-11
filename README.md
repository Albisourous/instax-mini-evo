# instax-mini-evo

Open-source tooling for the Fujifilm instax mini Evo — unpack, inspect, and
(eventually) modify its firmware so the camera can run custom software.

> **Warning:** firmware work on this device can permanently brick it. There is
> no confirmed recovery path on this model yet. See `docs/research.md`.

## Status

Early research. Confirmed so far:

- SoC: Sunplus iCatch CA5310A/CA5000A, MIPS32 4Kx, ThreadX RTOS
- Firmware: `FPUPDATE.DAT` (v1.09) is a Sunplus `SUNP BURN FILE`, publicly
  downloadable — see `docs/research.md` for the URL
- The `SUNP` format is partially documented by prior art on sibling iCatch
  devices (spca-fun, iCatch-V50-Playground)

## Tools

```sh
python3 tools/inspect.py firmware/FPUPDATE.DAT
```

Zero-dependency Python 3. Parses the top-level SUNP header and lists all
embedded burn sections.

## Layout

- `firmware/` — stock `FPUPDATE.DAT` (gitignored, ~93 MB; download it yourself)
- `tools/` — unpack/inspect/repack utilities
- `docs/` — research notes
