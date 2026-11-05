#!/usr/bin/env python3
"""Catalog protocol entries from an intact iOS dyld cache optimization table.

The table reports image basenames. A nonunique basename stays unresolved: the
printed address may refer to shared metadata outside every named image.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


LINE = re.compile(r"\s*0x([0-9a-fA-F]+): ([^\t\r\n]+)\t([^\t\r\n]+)\s*")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-catalog", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tool", default="ipsw")
    args = parser.parse_args()
    catalog = json.loads(args.cache_catalog.read_text(encoding="utf-8"))
    if (catalog["kind"] != "dyld_shared_cache" or
            catalog["image_count"] != len(catalog["images"]) or
            catalog["architecture"] != "arm64e" or catalog["platform"] != "iOS"):
        raise ValueError("incomplete or unexpected cache source catalog")
    by_label = defaultdict(list)
    for image in catalog["images"]:
        by_label[image["install_name"].rsplit("/", 1)[-1]].append(image["install_name"])

    raw = subprocess.run([args.tool, "dyld", "objc", str(args.cache), "--proto"],
                         capture_output=True, text=True, timeout=120, check=True).stdout
    rows = []
    counts = Counter()
    image_counts = Counter()
    ambiguous_labels = {}
    for line_number, line in enumerate(raw.splitlines(), 1):
        match = LINE.fullmatch(line)
        if not match:
            raise ValueError(f"unparsed cache optimization entry at line {line_number}: {line[:100]!r}")
        address, protocol, label = match.groups()
        candidates = by_label.get(label)
        if not candidates:
            raise ValueError(f"unknown image label {label!r} at line {line_number}")
        if len(candidates) == 1:
            image, resolution = candidates[0], "unique_label"
            image_counts[image] += 1
        else:
            image, resolution = None, "ambiguous_label"
            ambiguous_labels[label] = sorted(candidates)
        counts[resolution] += 1
        rows.append([protocol, "0x" + address.lower(), label, image, resolution])
    rows.sort(key=lambda row: (row[0].casefold(), row[2], row[1]))
    output = {"schema_version": 1, "kind": "dyld_objc_optimization_protocols",
              "source": "official_ipsw_intact_cache_family",
              "build": catalog["build"], "product_type": catalog["product_type"],
              "firmware_sha256": catalog["firmware_sha256"],
              "cache_uuid": catalog["cache_uuid"], "tool": args.tool,
              "command": "ipsw dyld objc <MAIN_DSC> --proto", "complete": True,
              "record_count": len(rows), "image_count_with_unique_labels": len(image_counts),
              "resolution_counts": dict(sorted(counts.items())),
              "ambiguous_labels": dict(sorted(ambiguous_labels.items())),
              "records": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=True,
                                      separators=(",", ":"), sort_keys=True) + "\n")
    print(f"{len(rows)} protocol entries; {dict(counts)} -> {args.output}")


if __name__ == "__main__":
    main()
