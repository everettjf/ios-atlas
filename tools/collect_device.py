#!/usr/bin/env python3
"""Read-only inventory of selected Apple system paths on a trusted iOS device.

Only the fixed roots below are scanned. User data, preboot, jailbreak prefixes,
device identifiers, file contents and SSH credentials are absent from output.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOTS = (
    "/rootfs/Applications",
    "/rootfs/Library",
    "/rootfs/System",
    "/rootfs/bin",
    "/rootfs/sbin",
    "/rootfs/usr",
    "/rootfs/private/etc",
)


def remote(args: argparse.Namespace, command: str, timeout: int = 240) -> bytes:
    ssh = ["ssh", "-p", str(args.port), "-i", str(args.identity),
           "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
           "-o", f"UserKnownHostsFile={args.known_hosts}",
           "-o", "ConnectTimeout=10", args.host, command]
    result = subprocess.run(ssh, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"remote read failed ({result.returncode}): "
                           + result.stderr.decode(errors="replace")[:500])
    if result.stderr:
        raise RuntimeError("remote scan reported errors: "
                           + result.stderr.decode(errors="replace")[:500])
    return result.stdout


def paths(args: argparse.Namespace, predicate: str) -> set[str]:
    roots = " ".join(shlex.quote(root) for root in ROOTS)
    command = f"find {roots} -xdev {predicate} -print0"
    raw = remote(args, command, timeout=600)
    if raw and not raw.endswith(b"\0"):
        raise ValueError("incomplete NUL-delimited find output")
    output = set()
    for encoded in raw.split(b"\0"):
        if not encoded:
            continue
        path = encoded.decode("utf-8", errors="surrogateescape")
        if not any(path == root or path.startswith(root + "/") for root in ROOTS):
            raise ValueError("path escaped selected system roots")
        output.add(path.removeprefix("/rootfs"))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="root@127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--known-hosts", required=True, type=Path)
    parser.add_argument("--product", required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    identity = remote(args, "uname -m; sw_vers -buildVersion", timeout=30).decode().splitlines()
    if len(identity) < 2 or identity[0] != args.product or identity[1] != args.build:
        raise ValueError(f"device identity mismatch: {identity[:2]}")
    all_paths = paths(args, "")
    types = {}
    for predicate, kind in (("-type f", "file"), ("-type d", "directory"),
                            ("-type l", "symlink")):
        for path in paths(args, predicate):
            if path in types:
                raise ValueError(f"overlapping file kinds: {path}")
            types[path] = kind
    if not set(types).issubset(all_paths):
        raise ValueError("typed scan contains a path missing from full scan")
    records = [[path, types.get(path, "other")] for path in sorted(all_paths)]
    output = {
        "schema_version": 1,
        "kind": "device_system_path_observation",
        "source": "trusted_device_rootfs_read_only_ssh",
        "product_type": args.product,
        "build": args.build,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "device_namespace": "/rootfs",
        "scanned_roots": [root.removeprefix("/rootfs") for root in ROOTS],
        "excluded": "All other roots, including private/var, private/preboot, dev, and jailbreak namespace",
        "complete": True,
        "entry_count": len(records),
        "type_counts": {kind: sum(item[1] == kind for item in records)
                        for kind in ("file", "directory", "symlink", "other")},
        "entries": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(output, ensure_ascii=True, separators=(",", ":"),
                          sort_keys=True) + "\n").encode()
    args.output.write_bytes(gzip.compress(payload, mtime=0))
    print(f"{len(records)} selected system paths -> {args.output}")


if __name__ == "__main__":
    main()
