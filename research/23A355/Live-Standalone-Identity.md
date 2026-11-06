# Which IPSW Mach-O files match this iPhone byte for byte?

## Scope and method

On 2026-11-05, the connected iPhone 11 identified itself as `iPhone12,1` on iOS 26.0.1 build `23A355`. A pinned USB SSH session authenticated the exact phone as root. The private live snapshot had complete scans of `/rootfs` and `/rootfs/private/preboot`; the [collection procedure](../../docs/live-device-collection.md) records their scope. The official firmware's [standalone Mach-O inventory](Standalone-MachO-Coverage.md) contains 3,363 physical files across FileSystem, SystemOS, and AppOS.

Each official path was mapped to a physical path in the RootHide view: FileSystem under `/rootfs`, SystemOS under `/rootfs/private/preboot/Cryptexes/OS`, and AppOS under `/rootfs/private/preboot/Cryptexes/App`. Only records with a regular file of the same size in the relevant complete snapshot were sent to the phone for a read-only, NUL-delimited `sha256sum -z` pass. The [verifier](../../tools/verify_live_standalone.py) checks the device product and build again immediately before hashing, and records an explicit status for every firmware file.

## Result

**3,157 of 3,363** official standalone Mach-O files were present at those mapped physical paths, and **all 3,157 device SHA-256 hashes equaled the corresponding complete-file IPSW hashes**. This comprises 3,117 FileSystem files, 25 SystemOS files, and 15 AppOS files. The hash command returned successfully with no missing hash records. Their existing Objective-C, symbol, and Swift metadata pages can therefore identify the exact bytes observed on this phone at the recorded time.

The website exposes the 3,157 verified identities through a public index. All 3,117 matched FileSystem binaries have a reviewed live-device path and a link from that path to the exact firmware Mach-O page. The 40 matched cryptex binaries have an identity status on their firmware pages, but no physical preboot path is emitted into the site index. The builder checks every original firmware hash, device hash, size, mapped path, and snapshot identity before publishing these links. The 206 staging-path results remain in this research record; the website does not present them as a device comparison or absence claim. A match remains a time-bounded byte observation, not proof of runtime loading.

The remaining **206** official records all have paths beneath `/private/var/staged_system_apps` in the FileSystem image. No regular files were observed at those same mapped staging paths in the snapshot. This is a **path-location result**, not evidence that those apps or their executables are absent from the phone; installation may place them elsewhere. No firmware metadata is labeled device-verified for these 206 records.

## Limits and next work

- The device was mutable during the scan and hash pass. The catalog records both observation times; it is not an atomic filesystem snapshot.
- Matching SHA-256 proves identity of each measured file at that moment. It does not prove execution, process ownership, or safe tweak targets.
- This pass starts from the firmware Mach-O inventory. It does not discover every additional base-system binary or binaries inside private data-volume locations.
- Direct dyld shared-cache files were verified separately; in-cache logical images remain distinct from these standalone files.

Next, identify any code-bearing live base-system files absent from the firmware inventory, reconcile the installed locations of staged system apps without publishing private app data, and add source-backed purpose notes. The [research TODO](../../docs/research-todo.md) tracks the remaining scope.
