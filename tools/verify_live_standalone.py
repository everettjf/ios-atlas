#!/usr/bin/env python3
"""Match exact-build standalone Mach-O bytes to read-only live device hashes.

Requires an already authenticated, pinned USB SSH forward. The complete
observation, including failure diagnostics, stays under ignored .local.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from collect_live_device import private_path, ssh_prefix


DEVICE_PREFIX = {
    "FileSystem": ("/rootfs", "/rootfs"),
    "SystemOS": ("/rootfs/private/preboot", "/rootfs/private/preboot/Cryptexes/OS"),
    "AppOS": ("/rootfs/private/preboot", "/rootfs/private/preboot/Cryptexes/App"),
}
HASH_ROW = re.compile(rb"([0-9a-f]{64})  (/.+)")


def snapshot_files(directory: Path, scan: dict) -> dict[str, tuple[str, int | None]]:
    source = directory / scan["file"]
    if (source.resolve().parent != directory.resolve() or
            hashlib.sha256(source.read_bytes()).hexdigest() != scan["sha256"] or
            scan["status"] != "complete"):
        raise ValueError("system or cryptex snapshot is incomplete or changed")
    files = {}
    with gzip.open(source, "rt", encoding="ascii") as stream:
        for line in stream:
            path, kind, size, *_ = json.loads(line)
            if path in files:
                raise ValueError("duplicate path in a scan root")
            files[path] = (kind, size)
    if len(files) != scan["entry_count"]:
        raise ValueError("snapshot row count differs")
    return files


def verify(args: argparse.Namespace) -> dict:
    manifest_path = private_path(args.manifest)
    output = private_path(args.output)
    manifest = json.loads(manifest_path.read_text())
    stock = json.loads(gzip.decompress(args.stock_catalog.read_bytes()))
    if (manifest.get("kind") != "private_live_device_snapshot" or
            manifest.get("product_type") != args.product or
            manifest.get("build") != args.build or
            stock.get("product_type") != args.product or
            stock.get("build") != args.build or
            stock.get("kind") != "standalone_macho_file_inventory" or
            stock.get("source") != "official_ipsw_mounted_images" or
            len(stock.get("records", [])) != stock.get("macho_file_count")):
        raise ValueError("snapshot and firmware catalog identity differ")
    snapshots = {root: snapshot_files(manifest_path.parent, manifest["scans"][root])
                 for root in ("/rootfs", "/rootfs/private/preboot")}
    records = []
    requested = {}
    for item in stock["records"]:
        if item["volume"] not in DEVICE_PREFIX:
            raise ValueError("unmapped firmware volume")
        snapshot_root, prefix = DEVICE_PREFIX[item["volume"]]
        device_path = prefix + item["path"]
        if not item["path"].startswith("/") or device_path in requested:
            raise ValueError("invalid or duplicate device path mapping")
        seen = snapshots[snapshot_root].get(device_path)
        status = ("unobserved_at_mapped_path" if seen is None else
                  "non_file_at_mapped_path" if seen[0] != "file" else
                  "size_differs_at_snapshot" if seen[1] != item["size"] else
                  "pending_hash")
        record = {"volume": item["volume"], "path": item["path"],
                  "device_path": device_path, "size": item["size"],
                  "firmware_sha256": item["sha256"], "status": status,
                  "device_sha256": None}
        records.append(record)
        if status == "pending_hash":
            requested[device_path] = record
    # The inventory collector uses ssh -n because it never sends stdin.
    # This NUL-safe batch does send the exact path list through SSH stdin.
    prefix = [argument for argument in ssh_prefix(args) if argument != "-n"]
    identity = subprocess.run(prefix + ["uname -m; sw_vers -buildVersion"],
                              capture_output=True, timeout=30, check=True)
    if identity.stdout.decode().splitlines() != [args.product, args.build]:
        raise ValueError("connected phone product/build changed")
    start = datetime.now(timezone.utc).isoformat()
    request = b"".join(path.encode("utf-8", "surrogateescape") + b"\0"
                       for path in requested)
    command = "PATH=/usr/bin:/bin:/var/jb/usr/bin:$PATH; xargs -0 -r -n 16 sha256sum -z"
    print(f"hashing {len(requested)} snapshot-mapped files on the verified phone", flush=True)
    result = subprocess.run(prefix + [command], input=request, capture_output=True,
                            timeout=args.timeout, check=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    if result.stderr:
        output.with_suffix(output.suffix + ".stderr").write_bytes(result.stderr)
    if result.stdout and not result.stdout.endswith(b"\0"):
        raise ValueError("truncated device hash stream")
    hashed = set()
    for raw in result.stdout.split(b"\0")[:-1]:
        match = HASH_ROW.fullmatch(raw)
        if not match:
            raise ValueError("unexpected device hash record")
        path = match[2].decode("utf-8", "surrogateescape")
        if path not in requested or path in hashed:
            raise ValueError("extra or duplicate device hash")
        hashed.add(path)
        record = requested[path]
        record["device_sha256"] = match[1].decode("ascii")
        record["status"] = ("matched" if record["device_sha256"] ==
                            record["firmware_sha256"] else "content_differs")
    for path in requested.keys() - hashed:
        requested[path]["status"] = "hash_failed"
    counts = Counter(item["status"] for item in records)
    data = {"schema_version": 1, "kind": "live_standalone_macho_identity",
            "source": "read_only_device_sha256_and_exact_build_ipsw",
            "build": args.build, "product_type": args.product,
            "firmware_sha256": stock["firmware_sha256"],
            "private_snapshot_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "snapshot_observed_at_utc": manifest["observed_at_utc"],
            "hash_started_at_utc": start,
            "hash_finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "hash_command_exit_code": result.returncode,
            "counts": dict(counts), "record_count": len(records),
            "records": records}
    payload = json.dumps(data, sort_keys=True, ensure_ascii=True,
                         separators=(",", ":")).encode() + b"\n"
    output.write_bytes(gzip.compress(payload, mtime=0))
    print(f"{len(records)} firmware files, {counts['matched']} byte-matched, "
          f"{counts['unobserved_at_mapped_path']} unmapped paths, "
          f"{counts['hash_failed']} hash failures -> {output}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--stock-catalog", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--known-hosts", required=True, type=Path)
    parser.add_argument("--product", required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    verify(parser.parse_args())


if __name__ == "__main__":
    main()
