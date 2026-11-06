# What does the stock versus device path comparison show?

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`). The stock source is the official IPSW with SHA-256 `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`. The device source is a read-only, filtered observation of the RootHide `/rootfs` namespace, not a pre-jailbreak snapshot.

## Exact comparison

The device collector scanned `/Applications`, `/Library`, `/System`, `/bin`, `/sbin`, `/usr`, and `/private/etc` under `/rootfs`. Within those same path prefixes, the three mounted stock images contain **434,852 distinct path-and-type pairs**. The filtered device index contains **430,719 pairs**, all with an exact stock match. The remaining **4,133 stock pairs** did not appear at the same path and type in that device scan.

- FileSystem: 430,719 stock pairs in scope; all 430,719 have the same path and type in the device index.
- SystemOS: 2,930 stock pairs in scope; 26 have a same-path device match and 2,904 do not.
- AppOS: 1,249 stock pairs in scope; 20 have a same-path device match and 1,229 do not.

These volume counts are **not additive** because an IPSW path can occur in more than one image. Of the 4,133 distinct stock-only pairs, 4,111 are under `/System` and 22 are under `/usr`. The site lists each with its stock volume. No device-only path is published: the site build explicitly rejects any device path/type absent from the official stock indexes. That gate is a privacy and provenance rule, not independent proof that the live device has no additions.

## Interpretation

The FileSystem result gives strong evidence that the selected `/rootfs` path names and types agree with the official FileSystem distribution image. It does **not** compare file bytes: the current file index has no per-file content hashes. A matching path is not a matching binary.

SystemOS and AppOS are separate IPSW filesystem images. Their logical paths may be presented through cryptex mounts or other live namespace mappings, so a stock path absent from this filtered `/rootfs` scan is **not** evidence that the file is absent from the phone. The previously verified live iOS dyld cache resides under `/private/preboot/Cryptexes/OS/`; its 80 files and the three DriverKit cache files matched the IPSW cache family by SHA-256. Cache bytes and logical in-cache image names are separate from ordinary filesystem paths.

The phone already had historical jailbreak state. Without a clean pre-jailbreak snapshot from the **same device and build**, this comparison cannot attribute an addition, removal, or changed file to Relaxin. The device scan also excludes private user data, generated data, preboot paths, and the jailbreak namespace. This is a bounded system-path comparison, not a whole-device file list.

## Reproduce and inspect

The inputs were the [FileSystem](../../catalog/ios/23A355/filesystem.json.gz), [SystemOS](../../catalog/ios/23A355/systemos.json), [AppOS](../../catalog/ios/23A355/appos.json), and [filtered device](../../catalog/ios/23A355/device-rootfs.json.gz) indexes. This historical note records a bounded `(path, type)` check across seven root prefixes. The website now opens on the live device inventory and has no stock-versus-device comparison view. The [acquisition record](../../docs/acquisition-23A355.md) explains how each source was collected and what it excludes.
