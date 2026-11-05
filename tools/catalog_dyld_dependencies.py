#!/usr/bin/env python3
"""Catalog every direct Mach-O dylib load in one intact dyld cache family."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def inspect(tool: str, cache: Path, image: dict) -> dict:
    name = image["install_name"]
    result = subprocess.run([tool, "dyld", "macho", str(cache), name,
                             "--json", "--loads"], capture_output=True,
                            text=True, timeout=120, check=True)
    macho = json.loads(result.stdout)
    uuids = [item["uuid"] for item in macho["loads"] if item["load_cmd"] == "LC_UUID"]
    if uuids != [image["uuid"]]:
        raise ValueError(f"Mach-O UUID differs from cache inventory: {name}")
    imports = []
    for item in macho["loads"]:
        command = item["load_cmd"]
        if "DYLIB" in command and command != "LC_ID_DYLIB":
            if not item.get("name"):
                raise ValueError(f"dylib command without name: {name}: {command}")
            imports.append({"install_name": item["name"], "load_command": command})
    return {"install_name": name, "uuid": image["uuid"],
            "macho_type": macho["header"]["type"],
            "architecture": macho["header"]["subcpu"],
            "imports": imports}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-catalog", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tool", default="ipsw")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    catalog = json.loads(args.cache_catalog.read_text(encoding="utf-8"))
    if (catalog["image_count"] != len(catalog["images"]) or
            catalog["file_count"] != len(catalog["files"]) or
            catalog["architecture"] != "arm64e"):
        raise ValueError("incomplete or unexpected dyld cache source catalog")
    source = {"build": catalog["build"], "product_type": catalog["product_type"],
              "firmware_sha256": catalog["firmware_sha256"],
              "cache_uuid": catalog["cache_uuid"],
              "image_count": catalog["image_count"]}
    by_name = {item["install_name"]: item for item in catalog["images"]}
    if len(by_name) != len(catalog["images"]):
        raise ValueError("duplicate cache image install name")

    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if args.checkpoint.exists():
        with args.checkpoint.open(encoding="utf-8") as stream:
            first = json.loads(next(stream))
            if first != {"source": source}:
                raise ValueError("checkpoint describes another cache source")
            for line in stream:
                item = json.loads(line)
                name = item["install_name"]
                if name not in by_name or item["uuid"] != by_name[name]["uuid"] or name in done:
                    raise ValueError(f"invalid checkpoint entry: {name}")
                done[name] = item
    else:
        args.checkpoint.write_text(json.dumps({"source": source}, sort_keys=True) + "\n")

    pending = [item for item in catalog["images"] if item["install_name"] not in done]
    print(f"{len(done)} resumed; {len(pending)} remaining", flush=True)
    with args.checkpoint.open("a", encoding="utf-8") as stream:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(inspect, args.tool, args.cache, item): item["install_name"]
                       for item in pending}
            for future in as_completed(futures):
                item = future.result()
                done[item["install_name"]] = item
                stream.write(json.dumps(item, ensure_ascii=True,
                                        separators=(",", ":"), sort_keys=True) + "\n")
                stream.flush()
                if len(done) % 100 == 0 or len(done) == len(by_name):
                    print(f"{len(done)}/{len(by_name)} images", flush=True)

    if len(done) != len(by_name):
        raise ValueError("cache image dependency collection is incomplete")
    records = [done[name] for name in sorted(done)]
    command_counts = Counter(imp["load_command"] for item in records for imp in item["imports"])
    target_names = set(by_name)
    exact_matches = sum(imp["install_name"] in target_names for item in records
                        for imp in item["imports"])
    output = {"schema_version": 1, "kind": "dyld_image_direct_loads",
              "source": "official_ipsw_intact_cache_family",
              **source, "tool": args.tool, "complete": True,
              "direct_import_count": sum(command_counts.values()),
              "exact_cache_name_match_count": exact_matches,
              "load_command_counts": dict(sorted(command_counts.items())),
              "images": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=True,
                                      separators=(",", ":"), sort_keys=True) + "\n")
    print(f"{len(records)} cache images, {output['direct_import_count']} direct loads, "
          f"{exact_matches} exact cache-name matches -> {args.output}")


if __name__ == "__main__":
    main()
