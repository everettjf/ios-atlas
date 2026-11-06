#!/usr/bin/env python3
"""Catalog direct loads of every standalone Mach-O in the exact IPSW images."""

from __future__ import annotations

import argparse
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from catalog_live_jailbreak_dependencies import PRIVATE_REFERENCE, dump, inspect, load


VOLUMES = {"FileSystem": "filesystem_root", "SystemOS": "systemos_root",
           "AppOS": "appos_root"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macho-catalog", required=True, type=Path)
    for option in VOLUMES.values():
        parser.add_argument("--" + option.replace("_", "-"), required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    source = load(args.macho_catalog)
    if (source.get("kind") != "standalone_macho_file_inventory" or
            source.get("source") != "official_ipsw_mounted_images" or
            source.get("macho_file_count") != len(source.get("records", []))):
        raise ValueError("invalid standalone Mach-O inventory")
    roots = {volume: getattr(args, option).resolve() for volume, option in VOLUMES.items()}
    workdir = args.workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    def one(item: dict) -> dict:
        volume = item["volume"]
        if volume not in roots:
            raise ValueError("unknown IPSW volume")
        checkpoint_dir = workdir / volume
        checkpoint_dir.mkdir(exist_ok=True)
        result = inspect(item, roots[volume], checkpoint_dir)
        return {"volume": volume, **result}

    records = []
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(one, item): (item["volume"], item["path"])
                   for item in source["records"]}
        for future in as_completed(futures):
            try:
                records.append(future.result())
            except Exception as error:
                failures.append((futures[future], str(error)))
            if (len(records) + len(failures)) % 250 == 0:
                print(f"inspected {len(records)} / {len(futures)}; failed {len(failures)}", flush=True)
    if failures:
        for key, reason in failures[:10]:
            print(f"failed {key}: {reason}", flush=True)
        raise RuntimeError(f"{len(failures)} standalone dependency inspections failed")
    records.sort(key=lambda item: (item["volume"], item["path"]))
    totals = Counter()
    for item in records:
        for part in item["slices"]:
            if part["install_name"] and PRIVATE_REFERENCE.search(part["install_name"]):
                raise ValueError("private install name needs manual review")
            if any(PRIVATE_REFERENCE.search(row["install_name"])
                   for row in part["dependencies"]):
                raise ValueError("private load name needs manual review")
            safe = [name for name in part["rpaths"]
                    if not PRIVATE_REFERENCE.search(name) and
                    not re.search(r"[\x00-\x1f\x7f]", name)]
            part["redacted_rpath_count"] = len(part["rpaths"]) - len(safe)
            part["rpaths"] = safe
            totals["slices"] += 1
            totals["direct_loads"] += len(part["dependencies"])
            totals["rpaths"] += len(safe)
            totals["redacted_rpaths"] += part["redacted_rpath_count"]
            totals["without_loads"] += not part["dependencies"]
    output = {"schema_version": 1, "kind": "standalone_macho_direct_dependencies",
              "source": "official_ipsw_mounted_images", "build": source["build"],
              "product_type": source["product_type"],
              "firmware_sha256": source["firmware_sha256"],
              "macho_file_count": len(records), "totals": dict(totals),
              "files": records}
    dump(args.output, output)
    print(f"{len(records)} files; {totals['direct_loads']} direct loads -> {args.output}")


if __name__ == "__main__":
    main()
