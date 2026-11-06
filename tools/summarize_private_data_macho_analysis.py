#!/usr/bin/env python3
"""Validate private data-volume Mach-O analyses and emit aggregate-only counts.

Individual app paths, symbols, methods, dependencies, hashes and signing fields
remain in ignored .local. A failed Objective-C inspection is never counted as
an empty metadata result.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

from collect_live_device import private_path


def load_gzip(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()))


def validate_group(name: str, path: Path, source: dict[str, dict]) -> tuple[dict, str]:
    raw = path.read_bytes()
    group = json.loads(gzip.decompress(raw))
    files = group.get("files")
    if not isinstance(files, list) or len(files) != len(source):
        raise ValueError(f"{name}: incomplete analysis file count")
    seen = set()
    for item in files:
        original = source.get(item.get("path"))
        if (original is None or item["path"] in seen or
                item.get("sha256") != original["device_sha256"] or
                item.get("slice_count") != len(original["slices"]) or
                len(item.get("slices", [])) != len(original["slices"])):
            raise ValueError(f"{name}: source file identity differs")
        seen.add(item["path"])
        if any((part.get("architecture"), part.get("uuid")) !=
               (expected["architecture"], expected["uuid"])
               for part, expected in zip(item["slices"], original["slices"])):
            raise ValueError(f"{name}: source slice identity differs")
    if seen != set(source):
        raise ValueError(f"{name}: source file set differs")
    return group, hashlib.sha256(raw).hexdigest()


def summarize(acquisition_path: Path, hash_path: Path, analysis_dir: Path) -> dict:
    acquisition_bytes = acquisition_path.read_bytes()
    acquired = json.loads(acquisition_bytes)
    hash_bytes = hash_path.read_bytes()
    hashes = json.loads(hash_bytes)
    rows = acquired.get("records", [])
    source = {item["path"]: item for item in rows}
    if (acquired.get("kind") != "private_live_data_macho_acquisition" or
            len(rows) != len(source) or len(rows) != 306 or
            any(item.get("status") != "verified_and_parsed" or
                item.get("device_sha256") != item.get("local_sha256")
                for item in rows)):
        raise ValueError("incomplete private acquisition")
    if (hashlib.sha256(hash_bytes).hexdigest() != acquired["hash_manifest_sha256"] or
            hashes.get("kind") != "private_live_data_macho_hashes"):
        raise ValueError("private hash manifest identity differs")
    mount_paths = {group["root_label"]: {item["path"] for item in group["candidates"]}
                   for group in hashes["groups"]}
    if (set(mount_paths) != {"data", "mobile_data"} or
            mount_paths["data"] & mount_paths["mobile_data"] or
            set().union(*mount_paths.values()) != set(source)):
        raise ValueError("private mount candidate sets differ")
    evidence = {}
    groups = {}
    totals = {"files": len(rows), "slices": sum(len(item["slices"]) for item in rows),
              "dsym_not_applicable_for_objc": sum(
                  any(part["file_type"] == "dsym" for part in item["slices"])
                  for item in rows)}
    for name in ("dependencies", "symbols", "swift", "signatures"):
        group, digest = validate_group(name, analysis_dir / f"{name}.json.gz", source)
        evidence[name + "_sha256"] = digest
        if group.get("totals", {}).get("slices") != totals["slices"]:
            raise ValueError(f"{name}: incomplete slice total")
        totals[name] = group["totals"]
        groups[name] = {item["path"]: item for item in group["files"]}
    checkpoint_dir = analysis_dir / "objc-work"
    objc = Counter()
    failures = []
    objc_by_path = {}
    for item in rows:
        if any(part["file_type"] == "dsym" for part in item["slices"]):
            continue
        key = hashlib.sha256(f"Jailbreak\0{item['path']}".encode()).hexdigest()
        path = checkpoint_dir / f"{key}.json.gz"
        if not path.is_file():
            failures.append(item["path"])
            objc["failed"] += 1
            objc_by_path[item["path"]] = None
            continue
        result = load_gzip(path)
        if ((result.get("path"), result.get("sha256"), result.get("uuid")) !=
                (item["path"], item["device_sha256"], item["slices"][0]["uuid"]) or
                result.get("status") not in ("parsed", "no_objc_info") or
                result.get("method_count") != len(result.get("records", [])) or
                (result["status"] == "no_objc_info" and result["method_count"] != 0)):
            raise ValueError("Objective-C checkpoint identity or count differs")
        objc[result["status"]] += 1
        objc_by_path[item["path"]] = result
        objc["methods"] += result["method_count"]
        objc["classes"] += result["class_count"]
        objc["categories"] += result["category_count"]
    if sum(objc[status] for status in ("parsed", "no_objc_info", "failed")) + totals[
            "dsym_not_applicable_for_objc"] != len(rows):
        raise ValueError("Objective-C status partition differs")
    totals["objc"] = dict(objc)
    evidence["acquisition_sha256"] = hashlib.sha256(acquisition_bytes).hexdigest()
    evidence["hash_manifest_sha256"] = hashlib.sha256(hash_bytes).hexdigest()
    by_mount = {}
    for label, paths in mount_paths.items():
        counts = Counter()
        for path in paths:
            item = source[path]
            counts["files"] += 1
            counts["slices"] += len(item["slices"])
            if any(part["file_type"] == "dsym" for part in item["slices"]):
                counts["objc_not_applicable_dsym"] += 1
            else:
                obj = objc_by_path[path]
                counts["objc_" + (obj["status"] if obj else "failed")] += 1
                if obj:
                    counts["objc_methods"] += obj["method_count"]
            for part in groups["dependencies"][path]["slices"]:
                counts["direct_loads"] += len(part["dependencies"])
            for part in groups["symbols"][path]["slices"]:
                counts["named_symbols"] += part["named_symbol_count"]
            for part in groups["swift"][path]["slices"]:
                counts["swift_declarations"] += part["declaration_count"]
            for part in groups["signatures"][path]["slices"]:
                counts["code_directories"] += part["status"] == "code_directory"
        by_mount[label] = dict(counts)
    expected = {"files": totals["files"], "slices": totals["slices"],
                "objc_methods": objc["methods"],
                "objc_parsed": objc["parsed"],
                "objc_no_objc_info": objc["no_objc_info"],
                "objc_failed": objc["failed"],
                "objc_not_applicable_dsym": totals["dsym_not_applicable_for_objc"],
                "direct_loads": totals["dependencies"]["direct_loads"],
                "named_symbols": totals["symbols"]["named_symbols"],
                "swift_declarations": totals["swift"]["declarations"],
                "code_directories": totals["signatures"]["code_directory"]}
    if any(sum(group.get(key, 0) for group in by_mount.values()) != value
           for key, value in expected.items()):
        raise ValueError("private mount totals do not reconcile")
    # Failure paths are written only to a private file, never to stdout or the site.
    (analysis_dir / "objc-failure-paths.json").write_text(
        json.dumps(failures, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    (analysis_dir / "objc-failure-paths.json").chmod(0o600)
    return {"schema_version": 1, "kind": "private_data_volume_macho_analysis_summary",
            "build": acquired["build"], "product_type": acquired["product_type"],
            "counts": totals, "mounts": by_mount, "evidence": evidence,
            "privacy": "aggregate-only; no individual app path, symbol or signature published"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition", required=True, type=Path)
    parser.add_argument("--hash-manifest", required=True, type=Path)
    parser.add_argument("--analysis-dir", required=True, type=Path)
    args = parser.parse_args()
    acquisition = private_path(args.acquisition)
    hashes = private_path(args.hash_manifest)
    analysis = private_path(args.analysis_dir)
    summary = summarize(acquisition, hashes, analysis)
    output = analysis / "aggregate-summary.json"
    output.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps({"counts": summary["counts"], "mounts": summary["mounts"]},
                     sort_keys=True))


if __name__ == "__main__":
    main()
