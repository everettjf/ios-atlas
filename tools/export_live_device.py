#!/usr/bin/env python3
"""Derive a small, privacy-reviewed public path catalog from a private snapshot.

The input contains every scanned device path and must remain under .local. The
allowlist selects only known system and jailbreak roots; no user/app data path,
UID, inode, symlink target, or private mount source enters the export.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from collect_live_device import private_path


SAFE_PREFIXES = (
    "/rootfs/Applications", "/rootfs/Library", "/rootfs/System",
    "/rootfs/bin", "/rootfs/sbin", "/rootfs/usr", "/rootfs/private/etc",
    "/Applications", "/Library", "/System", "/basebin", "/bin",
    "/etc", "/lib", "/sbin", "/usr",
)
KINDS = {"file", "directory", "symlink", "character_device", "block_device",
         "socket", "fifo", "unknown"}
DEVICE_SPECIFIC_PATH = re.compile(r"^/basebin/systemhook-[0-9A-Fa-f]{16}\.dylib$")


def inside(path: str, prefix: str) -> bool:
    return ((prefix == "/" and path.startswith("/")) or
            path == prefix or path.startswith(prefix + "/"))


def check_prefix(prefix: str) -> None:
    if (not isinstance(prefix, str) or not prefix.startswith("/") or
            any(part in ("", ".", "..") for part in prefix[1:].split("/")) or
            not any(inside(prefix, safe) for safe in SAFE_PREFIXES)):
        raise ValueError(f"public prefix is outside the reviewed system/jailbreak roots: {prefix}")


def has_private_characters(value: str) -> bool:
    return any(0xD800 <= ord(char) <= 0xDFFF or ord(char) < 32 for char in value)


def export(manifest_path: Path, allowlist_path: Path) -> dict:
    manifest_path = private_path(manifest_path)
    allowlist_path = private_path(allowlist_path)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    allowlist = json.loads(allowlist_path.read_text())
    if (manifest.get("schema_version") != 1 or
            manifest.get("kind") != "private_live_device_snapshot" or
            allowlist.get("schema_version") != 1 or
            not isinstance(allowlist.get("prefixes"), list) or
            not allowlist["prefixes"]):
        raise ValueError("invalid snapshot or public allowlist")
    prefixes = allowlist["prefixes"]
    if len(prefixes) != len(set(prefixes)):
        raise ValueError("duplicate public prefix")
    for prefix in prefixes:
        check_prefix(prefix)
    if not isinstance(manifest.get("scans"), dict) or not manifest.get("roots"):
        raise ValueError("snapshot has no scan manifest")
    root_paths = [item["path"] for item in manifest["roots"]]
    if len(root_paths) != len(set(root_paths)):
        raise ValueError("snapshot has duplicate mount roots")
    for prefix in prefixes:
        ancestors = [root for root in root_paths if inside(prefix, root)]
        if not ancestors:
            raise ValueError(f"public prefix has no discovered mount root: {prefix}")
        covering = max(ancestors, key=len)
        relevant = [root for root in root_paths if root == covering or inside(root, prefix)]
        if any(manifest["scans"].get(root, {}).get("status") != "complete" for root in relevant):
            raise ValueError(f"public prefix has incomplete mount coverage: {prefix}")
    rows = {}
    coverage = []
    unpublished_entry_count = 0
    for item in manifest["roots"]:
        root = item["path"]
        scan = manifest["scans"].get(root)
        if not scan or scan.get("status") != "complete":
            coverage.append({"status": scan.get("status", "not_scanned") if scan else "not_scanned",
                             "published": False})
            if scan:
                unpublished_entry_count += scan["entry_count"]
            continue
        source = manifest_path.parent / scan["file"]
        if source.resolve().parent != manifest_path.parent.resolve() or not source.is_file():
            raise ValueError("scan file escaped private snapshot directory")
        if hashlib.sha256(source.read_bytes()).hexdigest() != scan["sha256"]:
            raise ValueError("private scan hash differs from manifest")
        count = 0
        published = 0
        with gzip.open(source, "rt", encoding="ascii") as stream:
            for line in stream:
                row = json.loads(line)
                if len(row) != 10 or row[1] not in KINDS or not isinstance(row[0], str):
                    raise ValueError("invalid private device record")
                path, kind, size = row[:3]
                if not inside(path, root):
                    raise ValueError("scan path outside recorded root")
                count += 1
                if not any(inside(path, prefix) for prefix in prefixes):
                    unpublished_entry_count += 1
                    continue
                if DEVICE_SPECIFIC_PATH.fullmatch(path):
                    unpublished_entry_count += 1
                    continue
                if has_private_characters(path) or kind == "unknown":
                    raise ValueError("public candidate needs manual path/stat review")
                public = [path, kind, size if kind == "file" else None]
                if path in rows and rows[path] != public:
                    raise ValueError("different records for the same public path")
                rows[path] = public
                published += 1
        if count != scan["entry_count"]:
            raise ValueError("private scan count differs from manifest")
        coverage.append({"status": "complete", "published": published > 0,
                         "entry_count": count, "published_entry_count": published})
    if not rows:
        raise ValueError("allowlist selected no device paths")
    missing_prefixes = [prefix for prefix in prefixes if not any(inside(path, prefix) for path in rows)]
    if missing_prefixes:
        raise ValueError(f"public prefix has no complete matching scan: {missing_prefixes}")
    return {"schema_version": 1, "kind": "live_device_public_paths",
            "source": "trusted_device_private_snapshot_privacy_export",
            "product_type": manifest["product_type"], "build": manifest["build"],
            "observed_at_utc": manifest["observed_at_utc"],
            "private_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "reviewed_prefixes": prefixes, "entry_count": len(rows),
            "type_counts": dict(Counter(row[1] for row in rows.values())),
            "snapshot_root_count": len(manifest["roots"]),
            "complete_root_count": sum(item["status"] == "complete" for item in coverage),
            "unpublished_entry_count": unpublished_entry_count,
            "entries": [rows[path] for path in sorted(rows)]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--allowlist", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = private_path(args.output)
    data = export(args.manifest, args.allowlist)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode() + b"\n"
    output.write_bytes(gzip.compress(payload, mtime=0))
    print(f"{data['entry_count']} reviewed public paths -> {output}")


if __name__ == "__main__":
    main()
