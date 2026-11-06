#!/usr/bin/env python3
"""Hash private data-volume Mach-O type candidates on the exact live device.

This reads candidate bytes on the phone without copying them. Input and output
contain private app paths and must stay under ignored .local. No path or digest
is printed to stdout or admitted to the public site by this tool.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from catalog_live_jailbreak_macho import nul_items
from collect_live_device import private_path, remote, ssh_prefix


ROOTS = {
    "data": "/rootfs/private/var",
    "mobile_data": "/rootfs/private/var/mobile",
}
HASH = re.compile(rb"[0-9a-f]{64}")


def candidates(manifest: dict, directory: Path, label: str, types_path: Path) -> dict:
    root = ROOTS[label]
    scan = manifest.get("scans", {}).get(root)
    if not scan or scan.get("status") != "partial":
        raise ValueError("expected the recorded partial data-volume scan")
    source = directory / scan["file"]
    if (source.resolve().parent != directory.resolve() or
            hashlib.sha256(source.read_bytes()).hexdigest() != scan["sha256"]):
        raise ValueError("private snapshot file changed")
    files = {}
    with gzip.open(source, "rt", encoding="ascii") as stream:
        for line in stream:
            path, kind, size, *_ = json.loads(line)
            if kind == "file":
                if path in files:
                    raise ValueError("duplicate snapshot file")
                files[path] = size
    if len(files) != scan["type_counts"]["file"]:
        raise ValueError("snapshot regular-file count changed")
    parts = nul_items(types_path)
    if len(parts) % 2:
        raise ValueError("truncated file-type pairs")
    descriptions = {}
    for encoded, description in zip(parts[::2], parts[1::2]):
        path = encoded.decode("utf-8", "surrogateescape")
        if not path.startswith(root + "/") or path in descriptions:
            raise ValueError("file-type path outside the selected private root or duplicated")
        descriptions[path] = description
    selected = sorted(path for path, description in descriptions.items()
                      if b"Mach-O" in description or b"universal binary" in description)
    if any(path not in files for path in selected):
        raise ValueError("candidate absent from the private snapshot")
    return {
        "root_label": label,
        "snapshot_file_sha256": scan["sha256"],
        "file_types_sha256": hashlib.sha256(private_path(types_path).read_bytes()).hexdigest(),
        "snapshot_file_count": len(files),
        "type_file_count": len(descriptions),
        "appeared_count": len(descriptions.keys() - files.keys()),
        "disappeared_count": len(files.keys() - descriptions.keys()),
        "candidates": [{"path": path, "snapshot_size": files[path]}
                       for path in selected],
    }


def parse_hashes(payload: bytes, requested: set[bytes]) -> dict[bytes, str]:
    if payload and not payload.endswith(b"\0"):
        raise ValueError("truncated device hash output")
    records = {}
    for row in payload.split(b"\0")[:-1]:
        digest, separator, path = row.partition(b"  ")
        if (separator != b"  " or not HASH.fullmatch(digest) or
                path not in requested or path in records):
            raise ValueError("unexpected, duplicate, or malformed device hash")
        records[path] = digest.decode("ascii")
    return records


def collect(args: argparse.Namespace) -> dict:
    manifest_path = private_path(args.manifest)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if (manifest.get("kind") != "private_live_device_snapshot" or
            manifest.get("product_type") != args.product or
            manifest.get("build") != args.build):
        raise ValueError("private snapshot device identity differs")
    if (remote(args, "uname -m").strip() != args.product.encode() or
            remote(args, "sw_vers -buildVersion").strip() != args.build.encode()):
        raise ValueError("connected device identity differs")
    groups = [candidates(manifest, manifest_path.parent, label, types_path)
              for label, types_path in (("data", args.data_types),
                                        ("mobile_data", args.mobile_types))]
    selected = sorted({item["path"].encode("utf-8", "surrogateescape")
                       for group in groups for item in group["candidates"]})
    command = ssh_prefix(args)
    command[1] = "-T"  # Permit NUL-delimited stdin; collector's -n closes stdin.
    result = subprocess.run(command + ["xargs -0 -r -n 16 sha256sum -z --"],
                            input=b"\0".join(selected) + b"\0",
                            capture_output=True, timeout=args.timeout, check=False)
    hashes = parse_hashes(result.stdout, set(selected))
    for group in groups:
        for item in group["candidates"]:
            encoded = item["path"].encode("utf-8", "surrogateescape")
            item["device_sha256"] = hashes.get(encoded)
            item["status"] = "hashed" if encoded in hashes else "unavailable_at_hash_time"
        group["hashed_count"] = sum(item["status"] == "hashed"
                                    for item in group["candidates"])
        group["unavailable_count"] = len(group["candidates"]) - group["hashed_count"]
    output = private_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stderr = output.with_suffix(output.suffix + ".stderr")
    stderr.write_bytes(result.stderr)
    record = {
        "schema_version": 1,
        "kind": "private_live_data_macho_hashes",
        "privacy": "private; contains app paths and hashes; never publish directly",
        "product_type": args.product,
        "build": args.build,
        "snapshot_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "hash_finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "hash_command_exit_code": result.returncode,
        "hash_stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "hash_stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        "groups": groups,
    }
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=True, sort_keys=True,
                                    separators=(",", ":")) + "\n")
    temporary.replace(output)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--data-types", required=True, type=Path)
    parser.add_argument("--mobile-types", required=True, type=Path)
    parser.add_argument("--host", default="root@127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--known-hosts", required=True, type=Path)
    parser.add_argument("--product", required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    record = collect(args)
    for group in record["groups"]:
        print(f"{group['root_label']}: {group['hashed_count']} hashed, "
              f"{group['unavailable_count']} unavailable; "
              f"{group['appeared_count']} appeared and "
              f"{group['disappeared_count']} disappeared between earlier passes")
    print(f"hash command exit code: {record['hash_command_exit_code']}; "
          "full private output saved under .local")


if __name__ == "__main__":
    main()
