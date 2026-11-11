#!/usr/bin/env python3
"""Carve an instax mini Evo FPUPDATE.DAT into its component parts.

Writes each part plus a manifest.json recording the original layout so
tools/repack.py can rebuild a byte-identical file.

Usage:
    python3 tools/carve.py firmware/FPUPDATE.DAT [outdir]
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sunp


def carve(dat_path, outdir):
    data = open(dat_path, "rb").read()
    os.makedirs(outdir, exist_ok=True)

    manifest = {"source_size": len(data), "parts": []}
    for name, off, size in sunp.parts(data):
        fname = name.replace(".img", ".fat")
        with open(os.path.join(outdir, fname), "wb") as f:
            f.write(data[off:off + size])
        manifest["parts"].append({"name": fname, "offset": off, "size": size})
        print(f"{fname:12} 0x{off:08x} + 0x{size:08x}  ({size} bytes)")

    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    for name in ("A", "B"):
        off = dict((n, o) for n, o, s in sunp.parts(data))[name + ".img"]
        info = sunp.bpb_info(data, off)
        print(f"{name}.fat: {info['fat_type']} oem={info['oem']} "
              f"{info['total_sectors']} sectors x {info['bytes_per_sector']}B")
    print("wrote manifest.json")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    carve(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "out/carved")


if __name__ == "__main__":
    main()
