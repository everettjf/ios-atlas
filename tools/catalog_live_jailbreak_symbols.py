#!/usr/bin/env python3
"""Index named __text symbols from exact, acquired jailbreak Mach-O bytes.

The complete symbol rows and per-file checkpoints stay in ignored .local until
the public paths and names have passed a separate publication review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from catalog_live_jailbreak_dependencies import sha256, load, dump
from catalog_standalone_macho import fat_slices
from catalog_standalone_symbols import parse_symbols
from collect_live_device import private_path


def run(*command: str) -> bytes:
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"ipsw exited {result.returncode}: " +
                           result.stderr.decode(errors="replace")[-350:])
    return result.stdout


def thin_slice(binary: Path, offset: int, length: int, workdir: Path) -> Path:
    with tempfile.NamedTemporaryFile(dir=workdir, suffix=".macho", delete=False) as target:
        path = Path(target.name)
        with binary.open("rb") as source:
            source.seek(offset)
            remaining = length
            while remaining:
                block = source.read(min(remaining, 4 * 1024 * 1024))
                if not block:
                    path.unlink(missing_ok=True)
                    raise ValueError("truncated universal Mach-O slice")
                target.write(block)
                remaining -= len(block)
    return path


def inspect(item: dict, binary_root: Path, workdir: Path) -> dict:
    relative = Path(item["path"].lstrip("/"))
    if (not item["path"].startswith("/") or not relative.parts or
            ".." in relative.parts):
        raise ValueError("unsafe binary path")
    candidate = binary_root / relative
    binary = candidate.resolve()
    if (candidate.is_symlink() or binary_root not in binary.parents or
            not binary.is_file() or binary.stat().st_size != item["size"] or
            sha256(binary) != item["sha256"]):
        raise ValueError("acquired bytes differ from device inventory")
    checkpoint = workdir / (hashlib.sha256(item["path"].encode()).hexdigest() + ".json.gz")
    if checkpoint.exists():
        saved = load(checkpoint)
        if (saved.get("path"), saved.get("sha256"), saved.get("slice_count")) != (
                item["path"], item["sha256"], len(item["slices"])):
            raise ValueError("symbol checkpoint identity differs")
        return saved
    repeated_arch = len({part["architecture"] for part in item["slices"]}) != len(item["slices"])
    fat_parts = fat_slices(binary) if repeated_arch else []
    if repeated_arch and len(fat_parts) != len(item["slices"]):
        raise ValueError("fat slice count differs from device catalog")
    slices = []
    for index, original in enumerate(item["slices"]):
        temporary = None
        try:
            if repeated_arch:
                offset, length, _ = fat_parts[index]
                temporary = thin_slice(binary, offset, length, workdir)
                target = temporary
                arch = []
            else:
                target = binary
                arch = ["--arch", original["architecture"]]
            macho_bytes = run("ipsw", "macho", "info", str(target),
                              "--json", "--loads", "--no-color", *arch)
            macho = json.loads(macho_bytes)
            uuids = [row["uuid"] for row in macho["loads"] if row["load_cmd"] == "LC_UUID"]
            if uuids != ([original["uuid"]] if original["uuid"] else []):
                raise ValueError("Mach-O UUID differs from device catalog")
            sections = [[row["name"], section["addr"], section["size"]]
                        for row in macho["loads"] if row["load_cmd"] == "LC_SEGMENT_64"
                        and "x" in row.get("prot", "")
                        for section in row.get("sections", []) if section["name"] == "__text"]
            symbol_bytes = run("ipsw", "macho", "info", str(target),
                               "--symbols", "--demangle", "--no-color", *arch)
            names, duplicates, unnamed, outside = parse_symbols(symbol_bytes, sections)
            slices.append({"architecture": original["architecture"],
                           "uuid": original["uuid"],
                           "macho_loads_sha256": hashlib.sha256(macho_bytes).hexdigest(),
                           "symbol_dump_sha256": hashlib.sha256(symbol_bytes).hexdigest(),
                           "symbol_dump_replacement_char_count": symbol_bytes.decode(
                               "utf-8", errors="replace").count("\ufffd"),
                           "text_sections": sections, "named_symbol_count": len(names),
                           "duplicate_symbol_row_count": duplicates,
                           "unnamed_text_row_count": unnamed,
                           "outside_text_row_count": outside,
                           "symbols": names})
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
    record = {"path": item["path"], "sha256": item["sha256"],
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
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.workers < 1 or args.limit < 0:
        parser.error("invalid worker or limit count")
    binary_root = private_path(args.binary_root)
    workdir = private_path(args.workdir)
    output = private_path(args.output)
    source = load(args.macho_catalog)
    if (source.get("schema_version") != 1 or
            source.get("kind") != "live_jailbreak_macho_inventory" or
            source.get("source") != "verified_live_device_macho_bytes" or
            source.get("macho_file_count") != len(source.get("records", []))):
        raise ValueError("invalid live Mach-O source")
    workdir.mkdir(parents=True, exist_ok=True)
    pending = [item for item in source["records"] if not (
        workdir / (hashlib.sha256(item["path"].encode()).hexdigest() + ".json.gz")).exists()]
    selected = pending[:args.limit] if args.limit else pending
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(inspect, item, binary_root, workdir): item
                   for item in selected}
        for number, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
                if number % 50 == 0 or number == len(selected):
                    print(f"inspected {number}/{len(selected)} new files", flush=True)
            except Exception as error:
                failures.append((futures[future]["path"], str(error)))
    if failures:
        raise RuntimeError(f"{len(failures)} symbol inspections failed: {failures[:3]}")
    if len(selected) != len(pending):
        print(f"partial pass: {len(pending) - len(selected)} files remain", flush=True)
        return
    records = [inspect(item, binary_root, workdir) for item in source["records"]]
    records.sort(key=lambda item: item["path"])
    totals = Counter()
    for item in records:
        totals["slices"] += item["slice_count"]
        for part in item["slices"]:
            totals["named_symbols"] += part["named_symbol_count"]
            totals["duplicate_rows"] += part["duplicate_symbol_row_count"]
            totals["unnamed_rows"] += part["unnamed_text_row_count"]
            totals["outside_rows"] += part["outside_text_row_count"]
            totals["slices_without_names"] += not part["symbols"]
        totals["files_without_names"] += all(not part["symbols"] for part in item["slices"])
    data = {"schema_version": 1, "kind": "live_jailbreak_named_text_symbols",
            "source": "verified_live_device_macho_bytes", "tool": "ipsw macho info --symbols --demangle",
            "product_type": source["product_type"], "build": source["build"],
            "macho_file_count": len(records), "totals": dict(totals), "files": records}
    dump(output, data)
    print(f"{len(records)} files, {totals['named_symbols']} named symbols -> {output}")


if __name__ == "__main__":
    main()
