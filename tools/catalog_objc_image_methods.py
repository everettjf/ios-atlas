#!/usr/bin/env python3
"""Index class and category method metadata from one exact dyld cache image."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def selector_from_declaration(line: str) -> tuple[str, str]:
    declaration = re.fullmatch(r"([+-]) \([^)]*\)(.+);", line)
    if not declaration:
        raise ValueError(f"unrecognized method declaration: {line[:160]}")
    body = declaration[2].strip()
    pieces = re.findall(r"\b([A-Za-z_][A-Za-z_0-9]*:)\s*\(", body)
    selector = "".join(pieces) if pieces else body
    if not re.fullmatch(r"(?:[A-Za-z_][A-Za-z_0-9]*:)+|\.?[A-Za-z_][A-Za-z_0-9]*", selector):
        raise ValueError(f"could not recover selector: {line[:160]}")
    # Bitfield types contain colons, so counting ':' in the whole declaration is incorrect.
    return declaration[1], selector


def parse_dump(text: str, class_table: set[tuple[str, str]],
               ranges: list[tuple[int, int]], code_range: tuple[int, int]) -> tuple[list[dict], list[list]]:
    lines = text.splitlines()
    toc = {}
    for line in lines[:15]:
        match = re.fullmatch(r"  (__objc_classlist|__objc_catlist|__objc_protolist)\s+=\s+(\d+)", line)
        if match:
            toc[match[1]] = int(match[2])
    if set(toc) != {"__objc_classlist", "__objc_catlist", "__objc_protolist"}:
        raise ValueError("class dump lacks complete Objective-C TOC")

    groups: list[dict] = []
    records: list[list] = []
    current: int | None = None
    protocol_count = 0
    for number, line in enumerate(lines):
        if line.startswith("@protocol "):
            if current is not None:
                raise ValueError(f"unterminated interface at line {number + 1}")
            protocol_count += 1
            current = None
        elif line.startswith("@interface "):
            if current is not None:
                raise ValueError(f"unterminated interface at line {number + 1}")
            match = re.match(r"^@interface (\S+)(?: \(([^)]+)\))?.*// (0x[0-9a-f]+)$", line)
            if not match:
                raise ValueError(f"unrecognized interface header at line {number + 1}")
            class_name, category_name, address = match.groups()
            metadata = int(address, 16)
            if not any(start <= metadata < end for start, end in ranges):
                raise ValueError(f"interface metadata outside defining image: {address}")
            groups.append({
                "class_name": class_name,
                "category_name": category_name,
                "display_name": class_name if category_name is None else f"{class_name} ({category_name})",
                "metadata_address": address,
                "method_count": 0,
            })
            current = len(groups) - 1
        elif line == "@end":
            current = None
        elif line.startswith(("+ (", "- (")) and current is not None:
            prior = lines[number - 1] if number else ""
            address = re.fullmatch(r"// (0x[0-9a-f]+)", prior)
            if not address:
                raise ValueError(f"method lacks adjacent IMP address at line {number + 1}")
            method_kind, selector = selector_from_declaration(line)
            imp = int(address[1], 16)
            if not code_range[0] <= imp < code_range[1]:
                raise ValueError(f"method IMP outside defining image __TEXT: {address[1]}")
            records.append([current, method_kind, selector, address[1]])
            groups[current]["method_count"] += 1

    class_groups = [group for group in groups if group["category_name"] is None]
    category_groups = [group for group in groups if group["category_name"] is not None]
    if (len(class_groups) != toc["__objc_classlist"] or
            len(category_groups) != toc["__objc_catlist"] or
            protocol_count != toc["__objc_protolist"] or
            {(group["class_name"], group["metadata_address"]) for group in class_groups} != class_table or
            len({group["display_name"] for group in groups}) != len(groups) or
            len({tuple(row) for row in records}) != len(records) or
            sum(group["method_count"] for group in groups) != len(records)):
        raise ValueError("class, category, protocol, or method counts disagree with source metadata")
    return groups, records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-dump", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--install-name", required=True)
    parser.add_argument("--segments", required=True, type=Path)
    parser.add_argument("--objc-classes", required=True, type=Path)
    parser.add_argument("--expected-method-count", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    image_hash = sha256(args.image)
    if image_hash != args.image_sha256.lower():
        raise ValueError(f"extracted image SHA-256 mismatch: {image_hash}")
    segments = json.loads(args.segments.read_text())
    classes = json.loads(args.objc_classes.read_text())
    images = [image for image in segments["images"]
              if image["install_name"] == args.install_name]
    if (len(images) != 1 or not segments["complete"] or not classes["complete"] or
            segments["source"] != "official_ipsw_intact_cache_family" or
            classes["source"] != "official_ipsw_intact_cache_family" or
            any(segments[key] != classes[key] for key in
                ("product_type", "build", "firmware_sha256", "cache_uuid"))):
        raise ValueError("source catalogs are incomplete or mismatched")
    image = images[0]
    uuid_output = subprocess.run(("xcrun", "dwarfdump", "--uuid", str(args.image)),
                                 check=True, capture_output=True, text=True).stdout
    if image["uuid"] not in uuid_output:
        raise ValueError("extracted image UUID differs from intact cache")
    text_parts = [part for part in image["segments"] if part["name"] == "__TEXT"]
    if len(text_parts) != 1:
        raise ValueError("defining image has no unique __TEXT segment")
    code_range = (text_parts[0]["addr"], text_parts[0]["addr"] + text_parts[0]["memsz"])
    ranges = [(part["addr"], part["addr"] + part["memsz"])
              for part in image["segments"] if part["name"] != "__LINKEDIT"]
    class_table = {(row[0], row[1]) for row in classes["records"]
                   if row[3] == args.install_name}
    groups, records = parse_dump(args.class_dump.read_text(encoding="utf-8"),
                                 class_table, ranges, code_range)
    if len(records) != args.expected_method_count:
        raise ValueError(f"expected {args.expected_method_count} methods, found {len(records)}")
    selector_counts = Counter((row[0], row[1], row[2]) for row in records)
    output = {
        "schema_version": 1,
        "kind": "dyld_objc_image_methods",
        "source": "official_ipsw_intact_cache_family",
        "tool": "ipsw class-dump --re -V",
        "product_type": segments["product_type"],
        "build": segments["build"],
        "firmware_sha256": segments["firmware_sha256"],
        "cache_uuid": segments["cache_uuid"],
        "install_name": args.install_name,
        "image_uuid": image["uuid"],
        "extracted_image_sha256": image_hash,
        "class_dump_sha256": sha256(args.class_dump),
        "class_count": sum(group["category_name"] is None for group in groups),
        "category_count": sum(group["category_name"] is not None for group in groups),
        "method_count": len(records),
        "duplicate_selector_group_count": sum(count > 1 for count in selector_counts.values()),
        "groups": groups,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(json.dumps(output, sort_keys=True,
                                               separators=(",", ":")).encode() + b"\n", mtime=0))
    print(f"{len(groups)} class/category declarations, {len(records)} methods -> {args.output}")


if __name__ == "__main__":
    main()
