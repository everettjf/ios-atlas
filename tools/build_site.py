#!/usr/bin/env python3
"""Build the static GitHub Pages explorer from validated public catalogs."""

from __future__ import annotations

import gzip
import hashlib
import html
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse

from export_live_device import KINDS as LIVE_DEVICE_KINDS
from export_live_device import DEVICE_SPECIFIC_PATH
from export_live_device import check_prefix as check_live_prefix
from export_live_device import has_private_characters, inside
from catalog_live_jailbreak_dependencies import PRIVATE_REFERENCE
from catalog_live_load_targets import catalog as catalog_live_load_targets
from export_live_coverage import ROOTS as LIVE_COVERAGE_ROOTS
from verify_live_standalone import DEVICE_PREFIX as STANDALONE_DEVICE_PREFIX
from catalog_live_file_formats import CATEGORIES as LIVE_FILE_FORMAT_CATEGORIES


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "ios"
SITE = ROOT / "site"
DIST = ROOT / "dist"


def render_note(markdown: str, note_path: str) -> str:
    """Render the small, explicit Markdown subset used by authored research notes."""
    base = f"https://github.com/everettjf/ios-atlas/blob/main/{note_path}"
    tokens = re.compile(r"`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*")

    def inline(value: str) -> str:
        output = []
        offset = 0
        for match in tokens.finditer(value):
            output.append(html.escape(value[offset:match.start()]))
            if match[1] is not None:
                output.append(f"<code>{html.escape(match[1])}</code>")
            elif match[2] is not None:
                url = urljoin(base, match[3])
                if urlparse(url).scheme != "https":
                    raise ValueError(f"unsupported research link: {match[3]}")
                output.append(f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">{html.escape(match[2])} ↗</a>')
            else:
                output.append(f"<strong>{html.escape(match[4])}</strong>")
            offset = match.end()
        output.append(html.escape(value[offset:]))
        return "".join(output)

    blocks = []
    paragraph = []
    list_kind = None

    def close_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal list_kind
        if list_kind:
            blocks.append(f"</{list_kind}>")
            list_kind = None

    for line in markdown.splitlines():
        line = line.strip()
        if not line:
            close_paragraph()
            close_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        bullet = re.match(r"^(-|\d+\.)\s+(.+)$", line)
        if heading:
            close_paragraph()
            close_list()
            level = len(heading[1]) + 1
            blocks.append(f"<h{level}>{inline(heading[2])}</h{level}>")
        elif bullet:
            close_paragraph()
            kind = "ul" if bullet[1] == "-" else "ol"
            if list_kind != kind:
                close_list()
                blocks.append(f"<{kind}>")
                list_kind = kind
            blocks.append(f"<li>{inline(bullet[2])}</li>")
        else:
            close_list()
            paragraph.append(line)
    close_paragraph()
    close_list()
    return "\n".join(blocks)


def load(path: Path) -> dict:
    if path.suffix == ".gz":
        return json.loads(gzip.decompress(path.read_bytes()))
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: object, compressed: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode() + b"\n"
    path.write_bytes(gzip.compress(content, mtime=0) if compressed else content)


def publish_live_device(build: str, product: str, path: Path) -> dict:
    """Revalidate the privacy export before placing it in public site assets."""
    data = load(path)
    prefixes = data.get("reviewed_prefixes")
    entries = data.get("entries")
    if (data.get("schema_version") != 1 or data.get("kind") != "live_device_public_paths" or
            data.get("source") != "trusted_device_private_snapshot_privacy_export" or
            data.get("build") != build or data.get("product_type") != product or
            not isinstance(data.get("private_manifest_sha256"), str) or
            not re.fullmatch(r"[0-9a-f]{64}", data.get("private_manifest_sha256", "")) or
            not isinstance(prefixes, list) or not prefixes or len(prefixes) != len(set(prefixes)) or
            not isinstance(entries, list) or not entries or data.get("entry_count") != len(entries)):
        raise ValueError("incomplete or mismatched live-device public catalog")
    for prefix in prefixes:
        check_live_prefix(prefix)
    seen = set()
    counts = Counter()
    for row in entries:
        if (not isinstance(row, list) or len(row) != 3 or
                not isinstance(row[0], str) or not row[0].startswith("/") or
                any(part in ("", ".", "..") for part in row[0][1:].split("/")) or
                has_private_characters(row[0]) or
                DEVICE_SPECIFIC_PATH.fullmatch(row[0]) or
                not any(inside(row[0], prefix) for prefix in prefixes) or
                row[1] not in LIVE_DEVICE_KINDS or row[1] == "unknown" or
                (row[1] == "file" and (not isinstance(row[2], int) or row[2] < 0)) or
                (row[1] != "file" and row[2] is not None) or row[0] in seen):
            raise ValueError("unsafe or duplicate live-device public path")
        seen.add(row[0])
        counts[row[1]] += 1
    if data.get("type_counts") != dict(counts):
        raise ValueError("live-device path types disagree with recorded totals")
    if (not isinstance(data.get("snapshot_root_count"), int) or
            not isinstance(data.get("complete_root_count"), int) or
            not 0 <= data["complete_root_count"] <= data["snapshot_root_count"] or
            not isinstance(data.get("unpublished_entry_count"), int) or
            data["unpublished_entry_count"] < 0):
        raise ValueError("invalid live-device snapshot coverage")
    url = f"data/{build}-device-live.json.gz"
    shutil.copy2(path, DIST / url)
    return {"device_url": url, "device_count": len(entries),
            "device_observed_at_utc": data["observed_at_utc"],
            "device_snapshot_sha256": data["private_manifest_sha256"],
            "device_scope": "reviewed_live", "device_snapshot_root_count": data["snapshot_root_count"],
            "device_complete_root_count": data["complete_root_count"],
            "device_unpublished_entry_count": data["unpublished_entry_count"]}


def publish_live_file_formats(build: str, product: str, path: Path,
                              device_path: Path) -> dict:
    """Admit only fixed format categories for every reviewed regular file."""
    data = load(path)
    device = load(device_path)
    regular = {row[0] for row in device["entries"] if row[1] == "file"}
    if (data.get("schema_version") != 1 or
            data.get("kind") != "live_device_public_file_formats" or
            data.get("source") != "private_live_file_type_pass_fixed_categories" or
            data.get("build") != build or data.get("product_type") != product or
            data.get("private_manifest_sha256") != device["private_manifest_sha256"] or
            data.get("device_catalog_sha256") != hashlib.sha256(device_path.read_bytes()).hexdigest() or
            data.get("file_count") != len(regular) or
            not isinstance(data.get("records"), list) or
            len(data["records"]) != len(regular) or
            data.get("excluded_private_type_paths") != 4):
        raise ValueError("live file-format catalog source or count differs")
    seen = set()
    counts = Counter()
    for row in data["records"]:
        if (not isinstance(row, list) or len(row) != 2 or
                row[0] not in regular or row[0] in seen or
                row[1] not in LIVE_FILE_FORMAT_CATEGORIES):
            raise ValueError("unsafe or duplicate live file-format row")
        seen.add(row[0])
        counts[row[1]] += 1
    if seen != regular or data.get("category_counts") != dict(counts):
        raise ValueError("live file-format coverage or totals differ")
    url = f"data/{build}-device-file-formats.json.gz"
    shutil.copy2(path, DIST / url)
    return {"device_format_url": url, "device_format_count": len(regular),
            "device_script_count": counts["script"],
            "device_elf_count": counts["elf"]}


def publish_live_coverage(build: str, product: str, path: Path,
                          device_path: Path) -> dict:
    """Admit only fixed public labels and numeric mount summaries."""
    data = load(path)
    device = load(device_path)
    expected_top = {"schema_version", "kind", "source", "build", "product_type",
                    "observed_at_utc", "private_manifest_sha256", "public_path_count",
                    "roots", "totals"}
    expected_row = {"label", "mount_type", "publication", "status",
                    "observations", "regular_files", "access_errors"}
    expected_totals = {"root_count", "complete_root_count", "partial_root_count",
                       "observations", "regular_files", "access_errors"}
    if (not isinstance(data, dict) or set(data) != expected_top or
            data.get("schema_version") != 1 or
            data.get("kind") != "live_mount_coverage_public" or
            data.get("source") != "reviewed_private_live_device_snapshot" or
            data.get("build") != build or data.get("product_type") != product or
            data.get("observed_at_utc") != device.get("observed_at_utc") or
            data.get("private_manifest_sha256") != device.get("private_manifest_sha256") or
            data.get("public_path_count") != device.get("entry_count") or
            not isinstance(data.get("roots"), list) or
            len(data["roots"]) != len(LIVE_COVERAGE_ROOTS) or
            not isinstance(data.get("totals"), dict) or
            set(data["totals"]) != expected_totals):
        raise ValueError("invalid or mismatched public live coverage")
    for row, (_, (label, publication, mount_type)) in zip(
            data["roots"], LIVE_COVERAGE_ROOTS.items()):
        if (not isinstance(row, dict) or set(row) != expected_row or
                row["label"] != label or row["publication"] != publication or
                row["mount_type"] != mount_type or
                row["status"] not in ("complete", "partial") or
                any(type(row[key]) is not int or row[key] < 0
                    for key in ("observations", "regular_files", "access_errors")) or
                row["regular_files"] > row["observations"] or
                (row["status"] == "complete" and row["access_errors"] != 0) or
                (row["status"] == "partial" and row["access_errors"] == 0)):
            raise ValueError("unsafe public live coverage row")
    totals = data["totals"]
    expected = {"root_count": len(data["roots"]),
                "complete_root_count": sum(row["status"] == "complete" for row in data["roots"]),
                "partial_root_count": sum(row["status"] == "partial" for row in data["roots"]),
                **{key: sum(row[key] for row in data["roots"])
                   for key in ("observations", "regular_files", "access_errors")}}
    if (any(type(totals[key]) is not int for key in expected_totals) or
            totals != expected or
            totals["root_count"] != device.get("snapshot_root_count") or
            totals["complete_root_count"] != device.get("complete_root_count")):
        raise ValueError("public live coverage totals disagree")
    url = f"data/{build}-live-coverage.json"
    dump(DIST / url, data)
    return {"device_coverage_url": url,
            "device_access_error_count": totals["access_errors"],
            "device_observation_count": totals["observations"]}


def publish_standalone_device_identity(build: str, product: str, path: Path,
                                       standalone: dict, device_path: Path) -> dict:
    """Publish hash identity while withholding nonpublic physical device paths."""
    identity = load(path)
    device = load(device_path)
    source_files = {(item["volume"], item["path"]): item
                    for item in standalone["records"]}
    public_files = {row[0]: row for row in device["entries"]}
    records = identity.get("records", [])
    if (identity.get("schema_version") != 1 or
            identity.get("kind") != "live_standalone_macho_identity" or
            identity.get("source") != "read_only_device_sha256_and_exact_build_ipsw" or
            identity.get("build") != build or identity.get("product_type") != product or
            identity.get("firmware_sha256") != standalone["firmware_sha256"] or
            identity.get("private_snapshot_manifest_sha256") !=
            device.get("private_manifest_sha256") or
            identity.get("snapshot_observed_at_utc") != device.get("observed_at_utc") or
            identity.get("hash_command_exit_code") != 0 or
            not isinstance(records, list) or
            identity.get("record_count") != len(records) or
            len(records) != len(source_files) or
            len(source_files) != len(standalone["records"])):
        raise ValueError("incomplete or mismatched standalone live identity")
    counts = Counter()
    seen = set()
    for row in records:
        key = (row.get("volume"), row.get("path"))
        original = source_files.get(key)
        if original is None or key in seen:
            raise ValueError("unknown or duplicate standalone identity")
        seen.add(key)
        volume, firmware_path = key
        mapped_path = STANDALONE_DEVICE_PREFIX[volume][1] + firmware_path
        if (row.get("device_path") != mapped_path or
                row.get("size") != original["size"] or
                row.get("firmware_sha256") != original["sha256"]):
            raise ValueError("standalone identity mapping differs")
        status = row.get("status")
        if status == "matched":
            if row.get("device_sha256") != original["sha256"]:
                raise ValueError("standalone device hash differs")
            counts["matched"] += 1
            observed = public_files.get(mapped_path)
            if volume == "FileSystem":
                if observed is None or observed[1:] != ["file", original["size"]]:
                    raise ValueError("matched base-system file absent from public paths")
                counts["matched_public_path"] += 1
            elif observed is not None:
                raise ValueError("private cryptex path entered public path catalog")
        elif status == "unobserved_at_mapped_path":
            if row.get("device_sha256") is not None or mapped_path in public_files:
                raise ValueError("unobserved standalone path has a device record")
            counts["unobserved_at_mapped_path"] += 1
        else:
            raise ValueError("unsupported standalone identity status")
    if (seen != set(source_files) or
            identity.get("counts") != {key: counts[key]
                                      for key in ("matched", "unobserved_at_mapped_path")}):
        raise ValueError("standalone identity counts disagree")
    return {"standalone_device_matched_count": counts["matched"],
            "standalone_device_public_match_count": counts["matched_public_path"]}


def publish_live_macho(build: str, product: str, path: Path, device_path: Path) -> dict:
    """Publish verified live Mach-O metadata only for reviewed device file paths."""
    data = load(path)
    device = load(device_path)
    files = {row[0]: row[2] for row in device["entries"] if row[1] == "file"}
    records = data.get("records")
    if (data.get("schema_version") != 1 or
            data.get("kind") != "live_jailbreak_macho_inventory" or
            data.get("source") != "verified_live_device_macho_bytes" or
            data.get("build") != build or data.get("product_type") != product or
            not isinstance(records, list) or data.get("macho_file_count") != len(records) or
            not isinstance(data.get("classification_file_count"), int) or
            not isinstance(data.get("withheld_identifier_count"), int) or
            data["withheld_identifier_count"] < 0 or
            data["classification_file_count"] < len(records) + data["withheld_identifier_count"] or
            data.get("failed_count") != len(data.get("failures", [])) or
            data.get("failed_count") != 0):
        raise ValueError("incomplete or mismatched live Mach-O catalog")
    seen = set()
    for record in records:
        item_path = record.get("path")
        if (not isinstance(item_path, str) or item_path.startswith("/rootfs/") or
                item_path not in files or files[item_path] != record.get("size") or
                item_path in seen or has_private_characters(item_path) or
                DEVICE_SPECIFIC_PATH.fullmatch(item_path) or
                not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", "")) or
                not isinstance(record.get("slices"), list) or not record["slices"] or
                any(not isinstance(part.get("architecture"), str) or
                    not isinstance(part.get("file_type"), str) or
                    (part.get("uuid") is not None and
                     not re.fullmatch(r"[0-9A-F-]{36}", part["uuid"]))
                    for part in record["slices"])):
            raise ValueError("unsafe or unreviewed live Mach-O record")
        seen.add(item_path)
    url = f"data/{build}-jailbreak-macho.json.gz"
    shutil.copy2(path, DIST / url)
    return {"device_macho_url": url, "device_macho_count": len(records),
            "device_macho_scanned_file_count": data["classification_file_count"],
            "device_macho_verified_count": len(records) + data["withheld_identifier_count"],
            "device_macho_withheld_count": data["withheld_identifier_count"]}


def publish_live_developer_macho(build: str, product: str, path: Path,
                                 device_path: Path) -> dict:
    """Publish only hash-verified Developer mount binaries with reviewed paths."""
    data = load(path)
    device = load(device_path)
    files = {row[0]: row[2] for row in device["entries"] if row[1] == "file"}
    records = data.get("records")
    if (data.get("schema_version") != 1 or
            data.get("kind") != "live_developer_macho_inventory" or
            data.get("source") != "verified_live_developer_mount_bytes" or
            data.get("mount_path") != "/rootfs/System/Developer" or
            data.get("build") != build or data.get("product_type") != product or
            not isinstance(records, list) or not records or
            data.get("macho_file_count") != len(records) or
            not isinstance(data.get("classification_file_count"), int) or
            data["classification_file_count"] < len(records) or
            data.get("failed_count") != 0 or data.get("failures") != []):
        raise ValueError("incomplete or mismatched Developer Mach-O catalog")
    seen = set()
    for record in records:
        item_path = record.get("path")
        if (not isinstance(item_path, str) or
                not item_path.startswith("/rootfs/System/Developer/") or
                item_path not in files or files[item_path] != record.get("size") or
                item_path in seen or has_private_characters(item_path) or
                any(part in ("", ".", "..") for part in item_path[1:].split("/")) or
                re.search(r"/[0-9A-Fa-f]{16,}(?:/|$)", item_path) or
                not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", "")) or
                not isinstance(record.get("slices"), list) or not record["slices"] or
                any(not isinstance(part.get("architecture"), str) or
                    not isinstance(part.get("file_type"), str) or
                    (part.get("uuid") is not None and
                     not re.fullmatch(r"[0-9A-F-]{36}", part["uuid"]))
                    for part in record["slices"])):
            raise ValueError("unsafe or unreviewed Developer Mach-O record")
        seen.add(item_path)
    url = f"data/{build}-developer-macho.json.gz"
    shutil.copy2(path, DIST / url)
    return {"developer_macho_url": url,
            "developer_macho_count": len(records),
            "developer_scanned_file_count": data["classification_file_count"]}


def publish_live_objc(build: str, product: str, path: Path, macho_path: Path,
                      family: str = "jailbreak") -> dict:
    """Validate per-file ObjC metadata against the exact acquired Mach-O index."""
    families = {
        "jailbreak": ("live_jailbreak_objc_methods", "verified_live_device_macho_bytes",
                      "Jailbreak", "jailbreak", "device_macho"),
        "developer": ("live_developer_objc_methods", "verified_live_developer_mount_bytes",
                      "Developer", "developer", "developer_macho"),
    }
    if family not in families:
        raise ValueError("unsupported live ObjC family")
    kind, source, volume, filename, key_prefix = families[family]
    data = load(path)
    macho = load(macho_path)
    originals = {item["path"]: item for item in macho["records"]}
    files = data.get("files")
    if (data.get("schema_version") != 1 or
            data.get("kind") != kind or
            data.get("source") != source or
            data.get("build") != build or data.get("product_type") != product or
            (family == "developer" and data.get("selected_architecture") != "arm64e") or
            not isinstance(files, list) or len(files) != len(originals) or
            data.get("macho_file_count") != len(files)):
        raise ValueError("incomplete live Objective-C method catalog")
    seen = set()
    totals = Counter()
    for item in files:
        original = originals.get(item.get("path"))
        selected = (next((part for part in original["slices"]
                          if part["architecture"] == "arm64e"), None)
                    if original and family == "developer" else
                    original["slices"][0] if original else None)
        groups = item.get("groups")
        methods = item.get("records")
        if (original is None or item["path"] in seen or
                selected is None or item.get("volume") != volume or
                (family == "developer" and item.get("architecture") != "arm64e") or
                item.get("sha256") != original["sha256"] or
                item.get("uuid") != selected["uuid"] or
                item.get("status") not in (("parsed", "no_objc_info", "failed")
                                           if family == "developer" else
                                           ("parsed", "no_objc_info")) or
                not isinstance(groups, list) or not isinstance(methods, list) or
                item.get("method_count") != len(methods) or
                item.get("class_count") != sum(group["category_name"] is None
                                               for group in groups) or
                item.get("category_count") != sum(group["category_name"] is not None
                                                  for group in groups)):
            raise ValueError("live Objective-C record differs from verified Mach-O")
        if item["status"] in ("no_objc_info", "failed") and (groups or methods):
            raise ValueError("empty or failed ObjC record contains methods")
        if item["status"] == "failed" and (
                item.get("failure_reason") != "class_dump_error" or
                any(item.get(field) != 0 for field in
                    ("class_count", "category_count", "method_count",
                     "unknown_selector_count"))):
            raise ValueError("invalid explicit ObjC inspection failure")
        if family == "developer" and (
                any(any(has_private_characters(str(value)) or
                        "/Users/" in str(value) for value in group.values())
                    for group in groups) or
                any(row[2] is not None and (
                    not isinstance(row[2], str) or
                    has_private_characters(row[2]) or "/" in row[2])
                    for row in methods)):
            raise ValueError("unsafe Developer ObjC name")
        if item["status"] == "parsed":
            start = int(item["text_address"], 16)
            end = start + item["text_size"]
            if any(not isinstance(row, list) or len(row) != 4 or
                   not isinstance(row[0], int) or not 0 <= row[0] < len(groups) or
                   row[1] not in ("+", "-") or
                   (row[2] is not None and not isinstance(row[2], str)) or
                   not isinstance(row[3], str) or
                   not re.fullmatch(r"0x[0-9a-f]+", row[3]) or
                   not start <= int(row[3], 16) < end for row in methods):
                raise ValueError("live Objective-C method address or group mismatch")
        seen.add(item["path"])
        totals[item["status"]] += 1
        for key, field in (("classes", "class_count"), ("categories", "category_count"),
                           ("methods", "method_count"),
                           ("unknown_selectors", "unknown_selector_count")):
            totals[key] += item[field]
    if seen != set(originals) or any(data["totals"].get(key) != value
                                     for key, value in totals.items()):
        raise ValueError("live Objective-C totals disagree")
    url = f"data/{build}-{filename}-objc-methods.json.gz"
    shutil.copy2(path, DIST / url)
    return {f"{key_prefix}_objc_url": url,
            f"{key_prefix}_objc_method_count": totals["methods"],
            f"{key_prefix}_objc_parsed_count": totals["parsed"],
            f"{key_prefix}_objc_no_info_count": totals["no_objc_info"],
            f"{key_prefix}_objc_failed_count": totals["failed"]}


def publish_live_dependencies(build: str, product: str, path: Path,
                              macho_path: Path, family: str = "jailbreak") -> dict:
    """Publish static direct-load declarations from exact verified live files."""
    families = {
        "jailbreak": ("live_jailbreak_direct_dependencies",
                      "verified_live_device_macho_bytes", "jailbreak",
                      "device_macho"),
        "developer": ("live_developer_direct_dependencies",
                      "verified_live_developer_mount_bytes", "developer",
                      "developer_macho"),
    }
    if family not in families:
        raise ValueError("unsupported live dependency family")
    kind, source, filename, key_prefix = families[family]
    data = load(path)
    macho = load(macho_path)
    originals = {item["path"]: item for item in macho["records"]}
    files = data.get("files")
    if (data.get("schema_version") != 1 or
            data.get("kind") != kind or
            data.get("source") != source or
            data.get("build") != build or data.get("product_type") != product or
            not isinstance(files, list) or len(files) != len(originals) or
            data.get("macho_file_count") != len(files)):
        raise ValueError("incomplete live direct-dependency catalog")
    seen = set()
    totals = Counter()
    load_kinds = {"LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB",
                  "LC_REEXPORT_DYLIB", "LC_LOAD_UPWARD_DYLIB",
                  "LC_LAZY_LOAD_DYLIB"}

    def public_string(value: str) -> bool:
        return (isinstance(value, str) and value and
                not has_private_characters(value) and
                not PRIVATE_REFERENCE.search(value))

    for item in files:
        original = originals.get(item.get("path"))
        if (original is None or item["path"] in seen or
                item.get("sha256") != original["sha256"] or
                item.get("slice_count") != len(original["slices"]) or
                not isinstance(item.get("slices"), list) or
                len(item["slices"]) != len(original["slices"])):
            raise ValueError("live dependency file identity differs")
        seen.add(item["path"])
        for part, expected in zip(item["slices"], original["slices"]):
            dependencies = part.get("dependencies")
            rpaths = part.get("rpaths")
            redacted = part.get("redacted_rpath_count")
            if (part.get("architecture") != expected["architecture"] or
                    part.get("uuid") != expected["uuid"] or
                    not re.fullmatch(r"[0-9a-f]{64}",
                                     part.get("load_dump_sha256", "")) or
                    (part.get("install_name") is not None and
                     not public_string(part["install_name"])) or
                    not isinstance(dependencies, list) or
                    not isinstance(rpaths, list) or
                    not isinstance(redacted, int) or redacted < 0 or
                    any(not public_string(name) for name in rpaths) or
                    any(not isinstance(row, dict) or
                        row.get("load_command") not in load_kinds or
                        not public_string(row.get("install_name"))
                        for row in dependencies)):
                raise ValueError("unsafe or mismatched live dependency slice")
            totals["slices"] += 1
            totals["direct_loads"] += len(dependencies)
            totals["rpaths"] += len(rpaths)
            totals["redacted_rpaths"] += redacted
            totals["without_loads"] += not dependencies
    if seen != set(originals) or any(data.get("totals", {}).get(key) != value
                                     for key, value in totals.items()):
        raise ValueError("live dependency totals disagree")
    url = f"data/{build}-{filename}-dependencies.json.gz"
    shutil.copy2(path, DIST / url)
    return {f"{key_prefix}_dependency_url": url,
            f"{key_prefix}_direct_load_count": totals["direct_loads"],
            f"{key_prefix}_redacted_rpath_count": totals["redacted_rpaths"]}


def publish_live_load_targets(build: str, product: str, directory: Path) -> dict:
    """Recompute every static name match before publishing reviewed live loads."""
    candidate = directory / "live-load-targets.json.gz"
    if not candidate.exists():
        return {}
    required = ("dyld.json", "driverkit-dyld.json", "developer-macho.json.gz",
                "developer-dependencies.json.gz", "jailbreak-macho.json.gz",
                "jailbreak-dependencies.json.gz")
    if any(not (directory / name).is_file() for name in required):
        raise ValueError("live load targets require both complete live families and caches")
    sources = {
        family: (load(directory / f"{family}-macho.json.gz"),
                 load(directory / f"{family}-dependencies.json.gz"))
        for family in ("developer", "jailbreak")
    }
    expected = catalog_live_load_targets(
        load(directory / "dyld.json"), load(directory / "driverkit-dyld.json"),
        sources)
    data = load(candidate)
    if (data != expected or data["build"] != build or
            data["product_type"] != product):
        raise ValueError("live static load-target catalog differs from exact sources")
    url = f"data/{build}-live-load-targets.json.gz"
    dump(DIST / url, data, compressed=True)
    totals = data["totals"]
    return {"live_load_target_url": url,
            "live_load_target_count": totals["loads"],
            "live_load_cache_match_count": totals.get("cache_install_name", 0),
            "live_load_live_match_count": totals.get("live_install_name", 0),
            "live_load_tokenized_count": totals.get("tokenized_name", 0),
            "live_load_unmatched_count": totals.get("no_exact_match", 0)}


def publish_live_symbols(build: str, product: str, path: Path,
                         macho_path: Path, family: str = "jailbreak") -> dict:
    """Publish reviewed per-slice names only for exact verified device files."""
    families = {
        "jailbreak": ("live_jailbreak_named_text_symbols",
                      "verified_live_device_macho_bytes", "jailbreak", "device_macho"),
        "developer": ("live_developer_named_text_symbols",
                      "verified_live_developer_mount_bytes", "developer", "developer_macho"),
    }
    if family not in families:
        raise ValueError("unsupported live symbol family")
    kind, source, filename, key_prefix = families[family]
    data = load(path)
    macho = load(macho_path)
    originals = {item["path"]: item for item in macho["records"]}
    files = data.get("files")
    if (data.get("schema_version") != 1 or
            data.get("kind") != kind or data.get("source") != source or
            data.get("build") != build or data.get("product_type") != product or
            not isinstance(files, list) or len(files) != len(originals) or
            data.get("macho_file_count") != len(files)):
        raise ValueError("incomplete live symbol catalog")
    seen = set()
    totals = Counter()
    summaries = []
    buckets = defaultdict(list)
    private_name = re.compile(
        r"/(?:Users|var/mobile|private/var/mobile|private/var/containers)/|"
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    )
    for item in files:
        original = originals.get(item.get("path"))
        if (original is None or item["path"] in seen or
                item.get("sha256") != original["sha256"] or
                item.get("slice_count") != len(original["slices"]) or
                not isinstance(item.get("slices"), list) or
                len(item["slices"]) != len(original["slices"])):
            raise ValueError("live symbol file differs from verified Mach-O")
        seen.add(item["path"])
        rows = []
        totals["slices"] += len(item["slices"])
        for part, original_part in zip(item["slices"], original["slices"]):
            sections = part.get("text_sections")
            names = part.get("symbols")
            if (part.get("architecture") != original_part["architecture"] or
                    part.get("uuid") != original_part["uuid"] or
                    not isinstance(sections, list) or not isinstance(names, list) or
                    part.get("named_symbol_count") != len(names) or
                    len({tuple(row) for row in names}) != len(names) or
                    any(not isinstance(part.get(field), str) or
                        not re.fullmatch(r"[0-9a-f]{64}", part[field]) for field in
                        ("macho_loads_sha256", "symbol_dump_sha256")) or
                    any(not isinstance(part.get(field), int) or part[field] < 0
                        for field in ("symbol_dump_replacement_char_count",
                                      "duplicate_symbol_row_count",
                                      "unnamed_text_row_count", "outside_text_row_count")) or
                    any(not isinstance(section, list) or len(section) != 3 or
                        not isinstance(section[0], str) or
                        not isinstance(section[1], int) or
                        not isinstance(section[2], int) or section[2] < 0
                        for section in sections)):
                raise ValueError("invalid live symbol slice")
            ranges = defaultdict(list)
            for segment, address, length in sections:
                ranges[segment].append((address, address + length))
            for row in names:
                if (not isinstance(row, list) or len(row) != 4 or
                        not isinstance(row[0], str) or
                        not re.fullmatch(r"0x[0-9a-f]+", row[0]) or
                        any(not isinstance(value, str) or not value or
                            has_private_characters(value) or "\ufffd" in value or
                            private_name.search(value) or PRIVATE_REFERENCE.search(value)
                            for value in row[1:]) or
                        row[3] not in ranges or
                        not any(lo <= int(row[0], 16) < hi
                                for lo, hi in ranges[row[3]])):
                    raise ValueError("unsafe or out-of-range live symbol")
                rows.append([*row, part["architecture"]])
            totals["named_symbols"] += len(names)
            totals["duplicate_rows"] += part["duplicate_symbol_row_count"]
            totals["unnamed_rows"] += part["unnamed_text_row_count"]
            totals["outside_rows"] += part["outside_text_row_count"]
            totals["slices_without_names"] += not names
        totals["files_without_names"] += not rows
        bucket_id = hashlib.sha256(item["path"].encode()).digest()[0] % 64
        bucket_url = (f"data/{build}-{filename}-symbols/{bucket_id:02x}.json.gz"
                      if rows else None)
        summaries.append({"path": item["path"], "sha256": item["sha256"],
                          "named_symbol_count": len(rows),
                          "slice_count": len(item["slices"]),
                          "bucket_url": bucket_url})
        if rows:
            buckets[bucket_id].append({"path": item["path"], "sha256": item["sha256"],
                                       "symbols": rows})
    if (seen != set(originals) or
            any(data.get("totals", {}).get(key) != value for key, value in totals.items())):
        raise ValueError("live symbol totals disagree")
    for bucket_id, entries in buckets.items():
        dump(DIST / f"data/{build}-{filename}-symbols/{bucket_id:02x}.json.gz",
             {"schema_version": 1, "build": build, "files": entries},
             compressed=True)
    index_url = f"data/{build}-{filename}-symbol-index.json.gz"
    dump(DIST / index_url,
         {"schema_version": 1, "build": build, "files": summaries,
          "totals": dict(totals)}, compressed=True)
    return {f"{key_prefix}_symbol_index_url": index_url,
            f"{key_prefix}_named_symbol_count": totals["named_symbols"],
            f"{key_prefix}_symbol_empty_file_count": totals["files_without_names"]}


def publish_live_swift(build: str, product: str, path: Path,
                       macho_path: Path, family: str = "jailbreak") -> dict:
    """Validate Swift dump lines against every exact device Mach-O slice."""
    families = {
        "jailbreak": ("live_jailbreak_swift_declarations",
                      "verified_live_device_macho_bytes", "jailbreak", "device_macho"),
        "developer": ("live_developer_swift_declarations",
                      "verified_live_developer_mount_bytes", "developer", "developer_macho"),
    }
    if family not in families:
        raise ValueError("unsupported live Swift family")
    kind, source, filename, key_prefix = families[family]
    data = load(path)
    macho = load(macho_path)
    originals = {item["path"]: item for item in macho["records"]}
    files = data.get("files")
    if (data.get("schema_version") != 1 or
            data.get("kind") != kind or data.get("source") != source or
            data.get("build") != build or data.get("product_type") != product or
            not isinstance(files, list) or len(files) != len(originals) or
            data.get("macho_file_count") != len(files)):
        raise ValueError("incomplete live Swift catalog")
    kinds = ("class", "struct", "enum", "protocol", "extension", "actor")
    statuses = ("parsed", "partially_parsed", "no_swift_info",
                "swift_sections_unparsed", "dump_without_swift_sections")
    private_line = re.compile(
        r"/(?:Users|var/mobile|private/var/mobile|private/var/containers)/|"
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    )
    seen = set()
    totals = Counter()
    summaries = []
    buckets = defaultdict(list)
    for item in files:
        original = originals.get(item.get("path"))
        if (original is None or item["path"] in seen or
                item.get("sha256") != original["sha256"] or
                item.get("slice_count") != len(original["slices"]) or
                not isinstance(item.get("slices"), list) or
                len(item["slices"]) != len(original["slices"])):
            raise ValueError("live Swift file differs from verified Mach-O")
        seen.add(item["path"])
        declarations = []
        file_members = 0
        file_unparsed = 0
        file_statuses = []
        totals["slices"] += len(item["slices"])
        for part, original_part in zip(item["slices"], original["slices"]):
            status = part.get("status")
            rows = part.get("declarations")
            sections = part.get("swift_sections")
            if (part.get("architecture") != original_part["architecture"] or
                    part.get("uuid") != original_part["uuid"] or
                    status not in statuses or not isinstance(rows, list) or
                    not isinstance(sections, list) or
                    part.get("declaration_count") != len(rows) or
                    any(not isinstance(part.get(field), str) or
                        not re.fullmatch(r"[0-9a-f]{64}", part[field]) for field in
                        ("macho_loads_sha256", "swift_dump_sha256")) or
                    any(not isinstance(part.get(field), int) or part[field] < 0
                        for field in ("swift_dump_replacement_char_count",
                                      "member_count", "stripped_member_count",
                                      "unparsed_line_count")) or
                    any(not isinstance(section, list) or len(section) != 4 or
                        not isinstance(section[0], str) or
                        not isinstance(section[1], str) or
                        not section[1].startswith("__swift5_") or
                        not isinstance(section[2], int) or
                        not isinstance(section[3], int) or section[3] < 0
                        for section in sections)):
                raise ValueError("invalid live Swift slice")
            if ((status == "no_swift_info" and
                 (rows or sections or part["unparsed_line_count"])) or
                    (status == "swift_sections_unparsed" and
                     (not sections or rows)) or
                    (status == "dump_without_swift_sections" and sections) or
                    (status in ("parsed", "partially_parsed") and not sections) or
                    (status == "parsed" and part["unparsed_line_count"]) or
                    (status == "partially_parsed" and
                     not part["unparsed_line_count"])):
                raise ValueError("live Swift status contradicts parsed sections")
            actual_kinds = Counter()
            members = 0
            stripped = 0
            for row in rows:
                if (not isinstance(row, dict) or row.get("kind") not in kinds or
                        not isinstance(row.get("name"), str) or not row["name"] or
                        not isinstance(row.get("members"), list)):
                    raise ValueError("invalid live Swift declaration")
                actual_kinds[row["kind"]] += 1
                for value in [row["name"], *(member[1] for member in row["members"]
                                                if isinstance(member, list) and len(member) == 2)]:
                    if (not isinstance(value, str) or not value or
                            has_private_characters(value) or "\ufffd" in value or
                            private_line.search(value) or PRIVATE_REFERENCE.search(value)):
                        raise ValueError("unsafe live Swift name or member")
                for member in row["members"]:
                    if (not isinstance(member, list) or len(member) != 2 or
                            member[0] not in ("methods", "requirements") or
                            not isinstance(member[1], str)):
                        raise ValueError("invalid live Swift member")
                    members += 1
                    stripped += "<stripped>" in member[1]
                declarations.append({"architecture": part["architecture"], **row})
            if (part["member_count"] != members or
                    part["stripped_member_count"] != stripped or
                    any(part.get("kind_counts", {}).get(kind) != actual_kinds[kind]
                        for kind in kinds)):
                raise ValueError("live Swift slice counts disagree")
            totals[status] += 1
            totals["declarations"] += len(rows)
            totals["members"] += members
            totals["stripped_members"] += stripped
            totals["unparsed_lines"] += part["unparsed_line_count"]
            for kind in kinds:
                totals[kind] += actual_kinds[kind]
            file_members += members
            file_unparsed += part["unparsed_line_count"]
            file_statuses.append(status)
        totals["files_without_declarations"] += not declarations
        bucket_id = hashlib.sha256(item["path"].encode()).digest()[0] % 64
        bucket_url = (f"data/{build}-{filename}-swift/{bucket_id:02x}.json.gz"
                      if declarations else None)
        summaries.append({"path": item["path"], "sha256": item["sha256"],
                          "slice_count": item["slice_count"],
                          "statuses": file_statuses,
                          "declaration_count": len(declarations),
                          "member_count": file_members,
                          "unparsed_line_count": file_unparsed,
                          "bucket_url": bucket_url})
        if declarations:
            buckets[bucket_id].append({"path": item["path"], "sha256": item["sha256"],
                                       "declarations": declarations})
    if (seen != set(originals) or
            any(data.get("totals", {}).get(key) != value for key, value in totals.items())):
        raise ValueError("live Swift totals disagree")
    for bucket_id, entries in buckets.items():
        dump(DIST / f"data/{build}-{filename}-swift/{bucket_id:02x}.json.gz",
             {"schema_version": 1, "build": build, "files": entries}, compressed=True)
    index_url = f"data/{build}-{filename}-swift-index.json.gz"
    dump(DIST / index_url,
         {"schema_version": 1, "build": build, "files": summaries,
          "totals": dict(totals)}, compressed=True)
    return {f"{key_prefix}_swift_index_url": index_url,
            f"{key_prefix}_swift_declaration_count": totals["declarations"],
            f"{key_prefix}_swift_no_info_slice_count": totals["no_swift_info"],
            f"{key_prefix}_swift_partial_slice_count": totals["partially_parsed"]}


def publish_live_signatures(build: str, product: str, path: Path,
                            macho_path: Path, family: str = "jailbreak") -> dict:
    """Publish code-signing summaries without raw output or entitlement values."""
    families = {
        "jailbreak": ("live_jailbreak_code_signatures",
                      "verified_live_device_macho_bytes", "jailbreak", "device_macho"),
        "developer": ("live_developer_code_signatures",
                      "verified_live_developer_mount_bytes", "developer", "developer_macho"),
    }
    if family not in families:
        raise ValueError("unsupported live signing family")
    kind, source, filename, key_prefix = families[family]
    data = load(path)
    macho = load(macho_path)
    originals = {item["path"]: item for item in macho["records"]}
    files = data.get("files")
    if (set(data) != {"schema_version", "kind", "source", "tool",
                      "product_type", "build", "macho_file_count",
                      "totals", "files"} or
            data.get("tool") != "codesign -dvvv and ipsw macho info --json --loads" or
            data.get("schema_version") != 1 or
            data.get("kind") != kind or data.get("source") != source or
            data.get("build") != build or data.get("product_type") != product or
            not isinstance(files, list) or len(files) != len(originals) or
            data.get("macho_file_count") != len(files)):
        raise ValueError("incomplete live code-signing catalog")
    private_value = re.compile(
        r"/(?:Users|var/mobile|private/var/mobile|private/var/containers)/|"
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    )
    totals = Counter()
    seen = set()
    public_files = []
    for item in files:
        original = originals.get(item.get("path"))
        if (original is None or item["path"] in seen or
                set(item) != {"checkpoint_schema_version", "path", "sha256",
                              "slice_count", "slices"} or
                item.get("checkpoint_schema_version") != 3 or
                item.get("sha256") != original["sha256"] or
                item.get("slice_count") != len(original["slices"]) or
                not isinstance(item.get("slices"), list) or
                len(item["slices"]) != len(original["slices"])):
            raise ValueError("live signing file differs from verified Mach-O")
        seen.add(item["path"])
        totals["slices"] += len(item["slices"])
        public_slices = []
        for part, original_part in zip(item["slices"], original["slices"]):
            status = part.get("status")
            if (set(part) != {"architecture", "uuid", "macho_loads_sha256",
                              "status", "signature_offset", "signature_size",
                              "identifier", "team_identifier", "cdhash",
                              "hash_type", "flags", "flags_label",
                              "signature_state", "entitlement_status",
                              "entitlement_key_count"} or
                    part.get("architecture") != original_part["architecture"] or
                    part.get("uuid") != original_part["uuid"] or
                    status not in ("code_directory", "no_embedded_signature") or
                    not isinstance(part.get("macho_loads_sha256"), str) or
                    not re.fullmatch(r"[0-9a-f]{64}", part["macho_loads_sha256"])):
                raise ValueError("invalid live signing slice")
            if status == "no_embedded_signature":
                if (any(part.get(field) is not None for field in
                        ("signature_offset", "signature_size", "identifier",
                         "team_identifier", "cdhash", "hash_type", "flags",
                         "flags_label", "signature_state")) or
                        part.get("entitlement_status") != "absent" or
                        part.get("entitlement_key_count") != 0):
                    raise ValueError("unsigned slice has code-signing metadata")
            else:
                offset, size = part.get("signature_offset"), part.get("signature_size")
                if (not isinstance(offset, int) or not isinstance(size, int) or
                        offset < 0 or size <= 0 or offset + size > original["size"] or
                        not isinstance(part.get("cdhash"), str) or
                        not re.fullmatch(r"[0-9a-f]{40}", part["cdhash"]) or
                        part.get("hash_type") not in
                        ("sha1", "sha256", "sha256-truncated", "sha384") or
                        not isinstance(part.get("flags"), str) or
                        not re.fullmatch(r"0x[0-9a-f]+", part["flags"]) or
                        part.get("signature_state") not in
                        ("adhoc", "no_cms_signature", "other_signature") or
                        part.get("entitlement_status") not in
                        ("parsed", "absent", "unparsed") or
                        (part["entitlement_status"] == "unparsed" and
                         part.get("entitlement_key_count") is not None) or
                        (part["entitlement_status"] == "absent" and
                         part.get("entitlement_key_count") != 0) or
                        (part["entitlement_status"] == "parsed" and
                         (not isinstance(part.get("entitlement_key_count"), int) or
                          part["entitlement_key_count"] < 0))):
                    raise ValueError("invalid code-signing summary")
                for value in (part.get("identifier"), part.get("flags_label")):
                    if (not isinstance(value, str) or not value or len(value) > 500 or
                            has_private_characters(value) or "\ufffd" in value or
                            private_value.search(value) or PRIVATE_REFERENCE.search(value)):
                        raise ValueError("unsafe code-signing identity")
                team = part.get("team_identifier")
                if (team is not None and
                    (not isinstance(team, str) or not team or len(team) > 500 or
                     has_private_characters(team) or "\ufffd" in team or
                     private_value.search(team) or PRIVATE_REFERENCE.search(team))):
                    raise ValueError("unsafe code-signing team identifier")
                totals[part["signature_state"]] += 1
                totals[f"entitlements_{part['entitlement_status']}"] += 1
                if part["entitlement_key_count"] is not None:
                    totals["entitlement_keys"] += part["entitlement_key_count"]
            totals[status] += 1
            public_slices.append({key: part[key] for key in
                                  ("architecture", "uuid", "status",
                                   "signature_offset", "signature_size",
                                   "identifier", "team_identifier", "cdhash",
                                   "hash_type", "flags", "flags_label",
                                   "signature_state", "entitlement_status",
                                   "entitlement_key_count")})
        public_files.append({"path": item["path"], "sha256": item["sha256"],
                             "slices": public_slices})
    if seen != set(originals) or data.get("totals") != dict(totals):
        raise ValueError("live code-signing totals disagree")
    url = f"data/{build}-{filename}-signatures.json.gz"
    dump(DIST / url,
         {"schema_version": 1, "build": build, "files": public_files,
          "totals": dict(totals)}, compressed=True)
    return {f"{key_prefix}_signature_url": url,
            f"{key_prefix}_code_directory_count": totals["code_directory"],
            f"{key_prefix}_adhoc_count": totals["adhoc"],
            f"{key_prefix}_no_cms_count": totals["no_cms_signature"],
            f"{key_prefix}_entitlements_unparsed_count": totals["entitlements_unparsed"]}


def publish_dependencies(path: Path, cache: dict, build: str, label: str) -> dict:
    dependencies = load(path)
    dependency_images = dependencies["images"]
    expected = {image["install_name"]: image["uuid"] for image in cache["images"]}
    actual = {image["install_name"]: image["uuid"] for image in dependency_images}
    imports = [imp for image in dependency_images for imp in image["imports"]]
    if (not dependencies["complete"] or
            dependencies["kind"] != "dyld_image_direct_loads" or
            dependencies["source"] != "official_ipsw_intact_cache_family" or
            dependencies["build"] != build or
            dependencies["product_type"] != cache["product_type"] or
            dependencies["firmware_sha256"] != cache["firmware_sha256"] or
            dependencies["cache_uuid"] != cache["cache_uuid"] or
            dependencies["image_count"] != len(dependency_images) or
            len(actual) != len(dependency_images) or actual != expected or
            dependencies["direct_import_count"] != len(imports) or
            dependencies["exact_cache_name_match_count"] != sum(
                imp["install_name"] in expected for imp in imports) or
            dependencies["load_command_counts"] != {
                command: sum(imp["load_command"] == command for imp in imports)
                for command in dependencies["load_command_counts"]} or
            sum(dependencies["load_command_counts"].values()) != len(imports)):
        raise ValueError(f"incomplete or mismatched {label} dependency catalog in {path.parent}")
    url = f"data/{build}-{label}-dependencies.json.gz"
    dump(DIST / url, {"schema_version": 1, "build": build,
         "images": [{"install_name": image["install_name"], "uuid": image["uuid"],
                     "imports": image["imports"]} for image in dependency_images]},
         compressed=True)
    return {f"{label}_dependency_image_count": len(dependency_images),
            f"{label}_direct_import_count": len(imports),
            f"{label}_exact_cache_match_count": dependencies["exact_cache_name_match_count"],
            f"{label}_dependency_url": url}


def publish_swift(directory: Path, cache: dict, images: list, build: str) -> dict:
    source = directory / "swift-conformances"
    if not (source / "index.json").exists():
        return {}
    index = load(source / "index.json")
    segments = load(directory / "dyld-segments.json")
    keys = ("build", "product_type", "firmware_sha256", "cache_uuid", "platform")
    expected = [(image["install_name"], image["uuid"]) for image in cache["images"]]
    segment_images = segments["images"]
    listed = [(image["install_name"], image["uuid"]) for image in index["images"]]
    if (not index["complete"] or index["kind"] != "dyld_swift_type_conformances" or
            index["source"] != "official_ipsw_intact_cache_family" or
            any(index[key] != cache[key] or segments[key] != cache[key] for key in keys) or
            not segments["complete"] or segments["kind"] != "dyld_image_macho_segments" or
            listed != expected or
            [(image["install_name"], image["uuid"]) for image in segment_images] != expected or
            len(index["image_counts"]) != len(expected) or
            len(index["buckets"]) != index["bucket_count"] or
            index["bucket_count"] != 64 or
            sum(index["image_counts"]) != index["record_count"] or
            sum(bucket["record_count"] for bucket in index["buckets"]) != index["record_count"]):
        raise ValueError(f"incomplete or mismatched Swift catalog in {directory}")
    ranges = [[(part["addr"], part["addr"] + part["memsz"])
               for part in image["segments"] if part["name"] != "__LINKEDIT" and part["memsz"]]
              for image in segment_images]
    counts = Counter()
    owner_counts = Counter()
    objc_owner = {}
    target = DIST / "data" / f"{build}-swift"
    target.mkdir(parents=True, exist_ok=True)
    for number, bucket in enumerate(index["buckets"]):
        filename = f"b{number:02d}.json.gz"
        path = source / filename
        blob = path.read_bytes()
        if (bucket["file"] != filename or bucket["size"] != len(blob) or
                bucket["sha256"] != hashlib.sha256(blob).hexdigest()):
            raise ValueError(f"Swift bucket integrity mismatch: {filename}")
        data = json.loads(gzip.decompress(blob))
        rows = data["records"]
        if (data["build"] != build or data["bucket"] != number or
                data["schema_version"] != 1 or len(rows) != bucket["record_count"]):
            raise ValueError(f"Swift bucket identity mismatch: {filename}")
        for row in rows:
            if (len(row) != 12 or not isinstance(row[0], int) or
                    not isinstance(row[1], int) or not isinstance(row[11], bool) or
                    not all(isinstance(row[pos], int) and 0 <= row[pos] < len(expected)
                            for pos in (4, 7, 10)) or row[10] % 64 != number):
                raise ValueError(f"invalid Swift row in {filename}")
            for address_pos, symbol_pos, image_pos, count_key in (
                    (2, 3, 4, "named_type"), (5, 6, 7, "named_protocol"),
                    (8, 9, 10, "named_conformance")):
                address = row[address_pos]
                if (not isinstance(address, int) or
                        not any(start <= address < end for start, end in ranges[row[image_pos]]) or
                        not (row[symbol_pos] is None or isinstance(row[symbol_pos], str))):
                    raise ValueError(f"Swift address outside matching image in {filename}")
                counts[count_key] += row[symbol_pos] is not None
            owner = objc_owner.setdefault(row[1], row[10])
            if owner != row[10]:
                raise ValueError("Swift Objective-C image index maps to multiple images")
            owner_counts[row[10]] += 1
            counts["duplicate"] += row[11]
            counts["record"] += 1
        shutil.copy2(path, target / filename)
    if (counts["record"] != index["record_count"] or
            counts["duplicate"] != index["duplicate_marker_count"] or
            counts["named_type"] != index["named_type_count"] or
            counts["named_protocol"] != index["named_protocol_count"] or
            counts["named_conformance"] != index["named_conformance_count"] or
            [owner_counts[i] for i in range(len(expected))] != index["image_counts"] or
            len(owner_counts) != index["image_count_with_conformances"]):
        raise ValueError(f"Swift catalog count mismatch in {directory}")
    counts_by_name = {name: owner_counts[index] for index, (name, _) in enumerate(expected)}
    for image in images:
        image["swift_conformance_count"] = counts_by_name[image["install_name"]]
    dump(DIST / "data" / f"{build}-swift-index.json", index)
    return {"swift_conformance_count": counts["record"],
            "swift_image_count": len(owner_counts),
            "swift_url": f"data/{build}-swift-index.json",
            "swift_bucket_base": f"data/{build}-swift/"}


def build() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    for name in ("index.html", "app.js", "styles.css", "tree.css", "reach.mjs", "tree.mjs"):
        shutil.copy2(SITE / name, DIST / name)

    directories = [directory for directory in sorted(CATALOG.iterdir()) if directory.is_dir()]
    if len(directories) != 1:
        raise ValueError("site requires exactly one complete iOS build catalog")
    for directory in directories:
        dyld = load(directory / "dyld.json")
        volumes = [load(directory / name) for name in
                   ("filesystem.json.gz", "systemos.json", "appos.json")]
        build = directory.name
        if dyld["build"] != build or dyld["product_type"] != "iPhone12,1":
            raise ValueError(f"dyld identity mismatch in {directory}")
        if any(not volume["complete"] or volume["build"] != build or
               volume["firmware_sha256"] != dyld["firmware_sha256"]
               for volume in volumes):
            raise ValueError(f"incomplete or mismatched filesystem catalog in {directory}")

        image_names = {image["install_name"] for image in dyld["images"]}
        driverkit_path = directory / "driverkit-dyld.json"
        if driverkit_path.exists():
            image_names.update(image["install_name"] for image in load(driverkit_path)["images"])
        physical = {}
        compact_entries = []
        volume_metadata = []
        for volume_index, volume in enumerate(volumes):
            volume_metadata.append({"name": volume["volume"],
                                    "image_name": volume["image_name"],
                                    "count": volume["entry_count"]})
            for item in volume["entries"]:
                compact_entries.append([volume_index, item["path"], item["type"],
                                        item.get("size"), item.get("target")])
                if item["type"] == "file" and item["path"] in image_names:
                    physical.setdefault(item["path"], []).append(volume["volume"])

        images = [{**image, "physical_volumes": physical.get(image["install_name"], [])}
                  for image in dyld["images"]]
        objc_info = {}
        objc_path = directory / "objc-classes.json"
        if objc_path.exists():
            objc = load(objc_path)
            records = objc["records"]
            known = {image["install_name"] for image in dyld["images"]}
            by_label = defaultdict(set)
            for name in known:
                by_label[name.rsplit("/", 1)[-1]].add(name)
            resolution_counts = Counter(row[4] for row in records)
            image_counts = Counter(row[3] for row in records if row[3])
            if (not objc["complete"] or
                    objc["kind"] != "dyld_objc_optimization_classes" or
                    objc["source"] != "official_ipsw_intact_cache_family" or
                    objc["build"] != build or
                    objc["product_type"] != dyld["product_type"] or
                    objc["firmware_sha256"] != dyld["firmware_sha256"] or
                    objc["cache_uuid"] != dyld["cache_uuid"] or
                    objc["record_count"] != len(records) or
                    objc["image_count_with_classes"] != len(image_counts) or
                    objc["resolution_counts"] != dict(resolution_counts) or
                    any(len(row) != 5 or not row[0] or
                        not re.fullmatch(r"0x[0-9a-f]+", row[1]) or
                        row[2] not in by_label or
                        (row[3] not in by_label[row[2]] if row[3] else row[4] != "unresolved") or
                        (row[4] == "unresolved") != (row[3] is None) or
                        (row[4] == "unique_label") != (len(by_label[row[2]]) == 1) or
                        row[4] not in ("unique_label", "segment_address", "unresolved")
                        for row in records)):
                raise ValueError(f"incomplete or mismatched ObjC class catalog in {directory}")
            for image in images:
                image["objc_class_count"] = image_counts[image["install_name"]]
            dump(DIST / "data" / f"{build}-objc.json.gz",
                 {"schema_version": 1, "build": build, "records": records},
                 compressed=True)
            objc_info = {"objc_class_count": len(records),
                         "objc_image_count": len(image_counts),
                         "objc_unresolved_count": resolution_counts["unresolved"],
                         "objc_url": f"data/{build}-objc.json.gz"}
        method_info = {}
        method_paths = sorted(directory.glob("objc-image-methods-*.json.gz"))
        if method_paths:
            if not objc_path.exists():
                raise ValueError("method catalogs require the Objective-C class catalog")
            segment_catalog = load(directory / "dyld-segments.json")
            if (not segment_catalog["complete"] or
                    segment_catalog["build"] != build or
                    segment_catalog["cache_uuid"] != dyld["cache_uuid"] or
                    segment_catalog["firmware_sha256"] != dyld["firmware_sha256"]):
                raise ValueError("method catalogs require matching Mach-O segments")
            segments_by_name = {item["install_name"]: item for item in segment_catalog["images"]}
            main_cache_files = [item for item in dyld["files"]
                                if item["name"] == f"dyld_shared_cache_{dyld['architecture']}"]
            if len(main_cache_files) != 1:
                raise ValueError("method catalogs require one identified main cache file")
            main_cache_hash = main_cache_files[0]["sha256"]
            method_images = []
            seen_images = set()
            method_uuid_counts = Counter(image["uuid"] for image in segment_catalog["images"])
            totals = Counter()
            for path in method_paths:
                source = load(path)
                install_name = source["install_name"]
                image = segments_by_name.get(install_name)
                if not image:
                    raise ValueError(f"method image absent from segment catalog: {path}")
                text_segments = [part for part in image["segments"] if part["name"] == "__TEXT"]
                groups = source["groups"]
                rows = source["records"]
                class_table = {(row[0], row[1]) for row in objc["records"] if row[3] == install_name}
                class_groups = [group for group in groups if group["category_name"] is None]
                category_groups = [group for group in groups if group["category_name"] is not None]
                actual_class_table = {(group["class_name"], group["metadata_address"])
                                      for group in class_groups}
                extra_classes = actual_class_table - class_table
                if (source["schema_version"] != 1 or
                        source["kind"] != "dyld_objc_image_methods" or
                        source["source"] != "official_ipsw_intact_cache_family" or
                        source["build"] != build or
                        source["product_type"] != dyld["product_type"] or
                        source["firmware_sha256"] != dyld["firmware_sha256"] or
                        source["cache_uuid"] != dyld["cache_uuid"] or
                        source["image_uuid"] != image["uuid"] or
                        install_name in seen_images or
                        len(text_segments) != 1 or
                        source["class_count"] != len(class_groups) or
                        source["toc_class_count"] != len(class_table) or
                        source["unlisted_swift_class_count"] != len(extra_classes) or
                        not class_table <= actual_class_table or
                        len(class_groups) != len(class_table) + len(extra_classes) or
                        any(not group["is_swift"] for group in class_groups
                            if (group["class_name"], group["metadata_address"]) in extra_classes) or
                        source["category_count"] != len(category_groups) or
                        source.get("unknown_category_class_count", 0) != sum(
                            group["class_name"] is None for group in category_groups) or
                        source["method_count"] != len(rows) or
                        not isinstance(source["class_dump_replacement_char_count"], int) or
                        source["class_dump_replacement_char_count"] < 0 or
                        not 0 <= source["rendered_protocol_count"] <= source["toc_protocol_count"] or
                        len({group["display_name"] for group in groups}) != len(groups) or
                        len({tuple(row) for row in rows}) != len(rows) or
                        not re.fullmatch(r"[0-9a-f]{64}", source["class_dump_sha256"]) or
                        (source.get("class_dump_empty", False) and
                         (source["class_dump_sha256"] != hashlib.sha256(b"").hexdigest() or
                          groups or rows or source["rendered_protocol_count"] or
                          source["toc_protocol_count"])) or
                        (source["extracted_image_sha256"] is None and
                         source.get("cache_main_sha256") != main_cache_hash) or
                        (source["extracted_image_sha256"] is not None and
                         not re.fullmatch(r"[0-9a-f]{64}", source["extracted_image_sha256"]))):
                    raise ValueError(f"incomplete or mismatched method catalog: {path}")
                start = text_segments[0]["addr"]
                end = start + text_segments[0]["memsz"]
                ranges = [(part["addr"], part["addr"] + part["memsz"])
                          for part in image["segments"] if part["name"] != "__LINKEDIT"]
                if any(len(row) != 4 or not isinstance(row[0], int) or
                       not 0 <= row[0] < len(groups) or row[1] not in ("+", "-") or
                       (row[2] is not None and
                        not re.fullmatch(r"(?:[^\W\d][\w$]*:|:)+|\.?[^\W\d][\w$]*", row[2])) or
                       not re.fullmatch(r"0x[0-9a-f]+", row[3]) or
                       not start <= int(row[3], 16) < end for row in rows):
                    raise ValueError(f"invalid method selector or address: {path}")
                group_counts = Counter(row[0] for row in rows)
                if (any(group["method_count"] != group_counts[index] or
                        not any(lo <= int(group["metadata_address"], 16) < hi for lo, hi in ranges) or
                        group["display_name"] != (group["class_name"] if group["category_name"] is None
                                                  else f"{group['class_name'] or '<unknown class>'} ({group['category_name']})")
                        for index, group in enumerate(groups))):
                    raise ValueError(f"method group counts or addresses disagree: {path}")
                duplicate_groups = Counter((row[0], row[1], row[2]) for row in rows if row[2] is not None)
                if (source["unknown_selector_count"] != sum(row[2] is None for row in rows) or
                        source["duplicate_selector_group_count"] != sum(count > 1 for count in duplicate_groups.values())):
                    raise ValueError(f"duplicate selector count mismatch: {path}")
                seen_images.add(install_name)
                totals["class"] += len(class_groups)
                totals["category"] += len(category_groups)
                totals["method"] += len(rows)
                totals["unknown_selector"] += source["unknown_selector_count"]
                totals["unlisted_swift_class"] += source["unlisted_swift_class_count"]
                classes = [{**group, "install_name": install_name, "image_uuid": image["uuid"],
                            "extracted_image_sha256": source["extracted_image_sha256"],
                            "cache_main_sha256": source.get("cache_main_sha256"),
                            "class_dump_sha256": source["class_dump_sha256"]}
                           for group in groups]
                method_rows = [[groups[row[0]]["display_name"], install_name,
                                row[1], row[2], row[3]] for row in rows]
                method_rows.sort(key=lambda row: (row[0].casefold(), (row[3] or "").casefold(), row[2], row[4]))
                suffix = ("-" + hashlib.sha256(install_name.encode()).hexdigest()[:12]
                          if method_uuid_counts[image["uuid"]] > 1 else "")
                url = f"data/{build}-objc-methods/{image['uuid']}{suffix}.json.gz"
                target = DIST / url
                dump(target, {"schema_version": 1, "build": build,
                              "install_name": install_name, "classes": classes,
                              "records": method_rows}, compressed=True)
                blob = target.read_bytes()
                method_images.append({"install_name": install_name, "uuid": image["uuid"],
                                      "class_count": len(class_groups),
                                      "category_count": len(category_groups),
                                      "method_count": len(rows),
                                      "unknown_selector_count": source["unknown_selector_count"],
                                      "unlisted_swift_class_count": source["unlisted_swift_class_count"],
                                      "groups": [[group["display_name"], group["method_count"]]
                                                 for group in groups],
                                      "url": url, "size": len(blob),
                                      "sha256": hashlib.sha256(blob).hexdigest()})
            method_images.sort(key=lambda item: item["install_name"])
            dump(DIST / "data" / f"{build}-objc-method-index.json.gz",
                 {"schema_version": 1, "build": build, "images": method_images},
                 compressed=True)
            method_info = {"objc_method_count": totals["method"],
                           "objc_method_class_count": totals["class"],
                           "objc_method_category_count": totals["category"],
                           "objc_method_unknown_selector_count": totals["unknown_selector"],
                           "objc_method_unlisted_swift_class_count": totals["unlisted_swift_class"],
                           "objc_method_image_count": len(seen_images),
                           "objc_method_index_url": f"data/{build}-objc-method-index.json.gz"}
        protocol_info = {}
        protocol_path = directory / "objc-protocols.json"
        if protocol_path.exists():
            protocols = load(protocol_path)
            protocol_records = protocols["records"]
            known = {image["install_name"] for image in dyld["images"]}
            by_label = defaultdict(set)
            for name in known:
                by_label[name.rsplit("/", 1)[-1]].add(name)
            resolution_counts = Counter(row[4] for row in protocol_records)
            image_counts = Counter(row[3] for row in protocol_records if row[3])
            observed_labels = {row[2] for row in protocol_records}
            ambiguous = {label: sorted(names) for label, names in by_label.items()
                         if len(names) > 1 and label in observed_labels}
            if (not protocols["complete"] or
                    protocols["kind"] != "dyld_objc_optimization_protocols" or
                    protocols["source"] != "official_ipsw_intact_cache_family" or
                    protocols["build"] != build or
                    protocols["product_type"] != dyld["product_type"] or
                    protocols["firmware_sha256"] != dyld["firmware_sha256"] or
                    protocols["cache_uuid"] != dyld["cache_uuid"] or
                    protocols["record_count"] != len(protocol_records) or
                    protocols["image_count_with_unique_labels"] != len(image_counts) or
                    protocols["resolution_counts"] != dict(resolution_counts) or
                    protocols["ambiguous_labels"] != ambiguous or
                    any(len(row) != 5 or not row[0] or
                        not re.fullmatch(r"0x[0-9a-f]+", row[1]) or
                        row[2] not in by_label or
                        (row[4] == "unique_label") != (len(by_label[row[2]]) == 1) or
                        (row[4] == "unique_label") != (row[3] in by_label[row[2]]) or
                        row[4] not in ("unique_label", "ambiguous_label")
                        for row in protocol_records)):
                raise ValueError(f"incomplete or mismatched ObjC protocol catalog in {directory}")
            for image in images:
                image["objc_protocol_entry_count"] = image_counts[image["install_name"]]
            dump(DIST / "data" / f"{build}-objc-protocols.json.gz",
                 {"schema_version": 1, "build": build, "records": protocol_records,
                  "ambiguous_labels": protocols["ambiguous_labels"]}, compressed=True)
            protocol_info = {"objc_protocol_entry_count": len(protocol_records),
                             "objc_protocol_unique_label_count": resolution_counts["unique_label"],
                             "objc_protocol_ambiguous_label_count": resolution_counts["ambiguous_label"],
                             "objc_protocol_url": f"data/{build}-objc-protocols.json.gz"}
        swift_info = publish_swift(directory, dyld, images, build)
        dump(DIST / "data" / f"{build}-files.json.gz",
             {"schema_version": 1, "build": build, "volumes": volume_metadata,
              "entries": compact_entries}, compressed=True)
        dump(DIST / "data" / f"{build}-dyld.json",
             {"schema_version": 1, "build": build, "cache_uuid": dyld["cache_uuid"],
              "files": dyld["files"], "images": images})
        ios_symbol_info = {}
        ios_symbol_path = directory / "ios-cache-symbols.json.gz"
        if ios_symbol_path.exists():
            symbols = load(ios_symbol_path)
            expected = {image["install_name"]: image["uuid"] for image in images}
            if (symbols["schema_version"] != 1 or
                    symbols["kind"] != "ios_cache_named_text_symbols" or
                    symbols["source"] != "official_ipsw_intact_cache_family" or
                    symbols["product_type"] != dyld["product_type"] or
                    symbols["build"] != build or
                    symbols["firmware_sha256"] != dyld["firmware_sha256"] or
                    symbols["cache_uuid"] != dyld["cache_uuid"] or
                    symbols["cache_files_sha256"] != {item["name"]: item["sha256"] for item in dyld["files"]} or
                    symbols["image_count"] != len(expected) or
                    len(symbols["images"]) != len(expected)):
                raise ValueError("iOS cache symbol source mismatch")
            totals = Counter()
            summaries = []
            buckets = defaultdict(list)
            seen = set()
            count_fields = ("named_symbols", "raw_named_rows", "duplicate_rows",
                            "unnamed_rows", "outside_rows", "replacement_chars",
                            "objc_method_names")
            for item in symbols["images"]:
                name = item["install_name"]
                rows = item["symbols"]
                sections = item["text_sections"]
                if (name not in expected or name in seen or item["uuid"] != expected[name] or
                        item["named_symbols"] != len(rows) or
                        item["raw_named_rows"] != len(rows) + item["duplicate_rows"] or
                        any(not isinstance(item[field], int) or item[field] < 0 for field in count_fields) or
                        any(not re.fullmatch(r"[0-9a-f]{64}", item[field]) for field in
                            ("macho_toc_sha256", "symbol_dump_sha256")) or
                        len({tuple(row) for row in rows}) != len(rows) or
                        any(len(section) != 3 or not section[0] or
                            not isinstance(section[1], int) or not isinstance(section[2], int) or
                            section[2] < 0 for section in sections)):
                    raise ValueError(f"invalid iOS cache symbol catalog: {name}")
                ranges = defaultdict(list)
                for segment, address, length in sections:
                    ranges[segment].append((address, address + length))
                if any(len(row) != 4 or not re.fullmatch(r"0x[0-9a-f]+", row[0]) or
                       not row[1] or not row[2] or row[3] not in ranges or
                       not any(lo <= int(row[0], 16) < hi for lo, hi in ranges[row[3]])
                       for row in rows):
                    raise ValueError(f"iOS cache symbol outside __text: {name}")
                objc_count = sum(bool(re.fullmatch(r"[+-]\[.+\]", row[1])) for row in rows)
                if item["objc_method_names"] != objc_count:
                    raise ValueError(f"iOS cache ObjC symbol count differs: {name}")
                seen.add(name)
                for field in count_fields:
                    totals[field] += item[field]
                totals["images_with_names"] += bool(rows)
                totals["images_without_names"] += not bool(rows)
                bucket_id = hashlib.sha256(name.encode()).digest()[0] % 128
                bucket_url = f"data/{build}-ios-symbols/{bucket_id:02x}.json.gz" if rows else None
                summaries.append({"install_name": name, "uuid": item["uuid"],
                                  "named_symbol_count": len(rows),
                                  "macho_toc_sha256": item["macho_toc_sha256"],
                                  "symbol_dump_sha256": item["symbol_dump_sha256"],
                                  "bucket_url": bucket_url})
                if rows:
                    buckets[bucket_id].append({"install_name": name, "uuid": item["uuid"],
                                               "symbols": rows})
            if seen != set(expected) or any(symbols["totals"].get(field) != value
                                            for field, value in totals.items()):
                raise ValueError("iOS cache symbol totals disagree")
            for bucket_id, entries in buckets.items():
                dump(DIST / f"data/{build}-ios-symbols/{bucket_id:02x}.json.gz",
                     {"schema_version": 1, "build": build,
                      "cache_uuid": dyld["cache_uuid"], "images": entries},
                     compressed=True)
            index_url = f"data/{build}-ios-symbol-index.json.gz"
            dump(DIST / index_url,
                 {"schema_version": 1, "build": build,
                  "cache_uuid": dyld["cache_uuid"], "images": summaries,
                  "totals": symbols["totals"]}, compressed=True)
            ios_symbol_info = {"ios_named_symbol_count": totals["named_symbols"],
                               "ios_symbol_image_count": len(summaries),
                               "ios_symbol_empty_image_count": totals["images_without_names"],
                               "ios_symbol_objc_method_name_count": totals["objc_method_names"],
                               "ios_symbol_index_url": index_url}
        dependency_info = {}
        dependency_path = directory / "dyld-dependencies.json"
        if dependency_path.exists():
            dependency_info = publish_dependencies(dependency_path, dyld, build, "dyld")
        driverkit_info = {}
        intro_info = {}
        if driverkit_path.exists():
            driverkit = load(driverkit_path)
            if (driverkit["build"] != build or driverkit["product_type"] != dyld["product_type"] or
                    driverkit["firmware_sha256"] != dyld["firmware_sha256"] or
                    driverkit["platform"] != "Driverkit" or
                    driverkit["file_count"] != len(driverkit["files"]) or
                    driverkit["image_count"] != len(driverkit["images"])):
                raise ValueError(f"incomplete or mismatched DriverKit cache catalog in {directory}")
            driverkit_images = [{**image, "physical_volumes": physical.get(image["install_name"], [])}
                                for image in driverkit["images"]]
            intros_path = directory / "library-intros.json"
            if intros_path.exists():
                intros = load(intros_path)
                by_install_name = {image["install_name"]: image for image in images + driverkit_images}
                seen_intros = set()
                if intros["schema_version"] != 1 or intros["build"] != build:
                    raise ValueError("library introduction catalog identity differs")
                for entry in intros["entries"]:
                    name = entry["install_name"]
                    if (name in seen_intros or name not in by_install_name or
                            not isinstance(entry["summary"], str) or
                            not 10 <= len(entry["summary"].strip()) <= 500 or
                            not isinstance(entry["source_label"], str) or
                            not entry["source_label"].strip() or
                            not isinstance(entry["source_url"], str) or
                            not entry["source_url"].startswith("https://") or
                            not re.fullmatch(r"[0-9a-f]{64}", entry.get("source_document_sha256", "")) or
                            not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry.get("source_checked_at", "")) or
                            not isinstance(entry.get("verbatim", False), bool) or
                            (entry.get("verbatim", False) and
                             len(entry["summary"].split()) > 25)):
                        raise ValueError(f"invalid library introduction: {name}")
                    seen_intros.add(name)
                    by_install_name[name]["functional_intro"] = {
                        "summary": entry["summary"],
                        "source_label": entry["source_label"],
                        "source_url": entry["source_url"],
                        "verbatim": entry.get("verbatim", False),
                    }
                intro_info = {"library_functional_intro_count": len(seen_intros),
                              "ios_functional_intro_count": sum(
                                  "functional_intro" in image for image in images),
                              "driverkit_functional_intro_count": sum(
                                  "functional_intro" in image for image in driverkit_images)}
                dump(DIST / "data" / f"{build}-dyld.json",
                     {"schema_version": 1, "build": build, "cache_uuid": dyld["cache_uuid"],
                      "files": dyld["files"], "images": images})
            dump(DIST / "data" / f"{build}-driverkit.json",
                 {"schema_version": 1, "build": build, "cache_uuid": driverkit["cache_uuid"],
                  "files": driverkit["files"], "images": driverkit_images})
            driverkit_info = {"driverkit_image_count": len(driverkit_images),
                              "driverkit_cache_file_count": len(driverkit["files"]),
                              "driverkit_url": f"data/{build}-driverkit.json"}
            driverkit_functions_path = directory / "driverkit-functions.json.gz"
            if driverkit_functions_path.exists():
                functions = load(driverkit_functions_path)
                expected_names = {image["install_name"]: image["uuid"] for image in driverkit_images}
                if (functions["schema_version"] != 1 or
                        functions["kind"] != "driverkit_named_text_functions" or
                        functions["source"] != "official_ipsw_intact_cache_family" or
                        functions["build"] != build or
                        functions["product_type"] != driverkit["product_type"] or
                        functions["firmware_sha256"] != driverkit["firmware_sha256"] or
                        functions["cache_uuid"] != driverkit["cache_uuid"] or
                        functions["cache_files_sha256"] != {
                            item["name"]: item["sha256"] for item in driverkit["files"]} or
                        functions["image_count"] != len(driverkit_images) or
                        len(functions["images"]) != len(driverkit_images) or
                        {image["install_name"] for image in functions["images"]} != set(expected_names) or
                        functions["named_function_count"] != sum(
                            image["named_function_count"] for image in functions["images"])):
                    raise ValueError("DriverKit function catalog identity or totals differ")
                for image in functions["images"]:
                    rows = image["functions"]
                    start = int(image["text_address"], 16)
                    end = start + image["text_size"]
                    if (image["uuid"] != expected_names[image["install_name"]] or
                            image["named_function_count"] != len(rows) or
                            image["duplicate_symbol_table_entry_count"] < 0 or
                            any(not re.fullmatch(r"[0-9a-f]{64}", image[field]) for field in
                                ("macho_toc_sha256", "symbol_dump_sha256", "class_dump_sha256")) or
                            (image["class_dump_empty"] and
                             image["class_dump_sha256"] != hashlib.sha256(b"").hexdigest()) or
                            any(image["objc_toc"].get(key, 0) != 0 for key in
                                ("__objc_classlist", "__objc_catlist")) or
                            len({tuple(row) for row in rows}) != len(rows) or
                            any(len(row) != 3 or not row[1] or not row[2] or
                                not re.fullmatch(r"0x[0-9a-f]+", row[0]) or
                                not start <= int(row[0], 16) < end for row in rows)):
                        raise ValueError(f"invalid DriverKit function catalog image: {image['install_name']}")
                function_url = f"data/{build}-driverkit-functions.json.gz"
                dump(DIST / function_url, functions, compressed=True)
                driverkit_info.update({"driverkit_function_url": function_url,
                                       "driverkit_named_function_count": functions["named_function_count"]})
            driverkit_dependency_path = directory / "driverkit-dependencies.json"
            if driverkit_dependency_path.exists():
                driverkit_info.update(publish_dependencies(driverkit_dependency_path,
                                                           driverkit, build, "driverkit"))
        standalone_info = {}
        standalone_path = directory / "standalone-macho.json.gz"
        if standalone_path.exists():
            standalone = load(standalone_path)
            rows = standalone["records"]
            excluded = standalone["excluded_candidates"]
            volume_names = {volume["volume"] for volume in volumes}
            wanted = {(item["volume"], item["path"]) for item in rows + excluded}
            observed = {(volume["volume"], item["path"]): item
                        for volume in volumes for item in volume["entries"]
                        if (volume["volume"], item["path"]) in wanted}
            if (standalone["schema_version"] != 1 or
                    standalone["kind"] != "standalone_macho_file_inventory" or
                    standalone["source"] != "official_ipsw_mounted_images" or
                    standalone["build"] != build or
                    standalone["product_type"] != dyld["product_type"] or
                    standalone["firmware_sha256"] != dyld["firmware_sha256"] or
                    standalone["volume_images"] != {
                        volume["volume"]: volume["image_name"] for volume in volumes} or
                    standalone["macho_file_count"] != len(rows) or
                    len(wanted) != len(rows) + len(excluded) or
                    len(observed) != len(wanted)):
                raise ValueError("standalone Mach-O catalog source or count mismatch")
            for volume in volumes:
                name = volume["volume"]
                files_checked = sum(item["type"] == "file" and
                                    (item.get("size") or 0) >= 4 for item in volume["entries"])
                macho_count = sum(item["volume"] == name for item in rows)
                excluded_count = sum(item["volume"] == name for item in excluded)
                if (standalone["scan_counts"].get(f"{name}_files_checked") != files_checked or
                        standalone["scan_counts"].get(f"{name}_header_candidates") !=
                        macho_count + excluded_count or
                        standalone["scan_counts"].get(f"{name}_macho_files") != macho_count):
                    raise ValueError(f"standalone Mach-O scan counts differ for {name}")
            for item in rows:
                disk = observed[(item["volume"], item["path"])]
                if (disk["type"] != "file" or disk["size"] != item["size"] or
                        item["volume"] not in volume_names or
                        not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) or
                        not re.fullmatch(r"[0-9a-f]{8}", item["header_magic"]) or
                        not item["slices"] or
                        any(not isinstance(part["cpu_type"], int) or
                            not isinstance(part["cpu_subtype"], int) or
                            not part["architecture"] or not part["file_type"] or
                            (part["uuid"] is not None and
                             not re.fullmatch(r"[0-9A-F-]{36}", part["uuid"]))
                            for part in item["slices"])):
                    raise ValueError(f"invalid standalone Mach-O record: {item['path']}")
            for item in excluded:
                disk = observed[(item["volume"], item["path"])]
                if (disk["type"] != "file" or disk["size"] != item["size"] or
                        not item["slice_magics"] or
                        item["reason"] not in ("fat_header_without_macho_slices",
                                               "fat_header_with_mixed_non_macho_slices")):
                    raise ValueError(f"invalid excluded Mach-O candidate: {item['path']}")
            standalone_url = f"data/{build}-standalone-macho.json.gz"
            dump(DIST / standalone_url, standalone, compressed=True)
            standalone_info = {"standalone_macho_file_count": len(rows),
                               "standalone_macho_url": standalone_url}
            live_identity_path = directory / "standalone-live-identity.json.gz"
            if live_identity_path.exists():
                device_catalog_path = directory / "device-live.json.gz"
                if not device_catalog_path.exists():
                    raise ValueError("standalone live identity requires public device paths")
                standalone_info.update(publish_standalone_device_identity(
                    build, dyld["product_type"], live_identity_path,
                    standalone, device_catalog_path))
            objc_path = directory / "standalone-objc-methods.json.gz"
            if objc_path.exists():
                objc_methods = load(objc_path)
                files = objc_methods["files"]
                by_file = {(item["volume"], item["path"]): item for item in rows}
                if (objc_methods["schema_version"] != 1 or
                        objc_methods["kind"] != "standalone_macho_objc_methods" or
                        objc_methods["source"] != "official_ipsw_mounted_images" or
                        objc_methods["product_type"] != dyld["product_type"] or
                        objc_methods["build"] != build or
                        objc_methods["firmware_sha256"] != dyld["firmware_sha256"] or
                        objc_methods["macho_file_count"] != len(files) or
                        len(files) != len(rows)):
                    raise ValueError("standalone Objective-C method source mismatch")
                status_counts = Counter()
                totals = Counter()
                summaries = []
                buckets = defaultdict(list)
                seen = set()
                selector_pattern = r"(?:[^\W\d][\w$]*:|:)+|\.?[^\W\d][\w$]*"
                for item in files:
                    key = (item["volume"], item["path"])
                    original = by_file.get(key)
                    groups = item["groups"]
                    methods = item["records"]
                    if (original is None or key in seen or
                            item["sha256"] != original["sha256"] or
                            item["uuid"] != original["slices"][0]["uuid"] or
                            item["status"] not in ("parsed", "no_objc_info") or
                            item["class_count"] != sum(group["category_name"] is None
                                                       for group in groups) or
                            item["category_count"] != sum(group["category_name"] is not None
                                                          for group in groups) or
                            item["method_count"] != len(methods) or
                            item["unknown_selector_count"] != sum(row[2] is None
                                                                   for row in methods) or
                            not 0 <= item["rendered_protocol_count"] <= item["toc_protocol_count"] or
                            not 0 <= item["unlisted_swift_class_count"] <= item["class_count"] or
                            not re.fullmatch(r"[0-9a-f]{64}", item["class_dump_sha256"]) or
                            item["class_dump_replacement_char_count"] < 0 or
                            len({group["display_name"] for group in groups}) != len(groups)):
                        raise ValueError(f"invalid standalone Objective-C catalog: {key}")
                    if item["status"] == "no_objc_info":
                        if (groups or methods or item["class_dump_sha256"] !=
                                hashlib.sha256(b"").hexdigest() or
                                item["class_count"] or item["category_count"] or
                                item["rendered_protocol_count"] or item["toc_protocol_count"]):
                            raise ValueError(f"invalid no-ObjC result: {key}")
                    else:
                        if (not re.fullmatch(r"[0-9a-f]{64}", item["macho_loads_sha256"]) or
                                item["text_size"] < 0 or
                                not re.fullmatch(r"0x[0-9a-f]+", item["text_address"])):
                            raise ValueError(f"invalid standalone Mach-O source metadata: {key}")
                        start = int(item["text_address"], 16)
                        end = start + item["text_size"]
                        group_counts = Counter(row[0] for row in methods)
                        if (any(len(row) != 4 or not isinstance(row[0], int) or
                                not 0 <= row[0] < len(groups) or row[1] not in ("+", "-") or
                                (row[2] is not None and not re.fullmatch(selector_pattern, row[2])) or
                                not re.fullmatch(r"0x[0-9a-f]+", row[3]) or
                                not start <= int(row[3], 16) < end for row in methods) or
                                any(group["method_count"] != group_counts[index] or
                                    group["display_name"] != (group["class_name"] if
                                        group["category_name"] is None else
                                        f"{group['class_name'] or '<unknown class>'} ({group['category_name']})")
                                    for index, group in enumerate(groups))):
                            raise ValueError(f"standalone method or group mismatch: {key}")
                    seen.add(key)
                    status_counts[item["status"]] += 1
                    totals["classes"] += item["class_count"]
                    totals["categories"] += item["category_count"]
                    totals["methods"] += item["method_count"]
                    totals["unknown_selectors"] += item["unknown_selector_count"]
                    bucket_id = hashlib.sha256(f'{key[0]}\0{key[1]}'.encode()).digest()[0] % 64
                    bucket_url = (f"data/{build}-standalone-objc/{bucket_id:02x}.json.gz"
                                  if groups else None)
                    summaries.append({"volume": key[0], "path": key[1],
                                      "sha256": item["sha256"], "uuid": item["uuid"],
                                      "status": item["status"],
                                      "class_count": item["class_count"],
                                      "category_count": item["category_count"],
                                      "method_count": item["method_count"],
                                      "bucket_url": bucket_url})
                    if groups:
                        buckets[bucket_id].append({"volume": key[0], "path": key[1],
                                                   "sha256": item["sha256"],
                                                   "groups": groups, "records": methods})
                if (len(seen) != len(rows) or
                        any(objc_methods["totals"].get(name) != value for name, value in
                            {**totals, **status_counts}.items())):
                    raise ValueError("standalone Objective-C method totals disagree")
                for bucket_id, entries in buckets.items():
                    dump(DIST / f"data/{build}-standalone-objc/{bucket_id:02x}.json.gz",
                         {"schema_version": 1, "build": build, "files": entries},
                         compressed=True)
                index_url = f"data/{build}-standalone-objc-index.json.gz"
                dump(DIST / index_url,
                     {"schema_version": 1, "build": build, "files": summaries,
                      "totals": objc_methods["totals"]}, compressed=True)
                standalone_info.update({"standalone_objc_method_count": totals["methods"],
                                        "standalone_objc_file_count": len(files),
                                        "standalone_objc_no_info_count": status_counts["no_objc_info"],
                                        "standalone_objc_index_url": index_url})
            symbol_path = directory / "standalone-symbols.json.gz"
            if symbol_path.exists():
                symbols = load(symbol_path)
                files = symbols["files"]
                by_file = {(item["volume"], item["path"]): item for item in rows}
                if (symbols["schema_version"] != 1 or
                        symbols["kind"] != "standalone_macho_named_text_symbols" or
                        symbols["source"] != "official_ipsw_mounted_images" or
                        symbols["product_type"] != dyld["product_type"] or
                        symbols["build"] != build or
                        symbols["firmware_sha256"] != dyld["firmware_sha256"] or
                        symbols["macho_file_count"] != len(files) or
                        len(files) != len(rows)):
                    raise ValueError("standalone symbol source mismatch")
                totals = Counter()
                summaries = []
                buckets = defaultdict(list)
                seen = set()
                for item in files:
                    key = (item["volume"], item["path"])
                    original = by_file.get(key)
                    sections = item["text_sections"]
                    named = item["symbols"]
                    if (original is None or key in seen or
                            item["sha256"] != original["sha256"] or
                            item["uuid"] != original["slices"][0]["uuid"] or
                            item["named_symbol_count"] != len(named) or
                            len({tuple(row) for row in named}) != len(named) or
                            any(not re.fullmatch(r"[0-9a-f]{64}", item[field]) for field in
                                ("macho_loads_sha256", "symbol_dump_sha256")) or
                            any(item[field] < 0 for field in
                                ("symbol_dump_replacement_char_count",
                                 "duplicate_symbol_row_count", "unnamed_text_row_count",
                                 "outside_text_row_count")) or
                            any(len(section) != 3 or not section[0] or
                                not isinstance(section[1], int) or
                                not isinstance(section[2], int) or section[2] < 0
                                for section in sections)):
                        raise ValueError(f"invalid standalone symbol catalog: {key}")
                    ranges = defaultdict(list)
                    for segment, address, length in sections:
                        ranges[segment].append((address, address + length))
                    if any(len(row) != 4 or not re.fullmatch(r"0x[0-9a-f]+", row[0]) or
                           not row[1] or not row[2] or row[3] not in ranges or
                           not any(lo <= int(row[0], 16) < hi for lo, hi in ranges[row[3]])
                           for row in named):
                        raise ValueError(f"standalone named symbol outside __text: {key}")
                    seen.add(key)
                    totals["named_symbols"] += len(named)
                    totals["duplicate_rows"] += item["duplicate_symbol_row_count"]
                    totals["unnamed_rows"] += item["unnamed_text_row_count"]
                    totals["outside_rows"] += item["outside_text_row_count"]
                    totals["files_without_names"] += not bool(named)
                    bucket_id = hashlib.sha256(f'{key[0]}\0{key[1]}'.encode()).digest()[0] % 64
                    bucket_url = (f"data/{build}-standalone-symbols/{bucket_id:02x}.json.gz"
                                  if named else None)
                    summaries.append({"volume": key[0], "path": key[1],
                                      "sha256": item["sha256"], "uuid": item["uuid"],
                                      "named_symbol_count": len(named),
                                      "bucket_url": bucket_url})
                    if named:
                        buckets[bucket_id].append({"volume": key[0], "path": key[1],
                                                   "sha256": item["sha256"],
                                                   "symbols": named})
                if (len(seen) != len(rows) or
                        any(symbols["totals"].get(name) != value for name, value in totals.items())):
                    raise ValueError("standalone symbol totals disagree")
                for bucket_id, entries in buckets.items():
                    dump(DIST / f"data/{build}-standalone-symbols/{bucket_id:02x}.json.gz",
                         {"schema_version": 1, "build": build, "files": entries},
                         compressed=True)
                index_url = f"data/{build}-standalone-symbol-index.json.gz"
                dump(DIST / index_url,
                     {"schema_version": 1, "build": build, "files": summaries,
                      "totals": symbols["totals"]}, compressed=True)
                standalone_info.update({"standalone_named_symbol_count": totals["named_symbols"],
                                        "standalone_symbol_file_count": len(files),
                                        "standalone_symbol_empty_file_count": totals["files_without_names"],
                                        "standalone_symbol_index_url": index_url})
            swift_path = directory / "standalone-swift.json.gz"
            if swift_path.exists():
                swift = load(swift_path)
                files = swift["files"]
                by_file = {(item["volume"], item["path"]): item for item in rows}
                if (swift["schema_version"] != 1 or
                        swift["kind"] != "standalone_macho_swift_declarations" or
                        swift["source"] != "official_ipsw_mounted_images" or
                        swift["product_type"] != dyld["product_type"] or
                        swift["build"] != build or
                        swift["firmware_sha256"] != dyld["firmware_sha256"] or
                        swift["macho_file_count"] != len(files) or len(files) != len(rows)):
                    raise ValueError("standalone Swift source mismatch")
                totals = Counter()
                summaries = []
                buckets = defaultdict(list)
                seen = set()
                kinds = ("class", "struct", "enum", "protocol", "extension", "actor")
                for item in files:
                    key = (item["volume"], item["path"])
                    original = by_file.get(key)
                    declarations = item["declarations"]
                    kind_counts = Counter(entry["kind"] for entry in declarations)
                    members = sum(len(entry["members"]) for entry in declarations)
                    stripped = sum("<stripped>" in member[1]
                                   for entry in declarations for member in entry["members"])
                    status = item["status"]
                    if (original is None or key in seen or
                            item["sha256"] != original["sha256"] or
                            item["uuid"] != original["slices"][0]["uuid"] or
                            status not in ("parsed", "partially_parsed", "no_swift_info") or
                            item["declaration_count"] != len(declarations) or
                            item["member_count"] != members or
                            item["stripped_member_count"] != stripped or
                            any(item["kind_counts"].get(kind) != kind_counts[kind] for kind in kinds) or
                            any(not re.fullmatch(r"[0-9a-f]{64}", item[field])
                                for field in ("macho_loads_sha256", "swift_dump_sha256")) or
                            item["swift_dump_replacement_char_count"] < 0 or
                            item["unparsed_line_count"] < 0 or
                            any(len(section) != 4 or not section[1].startswith("__swift5_") or
                                not isinstance(section[2], int) or
                                not isinstance(section[3], int) or section[3] < 0
                                for section in item["swift_sections"]) or
                            any(entry["kind"] not in kinds or not entry["name"] or
                                any(ord(char) < 32 or char == "\ufffd" for char in entry["name"]) or
                                any(len(member) != 2 or member[0] not in
                                    ("methods", "requirements") or not member[1] or
                                    any(ord(char) < 32 or char == "\ufffd" for char in member[1])
                                    for member in entry["members"])
                                for entry in declarations)):
                        raise ValueError(f"invalid standalone Swift catalog: {key}")
                    if ((status == "no_swift_info" and
                         (declarations or item["swift_sections"] or item["unparsed_line_count"])) or
                            (status != "no_swift_info" and not item["swift_sections"]) or
                            (status == "parsed" and item["unparsed_line_count"]) or
                            (status == "partially_parsed" and not item["unparsed_line_count"])):
                        raise ValueError(f"standalone Swift status mismatch: {key}")
                    seen.add(key)
                    totals[status] += 1
                    totals["declarations"] += len(declarations)
                    totals["members"] += members
                    totals["stripped_members"] += stripped
                    totals["unparsed_lines"] += item["unparsed_line_count"]
                    for kind in kinds:
                        totals[kind] += kind_counts[kind]
                    bucket_id = hashlib.sha256(f'{key[0]}\0{key[1]}'.encode()).digest()[0] % 64
                    bucket_url = (f"data/{build}-standalone-swift/{bucket_id:02x}.json.gz"
                                  if declarations else None)
                    summaries.append({"volume": key[0], "path": key[1],
                                      "sha256": item["sha256"], "uuid": item["uuid"],
                                      "status": status,
                                      "declaration_count": len(declarations),
                                      "member_count": members,
                                      "unparsed_line_count": item["unparsed_line_count"],
                                      "bucket_url": bucket_url})
                    if declarations:
                        buckets[bucket_id].append({"volume": key[0], "path": key[1],
                                                   "sha256": item["sha256"],
                                                   "declarations": declarations})
                if (len(seen) != len(rows) or
                        any(swift["totals"].get(name) != value for name, value in totals.items())):
                    raise ValueError("standalone Swift totals disagree")
                for bucket_id, entries in buckets.items():
                    dump(DIST / f"data/{build}-standalone-swift/{bucket_id:02x}.json.gz",
                         {"schema_version": 1, "build": build, "files": entries},
                         compressed=True)
                index_url = f"data/{build}-standalone-swift-index.json.gz"
                dump(DIST / index_url,
                     {"schema_version": 1, "build": build, "files": summaries,
                      "totals": swift["totals"]}, compressed=True)
                standalone_info.update({"standalone_swift_declaration_count": totals["declarations"],
                                        "standalone_swift_member_count": totals["members"],
                                        "standalone_swift_file_count": len(files),
                                        "standalone_swift_no_info_count": totals["no_swift_info"],
                                        "standalone_swift_partial_count": totals["partially_parsed"],
                                        "standalone_swift_index_url": index_url})
        device_info = {}
        live_device_path = directory / "device-live.json.gz"
        if live_device_path.exists():
            device_info.update(publish_live_device(build, dyld["product_type"], live_device_path))
        live_format_path = directory / "live-file-formats.json.gz"
        if live_format_path.exists():
            if not live_device_path.exists():
                raise ValueError("live file formats require reviewed device paths")
            device_info.update(publish_live_file_formats(
                build, dyld["product_type"], live_format_path, live_device_path))
        live_coverage_path = directory / "live-coverage.json"
        if live_coverage_path.exists():
            if not live_device_path.exists():
                raise ValueError("mount coverage requires reviewed live device paths")
            device_info.update(publish_live_coverage(
                build, dyld["product_type"], live_coverage_path, live_device_path))
        live_macho_path = directory / "jailbreak-macho.json.gz"
        if live_macho_path.exists():
            if not live_device_path.exists():
                raise ValueError("live Mach-O catalog requires the reviewed live path catalog")
            device_info.update(publish_live_macho(build, dyld["product_type"],
                                                  live_macho_path, live_device_path))
        developer_macho_path = directory / "developer-macho.json.gz"
        if developer_macho_path.exists():
            if not live_device_path.exists():
                raise ValueError("Developer Mach-O catalog requires reviewed live paths")
            device_info.update(publish_live_developer_macho(
                build, dyld["product_type"], developer_macho_path, live_device_path))
        developer_objc_path = directory / "developer-objc-methods.json.gz"
        if developer_objc_path.exists():
            if not developer_macho_path.exists():
                raise ValueError("Developer ObjC methods require verified Mach-O files")
            device_info.update(publish_live_objc(
                build, dyld["product_type"], developer_objc_path,
                developer_macho_path, "developer"))
        developer_dependencies_path = directory / "developer-dependencies.json.gz"
        if developer_dependencies_path.exists():
            if not developer_macho_path.exists():
                raise ValueError("Developer dependencies require verified Mach-O files")
            device_info.update(publish_live_dependencies(
                build, dyld["product_type"], developer_dependencies_path,
                developer_macho_path, "developer"))
        developer_symbols_path = directory / "developer-symbols.json.gz"
        if developer_symbols_path.exists():
            if not developer_macho_path.exists():
                raise ValueError("Developer symbols require verified Mach-O files")
            device_info.update(publish_live_symbols(
                build, dyld["product_type"], developer_symbols_path,
                developer_macho_path, "developer"))
        developer_swift_path = directory / "developer-swift.json.gz"
        if developer_swift_path.exists():
            if not developer_macho_path.exists():
                raise ValueError("Developer Swift metadata requires verified Mach-O files")
            device_info.update(publish_live_swift(
                build, dyld["product_type"], developer_swift_path,
                developer_macho_path, "developer"))
        developer_signatures_path = directory / "developer-signatures.json.gz"
        if developer_signatures_path.exists():
            if not developer_macho_path.exists():
                raise ValueError("Developer signatures require verified Mach-O files")
            device_info.update(publish_live_signatures(
                build, dyld["product_type"], developer_signatures_path,
                developer_macho_path, "developer"))
        live_objc_path = directory / "jailbreak-objc-methods.json.gz"
        if live_objc_path.exists():
            if not live_macho_path.exists():
                raise ValueError("live Objective-C methods require verified Mach-O files")
            device_info.update(publish_live_objc(build, dyld["product_type"],
                                                 live_objc_path, live_macho_path))
        live_dependencies_path = directory / "jailbreak-dependencies.json.gz"
        if live_dependencies_path.exists():
            if not live_macho_path.exists():
                raise ValueError("live dependencies require verified Mach-O files")
            device_info.update(publish_live_dependencies(
                build, dyld["product_type"], live_dependencies_path,
                live_macho_path))
        device_info.update(publish_live_load_targets(
            build, dyld["product_type"], directory))
        live_symbols_path = directory / "jailbreak-symbols.json.gz"
        if live_symbols_path.exists():
            if not live_macho_path.exists():
                raise ValueError("live symbols require verified Mach-O files")
            device_info.update(publish_live_symbols(
                build, dyld["product_type"], live_symbols_path,
                live_macho_path))
        live_swift_path = directory / "jailbreak-swift.json.gz"
        if live_swift_path.exists():
            if not live_macho_path.exists():
                raise ValueError("live Swift metadata requires verified Mach-O files")
            device_info.update(publish_live_swift(
                build, dyld["product_type"], live_swift_path,
                live_macho_path))
        live_signatures_path = directory / "jailbreak-signatures.json.gz"
        if live_signatures_path.exists():
            if not live_macho_path.exists():
                raise ValueError("live signatures require verified Mach-O files")
            device_info.update(publish_live_signatures(
                build, dyld["product_type"], live_signatures_path,
                live_macho_path))
        archive_info = {}
        archive_path = directory / "firmware-archive.json"
        kernel_path = directory / "kernel.json"
        kernel = load(kernel_path) if kernel_path.exists() else None
        restore_info = {}
        restore_paths = [directory / "rdisk-erase.json.gz", directory / "rdisk-upgrade.json.gz"]
        restore_volumes = []
        restore_entries = []
        if all(path.exists() for path in restore_paths):
            for volume_index, path in enumerate(restore_paths):
                volume = load(path)
                if (not volume["complete"] or volume["build"] != build or
                        volume["product_type"] != dyld["product_type"] or
                        volume["firmware_sha256"] != dyld["firmware_sha256"] or
                        volume["entry_count"] != len(volume["entries"])):
                    raise ValueError(f"incomplete or mismatched restore catalog in {directory}")
                restore_volumes.append({"name": volume["volume"],
                                        "image_name": volume["image_name"],
                                        "count": volume["entry_count"]})
                for item in volume["entries"]:
                    restore_entries.append([volume_index, item["path"], item["type"],
                                            item.get("size"), item.get("target")])
            dump(DIST / "data" / f"{build}-restore.json.gz",
                 {"schema_version": 1, "build": build, "volumes": restore_volumes,
                  "entries": restore_entries}, compressed=True)
            restore_info = {"restore_entry_count": len(restore_entries),
                            "restore_url": f"data/{build}-restore.json.gz",
                            "restore_volumes": restore_volumes}
        elif any(path.exists() for path in restore_paths):
            raise ValueError("only one restore ramdisk catalog exists")
        if archive_path.exists():
            archive = load(archive_path)
            if (archive["kind"] != "ipsw_archive" or archive["build"] != build or
                    archive["product_type"] != dyld["product_type"] or
                    archive["firmware_sha256"] != dyld["firmware_sha256"] or
                    archive["entry_count"] != len(archive["entries"]) or
                    archive["file_count"] != sum(item["kind"] != "directory" for item in archive["entries"])):
                raise ValueError(f"incomplete or mismatched IPSW archive catalog in {directory}")
            indexed_views = {volume["image_name"]: "Filesystem" for volume in volumes}
            indexed_views.update({volume["image_name"]: "Restore RAM disks" for volume in restore_volumes})
            if kernel:
                indexed_views.update({image["archive_path"]: "Kernel" for image in kernel["images"]})
            archive_entries = [{**item, "indexed_view": indexed_views.get(item["path"])}
                               for item in archive["entries"]]
            dump(DIST / "data" / f"{build}-archive.json",
                 {"schema_version": 1, "build": build, "entries": archive_entries,
                  "variants": archive["variants"]})
            archive_info = {"archive_entry_count": len(archive_entries),
                            "archive_file_count": archive["file_count"],
                            "archive_url": f"data/{build}-archive.json"}
        kernel_info = {}
        if kernel:
            if not archive_path.exists():
                raise ValueError("kernel catalog requires archive catalog")
            archive_by_path = {item["path"]: item for item in archive["entries"]}
            if (kernel["kind"] != "kernelcache_metadata" or kernel["build"] != build or
                    kernel["product_type"] != dyld["product_type"] or
                    kernel["firmware_sha256"] != dyld["firmware_sha256"] or
                    len(kernel["images"]) != 2 or
                    any(image["archive_path"] not in archive_by_path or
                        image["archive_sha256"] != archive_by_path[image["archive_path"]]["sha256"] or
                        image["kext_count"] != len(image["kexts"])
                        for image in kernel["images"])):
                raise ValueError(f"incomplete or mismatched kernel catalog in {directory}")
            kernel_images = [{key: value for key, value in image.items() if key != "kexts"}
                             for image in kernel["images"]]
            kexts = [{**kext, "variant": image["variant"], "kernel_uuid": image["macho_uuid"]}
                     for image in kernel["images"] for kext in image["kexts"]]
            dump(DIST / "data" / f"{build}-kernel.json",
                 {"schema_version": 1, "build": build, "images": kernel_images, "kexts": kexts})
            kernel_info = {"kernel_image_count": len(kernel_images),
                           "kext_record_count": len(kexts),
                           "kernel_url": f"data/{build}-kernel.json"}
        service_info = {}
        service_path = directory / "launchd.json"
        if service_path.exists():
            service = load(service_path)
            records = service["records"]
            source_plists = {entry["path"] for entry in volumes[0]["entries"]
                             if entry["type"] == "file" and entry["path"].endswith(".plist")
                             and any(f"/{folder}/" in entry["path"] for folder in
                                     ("LaunchDaemons", "LaunchAgents", "DeveloperModeLaunchDaemons"))}
            if (not service["complete"] or service["kind"] != "launchd_plists" or
                    service["build"] != build or service["product_type"] != dyld["product_type"] or
                    service["firmware_sha256"] != dyld["firmware_sha256"] or
                    service["image_name"] != volumes[0]["image_name"] or
                    service["record_count"] != len(records) or
                    service["job_count"] != sum(item["kind"] == "job" for item in records) or
                    {item["plist_path"] for item in records} != source_plists or
                    len({item["plist_path"] for item in records}) != len(records) or
                    service["mach_service_name_count"] != sum(len(item["mach_services"]) for item in records)):
                raise ValueError(f"incomplete or mismatched launchd catalog in {directory}")
            macho_path = directory / "service-macho.json"
            binaries = []
            import_info = {}
            if macho_path.exists():
                if not driverkit_path.exists():
                    raise ValueError("service Mach-O catalog requires the DriverKit cache catalog")
                macho = load(macho_path)
                binaries = macho["images"]
                service_keys = {(item["executable"]["matches"][0]["volume"],
                                 item["executable"]["source_path"])
                                for item in records if item["executable"]["status"]
                                in ("direct", "cryptex")}
                binary_keys = {(item["volume"], item["path"]) for item in binaries}
                expected_jobs = {}
                for item in records:
                    exe = item["executable"]
                    if exe["status"] in ("direct", "cryptex"):
                        key = (exe["matches"][0]["volume"], exe["source_path"])
                        expected_jobs.setdefault(key, set()).add(item["plist_path"])
                imports = [imp for item in binaries for imp in item["imports"]]
                file_locations = {}
                for volume in volumes:
                    for entry in volume["entries"]:
                        if entry["type"] == "file":
                            file_locations.setdefault(entry["path"], set()).add(volume["volume"])
                cache_identities = {(platform, item["install_name"], item["uuid"])
                                    for platform, catalog in (("iOS", dyld), ("DriverKit", driverkit))
                                    for item in catalog["images"]}
                if (not macho["complete"] or macho["kind"] != "service_executable_macho" or
                        macho["build"] != build or macho["product_type"] != dyld["product_type"] or
                        macho["firmware_sha256"] != dyld["firmware_sha256"] or
                        macho["image_count"] != len(binaries) or
                        binary_keys != service_keys or len(binary_keys) != len(binaries) or
                        any(item["kind"] != "macho" or item["file_type"] != "EXECUTE" or
                            item["volume"] not in file_locations.get(item["path"], ()) or
                            len(item["sha256"]) != 64 or
                            set(item["job_plists"]) != expected_jobs[(item["volume"], item["path"])]
                            for item in binaries) or
                        macho["direct_import_count"] != len(imports) or
                        macho["cache_matched_import_count"] != sum(bool(imp["cache_matches"]) for imp in imports) or
                        macho["file_matched_import_count"] != sum(bool(imp["file_matches"]) for imp in imports) or
                        macho["unmatched_import_count"] != sum(not imp["cache_matches"] and
                            not imp["file_matches"] for imp in imports) or
                        any(any((match["platform"], imp["install_name"], match["uuid"])
                                not in cache_identities for match in imp["cache_matches"]) or
                            set(imp["file_matches"]) != file_locations.get(imp["install_name"], set())
                            for imp in imports)):
                    raise ValueError(f"incomplete or mismatched service Mach-O catalog in {directory}")
                consumers = {}
                for binary in binaries:
                    key = (binary["volume"], binary["path"])
                    for imp in binary["imports"]:
                        for match in imp["cache_matches"]:
                            consumers.setdefault((match["platform"], imp["install_name"]), set()).add(key)
                for image in images:
                    image["service_consumer_count"] = len(consumers.get(("iOS", image["install_name"]), ()))
                dump(DIST / "data" / f"{build}-dyld.json",
                     {"schema_version": 1, "build": build, "cache_uuid": dyld["cache_uuid"],
                      "files": dyld["files"], "images": images})
                if driverkit_path.exists():
                    for image in driverkit_images:
                        image["service_consumer_count"] = len(consumers.get(("DriverKit", image["install_name"]), ()))
                    dump(DIST / "data" / f"{build}-driverkit.json",
                         {"schema_version": 1, "build": build, "cache_uuid": driverkit["cache_uuid"],
                          "files": driverkit["files"], "images": driverkit_images})
                import_info = {"service_executable_count": len(binaries),
                               "service_direct_import_count": len(imports),
                               "service_cache_matched_import_count": macho["cache_matched_import_count"]}
            dump(DIST / "data" / f"{build}-services.json", {"schema_version": 1,
                 "build": build, "records": records, "binaries": binaries})
            service_info = {"launchd_plist_count": len(records),
                            "launchd_job_count": service["job_count"],
                            "mach_service_name_count": service["mach_service_name_count"],
                            "service_url": f"data/{build}-services.json", **import_info}
        build_info = {"build": build, "version": "26.0.1",
                       "product_type": dyld["product_type"],
                       "firmware_sha256": dyld["firmware_sha256"],
                       "cache_uuid": dyld["cache_uuid"],
                       "image_count": len(images),
                       "cache_file_count": len(dyld["files"]),
                       "file_count": len(compact_entries),
                       "volumes": volume_metadata,
                       "files_url": f"data/{build}-files.json.gz",
                       "dyld_url": f"data/{build}-dyld.json", **dependency_info, **ios_symbol_info, **objc_info,
                       **method_info,
                       **protocol_info, **swift_info,
                       **device_info,
                       **driverkit_info, **intro_info, **standalone_info, **archive_info, **restore_info, **kernel_info,
                       **service_info}

    research = json.loads((ROOT / "research" / "index.json").read_text(encoding="utf-8"))
    if len({note["id"] for note in research}) != len(research):
        raise ValueError("duplicate research note id")
    for note in research:
        source = (ROOT / note["note"]).resolve()
        if (note["build"] != build_info["build"] or ROOT / "research" not in source.parents or
                not source.is_file()):
            raise ValueError(f"invalid research note source: {note['note']}")
        note["rendered_html"] = render_note(source.read_text(encoding="utf-8"), note["note"])
    dump(DIST / "data" / "manifest.json",
         {"schema_version": 2, "build": build_info, "research": research})
    digest = hashlib.sha256()
    for path in sorted(DIST.rglob("*")):
        if path.is_file() and path.name != "index.html":
            digest.update(str(path.relative_to(DIST)).encode())
            digest.update(path.read_bytes())
    version = digest.hexdigest()[:12]
    index = (DIST / "index.html").read_text(encoding="utf-8")
    index = index.replace('href="styles.css"', f'href="styles.css?v={version}"')
    index = index.replace('href="tree.css"', f'href="tree.css?v={version}"')
    index = index.replace('src="app.js"', f'src="app.js?v={version}"')
    (DIST / "index.html").write_text(index, encoding="utf-8")
    print(f"built {DIST} for {build_info['build']}")


if __name__ == "__main__":
    build()
