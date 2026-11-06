#!/usr/bin/env python3
"""Index Mach-O files acquired from the verified live Developer mount."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from catalog_live_jailbreak_macho import nul_items
from catalog_standalone_macho import FAT_MAGICS, MAGICS, THIN_MAGICS, fat_slices, parse_thin
from collect_live_device import private_path
from export_live_device import has_private_characters


MOUNT = "/rootfs/System/Developer"


def catalog(manifest_path: Path, types_path: Path, hashes_path: Path,
            binary_root: Path) -> dict:
    manifest_path = private_path(manifest_path)
    binary_root = private_path(binary_root)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    scan = manifest.get("scans", {}).get(MOUNT)
    if (manifest.get("kind") != "private_live_device_snapshot" or
            not scan or scan.get("status") != "complete"):
        raise ValueError("complete Developer mount scan required")
    source = manifest_path.parent / scan["file"]
    if (source.resolve().parent != manifest_path.parent.resolve() or
            hashlib.sha256(source.read_bytes()).hexdigest() != scan["sha256"]):
        raise ValueError("Developer mount snapshot changed")
    files = {}
    with gzip.open(source, "rt", encoding="ascii") as stream:
        for line in stream:
            path, kind, size, *_ = json.loads(line)
            if kind == "file":
                if path in files:
                    raise ValueError("duplicate Developer mount path")
                files[path] = size
    if len(files) != scan["type_counts"]["file"]:
        raise ValueError("Developer mount file count differs")
    parts = nul_items(types_path)
    if len(parts) != 2 * len(files):
        raise ValueError("file-type coverage differs from live scan")
    descriptions = {}
    for index in range(0, len(parts), 2):
        path = parts[index].decode("utf-8", "surrogateescape")
        if path not in files or path in descriptions:
            raise ValueError("file-type path differs from live scan")
        descriptions[path] = parts[index + 1]
    selected = {path for path, description in descriptions.items()
                if b"Mach-O" in description or b"universal binary" in description}
    hashes = {}
    for row in nul_items(hashes_path):
        digest, separator, encoded = row.partition(b"  ")
        path = encoded.decode("utf-8", "surrogateescape")
        if (separator != b"  " or len(digest) != 64 or
                any(char not in b"0123456789abcdef" for char in digest) or
                path in hashes):
            raise ValueError("invalid or duplicate device hash")
        hashes[path] = digest.decode("ascii")
    if set(descriptions) != set(files) or set(hashes) != selected:
        raise ValueError("hash or file-type pass is incomplete")
    records = []
    for path in sorted(selected):
        if (not path.startswith(MOUNT + "/") or has_private_characters(path) or
                any(part in ("", ".", "..") for part in path[1:].split("/"))):
            raise ValueError("unsafe Developer mount path")
        candidate = binary_root / path.lstrip("/")
        local = candidate.resolve()
        if (candidate.is_symlink() or binary_root not in local.parents or
                not local.is_file() or local.stat().st_size != files[path]):
            raise ValueError("acquired Developer binary missing or changed")
        digest = hashlib.sha256(local.read_bytes()).hexdigest()
        if digest != hashes[path]:
            raise ValueError("acquired binary differs from device-side SHA-256")
        magic = local.read_bytes()[:4]
        if magic not in MAGICS:
            raise ValueError("file-type classification has no Mach-O magic")
        if magic in FAT_MAGICS:
            members = fat_slices(local)
            if not all(bytes.fromhex(part_magic) in THIN_MAGICS
                       for _, _, part_magic in members):
                raise ValueError("mixed or non-Mach-O fat container")
            slices = [parse_thin(local, offset, length)
                      for offset, length, _ in members]
        else:
            slices = [parse_thin(local, 0, files[path])]
        records.append({"path": path, "size": files[path], "sha256": digest,
                        "header_magic": magic.hex(), "slices": slices})
    return {"schema_version": 1, "kind": "live_developer_macho_inventory",
            "source": "verified_live_developer_mount_bytes",
            "product_type": manifest["product_type"], "build": manifest["build"],
            "snapshot_observed_at_utc": manifest["observed_at_utc"],
            "private_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "mount_path": MOUNT, "classification_file_count": len(files),
            "macho_file_count": len(records), "failed_count": 0, "failures": [],
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
    print(f"{data['macho_file_count']} verified Developer mount Mach-O files -> {output}")


if __name__ == "__main__":
    main()
