#!/usr/bin/env python3
"""Build public, source-bound indexes from mounted IPSW images and ipsw DSC JSON.

Raw firmware, cache contents and personal device paths are deliberately not copied
into the output. This tool never follows filesystem symlinks.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import stat
from pathlib import Path


SCHEMA = 1


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = (json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode()
    if path.suffix == ".gz":
        temporary.write_bytes(gzip.compress(payload, mtime=0))
    else:
        temporary.write_bytes(payload)
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_kind(mode: int) -> str:
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISCHR(mode):
        return "character_device"
    if stat.S_ISBLK(mode):
        return "block_device"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    return "other"


def scan_filesystem(root: Path, excluded: set[str]) -> tuple[list[dict], list[dict]]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"not a mounted directory: {root}")
    device = root.stat().st_dev
    records: list[dict] = []
    errors: list[dict] = []
    stack = [(root, "/")]
    while stack:
        directory, logical_directory = stack.pop()
        try:
            children = sorted(os.scandir(directory), key=lambda child: child.name)
        except OSError as error:
            errors.append({"path": logical_directory, "error": str(error)})
            continue
        for child in children:
            logical = logical_directory.rstrip("/") + "/" + child.name
            if logical in excluded or any(logical.startswith(item.rstrip("/") + "/") for item in excluded):
                continue
            try:
                metadata = child.stat(follow_symlinks=False)
                kind = file_kind(metadata.st_mode)
                record = {
                    "path": logical,
                    "type": kind,
                    "size": metadata.st_size if kind == "file" else None,
                    "mode": stat.S_IMODE(metadata.st_mode),
                }
                if kind == "symlink":
                    record["target"] = os.readlink(child.path)
                records.append(record)
                if kind == "directory":
                    if metadata.st_dev == device:
                        stack.append((Path(child.path), logical))
                    else:
                        errors.append({"path": logical, "error": "nested volume skipped"})
            except OSError as error:
                errors.append({"path": logical, "error": str(error)})
    records.sort(key=lambda record: record["path"])
    return records, errors


def build_filesystem(args: argparse.Namespace) -> None:
    excluded = set(args.exclude)
    records, errors = scan_filesystem(args.root, excluded)
    output = {
        "schema_version": SCHEMA,
        "kind": "filesystem",
        "source": "official_ipsw_mounted_image",
        "product_type": args.product,
        "build": args.build,
        "volume": args.volume,
        "image_name": args.image_name,
        "firmware_sha256": args.firmware_sha256,
        "excluded_paths": sorted(excluded),
        "complete": not errors,
        "entry_count": len(records),
        "errors": errors,
        "entries": records,
    }
    write_json(args.output, output)
    print(f"{args.volume}: {len(records)} entries, {len(errors)} errors -> {args.output}")
    if errors:
        raise SystemExit(2)


def build_dyld(args: argparse.Namespace) -> None:
    with args.info.open(encoding="utf-8") as stream:
        raw = json.load(stream)
    if raw.get("platform") != "iOS" or "arm64e" not in raw.get("magic", ""):
        raise ValueError("cache platform or architecture does not match iOS arm64e")
    images = []
    seen = set()
    for item in raw["dylibs"]:
        name = item["name"]
        if not name.startswith("/") or name in seen:
            raise ValueError(f"invalid or duplicate install name: {name}")
        seen.add(name)
        images.append({
            "install_name": name,
            "uuid": item["uuid"],
            "version": item.get("version") or None,
            "load_address": item["load_address"],
        })
    images.sort(key=lambda image: image["install_name"])
    prefix = "dyld_shared_cache_arm64e"
    files = []
    for path in sorted(args.cache_dir.iterdir()):
        if path.is_file() and path.name.startswith(prefix):
            files.append({"name": path.name, "size": path.stat().st_size,
                          "sha256": sha256_file(path)})
    if not files or files[0]["name"] != prefix:
        raise ValueError("main arm64e cache is missing")
    result = {
        "schema_version": SCHEMA,
        "kind": "dyld_shared_cache",
        "source": "official_ipsw_systemos",
        "product_type": args.product,
        "build": args.build,
        "firmware_sha256": args.firmware_sha256,
        "architecture": "arm64e",
        "cache_uuid": raw["uuid"],
        "cache_magic": raw["magic"],
        "platform": raw["platform"],
        "tool": args.tool,
        "file_count": len(files),
        "image_count": len(images),
        "files": files,
        "images": images,
    }
    write_json(args.output, result)
    print(f"dyld: {len(files)} cache files, {len(images)} images -> {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("fs", "dyld"):
        command = subcommands.add_parser(name)
        command.add_argument("--product", required=True)
        command.add_argument("--build", required=True)
        command.add_argument("--firmware-sha256", required=True)
        command.add_argument("--output", required=True, type=Path)
        if name == "fs":
            command.add_argument("--root", required=True, type=Path)
            command.add_argument("--volume", required=True)
            command.add_argument("--image-name", required=True)
            command.add_argument("--exclude", action="append", default=[])
            command.set_defaults(run=build_filesystem)
        else:
            command.add_argument("--info", required=True, type=Path)
            command.add_argument("--cache-dir", required=True, type=Path)
            command.add_argument("--tool", required=True)
            command.set_defaults(run=build_dyld)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
