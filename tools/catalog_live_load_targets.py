#!/usr/bin/env python3
"""Classify static live Mach-O load names against exact-build verified catalogs.

An exact install-name match is a catalog relationship, not a runtime dyld
resolution. Tokenized paths are deliberately left unresolved.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from catalog_live_jailbreak_dependencies import dump, load


FAMILIES = {
    "developer": ("live_developer_macho_inventory",
                  "live_developer_direct_dependencies",
                  "verified_live_developer_mount_bytes"),
    "jailbreak": ("live_jailbreak_macho_inventory",
                  "live_jailbreak_direct_dependencies",
                  "verified_live_device_macho_bytes"),
}


def catalog(ios_cache: dict, driverkit_cache: dict,
            sources: dict[str, tuple[dict, dict]]) -> dict:
    build = ios_cache["build"]
    product = ios_cache["product_type"]
    if (ios_cache.get("kind") != "dyld_shared_cache" or
            driverkit_cache.get("kind") != "dyld_shared_cache" or
            ios_cache.get("platform") != "iOS" or
            driverkit_cache.get("platform") != "Driverkit" or
            driverkit_cache.get("build") != build or
            driverkit_cache.get("product_type") != product or
            set(sources) != set(FAMILIES)):
        raise ValueError("incomplete exact-build cache or live Mach-O sources")
    cache_names = {}
    for family, cache in (("ios_cache", ios_cache),
                          ("driverkit_cache", driverkit_cache)):
        if cache.get("image_count") != len(cache.get("images", [])):
            raise ValueError("incomplete cache image list")
        for image in cache["images"]:
            name = image["install_name"]
            if name in cache_names:
                raise ValueError("duplicate cache install name")
            cache_names[name] = {"kind": family, "install_name": name,
                                 "uuid": image["uuid"]}

    verified = {}
    absolute_names = defaultdict(dict)
    for family, (macho, dependencies) in sources.items():
        macho_kind, dependency_kind, source_name = FAMILIES[family]
        if (macho.get("kind") != macho_kind or
                dependencies.get("kind") != dependency_kind or
                macho.get("source") != source_name or
                dependencies.get("source") != source_name or
                any(data.get("build") != build or data.get("product_type") != product
                    for data in (macho, dependencies)) or
                macho.get("macho_file_count") != len(macho.get("records", [])) or
                dependencies.get("macho_file_count") != len(dependencies.get("files", []))):
            raise ValueError(f"incomplete {family} Mach-O or load catalog")
        macho_by_path = {item["path"]: item for item in macho["records"]}
        dependency_by_path = {item["path"]: item for item in dependencies["files"]}
        if (len(macho_by_path) != len(macho["records"]) or
                len(dependency_by_path) != len(dependencies["files"]) or
                set(macho_by_path) != set(dependency_by_path)):
            raise ValueError(f"{family} file identities differ")
        verified[family] = []
        for path in sorted(macho_by_path):
            original = macho_by_path[path]
            item = dependency_by_path[path]
            if (item["sha256"] != original["sha256"] or
                    item["slice_count"] != len(original["slices"]) or
                    len(item["slices"]) != len(original["slices"])):
                raise ValueError(f"{family} file hash or slice count differs")
            for part, expected in zip(item["slices"], original["slices"]):
                if (part["architecture"] != expected["architecture"] or
                        part["uuid"] != expected["uuid"]):
                    raise ValueError(f"{family} slice identity differs")
                name = part["install_name"]
                if name and name.startswith("/"):
                    key = (family, path)
                    absolute_names[(name, part["architecture"])][key] = {
                        "kind": "verified_live_macho", "family": family,
                        "path": path, "sha256": original["sha256"]}
            verified[family].append(item)

    totals = Counter()
    family_totals = {}
    records = []
    for family in FAMILIES:
        counts = Counter()
        for item in verified[family]:
            slices = []
            for part in item["slices"]:
                loads = []
                for row in part["dependencies"]:
                    name = row["install_name"]
                    if name.startswith("@"):
                        status, targets = "tokenized_name", []
                    elif name in cache_names:
                        status, targets = "cache_install_name", [cache_names[name]]
                    elif name.startswith("/"):
                        targets = list(absolute_names.get(
                            (name, part["architecture"]), {}).values())
                        status = ("live_install_name" if len(targets) == 1 else
                                  "ambiguous_live_install_name" if targets else
                                  "no_exact_match")
                    else:
                        status, targets = "unsupported_name", []
                    loads.append({"install_name": name,
                                  "load_command": row["load_command"],
                                  "status": status, "targets": targets})
                    counts[status] += 1
                    totals[status] += 1
                slices.append({"architecture": part["architecture"],
                               "uuid": part["uuid"], "loads": loads})
            records.append({"family": family, "path": item["path"],
                            "sha256": item["sha256"], "slices": slices})
        family_totals[family] = {"files": len(verified[family]),
                                 "loads": sum(counts.values()), **dict(counts)}
    return {"schema_version": 1, "kind": "live_static_load_target_matches",
            "source": "verified_live_macho_and_exact_build_cache_catalogs",
            "build": build, "product_type": product,
            "cache_uuids": {"ios": ios_cache["cache_uuid"],
                            "driverkit": driverkit_cache["cache_uuid"]},
            "families": family_totals,
            "totals": {"files": len(records), "loads": sum(totals.values()),
                       **dict(totals)}, "files": records}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    base = args.catalog_directory
    ios = json.loads((base / "dyld.json").read_text(encoding="utf-8"))
    driverkit = json.loads((base / "driverkit-dyld.json").read_text(encoding="utf-8"))
    sources = {family: (load(base / f"{family}-macho.json.gz"),
                        load(base / f"{family}-dependencies.json.gz"))
               for family in FAMILIES}
    data = catalog(ios, driverkit, sources)
    dump(args.output, data)
    print(f"{data['totals']['loads']} static loads across {data['totals']['files']} files: "
          f"{data['totals']} -> {args.output}")


if __name__ == "__main__":
    main()
