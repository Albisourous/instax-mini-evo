#!/usr/bin/env python3
"""Work with the FAT16 images carved from FPUPDATE.DAT.

Usage:
    python3 tools/fat.py ls   <image.fat>
    python3 tools/fat.py get  <image.fat> <PATH/IN/IMAGE> <outfile>
    python3 tools/fat.py put  <image.fat> <PATH/IN/IMAGE> <infile>
    python3 tools/fat.py xall <image.fat> <outdir>

`put` replaces an existing file's contents in place (may grow; free
clusters are allocated). Paths inside the image use / separators and
8.3 names, e.g. USER_RES/PRINTER.BIN.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fatfs import FatImage


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    cmd, img_path = sys.argv[1], sys.argv[2]
    fs = FatImage(open(img_path, "rb").read())

    if cmd == "ls":
        for path, e in fs.listdir():
            kind = "dir " if e.is_dir else "file"
            print(f"{kind} {e.size:>10} {path}")
    elif cmd == "get":
        data = fs.read(sys.argv[3])
        open(sys.argv[4], "wb").write(data)
        print(f"{sys.argv[3]} -> {sys.argv[4]} ({len(data)} bytes)")
    elif cmd == "put":
        data = open(sys.argv[4], "rb").read()
        fs.write(sys.argv[3], data)
        open(img_path, "wb").write(fs.img)
        print(f"{sys.argv[4]} -> {sys.argv[3]} ({len(data)} bytes)")
    elif cmd == "xall":
        outdir = sys.argv[3]
        for path, e in fs.listdir():
            dest = os.path.join(outdir, path)
            if e.is_dir:
                os.makedirs(dest, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                open(dest, "wb").write(fs.read(path))
        print(f"extracted to {outdir}/")
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
