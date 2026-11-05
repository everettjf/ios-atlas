#!/usr/bin/env python3
"""Index direct Mach-O library loads from acquired, device-hash-verified files.

This records load commands, not runtime dyld resolution. Inputs and checkpoints
stay in ignored .local; the site builder validates the public aggregate again.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from collect_live_device import private_path
from catalog_standalone_macho import fat_slices


PRIVATE_REFERENCE = re.compile(
    r"(?:^/Users/|^/(?:private/)?var/(?:mobile|containers)(?:/|$)|"
    r"systemhook-[0-9A-Fa-f]{16}\.dylib)"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as source:
        return json.load(source)


def dump(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True,
                         separators=(",", ":")).encode() + b"\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(gzip.compress(payload, mtime=0))
    temporary.replace(path)


def inspect(item: dict, binary_root: Path, workdir: Path) -> dict:
    path = item["path"]
    candidate = binary_root / path.lstrip("/")
    binary = candidate.resolve()
    if (candidate.is_symlink() or binary_root not in binary.parents or
            not binary.is_file() or binary.stat().st_size != item["size"] or
            sha256(binary) != item["sha256"]):
        raise ValueError("acquired binary differs from device inventory")
    checkpoint = workdir / (hashlib.sha256(path.encode()).hexdigest() + ".json.gz")
    if checkpoint.exists():
        saved = load(checkpoint)
        if (saved.get("path"), saved.get("sha256"), saved.get("slice_count")) != (
                path, item["sha256"], len(item["slices"])):
            raise ValueError("dependency checkpoint identity differs")
        return saved
    slices = []
    duplicate_architectures = len({part["architecture"] for part in item["slices"]}) != len(item["slices"])
    fat_parts = fat_slices(binary) if duplicate_architectures else []
    if duplicate_architectures and len(fat_parts) != len(item["slices"]):
        raise ValueError("fat slice count differs from verified inventory")
    for index, part in enumerate(item["slices"]):
        temporary_path = None
        try:
            if duplicate_architectures:
                offset, length, _ = fat_parts[index]
                with tempfile.NamedTemporaryFile(dir=workdir, suffix=".macho",
                                                 delete=False) as temporary:
                    temporary_path = Path(temporary.name)
                    with binary.open("rb") as source:
                        source.seek(offset)
                        remaining = length
                        while remaining:
                            block = source.read(min(remaining, 4 * 1024 * 1024))
                            if not block:
                                raise ValueError("truncated fat Mach-O slice")
                            temporary.write(block)
                            remaining -= len(block)
                command = ["ipsw", "macho", "info", str(temporary_path),
                           "--json", "--loads", "--no-color"]
            else:
                command = ["ipsw", "macho", "info", str(binary), "--json",
                           "--loads", "--no-color", "--arch", part["architecture"]]
            result = subprocess.run(command, capture_output=True, check=False)
        finally:
            if temporary_path:
                temporary_path.unlink(missing_ok=True)
        if result.returncode:
            raise RuntimeError("ipsw Mach-O load inspection failed: " +
                               result.stderr.decode(errors="replace")[-350:])
        parsed = json.loads(result.stdout)
        loads = parsed["loads"]
        uuids = [row["uuid"] for row in loads if row["load_cmd"] == "LC_UUID"]
        if uuids != ([part["uuid"]] if part["uuid"] else []):
            raise ValueError("Mach-O slice UUID differs from verified inventory")
        dependencies = []
        rpaths = []
        install_name = None
        for row in loads:
            kind = row["load_cmd"]
            if kind == "LC_RPATH":
                rpaths.append(row["path"])
            elif kind == "LC_ID_DYLIB":
                install_name = row["name"]
            elif kind in ("LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB",
                          "LC_REEXPORT_DYLIB", "LC_LOAD_UPWARD_DYLIB",
                          "LC_LAZY_LOAD_DYLIB"):
                dependencies.append({"load_command": kind, "install_name": row["name"]})
        slices.append({"architecture": part["architecture"], "uuid": part["uuid"],
                       "load_dump_sha256": hashlib.sha256(result.stdout).hexdigest(),
                       "install_name": install_name, "rpaths": rpaths,
                       "dependencies": dependencies})
    record = {"path": path, "sha256": item["sha256"],
              "slice_count": len(slices), "slices": slices}
    dump(checkpoint, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macho-catalog", required=True, type=Path)
    parser.add_argument("--binary-root", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    binary_root = private_path(args.binary_root)
    workdir = private_path(args.workdir)
    output = private_path(args.output)
    source = load(args.macho_catalog)
    if (source.get("kind") != "live_jailbreak_macho_inventory" or
            source.get("source") != "verified_live_device_macho_bytes" or
            source.get("macho_file_count") != len(source.get("records", []))):
        raise ValueError("invalid verified live Mach-O inventory")
    workdir.mkdir(parents=True, exist_ok=True)
    results = []
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(inspect, item, binary_root, workdir): item
                   for item in source["records"]}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as error:
                failures.append((futures[future]["path"], str(error)))
    if failures:
        raise RuntimeError(f"{len(failures)} live dependency inspections failed; "
                           "review private checkpoints")
    results.sort(key=lambda item: item["path"])
    counts = Counter()
    for item in results:
        for part in item["slices"]:
            if part["install_name"] and PRIVATE_REFERENCE.search(part["install_name"]):
                raise ValueError("private Mach-O install name needs manual review")
            if any(PRIVATE_REFERENCE.search(row["install_name"])
                   for row in part["dependencies"]):
                raise ValueError("private direct-load path needs manual review")
            public_rpaths = [path for path in part["rpaths"]
                             if not PRIVATE_REFERENCE.search(path)]
            redacted = len(part["rpaths"]) - len(public_rpaths)
            part["rpaths"] = public_rpaths
            part["redacted_rpath_count"] = redacted
            counts["slices"] += 1
            counts["direct_loads"] += len(part["dependencies"])
            counts["rpaths"] += len(public_rpaths)
            counts["redacted_rpaths"] += redacted
            counts["without_loads"] += not part["dependencies"]
    data = {"schema_version": 1, "kind": "live_jailbreak_direct_dependencies",
            "source": "verified_live_device_macho_bytes",
            "build": source["build"], "product_type": source["product_type"],
            "macho_file_count": len(results), "totals": dict(counts), "files": results}
    dump(output, data)
    print(f"{len(results)} files, {counts['direct_loads']} direct loads -> {output}")


if __name__ == "__main__":
    main()
