#!/usr/bin/env python3
"""Verify selected static SpringBoard startup instructions in an exact cache extraction."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from pathlib import Path


EXPECTED_SHA256 = "7732a59763b6fa34a52bfe8531d6dc0fcfa69761f6a96f438c0cda3363bb20be"
EXPECTED_UUID = "8676BE2A-9484-3492-888E-7DE10333250F"

# Address -> instruction fragment. These checks establish static call sites, not runtime execution.
INSTRUCTIONS = {
    0x21D604C88: "str\tx1, [sp, #0x60]",
    0x21D604C8C: "str\tw0, [sp, #0x5c]",
    0x21D605C20: "cbz\tx19, 0x21d605cb8",
    0x21D605C30: 'bl\t"_objc_msgSend$compareBuildVersion:withPrecision:"',
    0x21D605C40: "tbnz\tw8, #0x0, 0x21d605c60",
    0x21D605C4C: "bl\t_objc_msgSend$deleteAllSystemSnapshots",
    0x21D605C5C: 'bl\t"_objc_msgSend$_setClearSystemAppSnapshotsWhenLoaded:"',
    0x21D605C70: 'bl\t"_objc_msgSend$compareBuildVersionString:withPrecision:"',
    0x21D605C88: 'bl\t"_objc_msgSend$_setClearAllLegacySnapshotsWhenLoaded:"',
    0x21D605C9C: 'bl\t"_objc_msgSend$compareBuildVersionString:withPrecision:"',
    0x21D605CB4: 'bl\t"_objc_msgSend$_setClearAllLegacySnapshotsWhenLoaded:"',
    0x21D605CD8: "bl\t_objc_msgSend$migrateAndRemoveOldDefaults",
    0x21D605D2C: 'bl\t"_objc_msgSend$setLastSystemBuildVersion:"',
    0x21D605EC4: 'bl\t"_objc_msgSend$setLastRestoreIdentifier:"',
    0x21D606054: 'bl\t"_objc_msgSend$removeAllImagesWithCompletion:"',
    0x21D606064: "bl\t_objc_msgSend$earlyInitialization",
    0x21D6060F8: "ldr\tw0, [sp, #0x5c]",
    0x21D6060FC: "ldr\tx1, [sp, #0x60]",
    0x21D606104: "bl\t0x2225247a0",
}


def run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path, help="local ipsw dyld extract derivative")
    args = parser.parse_args()

    digest = hashlib.sha256(args.binary.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(f"unexpected binary SHA-256: {digest}")

    uuid = run("xcrun", "dwarfdump", "--uuid", str(args.binary))
    if EXPECTED_UUID not in uuid:
        raise ValueError(f"unexpected Mach-O UUID: {uuid.strip()}")

    disassembly = run("xcrun", "llvm-objdump", "-m", "-d", "--dis-symname",
                      "_SBSystemAppMain", str(args.binary))
    if "_SBSystemAppMain:\n21d604c60:" not in disassembly:
        raise ValueError("disassembly did not start at the expected function")
    lines = {}
    for line in disassembly.splitlines():
        match = re.match(r"^([0-9a-f]+):\t", line)
        if match:
            lines[int(match.group(1), 16)] = line
    for address, instruction in INSTRUCTIONS.items():
        line = lines.get(address, "")
        if instruction not in line:
            raise ValueError(f"instruction mismatch at 0x{address:x}: {line}")

    symbols = run("xcrun", "llvm-nm", "-n", str(args.binary))
    if not re.search(r"^00000002225247a0 \? _UIApplicationMain$", symbols, re.M):
        raise ValueError("branch target is not identified as _UIApplicationMain")

    print(f"Verified {len(INSTRUCTIONS)} instructions in _SBSystemAppMain")
    print(f"Mach-O UUID: {EXPECTED_UUID}; SHA-256: {EXPECTED_SHA256}")
    print("Direct branch at 0x21d606104 targets _UIApplicationMain at 0x2225247a0")
    print("Scope: static extracted image only; no device execution verified")


if __name__ == "__main__":
    main()
