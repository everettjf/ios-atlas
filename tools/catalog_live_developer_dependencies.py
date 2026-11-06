#!/usr/bin/env python3
"""Index direct dylib loads in the verified live Developer mount Mach-O files."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from catalog_live_jailbreak_dependencies import PRIVATE_REFERENCE, dump, inspect, load
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
        raise RuntimeError(f"{len(failures)} Developer mount dependency inspections failed; "
                           "review private checkpoints")
    results.sort(key=lambda item: item["path"])
    totals = Counter()
    for item in results:
        for part in item["slices"]:
            if (part["install_name"] and PRIVATE_REFERENCE.search(part["install_name"])) or any(
                    PRIVATE_REFERENCE.search(row["install_name"])
                    for row in part["dependencies"]):
                raise ValueError("private Developer load name needs manual review")
            public_rpaths = [path for path in part["rpaths"]
                             if not PRIVATE_REFERENCE.search(path)]
            part["redacted_rpath_count"] = len(part["rpaths"]) - len(public_rpaths)
            part["rpaths"] = public_rpaths
            totals["slices"] += 1
            totals["direct_loads"] += len(part["dependencies"])
            totals["rpaths"] += len(public_rpaths)
            totals["redacted_rpaths"] += part["redacted_rpath_count"]
            totals["without_loads"] += not part["dependencies"]
    return {"schema_version": 1, "kind": "live_developer_direct_dependencies",
            "source": "verified_live_developer_mount_bytes",
            "build": source["build"], "product_type": source["product_type"],
            "macho_file_count": len(results), "totals": dict(totals),
            "files": results}


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
          f"{data['totals']['direct_loads']} direct loads -> {output}")


if __name__ == "__main__":
    main()
