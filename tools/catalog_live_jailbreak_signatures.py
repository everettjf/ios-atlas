#!/usr/bin/env python3
"""Inspect embedded code-signing metadata in verified live jailbreak Mach-O bytes.

This reads signature structures; it does not assert trust, validity, or runtime
acceptance. Raw command output and acquired files remain private.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import re
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from catalog_live_jailbreak_dependencies import sha256, load, dump
from catalog_live_jailbreak_symbols import thin_slice
from catalog_standalone_macho import fat_slices
from collect_live_device import private_path


CODE_DIRECTORY_FLAGS = re.compile(r"flags=(0x[0-9a-fA-F]+)\(([^)]*)\)")


def parse_codesign(output: bytes) -> dict:
    lines = output.decode("utf-8", errors="replace").splitlines()
    fields = {key: value for line in lines if "=" in line
              for key, value in [line.split("=", 1)]}
    directory = next((line for line in lines if line.startswith("CodeDirectory ")), None)
    flags = CODE_DIRECTORY_FLAGS.search(directory or "")
    identifier = fields.get("Identifier")
    cdhash = fields.get("CDHash")
    hash_type = fields.get("Hash type", "").split(" ", 1)[0]
    team = fields.get("TeamIdentifier")
    if (not identifier or not cdhash or not re.fullmatch(r"[0-9a-fA-F]{40}", cdhash) or
            hash_type not in ("sha1", "sha256", "sha256-truncated", "sha384") or
            flags is None or team is None):
        raise ValueError("incomplete codesign display")
    if fields.get("Signature") == "adhoc":
        signature_state = "adhoc"
    elif any(line.endswith(": no signature") for line in lines):
        signature_state = "no_cms_signature"
    elif fields.get("Signature") or any(line.startswith("Authority=") for line in lines):
        signature_state = "other_signature"
    else:
        raise ValueError("unclassified codesign signature state")
    return {"identifier": identifier, "team_identifier": None if team == "not set" else team,
            "cdhash": cdhash.lower(), "hash_type": hash_type,
            "flags": flags[1].lower(), "flags_label": flags[2],
            "signature_state": signature_state}


def inspect(item: dict, binary_root: Path, workdir: Path) -> dict:
    relative = Path(item["path"].lstrip("/"))
    if (not item["path"].startswith("/") or not relative.parts or
            ".." in relative.parts):
        raise ValueError("unsafe binary path")
    candidate = binary_root / relative
    binary = candidate.resolve()
    if (candidate.is_symlink() or binary_root not in binary.parents or
            not binary.is_file() or binary.stat().st_size != item["size"] or
            sha256(binary) != item["sha256"]):
        raise ValueError("acquired bytes differ from device inventory")
    checkpoint = workdir / (hashlib.sha256(item["path"].encode()).hexdigest() + ".json.gz")
    if checkpoint.exists():
        saved = load(checkpoint)
        if (saved.get("path"), saved.get("sha256"), saved.get("slice_count")) != (
                item["path"], item["sha256"], len(item["slices"])):
            raise ValueError("signature checkpoint identity differs")
        if saved.get("checkpoint_schema_version") == 3:
            return saved
    repeated_arch = len({part["architecture"] for part in item["slices"]}) != len(item["slices"])
    fat_parts = fat_slices(binary) if len(item["slices"]) > 1 else []
    if fat_parts and len(fat_parts) != len(item["slices"]):
        raise ValueError("fat slice count differs from device catalog")
    slices = []
    for index, original in enumerate(item["slices"]):
        temporary = None
        try:
            if repeated_arch:
                offset, length, _ = fat_parts[index]
                temporary = thin_slice(binary, offset, length, workdir)
                target = temporary
                arch = []
            else:
                target = binary
                arch = ["--arch", original["architecture"]]
                length = fat_parts[index][1] if fat_parts else binary.stat().st_size
            macho = subprocess.run(["ipsw", "macho", "info", str(target),
                                    "--json", "--loads", "--no-color", *arch],
                                   capture_output=True, check=False)
            if macho.returncode:
                raise RuntimeError("Mach-O load inspection failed: " +
                                   macho.stderr.decode(errors="replace")[-350:])
            loads = json.loads(macho.stdout)["loads"]
            uuids = [row["uuid"] for row in loads if row["load_cmd"] == "LC_UUID"]
            if uuids != ([original["uuid"]] if original["uuid"] else []):
                raise ValueError("Mach-O UUID differs from device catalog")
            signature_loads = [row for row in loads if row["load_cmd"] == "LC_CODE_SIGNATURE"]
            if len(signature_loads) > 1:
                raise ValueError("multiple signature load commands")
            base = {"architecture": original["architecture"], "uuid": original["uuid"],
                    "macho_loads_sha256": hashlib.sha256(macho.stdout).hexdigest()}
            if not signature_loads:
                slices.append({**base, "status": "no_embedded_signature",
                               "signature_offset": None, "signature_size": None,
                               "identifier": None, "team_identifier": None,
                               "cdhash": None, "hash_type": None,
                               "flags": None, "flags_label": None,
                               "signature_state": None, "entitlement_status": "absent",
                               "entitlement_key_count": 0})
                continue
            signature = signature_loads[0]
            offset, size = signature["offset"], signature["size"]
            if (not isinstance(offset, int) or not isinstance(size, int) or
                    offset < 0 or size <= 0 or offset + size > length):
                raise ValueError("signature load outside Mach-O slice")
            result = subprocess.run(["codesign", "-dvvv", *arch, str(target)],
                                    capture_output=True, check=False)
            if result.returncode:
                raise RuntimeError("codesign could not inspect embedded signature: " +
                                   result.stderr.decode(errors="replace")[-350:])
            summary = parse_codesign(result.stderr)
            code_directories = signature.get("code_signature", {}).get("code_directories", [])
            if not any(isinstance(row.get("cd_hash"), str) and
                       row["cd_hash"].lower().startswith(summary["cdhash"])
                       for row in code_directories):
                raise ValueError("codesign CDHash differs from Mach-O code directory")
            entitlements = signature.get("code_signature", {}).get("entitlements")
            if entitlements:
                try:
                    parsed = plistlib.loads(entitlements.encode())
                except ValueError:
                    entitlement_status = "unparsed"
                    entitlement_count = None
                else:
                    if not isinstance(parsed, dict):
                        raise ValueError("entitlements are not a dictionary")
                    entitlement_status = "parsed"
                    entitlement_count = len(parsed)
            else:
                entitlement_status = "absent"
                entitlement_count = 0
            slices.append({**base, "status": "code_directory", "signature_offset": offset,
                           "signature_size": size, "entitlement_status": entitlement_status,
                           "entitlement_key_count": entitlement_count,
                           **summary})
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
    record = {"checkpoint_schema_version": 3,
              "path": item["path"], "sha256": item["sha256"],
              "slice_count": len(slices), "slices": slices}
    dump(checkpoint, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--macho-catalog", required=True, type=Path)
    parser.add_argument("--binary-root", required=True, type=Path)
    parser.add_argument("--workdir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.workers < 1 or args.limit < 0:
        parser.error("invalid worker or limit count")
    binary_root = private_path(args.binary_root)
    workdir = private_path(args.workdir)
    output = private_path(args.output)
    source = load(args.macho_catalog)
    if (source.get("schema_version") != 1 or
            source.get("kind") != "live_jailbreak_macho_inventory" or
            source.get("source") != "verified_live_device_macho_bytes" or
            source.get("macho_file_count") != len(source.get("records", []))):
        raise ValueError("invalid live Mach-O source")
    workdir.mkdir(parents=True, exist_ok=True)
    pending = [item for item in source["records"] if (
        not (workdir / (hashlib.sha256(item["path"].encode()).hexdigest() + ".json.gz")).exists() or
        load(workdir / (hashlib.sha256(item["path"].encode()).hexdigest() + ".json.gz")).get(
            "checkpoint_schema_version") != 3)]
    selected = pending[:args.limit] if args.limit else pending
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(inspect, item, binary_root, workdir): item
                   for item in selected}
        for number, future in enumerate(as_completed(futures), 1):
            try:
                future.result()
                if number % 50 == 0 or number == len(selected):
                    print(f"inspected {number}/{len(selected)} new files", flush=True)
            except Exception as error:
                failures.append((futures[future]["path"], str(error)))
    if failures:
        raise RuntimeError(f"{len(failures)} signature inspections failed: {failures[:3]}")
    if len(selected) != len(pending):
        print(f"partial pass: {len(pending) - len(selected)} files remain", flush=True)
        return
    records = [inspect(item, binary_root, workdir) for item in source["records"]]
    records.sort(key=lambda item: item["path"])
    totals = Counter()
    for item in records:
        totals["slices"] += item["slice_count"]
        for part in item["slices"]:
            totals[part["status"]] += 1
            if part["status"] == "code_directory":
                totals[part["signature_state"]] += 1
                totals[f"entitlements_{part['entitlement_status']}"] += 1
                if part["entitlement_key_count"] is not None:
                    totals["entitlement_keys"] += part["entitlement_key_count"]
    data = {"schema_version": 1, "kind": "live_jailbreak_code_signatures",
            "source": "verified_live_device_macho_bytes",
            "tool": "codesign -dvvv and ipsw macho info --json --loads",
            "product_type": source["product_type"], "build": source["build"],
            "macho_file_count": len(records), "totals": dict(totals), "files": records}
    dump(output, data)
    print(f"{len(records)} files, {totals['code_directory']} CodeDirectories -> {output}")


if __name__ == "__main__":
    main()
