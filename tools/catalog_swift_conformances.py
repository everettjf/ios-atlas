#!/usr/bin/env python3
"""Index Swift type-conformance records from an intact iOS dyld cache.

The ipsw text stream is parsed without retaining its ~200 MB output in memory.
Every type, protocol, and conformance address must fall in exactly one
non-linkedit segment of an image matching ipsw's printed image label.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


HEADER = re.compile(
    r"0x([0-9a-f]+): type: 0x([0-9a-f]+), protocol: 0x([0-9a-f]+) "
    r"proto_conformance: 0x([0-9a-f]+), dylib_objc_index: (\d+)"
    r"( \(next is duplicate\))?")
BASE = 0x180000000
BUCKETS = 64


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(address: int, label: str, by_label: dict) -> int:
    candidates = by_label.get(label)
    if not candidates:
        raise ValueError(f"unknown Swift image label: {label}")
    matches = [index for index, ranges in candidates
               if any(start <= address < end for start, end in ranges)]
    if len(matches) != 1:
        raise ValueError(f"Swift address 0x{address:x} with label {label!r} "
                         f"has {len(matches)} matching image segments")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-catalog", required=True, type=Path)
    parser.add_argument("--segments-catalog", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path,
                        help="stdout of ipsw dyld swift <MAIN_DSC> --types")
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    cache = load(args.cache_catalog)
    segments = load(args.segments_catalog)
    source_keys = ("build", "product_type", "firmware_sha256", "cache_uuid", "platform")
    if (not segments["complete"] or segments["kind"] != "dyld_image_macho_segments" or
            any(segments[key] != cache[key] for key in source_keys) or
            segments["image_count"] != cache["image_count"] or
            len(segments["images"]) != len(cache["images"])):
        raise ValueError("Swift source and segment catalogs differ")
    by_name = {item["install_name"]: item for item in cache["images"]}
    images = segments["images"]
    if (len(by_name) != len(images) or
            any(item["install_name"] not in by_name or
                item["uuid"] != by_name[item["install_name"]]["uuid"]
                for item in images)):
        raise ValueError("segment and cache image identities differ")
    by_label = defaultdict(list)
    for index, image in enumerate(images):
        ranges = [(part["addr"], part["addr"] + part["memsz"])
                  for part in image["segments"] if part["name"] != "__LINKEDIT"
                  and part["memsz"]]
        by_label[image["install_name"].rsplit("/", 1)[-1]].append((index, ranges))

    args.workdir.mkdir(parents=True, exist_ok=True)
    spools = [args.workdir / f"b{bucket:02d}.jsonl" for bucket in range(BUCKETS)]
    handles = [path.open("w", encoding="utf-8") for path in spools]
    counts = Counter()
    image_counts = Counter()
    index_owner = {}
    try:
        with args.input.open(encoding="utf-8") as source:
            while True:
                header = source.readline()
                if not header:
                    break
                match = HEADER.fullmatch(header.strip())
                if not match:
                    raise ValueError(f"unparsed Swift header after {counts['records']} records")
                record_offset, type_rel, protocol_rel, conformance_rel = (
                    int(value, 16) for value in match.groups()[:4])
                objc_index = int(match[5])
                roles = []
                for expected, relative in zip("TPC", (type_rel, protocol_rel, conformance_rel)):
                    line = source.readline()
                    words = line.split()
                    if (len(words) != 4 or words[1] != expected or
                            not words[0].endswith(":")):
                        raise ValueError(f"unparsed Swift {expected} line after {counts['records']} records")
                    address = int(words[0][:-1], 16)
                    if address - relative != BASE:
                        raise ValueError(f"relative and absolute Swift {expected} addresses differ")
                    label = words[3]
                    image_index = resolve(address, label, by_label)
                    roles.append((address, None if words[2] == "n/a" else words[2], image_index))
                    counts[f"named_{expected}"] += words[2] != "n/a"
                owner = roles[2][2]
                previous = index_owner.setdefault(objc_index, owner)
                if previous != owner:
                    raise ValueError(f"dylib_objc_index {objc_index} maps to multiple images")
                row = [record_offset, objc_index,
                       *roles[0], *roles[1], *roles[2], bool(match[6])]
                handles[owner % BUCKETS].write(json.dumps(row, ensure_ascii=True,
                                                         separators=(",", ":")) + "\n")
                image_counts[owner] += 1
                counts["duplicates"] += bool(match[6])
                counts["records"] += 1
                if counts["records"] % 100000 == 0:
                    print(f"{counts['records']} Swift conformances parsed", flush=True)
    finally:
        for handle in handles:
            handle.close()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    buckets = []
    for bucket, spool in enumerate(spools):
        rows = [json.loads(line) for line in spool.open(encoding="utf-8")]
        rows.sort(key=lambda row: (row[10], row[8], row[0], row[1]))
        content = json.dumps({"schema_version": 1, "build": cache["build"],
                              "bucket": bucket, "records": rows}, ensure_ascii=True,
                             separators=(",", ":"), sort_keys=True).encode() + b"\n"
        blob = gzip.compress(content, mtime=0)
        filename = f"b{bucket:02d}.json.gz"
        (args.output_dir / filename).write_bytes(blob)
        buckets.append({"file": filename, "record_count": len(rows),
                        "sha256": hashlib.sha256(blob).hexdigest(), "size": len(blob)})
    source_hash = hashlib.sha256()
    with args.input.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            source_hash.update(block)
    index = {"schema_version": 1, "kind": "dyld_swift_type_conformances",
             "source": "official_ipsw_intact_cache_family", "tool": "ipsw",
             "command": "ipsw dyld swift <MAIN_DSC> --types",
             "complete": True, **{key: cache[key] for key in source_keys},
             "record_count": counts["records"], "duplicate_marker_count": counts["duplicates"],
             "named_type_count": counts["named_T"],
             "named_protocol_count": counts["named_P"],
             "named_conformance_count": counts["named_C"],
             "image_count_with_conformances": len(image_counts),
             "input_sha256": source_hash.hexdigest(),
             "image_counts": [image_counts[index] for index in range(len(images))],
             "images": [{"install_name": image["install_name"], "uuid": image["uuid"]}
                        for image in images],
             "address_base": BASE,
             "record_fields": ["record_offset", "dylib_objc_index", "type_address",
                               "type_symbol", "type_image_index", "protocol_address",
                               "protocol_symbol", "protocol_image_index", "conformance_address",
                               "conformance_symbol", "conformance_image_index", "next_is_duplicate"],
             "bucket_count": BUCKETS, "buckets": buckets}
    (args.output_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n")
    print(f"{counts['records']} Swift type conformances across {len(image_counts)} images -> {args.output_dir}")


if __name__ == "__main__":
    main()
