#!/usr/bin/env python3
"""Publish safe content-format labels for every reviewed live regular file.

Raw `file` descriptions may contain private strings and remain under .local.
Only fixed category keys and already-reviewed public paths enter the output.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from collect_live_device import private_path


CATEGORIES = {
    "macho": "Mach-O or mixed Mach-O container",
    "script": "Script or makefile",
    "elf": "ELF binary",
    "pe": "PE binary",
    "plist": "Binary property list",
    "xml": "XML",
    "json": "JSON",
    "sqlite": "SQLite database",
    "image": "Image",
    "media": "Audio or video",
    "font": "Font",
    "archive": "Archive or compressed data",
    "text": "Text",
    "empty": "Empty file",
    "data": "Unidentified data",
    "other": "Other or unclassified format",
}
SCRIPT = re.compile(rb"\bscript\b", re.IGNORECASE)
ELF = re.compile(rb"\bELF\b")


def classify(description: bytes) -> str:
    value = description.lower()
    if b"mach-o" in value or b"universal binary" in value:
        return "macho"
    if SCRIPT.search(description):
        return "script"
    if ELF.search(description):
        return "elf"
    if b"pe32" in value or b"ms-dos executable" in value:
        return "pe"
    if value.startswith(b"apple binary property list"):
        return "plist"
    if b"xml" in value or value.startswith(b"html document"):
        return "xml"
    if value.startswith((b"json text data", b"json data")):
        return "json"
    if b"sqlite" in value:
        return "sqlite"
    if any(token in value for token in (b"image data", b"heif image", b"jpeg", b"svg scalable", b"photoshop image")):
        return "image"
    if any(token in value for token in (b"audio", b"video", b"quicktime movie", b"mpeg", b"mp4", b"iso media")):
        return "media"
    if any(token in value for token in (b"font", b"truetype", b"opentype")):
        return "font"
    if any(token in value for token in (b"archive", b"compressed data", b"zstandard", b"bzip2", b"xz compressed", b"xar", b"cpio")):
        return "archive"
    if b"text" in value or value.startswith((b"ascii", b"utf-8 unicode")):
        return "text"
    if value == b"empty":
        return "empty"
    if value == b"data":
        return "data"
    return "other"


def type_rows(path: Path) -> tuple[list[tuple[str, str]], str]:
    raw = private_path(path).read_bytes()
    if not raw.endswith(b"\0"):
        raise ValueError("truncated private file-type output")
    parts = raw.split(b"\0")[:-1]
    if len(parts) % 2:
        raise ValueError("unpaired private file-type output")
    rows = []
    seen = set()
    for encoded, description in zip(parts[::2], parts[1::2]):
        name = encoded.decode("utf-8", "surrogateescape")
        if not name.startswith("/") or name in seen or not description:
            raise ValueError("duplicate or malformed private file-type path")
        seen.add(name)
        rows.append((name, classify(description)))
    return rows, hashlib.sha256(raw).hexdigest()


def build(args: argparse.Namespace) -> dict:
    public = json.loads(gzip.decompress(args.device_catalog.read_bytes()))
    if (public.get("kind") != "live_device_public_paths" or
            public.get("product_type") != "iPhone12,1" or
            public.get("build") != "23A355" or
            public.get("entry_count") != len(public.get("entries", []))):
        raise ValueError("reviewed live-device path catalog differs")
    files = {row[0] for row in public["entries"] if row[1] == "file"}
    if len(files) != public["type_counts"]["file"]:
        raise ValueError("duplicate public regular-file path")
    paths = {}
    sources = {}
    for label, source_path in (("base", args.base_types),
                               ("jailbreak", args.jailbreak_types),
                               ("developer", args.developer_types)):
        rows, digest = type_rows(source_path)
        sources[label] = {"sha256": digest, "regular_files": len(rows)}
        for path, category in rows:
            if path in paths:
                raise ValueError("file type path appears in multiple source views")
            paths[path] = category
    if files - paths.keys():
        raise ValueError("some reviewed regular files lack a content type")
    rows = [[path, paths[path]] for path in sorted(files)]
    counts = dict(Counter(category for _, category in rows))
    if sum(counts.values()) != len(files) or set(counts) - CATEGORIES.keys():
        raise ValueError("content format categories do not reconcile")
    return {"schema_version": 1, "kind": "live_device_public_file_formats",
            "source": "private_live_file_type_pass_fixed_categories",
            "build": public["build"], "product_type": public["product_type"],
            "private_manifest_sha256": public["private_manifest_sha256"],
            "device_catalog_sha256": hashlib.sha256(args.device_catalog.read_bytes()).hexdigest(),
            "file_count": len(rows), "excluded_private_type_paths": len(paths.keys() - files),
            "type_sources": sources, "category_counts": counts, "records": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-catalog", required=True, type=Path)
    parser.add_argument("--base-types", required=True, type=Path)
    parser.add_argument("--jailbreak-types", required=True, type=Path)
    parser.add_argument("--developer-types", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = build(args)
    target = args.output.resolve()
    catalog_dir = Path(__file__).resolve().parents[1] / "catalog" / "ios" / "23A355"
    if ".local" in target.parts:
        private_path(target)
    elif target.parent != catalog_dir:
        raise ValueError("output must be in ignored .local or the exact-build public catalog")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(gzip.compress(json.dumps(output, ensure_ascii=True,
                     sort_keys=True, separators=(",", ":")).encode() + b"\n", mtime=0))
    print(json.dumps({"file_count": output["file_count"],
                      "excluded_private_type_paths": output["excluded_private_type_paths"],
                      "category_counts": output["category_counts"]}, sort_keys=True))


if __name__ == "__main__":
    main()
