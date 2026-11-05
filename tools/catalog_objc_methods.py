#!/usr/bin/env python3
"""Index one class's method selectors and IMP addresses from an exact dyld class dump."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_methods(text: str, class_name: str, start: int, end: int) -> list[list[str]]:
    lines = text.splitlines()
    headers = [line for line in lines if line.startswith("@interface ")]
    if len(headers) != 1 or not re.match(rf"^@interface {re.escape(class_name)}\s*:", headers[0]):
        raise ValueError("class dump does not contain exactly the requested interface")
    if sum(line.strip() == "@end" for line in lines) != 1:
        raise ValueError("class dump has an unexpected interface boundary")
    methods = []
    for number, line in enumerate(lines):
        if not line.startswith(("+ (", "- (")):
            continue
        address_line = lines[number - 1] if number else ""
        address_match = re.fullmatch(r"// (0x[0-9a-f]+)", address_line)
        declaration = re.fullmatch(r"([+-]) \([^)]*\)(.+);", line)
        if not address_match or not declaration:
            raise ValueError(f"unrecognized method declaration near line {number + 1}")
        address = int(address_match[1], 16)
        if not start <= address < end:
            raise ValueError(f"method address outside defining image __TEXT: {address_match[1]}")
        body = declaration[2].strip()
        pieces = re.findall(r"\b([A-Za-z_][A-Za-z_0-9]*:)\s*\(", body)
        selector = "".join(pieces) if pieces else body
        if (not re.fullmatch(r"(?:[A-Za-z_][A-Za-z_0-9]*:)+|\.?[A-Za-z_][A-Za-z_0-9]*", selector)
                or selector.count(":") != body.count(":")):
            raise ValueError(f"could not recover selector from: {line}")
        methods.append([declaration[1], selector, address_match[1]])
    if not methods or len({(row[0], row[1]) for row in methods}) != len(methods):
        raise ValueError("empty or duplicate method selectors")
    return sorted(methods, key=lambda row: (row[1].casefold(), row[0]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class-dump", required=True, type=Path)
    parser.add_argument("--class-name", required=True)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--install-name", required=True)
    parser.add_argument("--segments", required=True, type=Path)
    parser.add_argument("--expected-method-count", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    actual_hash = sha256(args.image)
    if actual_hash != args.image_sha256.lower():
        raise ValueError(f"extracted image SHA-256 mismatch: {actual_hash}")
    segments = json.loads(args.segments.read_text())
    matches = [item for item in segments["images"]
               if item["install_name"] == args.install_name]
    if (len(matches) != 1 or not segments["complete"] or
            segments["source"] != "official_ipsw_intact_cache_family"):
        raise ValueError("defining image absent from complete segment catalog")
    image = matches[0]
    uuid_output = subprocess.run(("xcrun", "dwarfdump", "--uuid", str(args.image)),
                                 check=True, capture_output=True, text=True).stdout
    if image["uuid"] not in uuid_output:
        raise ValueError("extracted image Mach-O UUID differs from intact cache")
    text_segments = [part for part in image["segments"] if part["name"] == "__TEXT"]
    if len(text_segments) != 1:
        raise ValueError("defining image has no unique __TEXT segment")
    start = text_segments[0]["addr"]
    end = start + text_segments[0]["memsz"]
    dump_text = args.class_dump.read_text(encoding="utf-8")
    methods = parse_methods(dump_text, args.class_name, start, end)
    if len(methods) != args.expected_method_count:
        raise ValueError(f"expected {args.expected_method_count} methods, found {len(methods)}")
    output = {
        "schema_version": 1,
        "kind": "selected_objc_class_methods",
        "source": "official_ipsw_intact_cache_family",
        "tool": "ipsw class-dump",
        "product_type": segments["product_type"],
        "build": segments["build"],
        "firmware_sha256": segments["firmware_sha256"],
        "cache_uuid": segments["cache_uuid"],
        "class_name": args.class_name,
        "install_name": args.install_name,
        "image_uuid": image["uuid"],
        "extracted_image_sha256": actual_hash,
        "class_dump_sha256": hashlib.sha256(args.class_dump.read_bytes()).hexdigest(),
        "method_count": len(methods),
        "class_method_count": sum(row[0] == "+" for row in methods),
        "instance_method_count": sum(row[0] == "-" for row in methods),
        "methods": methods,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, sort_keys=True, separators=(",", ":")) + "\n")
    print(f"{len(methods)} methods for {args.class_name} -> {args.output}")


if __name__ == "__main__":
    main()
