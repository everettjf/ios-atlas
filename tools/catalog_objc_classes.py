#!/usr/bin/env python3
"""Catalog Objective-C class entries from an intact iOS dyld cache.

The cache optimization table prints image basenames, not install names. Resolve
duplicate basenames with the defining class address and that image's Mach-O
segment ranges. Keep unresolved records explicit rather than guessing.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


LINE = re.compile(r"\s*0x([0-9a-fA-F]+): ([^\t\r\n]+)\t([^\t\r\n]+)\s*")


def segments(tool: str, cache: Path, image: dict) -> tuple[str, list[tuple[int, int]]]:
    name = image["install_name"]
    result = subprocess.run([tool, "dyld", "macho", str(cache), name,
                             "--json", "--loads"], capture_output=True,
                            text=True, timeout=120, check=True)
    macho = json.loads(result.stdout)
    uuids = [item["uuid"] for item in macho["loads"] if item["load_cmd"] == "LC_UUID"]
    if uuids != [image["uuid"]]:
        raise ValueError(f"Mach-O UUID differs from cache inventory: {name}")
    ranges = [(item["addr"], item["addr"] + item["memsz"])
              for item in macho["loads"] if item["load_cmd"] == "LC_SEGMENT_64"
              and item["name"] != "__LINKEDIT" and item["memsz"]]
    if not ranges:
        raise ValueError(f"no content segments for {name}")
    return name, ranges


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-catalog", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tool", default="ipsw")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    catalog = json.loads(args.cache_catalog.read_text(encoding="utf-8"))
    if (catalog["kind"] != "dyld_shared_cache" or
            catalog["image_count"] != len(catalog["images"])
            or catalog["architecture"] != "arm64e" or catalog["platform"] != "iOS"):
        raise ValueError("incomplete or unexpected cache source catalog")
    by_basename = defaultdict(list)
    for image in catalog["images"]:
        by_basename[image["install_name"].rsplit("/", 1)[-1]].append(image)

    raw = subprocess.run([args.tool, "dyld", "objc", str(args.cache), "--class"],
                         capture_output=True, text=True, timeout=120, check=True).stdout
    entries = []
    ambiguous = set()
    for line_number, line in enumerate(raw.splitlines(), 1):
        match = LINE.fullmatch(line)
        if not match:
            raise ValueError(f"unparsed cache optimization entry at line {line_number}: {line[:100]!r}")
        address, class_name, label = match.groups()
        candidates = by_basename.get(label)
        if not candidates:
            raise ValueError(f"unknown image label {label!r} at line {line_number}")
        if len(candidates) > 1:
            ambiguous.update(image["install_name"] for image in candidates)
        entries.append((class_name, int(address, 16), label))

    by_name = {image["install_name"]: image for image in catalog["images"]}
    ranges = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(segments, args.tool, args.cache, by_name[name]): name
                   for name in ambiguous}
        for future in as_completed(futures):
            name, found = future.result()
            ranges[name] = found
    print(f"{len(entries)} class entries; {len(ambiguous)} duplicate-basename images inspected", flush=True)

    rows = []
    resolution_counts = Counter()
    image_counts = Counter()
    for class_name, address, label in entries:
        candidates = by_basename[label]
        if len(candidates) == 1:
            install_name, resolution = candidates[0]["install_name"], "unique_label"
        else:
            matched = [image["install_name"] for image in candidates
                       if any(start <= address < end for start, end in ranges[image["install_name"]])]
            install_name, resolution = (matched[0], "segment_address") if len(matched) == 1 else (None, "unresolved")
        resolution_counts[resolution] += 1
        if install_name:
            image_counts[install_name] += 1
        rows.append([class_name, f"0x{address:x}", label, install_name, resolution])
    rows.sort(key=lambda row: (row[0].casefold(), row[2], row[1]))
    output = {"schema_version": 1, "kind": "dyld_objc_optimization_classes",
              "source": "official_ipsw_intact_cache_family",
              "build": catalog["build"], "product_type": catalog["product_type"],
              "firmware_sha256": catalog["firmware_sha256"],
              "cache_uuid": catalog["cache_uuid"], "tool": args.tool,
              "command": "ipsw dyld objc <MAIN_DSC> --class", "complete": True,
              "record_count": len(rows), "image_count_with_classes": len(image_counts),
              "resolution_counts": dict(sorted(resolution_counts.items())),
              "records": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=True,
                                      separators=(",", ":"), sort_keys=True) + "\n")
    print(f"{len(rows)} entries; {dict(resolution_counts)} -> {args.output}")


if __name__ == "__main__":
    main()
