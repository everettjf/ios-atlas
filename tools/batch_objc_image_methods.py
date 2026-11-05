#!/usr/bin/env python3
"""Resume bounded Objective-C method indexing for exact iOS cache images.

Raw class dumps and extracted analysis derivatives stay in an ignored local
workspace. Only validated, compressed metadata catalogs enter the output dir.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from catalog_objc_image_methods import sha256


def load(path: Path) -> dict:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as source:
        return json.load(source)


def run(command: list[str], output: Path | None = None) -> None:
    if output:
        temporary = output.with_suffix(output.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.PIPE,
                                    text=True, check=False)
        if result.returncode:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"{command[0]} exited {result.returncode}: "
                               f"{result.stderr.strip()[-1200:]}")
        temporary.replace(output)
    else:
        result = subprocess.run(command, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, text=True, check=False)
        if result.returncode:
            raise RuntimeError(f"{command[0]} exited {result.returncode}: "
                               f"{result.stderr.strip()[-1200:]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True,
                        help="Main file of the intact iOS cache family")
    parser.add_argument("--a2s", type=Path,
                        help="Symbol address cache generated for this cache family")
    parser.add_argument("--cache-only", action="store_true",
                        help="Use the verified intact cache without extracting every image")
    parser.add_argument("--dyld-catalog", type=Path,
                        help="Exact cache-file hashes; required with --cache-only")
    parser.add_argument("--segments", type=Path, required=True)
    parser.add_argument("--objc-classes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True,
                        help="Ignored local directory for full dumps and selected extracted images")
    parser.add_argument("--include", action="append", default=[],
                        help="Exact install name; repeat to select multiple images")
    parser.add_argument("--all-images", action="store_true",
                        help="Also inspect images absent from the Objective-C class optimization table")
    parser.add_argument("--limit", type=int, default=10,
                        help="Maximum new images to attempt, ordered by class count (default: 10)")
    parser.add_argument("--refresh-existing", action="store_true",
                        help="Regenerate selected catalogs after generator changes")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    if not args.cache.is_file():
        parser.error("the exact cache main file must exist")
    if args.cache_only:
        if args.dyld_catalog is None or not args.dyld_catalog.is_file():
            parser.error("--cache-only requires --dyld-catalog")
    elif args.a2s is None or not args.a2s.is_file():
        parser.error("extraction mode requires the exact .a2s symbol file")

    segments = load(args.segments)
    classes = load(args.objc_classes)
    if (not segments["complete"] or not classes["complete"] or
            any(segments[key] != classes[key] for key in
                ("product_type", "build", "firmware_sha256", "cache_uuid"))):
        parser.error("source catalogs are incomplete or disagree")
    if args.cache_only:
        dyld = load(args.dyld_catalog)
        if (dyld["source"] != "official_ipsw_systemos" or
                dyld["kind"] != "dyld_shared_cache" or
                dyld["file_count"] != len(dyld["files"]) or
                any(dyld[key] != segments[key] for key in
                    ("product_type", "build", "firmware_sha256", "cache_uuid"))):
            parser.error("dyld cache catalog is incomplete or has a different identity")
        if args.cache.name != f"dyld_shared_cache_{dyld['architecture']}":
            parser.error("--cache must be the main file of the cataloged cache family")
        for file in dyld["files"]:
            path = args.cache.parent / file["name"]
            if (not path.is_file() or path.stat().st_size != file["size"] or
                    sha256(path) != file["sha256"]):
                parser.error(f"cache family member differs from catalog: {file['name']}")
        print(f"verified all {len(dyld['files'])} cache files by SHA-256", flush=True)
    by_name = {image["install_name"]: image for image in segments["images"]}
    uuid_counts = Counter(image["uuid"] for image in segments["images"])
    counts = Counter(row[3] for row in classes["records"])
    existing = {}
    for path in args.output_dir.glob("objc-image-methods-*.json.gz"):
        data = load(path)
        name = data["install_name"]
        if (data["build"] != segments["build"] or
                data["cache_uuid"] != segments["cache_uuid"] or
                data["image_uuid"] != by_name[name]["uuid"]):
            parser.error(f"existing catalog has mismatched identity: {path}")
        if name in existing:
            parser.error(f"duplicate existing method catalog for {name}")
        existing[name] = path
    if args.include:
        unknown = set(args.include) - set(by_name)
        if unknown:
            parser.error(f"images absent from the iOS cache segment catalog: {sorted(unknown)}")
        candidates = list(dict.fromkeys(args.include))
    elif args.refresh_existing:
        candidates = sorted(existing, key=lambda name: (-counts[name], name))
    elif args.all_images:
        candidates = sorted(by_name, key=lambda name: (-counts[name], name))
    else:
        candidates = [name for name, _ in counts.most_common()]
    if not args.refresh_existing:
        candidates = [name for name in candidates if name not in existing]
    candidates = candidates[:args.limit]
    if not candidates:
        print("no new image selected")
        return

    failures = []
    for position, name in enumerate(candidates, 1):
        image = by_name[name]
        uuid = image["uuid"]
        # UUIDs identify Mach-O content, not unique install names: two cache
        # entries can share one. Keep their raw dumps and catalogs distinct.
        suffix = ("-" + hashlib.sha256(name.encode()).hexdigest()[:12]
                  if uuid_counts[uuid] > 1 else "")
        local = args.workdir / f"{uuid}{suffix}"
        local.mkdir(parents=True, exist_ok=True)
        dump = local / "classes.txt"
        extracted_dir = local / "extracted"
        extracted = extracted_dir / name.rsplit("/", 1)[-1]
        output = existing.get(name, args.output_dir /
                              f"objc-image-methods-{uuid}{suffix}.json.gz")
        print(f"[{position}/{len(candidates)}] {name} ({counts[name]} class entries)", flush=True)
        try:
            if not dump.is_file():
                run(["ipsw", "class-dump", str(args.cache), name,
                     "--re", "-V", "--no-color"], output=dump)
            if not args.cache_only and not extracted.is_file():
                extracted_dir.mkdir(exist_ok=True)
                run(["ipsw", "dyld", "extract", str(args.cache), name,
                     "--output", str(extracted_dir), "--slide", "--objc", "--stubs",
                     "--cache", str(args.a2s)])
            provenance = (["--cache-main", str(args.cache),
                           "--dyld-catalog", str(args.dyld_catalog)] if args.cache_only else
                          ["--image", str(extracted), "--image-sha256", sha256(extracted)])
            run([sys.executable, str(Path(__file__).with_name("catalog_objc_image_methods.py")),
                 "--class-dump", str(dump), *provenance, "--install-name", name,
                 "--segments", str(args.segments), "--objc-classes", str(args.objc_classes),
                 "--output", str(output)])
            data = load(output)
            print(f"  indexed {data['method_count']} methods; "
                  f"{data['unknown_selector_count']} selectors unavailable", flush=True)
        except (OSError, KeyError, ValueError, RuntimeError) as error:
            if name not in existing:
                output.unlink(missing_ok=True)
            failures.append((name, str(error)))
            print(f"  FAILED: {error}", file=sys.stderr, flush=True)
    if failures:
        print(f"{len(failures)} image(s) failed; inspect retained local dumps, then retry", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
