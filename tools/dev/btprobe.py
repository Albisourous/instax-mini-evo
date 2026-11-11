#!/usr/bin/env python3
"""Live probe for the instax mini Evo BLE FujiFile protocol.

DEV TOOL ONLY -- not part of the zero-dependency firmware toolchain.
Requires:  pip install bleak

Usage:
    python3 btprobe.py                # scan, enumerate, probe safe GETs
    python3 btprobe.py --op 01006012 --arg 00000000
                                    # raw opcode + payload (hex)

Put the camera into pairing/BT mode first:
    MENU -> BLUETOOTH SETTINGS -> PAIRING REGISTRATION

Camera answers app commands on a GATT characteristic with notifications.
Wire format hypothesis (from firmware): write = LE u32 opcode + payload.
Responses come back as notify frames -- first 4 bytes are probably the
reply opcode/status, rest is the payload we still need to map.
"""
import asyncio, struct, sys
from bleak import BleakClient, BleakScanner

# wire opcodes we decoded from the firmware (0x0100xxxx, LE on the wire)
OPS = {
    "GET_DEVICE_INFORMATION": 0x01006001,
    "GET_PRINTER_OP_INFO":    0x01006005,
    "GET_CAMERA_OP_INFO":     0x0100602f,
    "GET_PRINTER_CAP_INFO":   0x01006036,
    "GET_CAMERA_FAVORITE_HISTORY": 0x0100602e,
    "UPLOAD_PIC_START":       0x01006012,
    "UPLOAD_PIC_DATA":        0x01006013,
}

SAFE_GETS = [
    "GET_DEVICE_INFORMATION",
    "GET_CAMERA_OP_INFO",
    "GET_PRINTER_OP_INFO",
]


async def main():
    args = sys.argv[1:]
    raw_op = None
    if "--op" in args:
        i = args.index("--op")
        raw_op = (int(args[i+1], 16),
                  bytes.fromhex(args[i+2]) if i+2 < len(args) else b"")

    print("[*] scanning for INSTAX-* ...")
    dev = await BleakScanner.find_device_by_filter(
        lambda d, ad: d.name and "INSTAX" in d.name, timeout=20)
    if not dev:
        print("[!] no INSTAX device found -- is the camera in pairing mode?")
        return
    print(f"[*] found {dev.name} {dev.address}")

    async with BleakClient(dev) as c:
        print(f"[*] connected, MTU={c.mtu_size}")
        notifiable = []
        writable = []
        for svc in c.services:
            print(f"  svc {svc.uuid}")
            for ch in svc.characteristics:
                props = ",".join(ch.properties)
                print(f"    char {ch.uuid} [{props}] h={ch.handle:#x}")
                if "notify" in ch.properties or "indicate" in ch.properties:
                    notifiable.append(ch)
                if "write" in ch.properties or "write-without-response" in ch.properties:
                    writable.append(ch)
                for d in ch.descriptors:
                    try:
                        v = await c.read_gatt_descriptor(d.handle)
                        print(f"        desc {d.uuid} = {v!r}")
                    except Exception:
                        pass

        got = []
        def mk_handler(ch):
            def h(_, data):
                got.append((ch.uuid, bytes(data)))
                print(f"  << notify {ch.uuid}: {bytes(data).hex()}")
            return h
        for ch in notifiable:
            try:
                await c.start_notify(ch, mk_handler(ch))
                print(f"[*] notify ON  {ch.uuid}")
            except Exception as e:
                print(f"[!] notify fail {ch.uuid}: {e}")

        async def poke(opname, opcode, payload):
            frame = struct.pack("<I", opcode) + payload
            for ch in writable:
                for wr in (False, True):
                    try:
                        await c.write_gatt_char(ch, frame, response=wr)
                        print(f"  >> {opname} -> {ch.uuid}"
                              f" ({'with' if wr else 'no'} rsp): {frame.hex()}")
                    except Exception as e:
                        print(f"  .. write {ch.uuid} rsp={wr}: {e}")
            await asyncio.sleep(2.0)

        if raw_op:
            await poke(f"OP {raw_op[0]:#010x}", raw_op[0], raw_op[1])
        else:
            for name in SAFE_GETS:
                await poke(name, OPS[name], b"")

        if got:
            print("\n[+] responses:")
            for u, d in got:
                print(f"    {u}: {d.hex()}")
        else:
            print("\n[-] no notifications received")


if __name__ == "__main__":
    asyncio.run(main())
