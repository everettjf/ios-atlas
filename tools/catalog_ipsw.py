#!/usr/bin/env python3
"""Index every member of an exact IPSW archive without publishing its contents."""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def kind(path: str, is_dir: bool) -> str:
    if is_dir:
        return "directory"
    if path.startswith("kernelcache."):
        return "kernelcache"
    if path.endswith(".trustcache"):
        return "trustcache"
    if path.endswith((".dmg", ".dmg.aea")):
        return "disk_image"
    if path.endswith((".plist", ".xml")):
        return "manifest_or_metadata"
    if path.startswith("Firmware/"):
        return "firmware_payload"
    return "other"


def build(args: argparse.Namespace) -> None:
    firmware_hash = sha256_file(args.ipsw)
    if firmware_hash != args.firmware_sha256.lower():
        raise ValueError("IPSW SHA-256 does not match requested source")
    with ZipFile(args.ipsw) as archive:
        manifest = plistlib.loads(archive.read("BuildManifest.plist"))
        if (manifest["ProductBuildVersion"] != args.build or
                args.product not in manifest["SupportedProductTypes"]):
            raise ValueError("BuildManifest product or build mismatch")
        roles = defaultdict(set)
        variants = []
        for identity in manifest["BuildIdentities"]:
            variant = identity["Info"]["Variant"]
            variants.append(variant)
            for role, entry in identity["Manifest"].items():
                path = entry.get("Info", {}).get("Path")
                if path:
                    roles[path].add((variant, role))
        entries = []
        names = set()
        for item in archive.infolist():
            name = item.filename
            if name in names:
                raise ValueError(f"duplicate archive member: {name}")
            names.add(name)
            digest = None
            if not item.is_dir():
                sha = hashlib.sha256()
                with archive.open(item, "r") as stream:
                    for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                        sha.update(block)
                digest = sha.hexdigest()
            entries.append({
                "path": name,
                "kind": kind(name, item.is_dir()),
                "size": item.file_size,
                "compressed_size": item.compress_size,
                "crc32": f"{item.CRC:08x}",
                "sha256": digest,
                "manifest_roles": [list(pair) for pair in sorted(roles[name])],
            })
    missing = sorted(path for path in roles if path not in names)
    if missing:
        raise ValueError(f"BuildManifest references {len(missing)} absent archive members: {missing[:3]}")
    entries.sort(key=lambda entry: entry["path"])
    counts = {category: sum(item["kind"] == category for item in entries)
              for category in sorted({item["kind"] for item in entries})}
    output = {
        "schema_version": 1,
        "kind": "ipsw_archive",
        "source": "official_apple_restore_ipsw",
        "product_type": args.product,
        "build": args.build,
        "version": manifest["ProductVersion"],
        "firmware_sha256": firmware_hash,
        "entry_count": len(entries),
        "file_count": sum(item["kind"] != "directory" for item in entries),
        "total_uncompressed_size": sum(item["size"] for item in entries),
        "variants": sorted(set(variants)),
        "category_counts": counts,
        "entries": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=True,
                                      separators=(",", ":"), sort_keys=True) + "\n")
    print(f"{len(entries)} archive entries, {output['file_count']} files -> {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ipsw", required=True, type=Path)
    parser.add_argument("--product", required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--firmware-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    build(parser.parse_args())


if __name__ == "__main__":
    main()
