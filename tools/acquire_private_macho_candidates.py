#!/usr/bin/env python3
"""Privately acquire device-hashed data-volume candidates and parse Mach-O headers.

The phone is read through a pinned SSH tar stream; tar never writes on it.
Private app paths, file bytes, hashes, and errors remain under ignored .local.
Only aggregate counts are printed. No output from this tool is site input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from catalog_standalone_macho import FAT_MAGICS, MAGICS, THIN_MAGICS, fat_slices, parse_thin
from collect_live_device import private_path, remote, ssh_prefix


SHA256 = re.compile(r"[0-9a-f]{64}")


def archive_name(name: str, expected: set[str]) -> str:
    relative = name[2:] if name.startswith("./") else name
    if (name.startswith("/") or relative.startswith("/") or
            any(part in ("", ".", "..") for part in relative.split("/")) or
            relative not in expected):
        raise ValueError("tar member is not a requested private candidate")
    return relative


def parse_header(path: Path, size: int) -> list[dict]:
    with path.open("rb") as stream:
        magic = stream.read(4)
    if magic not in MAGICS:
        raise ValueError("acquired file has no standard Mach-O header")
    if magic in FAT_MAGICS:
        members = fat_slices(path)
        if not all(bytes.fromhex(part_magic) in THIN_MAGICS
                   for _, _, part_magic in members):
            raise ValueError("mixed or non-Mach-O fat container")
        return [parse_thin(path, offset, length) for offset, length, _ in members]
    return [parse_thin(path, 0, size)]


def acquire(args: argparse.Namespace) -> dict:
    source = private_path(args.hash_manifest)
    source_bytes = source.read_bytes()
    hashes = json.loads(source_bytes)
    if (hashes.get("kind") != "private_live_data_macho_hashes" or
            hashes.get("product_type") != args.product or
            hashes.get("build") != args.build or
            hashes.get("hash_command_exit_code") != 0):
        raise ValueError("incomplete or mismatched private candidate hashes")
    items = [item for group in hashes["groups"] for item in group["candidates"]]
    by_relative = {}
    for item in items:
        path = item["path"]
        relative = path.lstrip("/")
        if (item.get("status") != "hashed" or
                not SHA256.fullmatch(item.get("device_sha256") or "") or
                not path.startswith("/rootfs/private/var/") or
                relative in by_relative or
                any(part in ("", ".", "..") for part in relative.split("/"))):
            raise ValueError("unsafe, duplicate, or unverified private candidate")
        by_relative[relative] = item
    if (remote(args, "uname -m").strip() != args.product.encode() or
            remote(args, "sw_vers -buildVersion").strip() != args.build.encode()):
        raise ValueError("connected device identity differs")
    output_dir = private_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    files_dir = output_dir / "files"
    files_dir.mkdir(exist_ok=True)
    os.chmod(files_dir, 0o700)
    stderr_path = output_dir / "tar.stderr"
    records = {}
    command = ssh_prefix(args)
    command[1] = "-T"  # Permit the NUL-delimited input list.
    payload = b"\0".join(path.encode("utf-8", "surrogateescape")
                         for path in sorted("/" + name for name in by_relative)) + b"\0"
    with stderr_path.open("wb") as errors:
        os.chmod(stderr_path, 0o600)
        process = subprocess.Popen(command + ["tar --null -T - -cf -"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=errors)
        assert process.stdin is not None and process.stdout is not None
        try:
            process.stdin.write(payload)
            process.stdin.close()
            with tarfile.open(fileobj=process.stdout, mode="r|",
                              encoding="utf-8", errors="surrogateescape") as archive:
                for member in archive:
                    relative = archive_name(member.name, set(by_relative))
                    if relative in records or not member.isfile():
                        raise ValueError("duplicate or nonregular private tar member")
                    original = by_relative[relative]
                    token = hashlib.sha256(relative.encode("utf-8", "surrogateescape")).hexdigest()
                    target = files_dir / f"{token}.bin"
                    temporary = files_dir / f"{token}.part"
                    content = archive.extractfile(member)
                    if content is None:
                        raise ValueError("regular tar member has no content")
                    digest = hashlib.sha256()
                    size = 0
                    with temporary.open("wb") as sink:
                        os.chmod(temporary, 0o600)
                        while chunk := content.read(1024 * 1024):
                            sink.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                    row = {"path": original["path"],
                           "device_sha256": original["device_sha256"],
                           "snapshot_size": original["snapshot_size"],
                           "acquired_size": size,
                           "local_sha256": digest.hexdigest()}
                    if size != member.size or row["local_sha256"] != row["device_sha256"]:
                        temporary.unlink()
                        row["status"] = "changed_or_truncated"
                    else:
                        temporary.replace(target)
                        row["local_file"] = target.name
                        try:
                            row["slices"] = parse_header(target, size)
                            row["status"] = "verified_and_parsed"
                        except (ValueError, OSError, struct.error) as error:
                            row["status"] = "verified_header_failed"
                            row["header_error"] = type(error).__name__
                    records[relative] = row
                    if len(records) % 50 == 0:
                        print(f"processed {len(records)} private candidates", flush=True)
            process.stdout.close()
            exit_code = process.wait(timeout=args.timeout)
        except BaseException:
            process.kill()
            process.wait()
            raise
    for relative, original in by_relative.items():
        if relative not in records:
            records[relative] = {"path": original["path"],
                                 "device_sha256": original["device_sha256"],
                                 "snapshot_size": original["snapshot_size"],
                                 "status": "unavailable_at_acquisition_time"}
    counts = {status: sum(row["status"] == status for row in records.values())
              for status in ("verified_and_parsed", "verified_header_failed",
                             "changed_or_truncated", "unavailable_at_acquisition_time")}
    result = {
        "schema_version": 1,
        "kind": "private_live_data_macho_acquisition",
        "privacy": "private; contains app paths, hashes, and local binary names; never publish directly",
        "product_type": args.product,
        "build": args.build,
        "hash_manifest_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "tar_exit_code": exit_code,
        "tar_stderr_sha256": hashlib.sha256(stderr_path.read_bytes()).hexdigest(),
        "tar_stderr_bytes": stderr_path.stat().st_size,
        "counts": counts,
        "records": [records[name] for name in sorted(records)],
    }
    output = output_dir / "acquisition.json"
    temporary = output_dir / "acquisition.json.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=True, sort_keys=True,
                                    separators=(",", ":")) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hash-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--host", default="root@127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--known-hosts", required=True, type=Path)
    parser.add_argument("--product", required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    result = acquire(args)
    print(f"tar exit code: {result['tar_exit_code']}; private candidate outcomes: "
          + ", ".join(f"{key}={value}" for key, value in result["counts"].items()))


if __name__ == "__main__":
    main()
