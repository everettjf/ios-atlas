#!/usr/bin/env python3
"""Export reviewed mount-level counts without private device paths."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path

from collect_live_device import private_path
from export_live_device import inside


ROOTS = {
    "/": ("Jailbreak namespace", "reviewed_paths", "namespace"),
    "/rootfs": ("Base root filesystem", "reviewed_paths", "apfs"),
    "/rootfs/System/Developer": ("Developer volume", "reviewed_paths", "apfs"),
    "/rootfs/dev": ("Device nodes", "counts_only", "devfs"),
    "/rootfs/private/preboot": ("Preboot volume", "counts_only", "apfs"),
    "/rootfs/private/var": ("Data volume", "counts_only", "apfs"),
    "/rootfs/private/var/MobileSoftwareUpdate": ("Software update volume", "counts_only", "apfs"),
    "/rootfs/private/var/hardware": ("Hardware data volume", "counts_only", "apfs"),
    "/rootfs/private/var/mobile": ("Mobile data volume", "counts_only", "apfs"),
    "/rootfs/private/var/mobile/Library/LiveFiles": ("LiveFiles virtual filesystem", "counts_only", "lifs"),
    "/rootfs/private/var/wireless/baseband_data": ("Baseband data volume", "counts_only", "apfs"),
    "/rootfs/private/xarts": ("xARTS volume", "counts_only", "apfs"),
}
ERROR = re.compile(r"^find: [‘'](.+)[’']: Operation not permitted$")


def load(path: Path) -> dict:
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def export(manifest_path: Path, device_catalog_path: Path) -> dict:
    manifest_path = private_path(manifest_path)
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    public = load(device_catalog_path)
    roots = manifest.get("roots", [])
    scans = manifest.get("scans", {})
    if (manifest.get("kind") != "private_live_device_snapshot" or
            manifest.get("schema_version") != 1 or
            public.get("kind") != "live_device_public_paths" or
            public.get("private_manifest_sha256") != hashlib.sha256(raw).hexdigest() or
            public.get("build") != manifest.get("build") or
            public.get("product_type") != manifest.get("product_type") or
            public.get("observed_at_utc") != manifest.get("observed_at_utc") or
            public.get("snapshot_root_count") != len(ROOTS) or
            len(roots) != len(ROOTS) or
            {item["path"] for item in roots} != set(ROOTS) or
            set(scans) != set(ROOTS)):
        raise ValueError("private snapshot and public device catalog differ")

    rows = []
    for root in ROOTS:
        label, publication, mount_type = ROOTS[root]
        discovered = next(item for item in roots if item["path"] == root)
        scan = scans[root]
        if (discovered.get("mount_type") != mount_type or
                scan.get("path") != root or
                scan.get("status") not in ("complete", "partial") or
                not isinstance(scan.get("entry_count"), int) or
                scan["entry_count"] < 0 or
                not isinstance(scan.get("type_counts"), dict) or
                sum(scan["type_counts"].values()) != scan["entry_count"] or
                not isinstance(scan.get("stat_error_count"), int) or
                scan["stat_error_count"] != 0 or
                not isinstance(scan.get("find_exit_code"), int)):
            raise ValueError("invalid private mount scan summary")
        key = hashlib.sha256(root.encode("utf-8", "surrogateescape")).hexdigest()[:16]
        if scan.get("file") != f"root-{key}.jsonl.gz":
            raise ValueError("private scan file identity differs")
        source = manifest_path.parent / scan["file"]
        stderr = manifest_path.parent / f"root-{key}.stderr"
        if (not source.is_file() or not stderr.is_file() or
                hashlib.sha256(source.read_bytes()).hexdigest() != scan.get("sha256") or
                hashlib.sha256(stderr.read_bytes()).hexdigest() != scan.get("stderr_sha256") or
                stderr.stat().st_size != scan.get("stderr_bytes")):
            raise ValueError("private scan or error hash differs")
        errors = stderr.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in errors:
            match = ERROR.fullmatch(line)
            if not match or not inside(match[1], root):
                raise ValueError("unreviewed private scan error")
        if (scan["status"] == "complete") != (scan["find_exit_code"] == 0 and not errors):
            raise ValueError("scan status disagrees with access errors")
        rows.append({"label": label, "mount_type": mount_type,
                     "publication": publication, "status": scan["status"],
                     "observations": scan["entry_count"],
                     "regular_files": scan["type_counts"].get("file", 0),
                     "access_errors": len(errors)})

    result = {"schema_version": 1, "kind": "live_mount_coverage_public",
              "source": "reviewed_private_live_device_snapshot",
              "build": manifest["build"], "product_type": manifest["product_type"],
              "observed_at_utc": manifest["observed_at_utc"],
              "private_manifest_sha256": hashlib.sha256(raw).hexdigest(),
              "public_path_count": public["entry_count"],
              "roots": rows,
              "totals": {"root_count": len(rows),
                         "complete_root_count": sum(row["status"] == "complete" for row in rows),
                         "partial_root_count": sum(row["status"] == "partial" for row in rows),
                         "observations": sum(row["observations"] for row in rows),
                         "regular_files": sum(row["regular_files"] for row in rows),
                         "access_errors": sum(row["access_errors"] for row in rows)}}
    if result["totals"]["complete_root_count"] != public["complete_root_count"]:
        raise ValueError("public complete-root count differs")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--device-catalog", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    data = export(args.manifest, args.device_catalog)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=True, sort_keys=True,
                                     separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{data['totals']['root_count']} roots, "
          f"{data['totals']['access_errors']} access errors -> {args.output}")


if __name__ == "__main__":
    main()
