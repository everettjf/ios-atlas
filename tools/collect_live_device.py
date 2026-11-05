#!/usr/bin/env python3
"""Capture a private, read-only snapshot of all visible device mount points.

The output directory must be under .local. A public catalog is a separate,
explicit review/export step. No file contents are read by this collector.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shlex
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = (ROOT / ".local").resolve()
STAT_FORMAT = "%z|%p|%u|%g|%i|%d|%m|%HT"
FIND_BODY = r'''for path do
  printf '%s\0' "$path"
  if stat -n -f '__STAT_FORMAT__' "$path" 2>/dev/null; then
    printf '\0'
    if [ -L "$path" ]; then stat -n -f '%Y' "$path" 2>/dev/null; fi
    printf '\0'
  else
    printf '!stat-error\0\0'
  fi
done'''.replace("__STAT_FORMAT__", STAT_FORMAT)
KIND = {
    "Regular File": "file", "Directory": "directory", "Symbolic Link": "symlink",
    "Character Device": "character_device", "Block Device": "block_device",
    "Socket": "socket", "FIFO": "fifo",
}


def private_path(path: Path) -> Path:
    resolved = path.resolve()
    if PRIVATE_ROOT not in resolved.parents:
        raise ValueError(f"private snapshot output must be under {PRIVATE_ROOT}")
    return resolved


def ssh_prefix(args: argparse.Namespace) -> list[str]:
    return ["ssh", "-n", "-p", str(args.port), "-i", str(args.identity),
            "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={args.known_hosts}",
            "-o", "ConnectTimeout=10", args.host]


def remote(args: argparse.Namespace, command: str) -> bytes:
    result = subprocess.run(ssh_prefix(args) + [command], capture_output=True,
                            timeout=60, check=False)
    if result.returncode or result.stderr:
        raise RuntimeError(f"device command failed ({result.returncode}); "
                           "verify the pinned SSH connection")
    return result.stdout


def scan_command(root: str) -> str:
    if not root.startswith("/") or root != os.path.normpath(root) or "\0" in root:
        raise ValueError("scan root must be an absolute normalized path")
    return f"find {shlex.quote(root)} -xdev -exec sh -c {shlex.quote(FIND_BODY)} sh {{}} +"


def parse_mounts(output: str) -> list[dict]:
    mounts = []
    for line in output.splitlines():
        if " on " not in line or not line.endswith(")") or " (" not in line:
            raise ValueError("unrecognized mount output; review it locally")
        head, options = line.rsplit(" (", 1)
        source, target = head.rsplit(" on ", 1)
        options = options[:-1]
        if not target.startswith("/") or target != os.path.normpath(target):
            raise ValueError("unrecognized mount target; review it locally")
        mounts.append({"source": source, "target": target,
                       "type": options.split(",", 1)[0], "options": options})
    if not mounts or not any(item["target"] == "/" for item in mounts):
        raise ValueError("mount table has no root mount")
    if len({item["target"] for item in mounts}) != len(mounts):
        raise ValueError("duplicate mount targets need manual review")
    return mounts


def decode(value: bytes) -> str:
    return value.decode("utf-8", errors="surrogateescape")


def parse_record(parts: list[bytes], root: str) -> list:
    path, metadata, target = map(decode, parts)
    if not (path == root or path.startswith(root.rstrip("/") + "/")):
        raise ValueError("record escaped the selected mount root")
    if metadata == "!stat-error":
        return [path, "unknown", None, None, None, None, None, None, None, None]
    fields = metadata.split("|")
    if len(fields) != 8 or fields[-1] not in KIND:
        raise ValueError("unexpected Darwin stat format")
    try:
        size, mode, uid, gid, inode, device, mtime = (
            int(fields[0]), int(fields[1], 8), *(int(field) for field in fields[2:7]))
    except ValueError as error:
        raise ValueError("invalid numeric stat field") from error
    kind = KIND[fields[-1]]
    if (size < 0 or uid < 0 or gid < 0 or inode < 0 or device < 0 or
            (kind != "symlink" and target) or "\0" in target):
        raise ValueError("invalid stat record")
    return [path, kind, size, mode, uid, gid, inode, device, mtime,
            target if kind == "symlink" else None]


def records_from_chunks(chunks, root: str):
    pending = bytearray()
    fields = []
    for chunk in chunks:
        pending.extend(chunk)
        while True:
            end = pending.find(0)
            if end < 0:
                if len(pending) > 1024 * 1024:
                    raise ValueError("one device path or stat field exceeds 1 MiB")
                break
            fields.append(bytes(pending[:end]))
            del pending[:end + 1]
            if len(fields) == 3:
                yield parse_record(fields, root)
                fields.clear()
    if pending or fields:
        raise ValueError("truncated NUL-delimited device scan")


def save_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def discover(args: argparse.Namespace, output_dir: Path) -> dict:
    product = decode(remote(args, "uname -m")).strip()
    build = decode(remote(args, "sw_vers -buildVersion")).strip()
    if product != args.product or build != args.build:
        raise ValueError("connected device product/build differs from requested snapshot")
    raw_mounts = decode(remote(args, "mount"))
    mounts = parse_mounts(raw_mounts)
    rootfs = decode(remote(args, "if [ -d /rootfs ]; then printf yes; fi")) == "yes"
    roots = [{"path": item["target"], "source": item["source"],
              "mount_type": item["type"], "role": "mount"} for item in mounts]
    if rootfs and not any(item["path"] == "/rootfs" for item in roots):
        roots.append({"path": "/rootfs", "source": "RootHide base-system view",
                      "mount_type": "alias", "role": "namespace_alias"})
    roots.sort(key=lambda item: item["path"])
    manifest = {"schema_version": 1, "kind": "private_live_device_snapshot",
                "product_type": product, "build": build,
                "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                "mount_table_sha256": hashlib.sha256(raw_mounts.encode("utf-8", "surrogateescape")).hexdigest(),
                "mounts": mounts, "roots": roots, "scans": {},
                "privacy": "private; contains user and app paths; never publish directly"}
    save_json(output_dir / "manifest.json", manifest)
    (output_dir / "mount.txt").write_bytes(raw_mounts.encode("utf-8", "surrogateescape"))
    return manifest


def scan_root(args: argparse.Namespace, output_dir: Path, root: str) -> dict:
    key = hashlib.sha256(root.encode("utf-8", "surrogateescape")).hexdigest()[:16]
    output = output_dir / f"root-{key}.jsonl.gz"
    temporary = output.with_suffix(".jsonl.gz.part")
    stderr_path = output_dir / f"root-{key}.stderr"
    counts: Counter[str] = Counter()
    started = time.monotonic()
    with stderr_path.open("wb") as errors, gzip.open(temporary, "wt", encoding="ascii") as sink:
        process = subprocess.Popen(ssh_prefix(args) + [scan_command(root)],
                                   stdout=subprocess.PIPE, stderr=errors)
        assert process.stdout is not None
        try:
            chunks = iter(lambda: process.stdout.read(1024 * 1024), b"")
            for row in records_from_chunks(chunks, root):
                sink.write(json.dumps(row, ensure_ascii=True, separators=(",", ":")) + "\n")
                counts[row[1]] += 1
            exit_code = process.wait(timeout=60)
        except BaseException:
            process.kill()
            process.wait()
            raise
    stderr = stderr_path.read_bytes()
    status = "complete" if exit_code == 0 and not stderr and not counts["unknown"] else "partial"
    temporary.replace(output)
    return {"status": status, "path": root, "file": output.name,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "entry_count": sum(counts.values()), "type_counts": dict(counts),
            "stat_error_count": counts["unknown"], "find_exit_code": exit_code,
            "stderr_bytes": len(stderr), "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
            "elapsed_seconds": round(time.monotonic() - started, 3)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="root@127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--known-hosts", required=True, type=Path)
    parser.add_argument("--product", required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--output-dir", type=Path, default=PRIVATE_ROOT / "live-device")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--only-root", action="append", help="scan a named discovered mount; repeat for a pilot")
    parser.add_argument("--limit-roots", type=int, help="pilot only; leaves other roots unscanned")
    args = parser.parse_args()
    output_dir = private_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if (manifest["product_type"] != args.product or manifest["build"] != args.build or
                manifest["kind"] != "private_live_device_snapshot"):
            raise ValueError("existing snapshot identity differs")
        product = decode(remote(args, "uname -m")).strip()
        build = decode(remote(args, "sw_vers -buildVersion")).strip()
        if product != args.product or build != args.build:
            raise ValueError("connected device identity changed")
        mount_bytes = remote(args, "mount")
        if hashlib.sha256(mount_bytes).hexdigest() != manifest["mount_table_sha256"]:
            raise ValueError("device mount table changed; start a new snapshot directory")
    else:
        manifest = discover(args, output_dir)
    if args.discover_only:
        print(f"{len(manifest['roots'])} live roots recorded privately in {manifest_path}")
        return
    roots = manifest["roots"]
    if args.only_root:
        unknown = set(args.only_root) - {item["path"] for item in roots}
        if unknown:
            raise ValueError(f"requested roots absent from mount discovery: {sorted(unknown)}")
        roots = [item for item in roots if item["path"] in args.only_root]
    if args.limit_roots:
        roots = roots[:args.limit_roots]
    for item in roots:
        root = item["path"]
        prior = manifest["scans"].get(root)
        if prior and prior["status"] == "complete":
            saved = output_dir / prior["file"]
            if saved.is_file() and hashlib.sha256(saved.read_bytes()).hexdigest() == prior["sha256"]:
                continue
            raise ValueError(f"completed scan artifact changed for root {root}")
        result = scan_root(args, output_dir, root)
        manifest["scans"][root] = result
        save_json(manifest_path, manifest)
        print(f"{root}: {result['entry_count']} entries, {result['status']}", flush=True)
    complete = all(manifest["scans"].get(item["path"], {}).get("status") == "complete"
                   for item in manifest["roots"])
    print(f"snapshot complete={complete}; private manifest: {manifest_path}")


if __name__ == "__main__":
    main()
