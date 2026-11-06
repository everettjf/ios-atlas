#!/usr/bin/env python3
"""Index Objective-C methods in the arm64e slice of each verified Developer binary."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from catalog_standalone_objc_methods import inspect, dump, load
from collect_live_device import private_path


def catalog(macho_catalog: Path, binary_root: Path, workdir: Path,
            workers: int = 4) -> dict:
    source = load(macho_catalog)
    if (source.get("schema_version") != 1 or
            source.get("kind") != "live_developer_macho_inventory" or
            source.get("source") != "verified_live_developer_mount_bytes" or
            source.get("macho_file_count") != len(source.get("records", [])) or
            any(len([part for part in item["slices"]
                     if part["architecture"] == "arm64e"]) != 1
                for item in source["records"])):
        raise ValueError("Developer Mach-O catalog lacks exact arm64e slices")
    binary_root = private_path(binary_root)
    workdir = private_path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    items = []
    for record in source["records"]:
        selected = next(part for part in record["slices"]
                        if part["architecture"] == "arm64e")
        items.append({"volume": "Developer", **record,
                      "slices": [selected] + [part for part in record["slices"]
                                               if part is not selected]})
    results = []
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(inspect, item, {"Developer": binary_root}, workdir): item
                   for item in items}
        for future in as_completed(futures):
            try:
                result = future.result()
                result["architecture"] = "arm64e"
                results.append(result)
            except Exception as error:
                if isinstance(error, RuntimeError) and str(error).startswith(
                        "class-dump failed for Developer:"):
                    item = futures[future]
                    selected = item["slices"][0]
                    results.append({"volume": "Developer", "path": item["path"],
                                    "sha256": item["sha256"],
                                    "uuid": selected["uuid"],
                                    "architecture": "arm64e", "status": "failed",
                                    "failure_reason": "class_dump_error",
                                    "class_count": 0, "category_count": 0,
                                    "method_count": 0, "unknown_selector_count": 0,
                                    "groups": [], "records": []})
                else:
                    failures.append((futures[future]["path"], str(error)))
    if failures:
        raise RuntimeError(f"{len(failures)} Developer ObjC inspections failed; "
                           "review private checkpoints")
    results.sort(key=lambda item: item["path"])
    totals = Counter()
    for item in results:
        totals[item["status"]] += 1
        totals["classes"] += item["class_count"]
        totals["categories"] += item["category_count"]
        totals["methods"] += item["method_count"]
        totals["unknown_selectors"] += item["unknown_selector_count"]
    return {"schema_version": 1, "kind": "live_developer_objc_methods",
            "source": "verified_live_developer_mount_bytes",
            "tool": "ipsw class-dump --re -V; ipsw macho info --json --loads",
            "product_type": source["product_type"], "build": source["build"],
            "selected_architecture": "arm64e", "macho_file_count": len(results),
            "totals": dict(totals), "files": results}


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
          f"{data['totals']['methods']} arm64e ObjC methods -> {output}")


if __name__ == "__main__":
    main()
