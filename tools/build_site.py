#!/usr/bin/env python3
"""Build the static GitHub Pages explorer from validated public catalogs."""

from __future__ import annotations

import gzip
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
        builds.append({"build": build, "version": "26.0.1",
                       "product_type": dyld["product_type"],
                       "firmware_sha256": dyld["firmware_sha256"],
                       "cache_uuid": dyld["cache_uuid"],
                       "image_count": len(images),
                       "cache_file_count": len(dyld["files"]),
                       "file_count": len(compact_entries),
                       "volumes": volume_metadata,
                       "files_url": f"data/{build}-files.json.gz",
                       "dyld_url": f"data/{build}-dyld.json", **device_info, **driverkit_info})

    if not builds:
        raise ValueError("no complete catalogs found")
    research = json.loads((ROOT / "research" / "index.json").read_text(encoding="utf-8"))
    dump(DIST / "data" / "manifest.json",
         {"schema_version": 1, "builds": builds, "research": research})
    print(f"built {DIST} with {len(builds)} build(s)")


if __name__ == "__main__":
    build()
