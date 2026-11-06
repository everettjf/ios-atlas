#!/usr/bin/env python3
"""Classify public script and ELF signatures into fixed, privacy-reviewed labels."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

from collect_live_device import private_path


SCRIPT_SUBTYPES = {"sh", "bash", "zsh", "perl_or_awk", "perl", "dtrace",
                   "m4", "game_script", "makefile", "other"}
ELF_SUBTYPES = {"netronome_32_lsb_executable", "other"}


def subtype(kind: str, description: bytes) -> str:
    value = description.lower()
    if kind == "elf":
        return ("netronome_32_lsb_executable" if value.startswith(
            b"elf 32-bit lsb executable, netronome flow processor,") else "other")
    if kind != "script":
        raise ValueError("unsupported alternate-code kind")
    if value.startswith((b"posix shell script,", b"a /usr/bin/sh script,",
                         b"a /usr/bin/env sh script,")):
        return "sh"
    prefixes = ((b"bourne-again shell script,", "bash"),
                (b"paul falstad's zsh script,", "zsh"),
                (b"awk or perl script,", "perl_or_awk"),
                (b"perl script text executable", "perl"),
                (b"a /usr/sbin/dtrace -s script,", "dtrace"),
                (b"m4 macro processor script,", "m4"),
                (b"gta script (scm),", "game_script"),
                (b"makefile script,", "makefile"))
    return next((label for prefix, label in prefixes if value.startswith(prefix)), "other")


def build(formats_path: Path, sources: dict[str, Path]) -> dict:
    formats = json.loads(gzip.decompress(formats_path.read_bytes()))
    wanted = {path: kind for path, kind in formats["records"]
              if kind in ("script", "elf")}
    found = {}
    for label, source_path in sources.items():
        raw = private_path(source_path).read_bytes()
        expected = formats["type_sources"][label]
        if hashlib.sha256(raw).hexdigest() != expected["sha256"] or not raw.endswith(b"\0"):
            raise ValueError("private type source hash or terminator differs")
        parts = raw.split(b"\0")[:-1]
        if len(parts) % 2 or len(parts) // 2 != expected["regular_files"]:
            raise ValueError("private type source row count differs")
        for encoded, description in zip(parts[::2], parts[1::2]):
            path = encoded.decode("utf-8", "surrogateescape")
            if path not in wanted:
                continue
            if path in found:
                raise ValueError("duplicate public alternate-code path")
            kind = wanted[path]
            found[path] = (kind, subtype(kind, description))
    if set(found) != set(wanted):
        raise ValueError("script or ELF source coverage differs")
    records = [[path, *found[path]] for path in sorted(found)]
    counts = dict(Counter(f"{kind}:{detail}" for _, kind, detail in records))
    return {"schema_version": 1, "kind": "live_device_public_alternate_code",
            "source": "private_file_type_pass_fixed_subtypes",
            "build": formats["build"], "product_type": formats["product_type"],
            "format_catalog_sha256": hashlib.sha256(formats_path.read_bytes()).hexdigest(),
            "file_count": len(records), "subtype_counts": counts,
            "records": records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formats", required=True, type=Path)
    parser.add_argument("--base-types", required=True, type=Path)
    parser.add_argument("--jailbreak-types", required=True, type=Path)
    parser.add_argument("--developer-types", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = build(args.formats, {"base": args.base_types,
                                  "jailbreak": args.jailbreak_types,
                                  "developer": args.developer_types})
    target = args.output.resolve()
    catalog_dir = Path(__file__).resolve().parents[1] / "catalog" / "ios" / "23A355"
    if ".local" in target.parts:
        private_path(target)
    elif target.parent != catalog_dir:
        raise ValueError("output must be in ignored .local or exact-build public catalog")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(gzip.compress(json.dumps(output, sort_keys=True,
                     separators=(",", ":")).encode() + b"\n", mtime=0))
    print(f"{output['file_count']} paths: {output['subtype_counts']}")


if __name__ == "__main__":
    main()
