#!/usr/bin/env python3
"""Build the static GitHub Pages explorer from validated public catalogs."""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "ios"
SITE = ROOT / "site"
DIST = ROOT / "dist"


def load(path: Path) -> dict:
    if path.suffix == ".gz":
        return json.loads(gzip.decompress(path.read_bytes()))
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, value: object, compressed: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode() + b"\n"
    path.write_bytes(gzip.compress(content, mtime=0) if compressed else content)


def build() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    for name in ("index.html", "app.js", "styles.css"):
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
        dump(DIST / "data" / f"{build}-files.json.gz",
             {"schema_version": 1, "build": build, "volumes": volume_metadata,
              "entries": compact_entries}, compressed=True)
        dump(DIST / "data" / f"{build}-dyld.json",
             {"schema_version": 1, "build": build, "cache_uuid": dyld["cache_uuid"],
              "files": dyld["files"], "images": images})
        driverkit_info = {}
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
            dump(DIST / "data" / f"{build}-driverkit.json",
                 {"schema_version": 1, "build": build, "cache_uuid": driverkit["cache_uuid"],
                  "files": driverkit["files"], "images": driverkit_images})
            driverkit_info = {"driverkit_image_count": len(driverkit_images),
                              "driverkit_cache_file_count": len(driverkit["files"]),
                              "driverkit_url": f"data/{build}-driverkit.json"}
        device_info = {}
        device_path = directory / "device-rootfs.json.gz"
        if device_path.exists():
            device = load(device_path)
            if (not device["complete"] or device["build"] != build or
                    device["product_type"] != dyld["product_type"] or
                    device["kind"] != "device_system_path_observation" or
                    device["entry_count"] != len(device["entries"])):
                raise ValueError(f"incomplete or mismatched device catalog in {directory}")
            if any(path not in stock_types or kind not in stock_types[path]
                   for path, kind in device["entries"]):
                raise ValueError("device catalog contains paths or types absent from official IPSW; review before publishing")
            shutil.copy2(device_path, DIST / "data" / f"{build}-device.json.gz")
            device_info = {"device_count": device["entry_count"],
                           "device_url": f"data/{build}-device.json.gz",
                           "device_observed_at_utc": device["observed_at_utc"]}
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
                       "dyld_url": f"data/{build}-dyld.json", **device_info,
                       **driverkit_info, **archive_info, **restore_info, **kernel_info,
                       **service_info})

    if not builds:
        raise ValueError("no complete catalogs found")
    research = json.loads((ROOT / "research" / "index.json").read_text(encoding="utf-8"))
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
    index = index.replace('src="app.js"', f'src="app.js?v={version}"')
    (DIST / "index.html").write_text(index, encoding="utf-8")
    print(f"built {DIST} with {len(builds)} build(s)")


if __name__ == "__main__":
    build()
