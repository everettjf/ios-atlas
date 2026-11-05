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

SELECTOR_PATTERN = r"(?:[^\W\d][\w$]*:|:)+|\.?[^\W\d][\w$]*"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def selector_from_declaration(line: str) -> tuple[str, str | None]:
    if not re.match(r"^[+-] \(", line) or not line.endswith(";"):
        raise ValueError(f"unrecognized method declaration: {line[:160]}")
    depth = 0
    close = None
    for index, char in enumerate(line[2:-1], 2):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                close = index
                break
    if close is None:
        raise ValueError(f"unbalanced return type: {line[:160]}")
    body = line[close + 1:-1].strip()
    if not body:
        # Preserve an IMP whose selector the dump did not decode.
        return line[0], None
    if re.fullmatch(SELECTOR_PATTERN, body):
        # Some dumps print only a raw selector, including empty components.
        return line[0], body
    pieces = re.findall(r"\b([^\W\d][\w$]*:)\s*\(", body)
    selector = "".join(pieces) if pieces else body
    if not re.fullmatch(SELECTOR_PATTERN, selector):
        raise ValueError(f"could not recover selector: {line[:160]}")
    # Bitfield types contain colons, so counting ':' in the whole declaration is incorrect.
    return line[0], selector


def parse_dump(text: str, class_table: set[tuple[str, str]] | None,
               ranges: list[tuple[int, int]], code_range: tuple[int, int]) -> tuple[list[dict], list[list], int, int, int]:
    lines = text.splitlines()
    toc = {}
    if not lines and not class_table:
        # ipsw emits an empty, successful dump for some cache images.
        # Preserve this as an inspected zero-result rather than inventing a TOC.
        toc = {name: 0 for name in
               ("__objc_classlist", "__objc_catlist", "__objc_protolist")}
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
            match = re.match(r"^@interface (\S*)(?: \(([^)]+)\))?.*// (0x[0-9a-f]+)(?: \(([^)]*)\))?$", line)
            if not match:
                raise ValueError(f"unrecognized interface header at line {number + 1}")
            class_name, category_name, address, marker = match.groups()
            if not class_name and category_name is None:
                raise ValueError(f"interface lacks both class and category at line {number + 1}")
            class_name = class_name or None
            if marker not in (None, "Swift"):
                raise ValueError(f"unrecognized interface marker at line {number + 1}: {marker}")
            metadata = int(address, 16)
            if not any(start <= metadata < end for start, end in ranges):
                raise ValueError(f"interface metadata outside defining image: {address}")
            groups.append({
                "class_name": class_name,
                "category_name": category_name,
                "display_name": (class_name if category_name is None else
                                 f"{class_name or '<unknown class>'} ({category_name})"),
                "metadata_address": address,
                "is_swift": marker == "Swift",
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
    actual_class_table = {(group["class_name"], group["metadata_address"]) for group in class_groups}
    if class_table is None:
        # Standalone Mach-O files have no independent dyld optimization table.
        # Their TOC can already include Swift-marked classes, so validate
        # counts and ranges without inventing an external class association.
        extra_class_count = len(class_groups) - toc["__objc_classlist"]
        table_invalid = (extra_class_count < 0 or
                         extra_class_count > sum(group["is_swift"] for group in class_groups))
        missing_classes = 0
    else:
        extra_classes = actual_class_table - class_table
        extra_class_count = len(extra_classes)
        table_invalid = (len(class_table) != toc["__objc_classlist"] or
                         len(class_groups) != toc["__objc_classlist"] + extra_class_count or
                         not class_table <= actual_class_table or
                         any(not group["is_swift"] for group in class_groups
                             if (group["class_name"], group["metadata_address"]) in extra_classes))
        missing_classes = len(class_table - actual_class_table)
    if (table_invalid or
            len(category_groups) != toc["__objc_catlist"] or
            protocol_count > toc["__objc_protolist"] or
            len({group["display_name"] for group in groups}) != len(groups) or
            len({tuple(row) for row in records}) != len(records) or
            sum(group["method_count"] for group in groups) != len(records)):
        raise ValueError(
            "class/category/protocol/method validation failed: "
            f"classes {len(class_groups)}/{toc['__objc_classlist']}, "
            f"categories {len(category_groups)}/{toc['__objc_catlist']}, "
            f"protocols {protocol_count}/{toc['__objc_protolist']}, "
            f"class table missing {missing_classes}, "
            f"extra Swift classes {extra_class_count}, "
            f"unique groups {len({group['display_name'] for group in groups})}/{len(groups)}, "
            f"unique method rows {len({tuple(row) for row in records})}/{len(records)}"
        )
    return groups, records, protocol_count, toc["__objc_protolist"], extra_class_count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-dump", required=True, type=Path)
    parser.add_argument("--image", type=Path,
                        help="Extracted analysis image for an independently checked UUID")
    parser.add_argument("--image-sha256")
    parser.add_argument("--cache-main", type=Path,
                        help="Main cache file when generating directly from the intact cache")
    parser.add_argument("--dyld-catalog", type=Path,
                        help="Cache-file hashes and identity for --cache-main mode")
    parser.add_argument("--install-name", required=True)
    parser.add_argument("--segments", required=True, type=Path)
    parser.add_argument("--objc-classes", required=True, type=Path)
    parser.add_argument("--expected-method-count", type=int,
                        help="Optional independently reviewed count for a single-image run")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    extracted_mode = args.image is not None and args.image_sha256 is not None
    cache_mode = args.cache_main is not None and args.dyld_catalog is not None
    if extracted_mode == cache_mode or bool(args.image) != bool(args.image_sha256) or \
            bool(args.cache_main) != bool(args.dyld_catalog):
        parser.error("choose --image with --image-sha256 or --cache-main with --dyld-catalog")

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
    image_hash = None
    cache_main_hash = None
    if extracted_mode:
        image_hash = sha256(args.image)
        if image_hash != args.image_sha256.lower():
            raise ValueError(f"extracted image SHA-256 mismatch: {image_hash}")
        uuid_output = subprocess.run(("xcrun", "dwarfdump", "--uuid", str(args.image)),
                                     check=True, capture_output=True, text=True).stdout
        if image["uuid"] not in uuid_output:
            raise ValueError("extracted image UUID differs from intact cache")
    else:
        dyld = json.loads(args.dyld_catalog.read_text())
        if (dyld["source"] != "official_ipsw_systemos" or
                dyld["kind"] != "dyld_shared_cache" or
                any(dyld[key] != segments[key] for key in
                    ("product_type", "build", "firmware_sha256", "cache_uuid"))):
            raise ValueError("dyld cache catalog identity differs from source catalogs")
        matches = [item for item in dyld["files"] if item["name"] == args.cache_main.name]
        if len(matches) != 1 or args.cache_main.stat().st_size != matches[0]["size"]:
            raise ValueError("main cache file is absent or has the wrong size")
        cache_main_hash = sha256(args.cache_main)
        if cache_main_hash != matches[0]["sha256"]:
            raise ValueError("main cache hash differs from exact firmware catalog")
    text_parts = [part for part in image["segments"] if part["name"] == "__TEXT"]
    if len(text_parts) != 1:
        raise ValueError("defining image has no unique __TEXT segment")
    code_range = (text_parts[0]["addr"], text_parts[0]["addr"] + text_parts[0]["memsz"])
    ranges = [(part["addr"], part["addr"] + part["memsz"])
              for part in image["segments"] if part["name"] != "__LINKEDIT"]
    class_table = {(row[0], row[1]) for row in classes["records"]
                   if row[3] == args.install_name}
    # ipsw may print raw, invalid UTF-8 bytes in type or ivar descriptions.
    # They are not used as names or selectors, but their loss is recorded.
    dump_text = args.class_dump.read_bytes().decode("utf-8", errors="replace")
    groups, records, rendered_protocols, toc_protocols, extra_swift_classes = parse_dump(
        dump_text, class_table, ranges, code_range)
    if args.expected_method_count is not None and len(records) != args.expected_method_count:
        raise ValueError(f"expected {args.expected_method_count} methods, found {len(records)}")
    selector_counts = Counter((row[0], row[1], row[2]) for row in records if row[2] is not None)
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
        "cache_main_sha256": cache_main_hash,
        "class_dump_sha256": sha256(args.class_dump),
        "class_dump_empty": not bool(dump_text),
        "class_dump_replacement_char_count": dump_text.count("\ufffd"),
        "class_count": sum(group["category_name"] is None for group in groups),
        "toc_class_count": len(class_table),
        "unlisted_swift_class_count": extra_swift_classes,
        "category_count": sum(group["category_name"] is not None for group in groups),
        "unknown_category_class_count": sum(group["category_name"] is not None and
                                            group["class_name"] is None for group in groups),
        "rendered_protocol_count": rendered_protocols,
        "toc_protocol_count": toc_protocols,
        "method_count": len(records),
        "unknown_selector_count": sum(row[2] is None for row in records),
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
