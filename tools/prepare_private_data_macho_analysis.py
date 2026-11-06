#!/usr/bin/env python3
"""Prepare a private, hash-verified input for existing live Mach-O analyzers.

Hard links avoid copying acquired bytes. The catalog and path-shaped link tree
must stay in ignored .local; no output from this tool is a site input.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

from collect_live_device import private_path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def choose(records: list[dict], limit: int) -> list[dict]:
    if not limit or limit >= len(records):
        return records
    # Cover file types and architectures before filling remaining slots.
    buckets: dict[str, list[dict]] = {}
    for item in records:
        kind = item["slices"][0]["file_type"]
        buckets.setdefault(kind, []).append(item)
    for bucket in buckets.values():
        bucket.sort(key=lambda item: (len(item["slices"]) == 1,
                                      item["acquired_size"],
                                      hashlib.sha256(item["path"].encode()).digest()))
    selected: list[dict] = []
    while len(selected) < limit and any(buckets.values()):
        for kind in sorted(buckets):
            if buckets[kind] and len(selected) < limit:
                selected.append(buckets[kind].pop(0))
    return selected


def prepare(args: argparse.Namespace) -> dict:
    manifest_path = private_path(args.acquisition)
    output_dir = private_path(args.output_dir)
    source_bytes = manifest_path.read_bytes()
    source = json.loads(source_bytes)
    records = source.get("records")
    if (source.get("kind") != "private_live_data_macho_acquisition" or
            source.get("product_type") != "iPhone12,1" or
            source.get("build") != "23A355" or
            not isinstance(records, list) or len(records) != 306 or
            any(item.get("status") != "verified_and_parsed" for item in records)):
        raise ValueError("private acquisition is incomplete or differs from this device")
    selected = choose(records, args.limit)
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    binary_root = output_dir / "binary-root"
    binary_root.mkdir(exist_ok=True)
    os.chmod(binary_root, 0o700)
    originals = manifest_path.parent / "files"
    rows = []
    seen_paths = set()
    for item in selected:
        path = item["path"]
        relative = Path(path.lstrip("/"))
        name = item["local_file"]
        if (not path.startswith("/rootfs/private/var/") or
                not relative.parts or ".." in relative.parts or
                path in seen_paths or Path(name).name != name or
                not name.endswith(".bin")):
            raise ValueError("unsafe or duplicate private candidate")
        seen_paths.add(path)
        original = originals / name
        expected = item["device_sha256"]
        if (original.is_symlink() or not original.is_file() or
                original.stat().st_size != item["acquired_size"] or
                item["local_sha256"] != expected or
                sha256(original) != expected):
            raise ValueError("private acquired bytes differ from device hash")
        target = binary_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if binary_root not in target.parent.resolve().parents and target.parent.resolve() != binary_root:
            raise ValueError("private analysis path escapes its root")
        if target.exists():
            if target.is_symlink() or not target.is_file() or not os.path.samefile(original, target):
                raise ValueError("private analysis hard link differs")
        else:
            os.link(original, target)
        rows.append({"path": path, "size": item["acquired_size"],
                     "sha256": expected, "slices": item["slices"]})
    catalog = {"schema_version": 1, "kind": "live_jailbreak_macho_inventory",
               "source": "verified_live_device_macho_bytes",
               "product_type": source["product_type"], "build": source["build"],
               "macho_file_count": len(rows), "records": rows,
               "private_acquisition_sha256": hashlib.sha256(source_bytes).hexdigest(),
               "scope": "private_data_volume_analysis_only"}
    catalog_path = output_dir / "input-catalog.json.gz"
    catalog_path.write_bytes(gzip.compress(json.dumps(
        catalog, sort_keys=True, separators=(",", ":")).encode() + b"\n", mtime=0))
    os.chmod(catalog_path, 0o600)
    objc_rows = [row for row in rows if all(
        part["file_type"] != "dsym" for part in row["slices"])]
    objc_catalog = {**catalog, "macho_file_count": len(objc_rows),
                    "records": objc_rows,
                    "excluded_dsym_count": len(rows) - len(objc_rows)}
    objc_path = output_dir / "objc-input-catalog.json.gz"
    objc_path.write_bytes(gzip.compress(json.dumps(
        objc_catalog, sort_keys=True, separators=(",", ":")).encode() + b"\n", mtime=0))
    os.chmod(objc_path, 0o600)
    return {"files": len(rows), "slices": sum(len(row["slices"]) for row in rows),
            "types": dict(Counter(part["file_type"] for row in rows
                                  for part in row["slices"])),
            "private_catalog": str(catalog_path),
            "private_objc_catalog": str(objc_path),
            "objc_not_applicable_dsym_files": len(rows) - len(objc_rows),
            "private_binary_root": str(binary_root)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be nonnegative")
    summary = prepare(args)
    # Paths here are under .local; do not print any private device path.
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
