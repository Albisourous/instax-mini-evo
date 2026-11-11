#!/usr/bin/env python3
"""Minimal zero-dependency FAT16 reader/writer for the iCatch A: and B:
partition images carved from FPUPDATE.DAT.

Read support: list directories recursively, read file contents.
Write support: replace an existing file's contents. The file may grow -
free clusters are allocated from the FAT and the chain is extended.
Renaming, creating, and deleting files are NOT supported (the directory
layout of these partitions is fixed anyway).

Only plain 8.3 names are handled - sufficient for these images.
"""

import struct

END_OF_CHAIN = 0xFFF8
FREE = 0x0000
ATTR_DIR = 0x10


class FatError(Exception):
    pass


def u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


class Entry:
    """One 8.3 directory entry."""
    def __init__(self, name, attr, cluster, size, dir_off):
        self.name = name          # display name like "RO_RES/COLD.BIN" tail
        self.attr = attr
        self.cluster = cluster
        self.size = size
        self.dir_off = dir_off    # absolute offset of the 32B dir entry

    @property
    def is_dir(self):
        return bool(self.attr & ATTR_DIR)


class FatImage:
    """A FAT16 disk image held in a mutable bytearray."""

    def __init__(self, data):
        self.img = bytearray(data)
        b = self.img
        self.bps = u16(b, 11)
        self.spc = b[13]
        self.reserved = u16(b, 14)
        self.nfats = b[16]
        self.root_entries = u16(b, 17)
        self.fat_secs = u16(b, 22)
        if self.bps == 0 or self.spc == 0 or self.fat_secs == 0:
            raise FatError("not a FAT12/16 image")
        self.fat_off = self.reserved * self.bps
        self.root_off = self.fat_off + self.nfats * self.fat_secs * self.bps
        self.root_size = self.root_entries * 32
        self.data_off = self.root_off + self.root_size
        self.cluster_size = self.spc * self.bps
        total_secs = u16(b, 19) or u32(b, 32)
        self.nclusters = (total_secs * self.bps - self.data_off) \
            // self.cluster_size
        if self.nclusters >= 4085:
            self.fat_bits = 16
        else:
            # B: image reports FAT16 but could be small; treat by entry
            self.fat_bits = 16 if u16(b, 22) else 16

    # -- FAT helpers ----------------------------------------------------

    def _cluster_off(self, clus):
        return self.data_off + (clus - 2) * self.cluster_size

    def fat_get(self, clus):
        return u16(self.img, self.fat_off + clus * 2)

    def fat_set(self, clus, val):
        struct.pack_into("<H", self.img, self.fat_off + clus * 2, val)
        # keep second FAT copy in sync
        struct.pack_into("<H", self.img,
                         self.fat_off + self.fat_secs * self.bps + clus * 2,
                         val)

    def chain(self, start):
        out = []
        c = start
        while 2 <= c < END_OF_CHAIN and len(out) < self.nclusters + 2:
            out.append(c)
            c = self.fat_get(c)
        return out

    def read_cluster(self, clus):
        off = self._cluster_off(clus)
        return bytes(self.img[off:off + self.cluster_size])

    # -- directory walking ----------------------------------------------

    def _scan_dir(self, off, size, path, out):
        """Append (path, Entry) for each real entry in a dir region."""
        i = off
        end = off + size
        while i + 32 <= end:
            first = self.img[i]
            if first == 0x00:
                break
            if first != 0xE5 and self.img[i + 11] != 0x0F:  # skip deleted/LFN
                raw = self.img[i:i + 11]
                name = raw[:8].decode("ascii", "replace").rstrip()
                ext = raw[8:].decode("ascii", "replace").rstrip()
                if ext:
                    name += "." + ext
                e = Entry(name, self.img[i + 11], u16(self.img, i + 26),
                          u32(self.img, i + 28), i)
                full = f"{path}/{name}" if path else name
                out.append((full, e))
                if e.is_dir and name not in (".", "..") and e.cluster:
                    sub_off = self._cluster_off(e.cluster)
                    sub_size = len(self.chain(e.cluster)) * self.cluster_size
                    self._scan_dir(sub_off, sub_size, full, out)
            i += 32

    def listdir(self):
        """Return [(path, Entry)] for every file/dir in the image."""
        out = []
        self._scan_dir(self.root_off, self.root_size, "", out)
        return out

    def find(self, path):
        """Find one entry by full path (case-insensitive, / separated)."""
        want = path.strip("/").upper().replace("\\", "/")
        for p, e in self.listdir():
            if p.upper() == want:
                return e
        raise FatError(f"not found: {path}")

    # -- file data --------------------------------------------------------

    def read(self, path):
        e = self.find(path)
        return b"".join(self.read_cluster(c) for c in self.chain(e.cluster)) \
            [:e.size]

    def write(self, path, data):
        """Replace file contents. Grows the cluster chain if needed.

        The directory entry keeps its name and start cluster; only the
        size field and FAT chain change. Returns the entry.
        """
        e = self.find(path)
        old = self.chain(e.cluster)
        need = max(1, (len(data) + self.cluster_size - 1)
                   // self.cluster_size)

        if need > len(old):
            # allocate free clusters for the tail of the chain
            free = []
            for c in range(2, self.nclusters + 2):
                if self.fat_get(c) == FREE:
                    free.append(c)
                    if len(free) == need - len(old):
                        break
            else:
                raise FatError(f"image full: need {need} clusters, "
                               f"have {len(old)} + {len(free)} free")
            chain = old + free
        else:
            # shrink: free the tail beyond `need`
            chain = old[:need]
            for c in old[need:]:
                self.fat_set(c, FREE)

        for a, b in zip(chain, chain[1:]):
            self.fat_set(a, b)
        self.fat_set(chain[-1], 0xFFFF)

        pad = len(chain) * self.cluster_size - len(data)
        blob = bytes(data) + b"\x00" * pad
        for i, c in enumerate(chain):
            off = self._cluster_off(c)
            self.img[off:off + self.cluster_size] = \
                blob[i * self.cluster_size:(i + 1) * self.cluster_size]

        struct.pack_into("<I", self.img, e.dir_off + 28, len(data))
        e.size = len(data)
        return e
