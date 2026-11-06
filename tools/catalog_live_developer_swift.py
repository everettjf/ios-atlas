#!/usr/bin/env python3
"""Index Swift dump metadata in verified live Developer mount Mach-O files."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from catalog_live_jailbreak_dependencies import dump, load
from catalog_live_jailbreak_swift import KINDS, inspect
from collect_live_device import private_path


def catalog(macho_catalog: Path, binary_root: Path, workdir: Path,
            workers: int = 4) -> dict:
    source = load(macho_catalog)
    if (source.get("schema_version") != 1 or
            source.get("kind") != "live_developer_macho_inventory" or
            source.get("source") != "verified_live_developer_mount_bytes" or
            source.get("macho_file_count") != len(source.get("records", []))):
        raise ValueError("invalid verified Developer mount Mach-O catalog")
    binary_root = private_path(binary_root)
    workdir = private_path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    results = []
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(inspect, item, binary_root, workdir): item
                   for item in source["records"]}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as error:
                failures.append((futures[future]["path"], str(error)))
    if failures:
        raise RuntimeError(f"{len(failures)} Developer Swift inspections failed: "
                           f"{failures[:3]}")
    results.sort(key=lambda item: item["path"])
    totals = Counter()
    for item in results:
        totals["slices"] += item["slice_count"]
        for part in item["slices"]:
            totals[part["status"]] += 1
            for name, field in (("declarations", "declaration_count"),
                                ("members", "member_count"),
                                ("stripped_members", "stripped_member_count"),
                                ("unparsed_lines", "unparsed_line_count")):
                totals[name] += part[field]
            for kind in KINDS:
                totals[kind] += part["kind_counts"][kind]
        totals["files_without_declarations"] += not any(
            part["declaration_count"] for part in item["slices"])
    return {"schema_version": 1, "kind": "live_developer_swift_declarations",
            "source": "verified_live_developer_mount_bytes", "tool": "ipsw swift-dump",
            "product_type": source["product_type"], "build": source["build"],
            "macho_file_count": len(results), "totals": dict(totals), "files": results}


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
    output = private_path(args.output)
    data = catalog(args.macho_catalog, args.binary_root, args.workdir, args.workers)
    dump(output, data)
    print(f"{data['macho_file_count']} Developer files, "
          f"{data['totals']['declarations']} Swift declarations -> {output}")


if __name__ == "__main__":
    main()
