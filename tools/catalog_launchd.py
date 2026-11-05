#!/usr/bin/env python3
"""Index launchd plists in a mounted, verified official FileSystem image."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import plistlib
from collections import Counter, defaultdict
from pathlib import Path


def load(path: Path) -> dict:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def is_launchd_plist(path: str) -> bool:
    return path.endswith(".plist") and any(
        f"/{folder}/" in path
        for folder in ("LaunchDaemons", "LaunchAgents", "DeveloperModeLaunchDaemons")
    )


def event_names(value: dict) -> list[str]:
    names = []
    for domain, events in value.items():
        if isinstance(events, dict):
            names.extend(f"{domain}/{name}" for name in events)
        else:
            names.append(str(domain))
    return sorted(names)


def executable(program: str | None, paths: dict[str, list[dict]]) -> dict:
    if program is None:
        return {"status": "undeclared", "source_path": None, "matches": []}
    candidates = [(program, "direct")]
    for prefix in ("/System/Cryptexes/App", "/System/Cryptexes/OS"):
        if program.startswith(prefix + "/"):
            candidates.append((program[len(prefix):], "cryptex"))
    for path, status in candidates:
        matches = paths.get(path, [])
        if status == "cryptex":
            volume = "AppOS" if program.startswith("/System/Cryptexes/App/") else "SystemOS"
            matches = [match for match in matches if match["volume"] == volume]
        if matches:
            return {"status": status, "source_path": path, "matches": matches}
    return {"status": "unresolved", "source_path": None, "matches": []}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--filesystem-catalog", required=True, type=Path)
    parser.add_argument("--systemos-catalog", required=True, type=Path)
    parser.add_argument("--appos-catalog", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    catalogs = [load(path) for path in (args.filesystem_catalog,
                                       args.systemos_catalog, args.appos_catalog)]
    fs = catalogs[0]
    if (not all(item["complete"] and not item["errors"] for item in catalogs) or
            len({item["build"] for item in catalogs}) != 1 or
            len({item["product_type"] for item in catalogs}) != 1 or
            len({item["firmware_sha256"] for item in catalogs}) != 1 or
            [item["volume"] for item in catalogs] != ["FileSystem", "SystemOS", "AppOS"]):
        raise ValueError("source filesystem catalogs are incomplete or mismatched")

    paths: dict[str, list[dict]] = defaultdict(list)
    for catalog in catalogs:
        for entry in catalog["entries"]:
            paths[entry["path"]].append({"volume": catalog["volume"],
                                         "type": entry["type"]})

    records = []
    for entry in fs["entries"]:
        path = entry["path"]
        if entry["type"] != "file" or not is_launchd_plist(path):
            continue
        mounted = args.root / path.lstrip("/")
        raw = mounted.read_bytes()
        if entry["size"] != len(raw):
            raise ValueError(f"mounted plist size differs from catalog: {path}")
        plist = plistlib.loads(raw)
        if not isinstance(plist, dict):
            raise ValueError(f"launchd plist is not a dictionary: {path}")
        label = plist.get("Label")
        arguments = plist.get("ProgramArguments") or []
        program = plist.get("Program") or (arguments[0] if arguments else None)
        if label is not None and not isinstance(label, str):
            raise ValueError(f"unexpected label type: {path}")
        if program is not None and not isinstance(program, str):
            raise ValueError(f"unexpected executable type: {path}")
        if not all(isinstance(arg, str) for arg in arguments):
            raise ValueError(f"unexpected argument type: {path}")
        mach = plist.get("MachServices") or {}
        events = plist.get("LaunchEvents") or {}
        if not isinstance(mach, dict) or not isinstance(events, dict):
            raise ValueError(f"unexpected service or event map: {path}")
        records.append({
            "plist_path": path,
            "plist_sha256": hashlib.sha256(raw).hexdigest(),
            "kind": "job" if label else "configuration",
            "label": label,
            "program": program,
            "program_source": "Program" if plist.get("Program") else
                              "ProgramArguments[0]" if arguments else None,
            "program_arguments": arguments,
            "executable": executable(program, paths),
            "mach_services": sorted(mach),
            "launch_events": event_names(events),
            "run_at_load": plist.get("RunAtLoad"),
            "keep_alive": plist.get("KeepAlive"),
            "disabled": plist.get("Disabled"),
            "user": plist.get("UserName"),
            "group": plist.get("GroupName"),
            "process_type": plist.get("ProcessType"),
            "spawn_type": plist.get("POSIXSpawnType"),
        })
    records.sort(key=lambda item: item["plist_path"])
    status = Counter(record["executable"]["status"] for record in records)
    mach_names = [name for record in records for name in record["mach_services"]]
    output = {
        "schema_version": 1,
        "kind": "launchd_plists",
        "source": "official_ipsw_filesystem_image",
        "product_type": fs["product_type"],
        "build": fs["build"],
        "firmware_sha256": fs["firmware_sha256"],
        "image_name": fs["image_name"],
        "complete": True,
        "record_count": len(records),
        "job_count": sum(record["kind"] == "job" for record in records),
        "mach_service_name_count": len(mach_names),
        "unique_mach_service_name_count": len(set(mach_names)),
        "executable_status_counts": dict(sorted(status.items())),
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=True,
                                      separators=(",", ":"), sort_keys=True) + "\n")
    print(f"{len(records)} plists, {output['job_count']} jobs, "
          f"{len(mach_names)} Mach service declarations -> {args.output}")


if __name__ == "__main__":
    main()
