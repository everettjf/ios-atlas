#!/usr/bin/env python3
"""Index privately acquired jailbreak Mach-O bytes after exact device hash checks.

Inputs are read-only and must remain under ignored .local. The output is a
privacy-reviewed candidate; tools/build_site.py checks it again before use.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from catalog_standalone_macho import FAT_MAGICS, MAGICS, THIN_MAGICS, fat_slices, parse_thin
from export_live_device import DEVICE_SPECIFIC_PATH, check_prefix, has_private_characters
from collect_live_device import private_path


def nul_items(path: Path) -> list[bytes]:
    raw = private_path(path).read_bytes()
    if not raw.endswith(b"\0"):
        raise ValueError("truncated NUL-delimited acquisition")
    return raw.split(b"\0")[:-1]


def catalog(manifest_path: Path, file_types_path: Path, hashes_path: Path,
            binary_root: Path) -> dict:
    manifest_path = private_path(manifest_path)
    binary_root = private_path(binary_root)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    scan = manifest.get("scans", {}).get("/")
    if (manifest.get("kind") != "private_live_device_snapshot" or
            not scan or scan.get("status") != "complete"):
        raise ValueError("complete jailbreak-root scan required")
    root_file = manifest_path.parent / scan["file"]
    if root_file.resolve().parent != manifest_path.parent.resolve() or not root_file.is_file():
        raise ValueError("jailbreak scan escaped private snapshot")
    if hashlib.sha256(root_file.read_bytes()).hexdigest() != scan["sha256"]:
        raise ValueError("jailbreak scan hash changed")
    files = {}
    with gzip.open(root_file, "rt", encoding="ascii") as stream:
        for line in stream:
            path, kind, size, *_ = json.loads(line)
            if kind == "file":
                files[path] = size
    types = nul_items(file_types_path)
    if len(types) % 2:
        raise ValueError("file-type record pair is truncated")
    descriptions = {}
    for index in range(0, len(types), 2):
        path = types[index].decode("utf-8", "surrogateescape")
        if path not in files or path in descriptions:
            raise ValueError("file-type result differs from the private root scan")
        descriptions[path] = types[index + 1]
    if set(descriptions) != set(files):
        raise ValueError("file-type pass did not cover every regular jailbreak-root file")
    selected = {path for path, description in descriptions.items()
                if b"Mach-O" in description or b"universal binary" in description}
    hashes = {}
    for row in nul_items(hashes_path):
        digest, separator, encoded_path = row.partition(b"  ")
        if separator != b"  " or len(digest) != 64:
            raise ValueError("invalid device hash record")
        path = encoded_path.decode("utf-8", "surrogateescape")
        if path in hashes or any(char not in b"0123456789abcdef" for char in digest):
            raise ValueError("duplicate or invalid device hash")
        hashes[path] = digest.decode("ascii")
    if set(hashes) != selected:
        raise ValueError("device hashes do not cover the exact Mach-O candidate set")
    records = []
    withheld_count = 0
    for path in sorted(selected):
        withhold = bool(DEVICE_SPECIFIC_PATH.fullmatch(path))
        if (path.startswith("/rootfs/") or has_private_characters(path) or
                any(part in ("", ".", "..") for part in path[1:].split("/"))):
            raise ValueError("unsafe live Mach-O path")
        check_prefix(path)
        candidate = binary_root / path.lstrip("/")
        local = candidate.resolve()
        if (candidate.is_symlink() or binary_root not in local.parents or
                not local.is_file()):
            raise ValueError("acquired binary missing or outside private root")
        size = local.stat().st_size
        if size != files[path]:
            raise ValueError("acquired binary size differs from live scan")
        digest = hashlib.sha256(local.read_bytes()).hexdigest()
        if digest != hashes[path]:
            raise ValueError("acquired binary differs from device-side SHA-256")
        with local.open("rb") as stream:
            magic = stream.read(4)
        if magic not in MAGICS:
            raise ValueError("file classification has no Mach-O magic")
        if magic in FAT_MAGICS:
            parts = fat_slices(local)
            if not all(bytes.fromhex(part_magic) in THIN_MAGICS
                       for _, _, part_magic in parts):
                raise ValueError("mixed or non-Mach-O fat container")
            slices = [parse_thin(local, offset, length) for offset, length, _ in parts]
        else:
            slices = [parse_thin(local, 0, size)]
        if withhold:
            withheld_count += 1
        else:
            records.append({"path": path, "size": size, "sha256": digest,
                            "header_magic": magic.hex(), "slices": slices})
    return {"schema_version": 1, "kind": "live_jailbreak_macho_inventory",
            "source": "verified_live_device_macho_bytes",
            "product_type": manifest["product_type"], "build": manifest["build"],
            "snapshot_observed_at_utc": manifest["observed_at_utc"],
            "private_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "classification_file_count": len(descriptions),
            "macho_file_count": len(records), "withheld_identifier_count": withheld_count,
            "failed_count": 0, "failures": [],
            "records": records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--file-types", required=True, type=Path)
    parser.add_argument("--hashes", required=True, type=Path)
    parser.add_argument("--binary-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = private_path(args.output)
    data = catalog(args.manifest, args.file_types, args.hashes, args.binary_root)
    payload = json.dumps(data, ensure_ascii=True, separators=(",", ":"),
                         sort_keys=True).encode() + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(gzip.compress(payload, mtime=0))
    print(f"{data['macho_file_count']} verified live Mach-O files -> {output}")


if __name__ == "__main__":
    main()
