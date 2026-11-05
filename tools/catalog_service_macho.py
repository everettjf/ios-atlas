#!/usr/bin/env python3
"""Index direct Mach-O library loads of stock launchd executables."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path


LOAD_COMMANDS = {
    "LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB", "LC_REEXPORT_DYLIB",
    "LC_LOAD_UPWARD_DYLIB", "LC_LAZY_LOAD_DYLIB",
}
MACHO_MAGICS = {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf",
                b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
                b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}


def load(path: Path) -> dict:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launchd-catalog", required=True, type=Path)
    parser.add_argument("--dyld-catalog", required=True, type=Path)
    parser.add_argument("--driverkit-catalog", required=True, type=Path)
    parser.add_argument("--filesystem-catalog", required=True, type=Path)
    parser.add_argument("--systemos-catalog", required=True, type=Path)
    parser.add_argument("--appos-catalog", required=True, type=Path)
    parser.add_argument("--filesystem-root", required=True, type=Path)
    parser.add_argument("--systemos-root", required=True, type=Path)
    parser.add_argument("--appos-root", required=True, type=Path)
    parser.add_argument("--ipsw-tool", default="ipsw")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    launchd = load(args.launchd_catalog)
    dyld = load(args.dyld_catalog)
    driverkit = load(args.driverkit_catalog)
    volumes = [load(path) for path in (args.filesystem_catalog,
                                      args.systemos_catalog, args.appos_catalog)]
    for item in (dyld, driverkit, *volumes):
        if (item["build"] != launchd["build"] or
                item["product_type"] != launchd["product_type"] or
                item["firmware_sha256"] != launchd["firmware_sha256"]):
            raise ValueError("launchd and cache catalogs describe different firmware")
    if not launchd["complete"] or launchd["record_count"] != len(launchd["records"]):
        raise ValueError("launchd source catalog is incomplete")
    if ([item["volume"] for item in volumes] != ["FileSystem", "SystemOS", "AppOS"] or
            any(not item["complete"] or item["errors"] for item in volumes)):
        raise ValueError("filesystem source catalogs are incomplete")

    roots = {"FileSystem": args.filesystem_root, "SystemOS": args.systemos_root,
             "AppOS": args.appos_root}
    cache_names = defaultdict(list)
    for platform, catalog in (("iOS", dyld), ("DriverKit", driverkit)):
        for item in catalog["images"]:
            cache_names[item["install_name"]].append({"platform": platform,
                                                      "uuid": item["uuid"]})
    disk_files = defaultdict(list)
    for volume in volumes:
        for item in volume["entries"]:
            if item["type"] == "file":
                disk_files[item["path"]].append(volume["volume"])

    jobs = defaultdict(list)
    for record in launchd["records"]:
        exe = record["executable"]
        if exe["status"] not in ("direct", "cryptex"):
            continue
        if not exe["matches"] or exe["matches"][0]["type"] != "file":
            raise ValueError(f"non-file service executable: {record['plist_path']}")
        key = (exe["matches"][0]["volume"], exe["source_path"])
        jobs[key].append(record["plist_path"])

    images = []
    for (volume, path), plists in sorted(jobs.items()):
        if volume not in roots:
            raise ValueError(f"unexpected executable source volume: {volume}")
        artifact = roots[volume] / path.lstrip("/")
        with artifact.open("rb") as stream:
            magic = stream.read(4)
        digest = sha256_file(artifact)
        base = {"volume": volume, "path": path, "sha256": digest,
                "size": artifact.stat().st_size, "job_plists": sorted(plists)}
        if magic not in MACHO_MAGICS:
            images.append({**base, "kind": "other", "magic_hex": magic.hex(),
                           "macho_uuid": None, "architecture": None,
                           "file_type": None, "imports": [], "rpaths": []})
            continue
        result = subprocess.run([args.ipsw_tool, "macho", "info", str(artifact),
                                 "--json", "--loads"], capture_output=True,
                                text=True, timeout=120, check=True)
        info = json.loads(result.stdout)
        header = info["header"]
        loads = info["loads"]
        uuids = [entry["uuid"] for entry in loads if entry["load_cmd"] == "LC_UUID"]
        if len(uuids) != 1:
            raise ValueError(f"unexpected Mach-O UUID count: {volume}:{path}")
        imports = []
        for command in loads:
            if command["load_cmd"] in LOAD_COMMANDS:
                name = command["name"]
                imports.append({"install_name": name,
                                "load_command": command["load_cmd"],
                                "cache_matches": cache_names.get(name, []),
                                "file_matches": disk_files.get(name, [])})
        images.append({**base, "kind": "macho", "macho_uuid": uuids[0],
                       "architecture": header["subcpu"],
                       "file_type": header["type"],
                       "imports": imports,
                       "rpaths": [entry["path"] for entry in loads
                                  if entry["load_cmd"] == "LC_RPATH"]})

    kinds = Counter(item["kind"] for item in images)
    commands = Counter(imp["load_command"] for item in images for imp in item["imports"])
    matched = sum(bool(imp["cache_matches"]) for item in images for imp in item["imports"])
    file_matched = sum(bool(imp["file_matches"]) for item in images for imp in item["imports"])
    unmatched = sum(not imp["cache_matches"] and not imp["file_matches"]
                    for item in images for imp in item["imports"])
    output = {"schema_version": 1, "kind": "service_executable_macho",
              "source": "official_ipsw_mounted_images",
              "product_type": launchd["product_type"], "build": launchd["build"],
              "firmware_sha256": launchd["firmware_sha256"],
              "tool": args.ipsw_tool, "complete": True,
              "image_count": len(images), "kind_counts": dict(sorted(kinds.items())),
              "direct_import_count": sum(commands.values()),
              "cache_matched_import_count": matched,
              "file_matched_import_count": file_matched,
              "unmatched_import_count": unmatched,
              "load_command_counts": dict(sorted(commands.items())), "images": images}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=True,
                                      separators=(",", ":"), sort_keys=True) + "\n")
    print(f"{len(images)} executables, {output['direct_import_count']} direct loads, "
          f"{matched} cache matches, {file_matched} disk matches, "
          f"{unmatched} with neither -> {args.output}")


if __name__ == "__main__":
    main()
