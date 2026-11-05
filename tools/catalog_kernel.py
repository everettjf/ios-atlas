#!/usr/bin/env python3
"""Create a source-bound kernelcache metadata catalog from local Mach-O derivatives."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ipsw_json(tool: str, *args: str) -> object:
    result = subprocess.run([tool, *args], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def describe(path: Path, variant: str, archive_entry: dict, tool: str) -> dict:
    loads = ipsw_json(tool, "macho", "info", str(path), "--json", "--loads")
    header = loads["header"]
    if header["type"] != "FILESET" or header["subcpu"] != "ARM64e":
        raise ValueError(f"unexpected kernel Mach-O type for {variant}")
    uuids = [item["uuid"] for item in loads["loads"] if item["load_cmd"] == "LC_UUID"]
    if len(uuids) != 1:
        raise ValueError(f"kernel UUID count is not one for {variant}")
    version = ipsw_json(tool, "kernel", "version", "-j", str(path))["kernel"]
    raw_kexts = ipsw_json(tool, "kernel", "kexts", str(path), "--json")
    kexts = []
    seen = set()
    for item in raw_kexts:
        identifier = item["id"]
        if identifier in seen:
            raise ValueError(f"duplicate kext identifier in {variant}: {identifier}")
        seen.add(identifier)
        kexts.append({"id": identifier,
                      "name": item.get("name"),
                      "version": item.get("version"),
                      "bundle_path": item.get("bundle_path"),
                      "dependencies": item.get("os_bundle_libraries") or {}})
    kexts.sort(key=lambda item: item["id"])
    return {"variant": variant,
            "archive_path": archive_entry["path"],
            "archive_sha256": archive_entry["sha256"],
            "decompressed_macho_sha256": sha256_file(path),
            "macho_uuid": uuids[0],
            "macho_type": header["type"],
            "macho_architecture": header["subcpu"],
            "darwin": version["darwin"],
            "xnu": version["xnu"],
            "kernel_build_type": version["type"],
            "cpu": version["cpu"],
            "fileset_entry_count": sum(item["load_cmd"] == "LC_FILESET_ENTRY" for item in loads["loads"]),
            "kext_count": len(kexts),
            "kexts": kexts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-catalog", required=True, type=Path)
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--research", required=True, type=Path)
    parser.add_argument("--tool", default="ipsw")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    archive = json.loads(args.archive_catalog.read_text())
    entries = {item["path"]: item for item in archive["entries"]}
    images = []
    for variant, path in (("release", args.release), ("research", args.research)):
        name = f"kernelcache.{variant}.iphone12b"
        if name not in entries or entries[name]["kind"] != "kernelcache":
            raise ValueError(f"missing {variant} kernelcache in IPSW catalog")
        images.append(describe(path, variant, entries[name], args.tool))
    output = {"schema_version": 1,
              "kind": "kernelcache_metadata",
              "source": "official_ipsw_kernelcache_derivatives",
              "product_type": archive["product_type"],
              "build": archive["build"],
              "firmware_sha256": archive["firmware_sha256"],
              "images": images}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=True,
                                      separators=(",", ":"), sort_keys=True) + "\n")
    print(f"{len(images)} kernelcaches, {sum(item['kext_count'] for item in images)} kext records -> {args.output}")


if __name__ == "__main__":
    main()
