# Acquisition: iPhone12,1 / 23A355

Collected 2026-11-04 from the Apple restore IPSW for iPhone 11, iOS 26.0.1. `ipsw` version: `3.1.739`. Firmware SHA-256: `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`. `unzip -tq` reported no errors. The firmware and extracted binaries remain local, outside Git.

| Source image | Catalog | Entries | Scan errors |
| --- | --- | ---: | ---: |
| FileSystem (`043-93104-010.dmg.aea`) | [`filesystem.json.gz`](../catalog/ios/23A355/filesystem.json.gz) | 447,917 | 0 |
| SystemOS (`043-93547-010.dmg.aea`) | [`systemos.json`](../catalog/ios/23A355/systemos.json) | 2,930 | 0 |
| AppOS (`043-93709-010.dmg`) | [`appos.json`](../catalog/ios/23A355/appos.json) | 1,249 | 0 |
| SystemOS arm64e cache family | [`dyld.json`](../catalog/ios/23A355/dyld.json) | 80 physical files; 4,170 images | 0 |

Main cache UUID: `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`. Cache files have size and SHA-256 metadata. Filesystem records include path, type, mode, regular-file size and symlink target. They do not include per-file content hashes. Mount-generated `/.fseventsd` paths were excluded. The scan neither follows symlinks nor descends into nested volumes. Each catalog's `complete` and `errors` fields describe its own scan, not all firmware partitions or runtime paths.

## Reproduce

```sh
ipsw download ipsw --device iPhone12,1 --build 23A355 --confirm --output .local/firmware
shasum -a 256 .local/firmware/iPhone12,1_26.0.1_23A355_Restore.ipsw
unzip -tq .local/firmware/iPhone12,1_26.0.1_23A355_Restore.ipsw
ipsw mount fs .local/firmware/iPhone12,1_26.0.1_23A355_Restore.ipsw --mount-point .local/mount-fs --detach
ipsw mount sys .local/firmware/iPhone12,1_26.0.1_23A355_Restore.ipsw --mount-point .local/mount-sys --detach
ipsw mount app .local/firmware/iPhone12,1_26.0.1_23A355_Restore.ipsw --mount-point .local/mount-app --detach
ipsw extract .local/firmware/iPhone12,1_26.0.1_23A355_Restore.ipsw --dyld --dyld-arch arm64e --device iPhone12,1 --output .local/cache --json --json-format artifacts
ipsw dyld info --dylibs --json .local/cache/23A355__iPhone12,1/dyld_shared_cache_arm64e > .local/cache/dyld-info.json
```

Run `python3 tools/build_catalog.py fs --help` and `python3 tools/build_catalog.py dyld --help` for catalog arguments. Pass the exact firmware hash, mounted root, volume/image name, and the complete extracted cache directory as appropriate. Then run `python3 tools/build_site.py`.

## Interpretation and limits

A dyld image's install name is a logical path; its executable may be inside the cache without a separate regular file at that path. The [Foundation example](../research/23A355/Foundation.md) shows this directly. This dataset covers three mounted images and the SystemOS arm64e cache family. DriverKit's separate cache, kernelcache, other firmware components and runtime-generated data are outside this first catalog.

A trusted device with matching product and build was observed over read-only root SSH through USB. Its RootHide view uses `/rootfs` for the base system while `/` is a jailbreak-specific namespace. The main live cache is under `/private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld/`. All **80** files in that live arm64e cache family matched the corresponding extracted IPSW files by SHA-256; there were no extra or missing files in that family. The live `/rootfs` volume walk counted 430,745 paths including its root, but that namespace is not directly comparable to the three IPSW image catalogs. A separate DriverKit cache exists and is outside this count. This live observation is not a clean pre-jailbreak snapshot; IPSW-versus-device differences alone cannot establish jailbreak causation. No private device identifiers are published.

The [filtered device catalog](../catalog/ios/23A355/device-rootfs.json.gz) contains **430,719** paths and types from `/rootfs/Applications`, `/rootfs/Library`, `/rootfs/System`, `/rootfs/bin`, `/rootfs/sbin`, `/rootfs/usr`, and `/rootfs/private/etc`. It excludes `/private/var`, preboot, `dev`, all other roots, and the jailbreak namespace. Every published device path and type was checked against the official IPSW catalogs and matched a record there; the site build refuses to publish any unmatched device entry. This is a path/type check, not a content hash check. The device catalog is a live, filtered observation and does not represent every file on the phone.

The collector is `tools/collect_device.py`. It requires an existing trusted SSH key and pinned known-hosts file; it never stores those paths or device identifiers in the output. For a USB tunnel to port 22326, invoke it with `--port 22326 --identity <KEY> --known-hosts <KNOWN_HOSTS> --product iPhone12,1 --build 23A355 --output .local/device-rootfs.json.gz`, review the local result, then copy it into `catalog/ios/23A355/` only after the official-path validation succeeds.
