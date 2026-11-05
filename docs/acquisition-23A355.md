# Acquisition: iPhone12,1 / 23A355

Collected 2026-11-04 from the Apple restore IPSW for iPhone 11, iOS 26.0.1. `ipsw` version: `3.1.739`. Firmware SHA-256: `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`. `unzip -tq` reported no errors. The firmware and extracted binaries remain local, outside Git.

| Source image | Catalog | Entries | Scan errors |
| --- | --- | ---: | ---: |
| FileSystem (`043-93104-010.dmg.aea`) | [`filesystem.json.gz`](../catalog/ios/23A355/filesystem.json.gz) | 447,917 | 0 |
| SystemOS (`043-93547-010.dmg.aea`) | [`systemos.json`](../catalog/ios/23A355/systemos.json) | 2,930 | 0 |
| AppOS (`043-93709-010.dmg`) | [`appos.json`](../catalog/ios/23A355/appos.json) | 1,249 | 0 |
| SystemOS arm64e cache family | [`dyld.json`](../catalog/ios/23A355/dyld.json) | 80 physical files; 4,170 images | 0 |
| SystemOS DriverKit cache | [`driverkit-dyld.json`](../catalog/ios/23A355/driverkit-dyld.json) | 3 physical files; 51 images | 0 |
| Erase RestoreRamDisk (`043-93777-010.dmg`) | [`rdisk-erase.json.gz`](../catalog/ios/23A355/rdisk-erase.json.gz) | 1,911 | 0 |
| Upgrade RestoreRamDisk (`043-92637-010.dmg`) | [`rdisk-upgrade.json.gz`](../catalog/ios/23A355/rdisk-upgrade.json.gz) | 2,221 | 0 |
| IPSW ZIP archive | [`firmware-archive.json`](../catalog/ios/23A355/firmware-archive.json) | 127 entries, 110 files | 0 |
| Release and research kernelcaches | [`kernel.json`](../catalog/ios/23A355/kernel.json) | 2 Mach-O filesets, 256 kext records each | 0 |
| FileSystem launchd plists | [`launchd.json`](../catalog/ios/23A355/launchd.json) | 621 plists, 620 jobs, 2,186 Mach service declarations | 0 |
| Launchd executable Mach-O loads | [`service-macho.json`](../catalog/ios/23A355/service-macho.json) | 600 unique executables, 14,843 direct loads | 0 |
| iOS cache image Mach-O loads | [`dyld-dependencies.json`](../catalog/ios/23A355/dyld-dependencies.json) | 4,170 images, 90,837 direct loads | 0 |

Main iOS cache UUID: `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`. DriverKit cache UUID: `5CC15334-F5B0-3971-93BB-4FDDCE6F4BE7`. Cache files and all 110 archive files have size and SHA-256 metadata. Filesystem records include path, type, mode, regular-file size and symlink target. They do not include per-file content hashes. Mount-generated `/.fseventsd` paths were excluded. The scan neither follows symlinks nor descends into nested volumes. Each catalog's `complete` and `errors` fields describe its own scan, not all firmware partitions or runtime paths.

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
ipsw dyld info --dylibs --json .local/mount-sys/System/DriverKit/System/Library/dyld/dyld_shared_cache_arm64e > .local/cache/driverkit-info.json
python3 tools/catalog_ipsw.py --ipsw .local/firmware/iPhone12,1_26.0.1_23A355_Restore.ipsw --product iPhone12,1 --build 23A355 --firmware-sha256 2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2 --output catalog/ios/23A355/firmware-archive.json
ipsw mount rdisk .local/firmware/iPhone12,1_26.0.1_23A355_Restore.ipsw --ident Erase --mount-point .local/mount-rdisk-erase --detach
ipsw mount rdisk .local/firmware/iPhone12,1_26.0.1_23A355_Restore.ipsw --ident Upgrade --mount-point .local/mount-rdisk-upgrade --detach
python3 tools/build_catalog.py fs --product iPhone12,1 --build 23A355 --firmware-sha256 2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2 --root .local/mount-rdisk-erase --volume RestoreRamDiskErase --image-name 043-93777-010.dmg --exclude /.fseventsd --output catalog/ios/23A355/rdisk-erase.json.gz
python3 tools/build_catalog.py fs --product iPhone12,1 --build 23A355 --firmware-sha256 2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2 --root .local/mount-rdisk-upgrade --volume RestoreRamDiskUpgrade --image-name 043-92637-010.dmg --exclude /.fseventsd --output catalog/ios/23A355/rdisk-upgrade.json.gz
mkdir -p .local/kernel/release.decompressed .local/kernel/research.decompressed
unzip -p .local/firmware/iPhone12,1_26.0.1_23A355_Restore.ipsw kernelcache.release.iphone12b > .local/kernel/kernelcache.release.iphone12b
unzip -p .local/firmware/iPhone12,1_26.0.1_23A355_Restore.ipsw kernelcache.research.iphone12b > .local/kernel/kernelcache.research.iphone12b
ipsw kernel dec .local/kernel/kernelcache.release.iphone12b --output .local/kernel/release.decompressed/kernelcache.release.iphone12b.decompressed
ipsw kernel dec .local/kernel/kernelcache.research.iphone12b --output .local/kernel/research.decompressed/kernelcache.research.iphone12b.decompressed
python3 tools/catalog_kernel.py --archive-catalog catalog/ios/23A355/firmware-archive.json --release .local/kernel/release.decompressed/kernelcache.release.iphone12b.decompressed --research .local/kernel/research.decompressed/kernelcache.research.iphone12b.decompressed --output catalog/ios/23A355/kernel.json
python3 tools/catalog_launchd.py --root .local/mount-fs --filesystem-catalog catalog/ios/23A355/filesystem.json.gz --systemos-catalog catalog/ios/23A355/systemos.json --appos-catalog catalog/ios/23A355/appos.json --output catalog/ios/23A355/launchd.json
python3 tools/catalog_service_macho.py --launchd-catalog catalog/ios/23A355/launchd.json --dyld-catalog catalog/ios/23A355/dyld.json --driverkit-catalog catalog/ios/23A355/driverkit-dyld.json --filesystem-catalog catalog/ios/23A355/filesystem.json.gz --systemos-catalog catalog/ios/23A355/systemos.json --appos-catalog catalog/ios/23A355/appos.json --filesystem-root .local/mount-fs --systemos-root .local/mount-sys --appos-root .local/mount-app --output catalog/ios/23A355/service-macho.json
python3 tools/catalog_dyld_dependencies.py --cache-catalog catalog/ios/23A355/dyld.json --cache .local/cache/23A355__iPhone12,1/dyld_shared_cache_arm64e --checkpoint .local/dyld-deps-progress.jsonl --output catalog/ios/23A355/dyld-dependencies.json --workers 4
```

Run `python3 tools/build_catalog.py fs --help` and `python3 tools/build_catalog.py dyld --help` for catalog arguments. Pass the exact firmware hash, mounted root, volume/image name, and the complete extracted cache directory as appropriate. Use `--platform Driverkit` and the mounted DriverKit dyld directory for its separate catalog. Then run `python3 tools/build_site.py`.

## Interpretation and limits

A dyld image's install name is a logical path; its executable may be inside the cache without a separate regular file at that path. The [Foundation example](../research/23A355/Foundation.md) shows this directly. This dataset covers all 127 IPSW archive members, mounted contents of all five disk images, the iOS and DriverKit cache families, and both kernelcache variants. Other firmware payloads have hashes and BuildManifest roles but have not been decompiled. Runtime-generated data remains outside this official-distribution catalog.

All 621 launchd plists in the scanned FileSystem image parsed successfully. Their executable declarations resolve directly to a path in the three installed-system image catalogs for 604 plists; nine more map through the explicit AppOS/SystemOS cryptex prefixes; seven have no matching path in those scans; one jetsam configuration has no executable declaration. “Unresolved” is a bounded catalog result, not proof that an executable never exists on a running device. Five labels occur in two variant plists, so service records are keyed by plist path rather than label. See the [SpringBoard chain](../research/23A355/SpringBoard.md) for a worked example.

The 613 resolved launchd plist records point to 600 distinct executable files. All 600 parse as Mach-O executables: 599 arm64e and one arm64. Their load commands declare 14,843 direct dylib imports, of which 14,777 have an exact install-name match in the indexed iOS cache, four match separate regular files in the three scanned installed-system images, and 62 match neither indexed source. Of those 62, 61 are weak loads; the one required load is `FusionPluginKit` from `fusiond`. These are **direct static declarations only**: no transitive dependency closure, `@rpath` expansion, load-time condition, or runtime loading is claimed. An unmatched name is not evidence that a running device cannot resolve it.

Every image in the intact iOS arm64e cache parsed as a Mach-O with the UUID listed in the cache inventory (4,169 dylibs and one dynamic linker image). Their load commands declare **90,837 direct dylib loads**: 64,687 ordinary, 25,772 weak, 171 upward, and 207 re-export. An exact install-name match exists for 90,806 loads within this cache family. The other 31 loads use 20 distinct names, and all 31 are weak. The website shows both outgoing declarations and reverse direct importers; it does not imply that these loads resolved or that any process executed a library. The collector stores a resumable checkpoint outside Git and verifies each image UUID against the original cache inventory. A second run from the complete checkpoint produced byte-identical output.

A trusted device with matching product and build was observed over read-only root SSH through USB. Its RootHide view uses `/rootfs` for the base system while `/` is a jailbreak-specific namespace. The main live cache is under `/private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld/`. All **80** files in that live arm64e cache family matched the corresponding extracted IPSW files by SHA-256; there were no extra or missing files in that family. The live `/rootfs` volume walk counted 430,745 paths including its root, but that namespace is not directly comparable to the three IPSW image catalogs. The separate DriverKit cache also matched the device for all three files by SHA-256; it is outside the 80-file iOS cache count. This live observation is not a clean pre-jailbreak snapshot; IPSW-versus-device differences alone cannot establish jailbreak causation. No private device identifiers are published.

The [filtered device catalog](../catalog/ios/23A355/device-rootfs.json.gz) contains **430,719** paths and types from `/rootfs/Applications`, `/rootfs/Library`, `/rootfs/System`, `/rootfs/bin`, `/rootfs/sbin`, `/rootfs/usr`, and `/rootfs/private/etc`. It excludes `/private/var`, preboot, `dev`, all other roots, and the jailbreak namespace. Every published device path and type was checked against the official IPSW catalogs and matched a record there; the site build refuses to publish any unmatched device entry. This is a path/type check, not a content hash check. The device catalog is a live, filtered observation and does not represent every file on the phone.

The collector is `tools/collect_device.py`. It requires an existing trusted SSH key and pinned known-hosts file; it never stores those paths or device identifiers in the output. For a USB tunnel to port 22326, invoke it with `--port 22326 --identity <KEY> --known-hosts <KNOWN_HOSTS> --product iPhone12,1 --build 23A355 --output .local/device-rootfs.json.gz`, review the local result, then copy it into `catalog/ios/23A355/` only after the official-path validation succeeds.
