#!/usr/bin/env python3
"""Index Mach-O segment ranges for every image in an intact dyld cache."""

from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def inspect(tool: str, cache: Path, image: dict) -> dict:
    name = image["install_name"]
    result = subprocess.run([tool, "dyld", "macho", str(cache), name,
                             "--json", "--loads"], capture_output=True,
                            text=True, timeout=120, check=True)
    macho = json.loads(result.stdout)
    uuids = [load["uuid"] for load in macho["loads"] if load["load_cmd"] == "LC_UUID"]
    if uuids != [image["uuid"]]:
        raise ValueError(f"Mach-O UUID differs from cache inventory: {name}")
    segments = [{key: load.get(key, 0) if key in ("memsz", "filesz") else load[key]
                 for key in ("name", "addr", "memsz", "offset", "filesz", "maxprot", "prot")}
                for load in macho["loads"] if load["load_cmd"] == "LC_SEGMENT_64"]
    if not any(segment["name"] == "__TEXT" for segment in segments):
        raise ValueError(f"no text segment in {name}")
    return {"install_name": name, "uuid": image["uuid"], "segments": segments}


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
    if (catalog["kind"] != "dyld_shared_cache" or
            catalog["image_count"] != len(catalog["images"]) or
            catalog["architecture"] != "arm64e"):
        raise ValueError("incomplete or unexpected dyld cache catalog")
    source = {key: catalog[key] for key in
              ("build", "product_type", "firmware_sha256", "cache_uuid", "image_count", "platform")}
    by_name = {image["install_name"]: image for image in catalog["images"]}
    if len(by_name) != len(catalog["images"]):
        raise ValueError("duplicate cache image install name")
    done = {}
    args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
    if args.checkpoint.exists():
        with args.checkpoint.open(encoding="utf-8") as stream:
            if json.loads(next(stream)) != {"source": source}:
                raise ValueError("checkpoint describes a different source")
            for line in stream:
                item = json.loads(line)
                name = item["install_name"]
                if name not in by_name or item["uuid"] != by_name[name]["uuid"] or name in done:
                    raise ValueError(f"invalid checkpoint entry: {name}")
                done[name] = item
    else:
        args.checkpoint.write_text(json.dumps({"source": source}, sort_keys=True) + "\n")
    pending = [image for image in catalog["images"] if image["install_name"] not in done]
    print(f"{len(done)} resumed; {len(pending)} remaining", flush=True)
    with args.checkpoint.open("a", encoding="utf-8") as stream:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(inspect, args.tool, args.cache, image) for image in pending]
            for future in as_completed(futures):
                item = future.result()
                done[item["install_name"]] = item
                stream.write(json.dumps(item, ensure_ascii=True,
                                        separators=(",", ":"), sort_keys=True) + "\n")
                stream.flush()
                if len(done) % 100 == 0 or len(done) == len(by_name):
                    print(f"{len(done)}/{len(by_name)} images", flush=True)
    if len(done) != len(by_name):
        raise ValueError("segment collection is incomplete")
    images = [done[name] for name in sorted(done)]
    output = {"schema_version": 1, "kind": "dyld_image_macho_segments",
              "source": "official_ipsw_intact_cache_family", "tool": args.tool,
              "complete": True, **source,
              "segment_count": sum(len(image["segments"]) for image in images),
              "images": images}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=True,
                                      separators=(",", ":"), sort_keys=True) + "\n")
    print(f"{len(images)} images, {output['segment_count']} segments -> {args.output}")


if __name__ == "__main__":
    main()
