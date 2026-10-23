#!/usr/bin/env python3
"""Compare the AIC AWDL vtable with this Mac's IO80211Family vtable."""

import re
import struct
import subprocess
import sys
from pathlib import Path


KERNEL_HIGH = 0xFFFFFF8000000000
VTABLE_SLOTS = 502
APPLE_VTABLE = "__ZTV23IO80211VirtualInterface"
AIC_VTABLE = "__ZTV22AICNativeAWDLInterface"
APPLE_DTOR = "__ZN23IO80211VirtualInterfaceD1Ev"


def output(*args):
    return subprocess.check_output(args, stderr=subprocess.DEVNULL,
                                   text=True, errors="replace")


def symbols(path):
    result = {}
    for line in output("xcrun", "nm", "-n", str(path)).splitlines():
        fields = line.split(maxsplit=2)
        if len(fields) != 3:
            continue
        try:
            result[int(fields[0], 16)] = fields[2]
        except ValueError:
            pass
    return result


def segment_for_address(path, address):
    lines = output("otool", "-l", str(path)).splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "cmd LC_SEGMENT_64":
            continue
        values = {}
        for candidate in lines[index + 1:index + 16]:
            parts = candidate.split()
            if len(parts) == 2 and parts[0] in {
                    "vmaddr", "vmsize", "fileoff", "filesize"}:
                values[parts[0]] = int(parts[1], 0)
        if all(key in values for key in ("vmaddr", "vmsize", "fileoff")):
            if values["vmaddr"] <= address < values["vmaddr"] + values["vmsize"]:
                return values
    raise RuntimeError(f"no Mach-O segment contains {address:#x}")


def io80211_data_mapping(kernel_collection):
    lines = output("kmutil", "inspect", "--show-fileset-entries", "-B",
                   str(kernel_collection)).splitlines()
    inside = False
    for line in lines:
        if "LC_FILESET_ENTRY" in line:
            if inside:
                break
            inside = "entry:com.apple.iokit.IO80211Family" in line
            continue
        if inside and "segment '__DATA'" in line:
            match = re.search(r"vmaddr:(0x[0-9a-f]+).*fileoff:([0-9]+)", line)
            if match:
                return int(match.group(1), 16), int(match.group(2))
    raise RuntimeError("IO80211Family __DATA mapping not found")


def external_relocations(binary):
    result = {}
    for line in output("otool", "-rv", str(binary)).splitlines():
        fields = line.split()
        if (len(fields) >= 8 and re.fullmatch(r"[0-9a-fA-F]{8}", fields[0])
                and fields[4] == "True"):
            result[int(fields[0], 16)] = fields[-1]
    return result


def read_slots(path, offset):
    with path.open("rb") as stream:
        stream.seek(offset)
        data = stream.read(VTABLE_SLOTS * 8)
    if len(data) != VTABLE_SLOTS * 8:
        raise RuntimeError("truncated vtable")
    return struct.unpack("<" + "Q" * VTABLE_SLOTS, data)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_native_virtual_interface_abi.py BOOT_KC AIC_BINARY")
    kernel_collection = Path(sys.argv[1])
    binary = Path(sys.argv[2])
    kernel_symbols = symbols(kernel_collection)
    binary_symbols = symbols(binary)
    reverse_kernel = {name: address for address, name in kernel_symbols.items()}
    reverse_binary = {name: address for address, name in binary_symbols.items()}

    apple_address = reverse_kernel[APPLE_VTABLE]
    data_vmaddr, data_fileoff = io80211_data_mapping(kernel_collection)
    apple_slots = read_slots(
        kernel_collection, data_fileoff + apple_address - data_vmaddr)

    # Fileset chained pointers store a low address plus a collection bias.
    destructor_raw = apple_slots[2] & 0xFFFFFFFF
    chained_bias = reverse_kernel[APPLE_DTOR] - KERNEL_HIGH - destructor_raw
    apple_names = []
    for raw in apple_slots:
        address = 0 if raw == 0 else KERNEL_HIGH + (raw & 0xFFFFFFFF) + chained_bias
        apple_names.append(kernel_symbols.get(address, f"{address:#x}"))

    aic_address = reverse_binary[AIC_VTABLE]
    segment = segment_for_address(binary, aic_address)
    aic_slots = read_slots(
        binary, segment["fileoff"] + aic_address - segment["vmaddr"])
    relocations = external_relocations(binary)
    aic_names = []
    for index, raw in enumerate(aic_slots):
        slot_address = aic_address + index * 8
        aic_names.append(relocations.get(
            slot_address, binary_symbols.get(raw, f"{raw:#x}")))

    # Object identity slots must differ. The only abstract Apple slot is the
    # hardware MAC setter implemented by AICNativeAWDLInterface.
    identity_slots = {0, 1, 2, 3, 9}
    mismatches = []
    for index, (apple, aic) in enumerate(zip(apple_names, aic_names)):
        if index in identity_slots or apple == "___cxa_pure_virtual":
            continue
        if apple != aic:
            mismatches.append((index, apple, aic))
    if mismatches:
        for index, apple, aic in mismatches:
            print(f"slot {index}: Apple={apple} AIC={aic}", file=sys.stderr)
        raise SystemExit(f"AWDL vtable mismatch count: {len(mismatches)}")
    print(f"AWDL vtable: {VTABLE_SLOTS} slots checked, 0 mismatches")


if __name__ == "__main__":
    main()
