#!/usr/bin/env python3
"""Catalog Objective-C methods in every verified live jailbreak Mach-O file.

The private acquired binaries and per-file checkpoints remain under .local.
Only a complete aggregate can be passed to the site builder for publication.
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from catalog_standalone_objc_methods import inspect
from collect_live_device import private_path


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
    catalog_path = args.macho_catalog.resolve()
    binary_root = private_path(args.binary_root)
    workdir = private_path(args.workdir)
    output = private_path(args.output)
    source = json.loads(gzip.decompress(catalog_path.read_bytes()))
    if (source.get("schema_version") != 1 or
            source.get("kind") != "live_jailbreak_macho_inventory" or
            source.get("source") != "verified_live_device_macho_bytes" or
            source.get("macho_file_count") != len(source.get("records", []))):
        raise ValueError("invalid live Mach-O source catalog")
    workdir.mkdir(parents=True, exist_ok=True)
    items = [{"volume": "Jailbreak", **record} for record in source["records"]]
    results = []
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(inspect, item, {"Jailbreak": binary_root}, workdir): item
                   for item in items}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as error:
                failures.append((futures[future]["path"], str(error)))
    if failures:
        raise RuntimeError(f"{len(failures)} live files failed Objective-C inspection; "
                           "review private checkpoints before publishing")
    results.sort(key=lambda item: item["path"])
    totals = Counter()
    for item in results:
        totals[item["status"]] += 1
        totals["classes"] += item["class_count"]
        totals["categories"] += item["category_count"]
        totals["methods"] += item["method_count"]
        totals["unknown_selectors"] += item["unknown_selector_count"]
    data = {"schema_version": 1, "kind": "live_jailbreak_objc_methods",
            "source": "verified_live_device_macho_bytes",
            "product_type": source["product_type"], "build": source["build"],
            "macho_file_count": len(results), "totals": dict(totals), "files": results}
    payload = json.dumps(data, ensure_ascii=True, separators=(",", ":"),
                         sort_keys=True).encode() + b"\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(gzip.compress(payload, mtime=0))
    print(f"{len(results)} files, {totals['methods']} ObjC methods -> {output}")


if __name__ == "__main__":
    main()
