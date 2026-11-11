#!/usr/bin/env python3
"""Repack carved parts back into an FPUPDATE.DAT.

Reads the parts listed in manifest.json (written by tools/carve.py),
concatenates them in order, and rewrites the top-level header offsets and
file_size field. Part sizes may differ from the original - all offsets are
recomputed.

WARNING: the signature/checksum trailer in the 'tail' part is preserved
verbatim and will be STALE after any modification. On the sibling iCatch
V50 the updater ignored checksum failures, but on the mini Evo this is
UNVERIFIED. Flashing a repacked image may permanently brick the camera.

Usage:
    python3 tools/repack.py <carved_dir> <outfile.DAT>
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sunp


def repack(carved_dir, outfile):
    manifest = json.load(open(os.path.join(carved_dir, "manifest.json")))
    blobs = []
    for p in manifest["parts"]:
        path = os.path.join(carved_dir, p["name"])
        blob = open(path, "rb").read()
        blobs.append((p["name"], blob))
        if len(blob) != p["size"]:
            print(f"  {p['name']}: resized {p['size']} -> {len(blob)}")

    data = sunp.build(blobs)
    with open(outfile, "wb") as f:
        f.write(data)
    print(f"wrote {outfile} ({len(data)} bytes)")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    repack(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
