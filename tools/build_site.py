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


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "ios"
SITE = ROOT / "site"
DIST = ROOT / "dist"
DEVICE_SYSTEM_ROOTS = (
    "/Applications", "/Library", "/System", "/bin", "/sbin", "/usr",
    "/private/etc",
)


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
            "device_scope": "reviewed_live", "device_snapshot_root_count": data["snapshot_root_count"],
            "device_complete_root_count": data["complete_root_count"],
            "device_unpublished_entry_count": data["unpublished_entry_count"]}


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
    return {"device_macho_url": url, "device_macho_count": len(records)}


def publish_live_objc(build: str, product: str, path: Path, macho_path: Path) -> dict:
    """Validate per-file ObjC metadata against the exact acquired Mach-O index."""
    data = load(path)
    macho = load(macho_path)
    originals = {item["path"]: item for item in macho["records"]}
    files = data.get("files")
    if (data.get("schema_version") != 1 or
            data.get("kind") != "live_jailbreak_objc_methods" or
            data.get("source") != "verified_live_device_macho_bytes" or
            data.get("build") != build or data.get("product_type") != product or
            not isinstance(files, list) or len(files) != len(originals) or
            data.get("macho_file_count") != len(files)):
        raise ValueError("incomplete live Objective-C method catalog")
    seen = set()
    totals = Counter()
    for item in files:
        original = originals.get(item.get("path"))
        groups = item.get("groups")
        methods = item.get("records")
        if (original is None or item["path"] in seen or
                item.get("volume") != "Jailbreak" or
                item.get("sha256") != original["sha256"] or
                item.get("uuid") != original["slices"][0]["uuid"] or
                item.get("status") not in ("parsed", "no_objc_info") or
                not isinstance(groups, list) or not isinstance(methods, list) or
                item.get("method_count") != len(methods) or
                item.get("class_count") != sum(group["category_name"] is None
                                               for group in groups) or
                item.get("category_count") != sum(group["category_name"] is not None
                                                  for group in groups)):
            raise ValueError("live Objective-C record differs from verified Mach-O")
        if item["status"] == "no_objc_info" and (groups or methods):
            raise ValueError("no-ObjC record contains methods")
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
    url = f"data/{build}-jailbreak-objc-methods.json.gz"
    shutil.copy2(path, DIST / url)
    return {"device_macho_objc_url": url,
            "device_macho_objc_method_count": totals["methods"],
            "device_macho_objc_parsed_count": totals["parsed"],
            "device_macho_objc_no_info_count": totals["no_objc_info"]}


def publish_device_comparison(build: str, device: dict, device_path: Path,
                              stock_entries: list, volume_metadata: list,
                              firmware_sha256: str) -> dict:
    """Compare exact path/type pairs only inside the published /rootfs scan scope."""
    roots = device["scanned_roots"]
    if roots != list(DEVICE_SYSTEM_ROOTS):
        raise ValueError("unexpected device scan roots; review privacy boundary")

    def in_scope(path: str) -> bool:
        return any(path == root or path.startswith(root + "/") for root in roots)

    observed = [tuple(row) for row in device["entries"]]
    observed_set = set(observed)
    if (len(observed_set) != len(observed) or
            any(len(row) != 2 or not in_scope(row[0]) for row in observed)):
        raise ValueError("duplicate or out-of-scope device path")
    stock_sources = defaultdict(set)
    per_volume = [set() for _ in volume_metadata]
    for volume_index, path, kind, _, _ in stock_entries:
        if in_scope(path):
            pair = (path, kind)
            stock_sources[pair].add(volume_index)
            per_volume[volume_index].add(pair)
    stock_set = set(stock_sources)
    if not observed_set <= stock_set:
        raise ValueError("device path outside official same-path/type index")
    stock_only = sorted(stock_set - observed_set)
    url = f"data/{build}-stock-device.json.gz"
    payload = {
        "schema_version": 1, "kind": "stock_distribution_vs_filtered_device_paths",
        "build": build, "product_type": device["product_type"],
        "firmware_sha256": firmware_sha256,
        "device_catalog_sha256": hashlib.sha256(device_path.read_bytes()).hexdigest(),
        "device_observed_at_utc": device["observed_at_utc"],
        "device_namespace": device["device_namespace"],
        "scanned_roots": roots,
        "unique_stock_pair_count": len(stock_set),
        "observed_pair_count": len(observed_set),
        "same_path_type_count": len(stock_set & observed_set),
        "stock_only_pair_count": len(stock_only),
        "device_only_pair_count": len(observed_set - stock_set),
        "volumes": [{"name": volume_metadata[index]["name"],
                     "stock_pair_count": len(pairs),
                     "same_path_type_count": len(pairs & observed_set),
                     "stock_only_pair_count": len(pairs - observed_set)}
                    for index, pairs in enumerate(per_volume)],
        "roots": [{"path": root,
                   "stock_pair_count": sum(path == root or path.startswith(root + "/")
                                           for path, _ in stock_set),
                   "observed_pair_count": sum(path == root or path.startswith(root + "/")
                                              for path, _ in observed_set),
                   "stock_only_pair_count": sum(path == root or path.startswith(root + "/")
                                                for path, _ in stock_only)} for root in roots],
        "stock_only": [[path, kind,
                        sorted(volume_metadata[index]["name"]
                               for index in stock_sources[(path, kind)])]
                       for path, kind in stock_only],
    }
    if (payload["same_path_type_count"] != payload["observed_pair_count"] or
            payload["same_path_type_count"] + payload["stock_only_pair_count"] !=
            payload["unique_stock_pair_count"] or
            sum(row["stock_only_pair_count"] for row in payload["roots"]) !=
            len(stock_only)):
        raise ValueError("device comparison count mismatch")
    dump(DIST / url, payload, compressed=True)
    return {"stock_device_url": url, "stock_device_unique_stock_count": len(stock_set),
            "stock_device_only_count": len(stock_only)}


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
    for name in ("index.html", "app.js", "styles.css", "tree.css", "observation.css", "reach.mjs", "tree.mjs"):
        shutil.copy2(SITE / name, DIST / name)

    builds = []
    for directory in sorted(CATALOG.iterdir()):
        if not directory.is_dir():
            continue
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
        stock_types = {}
        compact_entries = []
        volume_metadata = []
        for volume_index, volume in enumerate(volumes):
            volume_metadata.append({"name": volume["volume"],
                                    "image_name": volume["image_name"],
                                    "count": volume["entry_count"]})
            for item in volume["entries"]:
                stock_types.setdefault(item["path"], set()).add(item["type"])
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
        device_path = directory / "device-rootfs.json.gz"
        if device_path.exists():
            device = load(device_path)
            if (not device["complete"] or device["build"] != build or
                    device["product_type"] != dyld["product_type"] or
                    device["kind"] != "device_system_path_observation" or
                    device["device_namespace"] != "/rootfs" or
                    device["entry_count"] != len(device["entries"])):
                raise ValueError(f"incomplete or mismatched device catalog in {directory}")
            if any(path not in stock_types or kind not in stock_types[path]
                   for path, kind in device["entries"]):
                raise ValueError("device catalog contains paths or types absent from official IPSW; review before publishing")
            shutil.copy2(device_path, DIST / "data" / f"{build}-device.json.gz")
            device_info = {"device_count": device["entry_count"],
                           "device_url": f"data/{build}-device.json.gz",
                           "device_observed_at_utc": device["observed_at_utc"],
                           **publish_device_comparison(build, device, device_path,
                                                       compact_entries, volume_metadata,
                                                       dyld["firmware_sha256"])}
        live_device_path = directory / "device-live.json.gz"
        if live_device_path.exists():
            device_info.update(publish_live_device(build, dyld["product_type"], live_device_path))
        live_macho_path = directory / "jailbreak-macho.json.gz"
        if live_macho_path.exists():
            if not live_device_path.exists():
                raise ValueError("live Mach-O catalog requires the reviewed live path catalog")
            device_info.update(publish_live_macho(build, dyld["product_type"],
                                                  live_macho_path, live_device_path))
        live_objc_path = directory / "jailbreak-objc-methods.json.gz"
        if live_objc_path.exists():
            if not live_macho_path.exists():
                raise ValueError("live Objective-C methods require verified Mach-O files")
            device_info.update(publish_live_objc(build, dyld["product_type"],
                                                 live_objc_path, live_macho_path))
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
        builds.append({"build": build, "version": "26.0.1",
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
                       **service_info})

    if not builds:
        raise ValueError("no complete catalogs found")
    research = json.loads((ROOT / "research" / "index.json").read_text(encoding="utf-8"))
    known_builds = {item["build"] for item in builds}
    if len({note["id"] for note in research}) != len(research):
        raise ValueError("duplicate research note id")
    for note in research:
        source = (ROOT / note["note"]).resolve()
        if (note["build"] not in known_builds or ROOT / "research" not in source.parents or
                not source.is_file()):
            raise ValueError(f"invalid research note source: {note['note']}")
        note["rendered_html"] = render_note(source.read_text(encoding="utf-8"), note["note"])
    dump(DIST / "data" / "manifest.json",
         {"schema_version": 1, "builds": builds, "research": research})
    digest = hashlib.sha256()
    for path in sorted(DIST.rglob("*")):
        if path.is_file() and path.name != "index.html":
            digest.update(str(path.relative_to(DIST)).encode())
            digest.update(path.read_bytes())
    version = digest.hexdigest()[:12]
    index = (DIST / "index.html").read_text(encoding="utf-8")
    index = index.replace('href="styles.css"', f'href="styles.css?v={version}"')
    index = index.replace('href="tree.css"', f'href="tree.css?v={version}"')
    index = index.replace('href="observation.css"', f'href="observation.css?v={version}"')
    index = index.replace('src="app.js"', f'src="app.js?v={version}"')
    (DIST / "index.html").write_text(index, encoding="utf-8")
    print(f"built {DIST} with {len(builds)} build(s)")


if __name__ == "__main__":
    build()
