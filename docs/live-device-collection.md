# Live device collection and publication

Target: the currently connected `iPhone12,1` on iOS `23A355`. This workflow is read-only on the phone. The initial filesystem collector scans metadata and symlink targets; later file-type and binary-identity passes read file bytes. Raw results contain private paths and remain under ignored `.local`.

## Preconditions

The USB device must report the exact product/build above, and an existing pinned root SSH connection must work. On 2026-11-05, the device-specific SSH profile saved by the adjacent CopyApp checkout authenticated both `mobile` and `root` for this exact phone; the Mac's default SSH key did not. iCTRL can confirm the device and operate Relaxin's UI, but its API has no filesystem or shell method. The ordinary AFC service is limited to `/var/mobile/Media`; this phone did not expose AFC2 when checked. Do not infer root access from pairing or from a running `jailbreakd` process.

The collector validates the device identity and mount-table digest before continuing an earlier snapshot. If either changes, use a new `.local` output directory. The local USB tunnel and SSH credential paths are operator inputs; they do not enter the snapshot JSON. Example with an already working pinned key:

```sh
ipsw idev proxy -l 22326 -r 22
python3 tools/collect_live_device.py --host root@127.0.0.1 --port 22326 --identity <DEVICE_KEY> --known-hosts <PINNED_HOST_KEYS> --product iPhone12,1 --build 23A355 --output-dir .local/live-device --discover-only
```

Review `.local/live-device/manifest.json` and `.local/live-device/mount.txt` privately. Relaxin's RootHide SSH namespace exposes the base system under `/rootfs`, while the kernel mount table names the base system paths without that prefix. The collector maps each mount target to `/rootfs/<target>`, includes `/` separately for the jailbreak view, and requires the GNU `find`/`stat` tools shipped on this phone. Run a pilot with an explicit mapped root before the full scan:

```sh
python3 tools/collect_live_device.py --host root@127.0.0.1 --port 22326 --identity <DEVICE_KEY> --known-hosts <PINNED_HOST_KEYS> --product iPhone12,1 --build 23A355 --output-dir .local/live-device --only-root /rootfs/System/Developer
python3 tools/collect_live_device.py --host root@127.0.0.1 --port 22326 --identity <DEVICE_KEY> --known-hosts <PINNED_HOST_KEYS> --product iPhone12,1 --build 23A355 --output-dir .local/live-device
```

The full pass enumerates each discovered mount independently with `find -xdev`; symlinks are not followed. Files named with newlines are preserved through a NUL-delimited protocol. Each root gets a compressed JSONL file, count, SHA-256, and `complete`/`partial` status. A partial root is retried on the next run. On 2026-11-05, 10 of 12 roots completed. `/rootfs/private/var` reported 16 protected-directory errors, and `/rootfs/private/var/mobile` reported 57; their reachable entries remain private. All 73 errors were `Operation not permitted`. A private review found 73 distinct blocked directory paths with no overlap between these two views; all are outside the reviewed public path allowlist. Their descendant counts remain unknown. Local stderr files include private paths and must not be published. Duplicate namespace views remain distinct until a reviewed mapping exists. Because the phone can change during collection, the result is a time-bounded observation, not an atomic filesystem snapshot.

The separate mount-coverage export replaces every private source path with a fixed reviewed label and retains only scan status, path-observation count, reachable regular-file count, and access-error count. It checks the private manifest and scan-file hashes against the public device catalog before producing a candidate:

```sh
python3 tools/export_live_coverage.py \
  --manifest .local/live-device-23A355/manifest.json \
  --device-catalog catalog/ios/23A355/device-live.json.gz \
  --output .local/live-device-23A355/live-coverage-candidate.json
```

Review the labels and totals before copying the candidate to `catalog/ios/23A355/live-coverage.json`. The site builder accepts only the fixed labels and numeric fields, checks 12 roots against the public device catalog, and rejects raw path fields. The current export has 531,311 path observations and 284,150 reachable regular-file records across independently scanned roots. Nested views may overlap, and descendants of the 73 protected directories remain uncounted. These totals are not the 439,365 deduplicated public path records.

## Public export

Create a **private** `.local/live-device/allowlist.json` after reviewing actual mounts and paths. Its schema is `{"schema_version":1,"prefixes":["/rootfs/System"]}`. The exporter accepts only hardcoded system and jailbreak prefix families; broad `/`, `/private`, and `/var/mobile` exports are rejected. Add the actual jailbreak prefix only after inspecting it. The export strips UID/GID, inode, mount source, symlink target, and all path records outside the allowlist.

```sh
python3 tools/export_live_device.py --manifest .local/live-device/manifest.json --allowlist .local/live-device/allowlist.json --output .local/live-device/public-candidate.json.gz
```

Review the candidate's paths and counts, then copy only that reviewed file to `catalog/ios/23A355/device-live.json.gz`. `tools/build_site.py` independently revalidates every public path against the reviewed prefixes before copying it into `dist`. The website labels published scope and the number of completed snapshot roots; it must never imply that unpublished user/app paths are absent from the device.

Tests: `python3 tools/test_live_device_pipeline.py` checks NUL-safe filenames, exact symlink targets, rejection of private prefixes, and the site builder's second privacy gate.

## First live code pass

The separately mounted `/rootfs/System/Developer` tree contains 117 regular files that are absent from the official FileSystem image's path inventory. A device-side `file -0 -0` pass identified 42 Mach-O files. Their exact live bytes were acquired privately, and each local copy matched a device-side SHA-256 result. All 42 files have arm64 and arm64e slices, giving 84 parsed Mach-O headers with architecture, file type, and UUID. The public catalog contains only derived metadata and reviewed system paths; it does not contain the binaries. Generate the catalog with:

```sh
python3 tools/catalog_live_developer_macho.py \
  --manifest .local/live-device/manifest.json \
  --file-types .local/live-device/developer-file-types.nul \
  --hashes .local/live-device/developer-macho-sha256.nul \
  --binary-root .local/live-device/developer-macho-files \
  --output .local/live-device/developer-macho-candidate.json.gz
```

The private snapshot also shows 219,216 regular files under the base `/rootfs` mount, each with a same-path record in the official FileSystem image. All 2,091 OS and 1,099 App cryptex regular files likewise have same-path records in their respective official images. Same-path presence alone is not a byte match. Another 67 regular files in preboot lie outside the two mounted cryptex trees; these are firmware payloads, tickets, and mount metadata in device-specific paths and are not published as live Mach-O library records.

The site's **Verified code by mount** table separates path scanning from byte-verified Mach-O work. All 6,449 reachable jailbreak regular files and all 117 Developer regular files were classified by `file`; 464 and 42, respectively, were identified as Mach-O and verified on the phone. The public jailbreak catalog omits one randomized filename, leaving 463 browseable records. A separate exact-build hash pass verified 3,117 base-root and 40 cryptex standalone Mach-O files. A later read-only `file-5.43` pass classified all 219,216 reachable base-root regular files against the same private path snapshot: the 3,117 standard Mach-O files were already matched, and one mixed QuartzCore Metal container was independently hash-verified against the device and official FileSystem. The [base-root note](../research/23A355/Base-Root-Code-Coverage.md) records the exact evidence. Another `file-5.43` pass classified all 3,257 reachable Preboot regular files: the 40 standard Mach-O files were already matched, and its corresponding mixed Metal container matched official SystemOS. The [Preboot note](../research/23A355/Preboot-Metal-Container.md) keeps that physical path private. Three smaller completed mounts had exact path-set type passes and zero ordinary Mach-O candidates; see the [small-mount note](../research/23A355/Peripheral-Mount-Type-Coverage.md). A later Software Update snapshot and type pass reconciled all 2,080 reachable regular files and found exactly two ordinary Mach-O candidates. Both were rechecked by device SHA-256 and received a first static pass. The earlier published mount summary still records 2,055 files at its own observation time; see the [UpdateBrain note](../research/23A355/UpdateBrain-Live-Code.md). Other mounts have no complete code-classification pass; two data-volume scans also have inaccessible descendants. The mount views can overlap, and these counts are not a unique whole-device binary total.

The first static analysis pass over all 84 Developer Mach-O slices reads `LC_LOAD_*` and `LC_RPATH` declarations from the acquired, hash-verified bytes. It found 1,778 direct library loads and 158 public runpath declarations. The catalog preserves weak loads and architecture-specific duplication; it does not resolve `@rpath` against a running process or prove that any file was loaded. Generate the private aggregate before review and publication with:

```sh
python3 tools/catalog_live_developer_dependencies.py \
  --macho-catalog catalog/ios/23A355/developer-macho.json.gz \
  --binary-root .local/live-device/developer-macho-files \
  --workdir .local/live-device/developer-dependency-work \
  --output .local/live-device/developer-dependencies-candidate.json.gz
```

The first Objective-C pass selects the **arm64e** slice of each of the 42 verified Developer binaries. It parsed 7,735 method entries across 40 files; one file explicitly reported no ObjC info. `XCTest.framework/XCTest` returned a class-dump error with partial output for both arm64e and arm64, so its method count is **unknown**, and its partial output is not published. The catalog preserves this as one `failed` record rather than an inspected zero. Reproduce the private pass with:

```sh
python3 tools/catalog_live_developer_objc.py \
  --macho-catalog catalog/ios/23A355/developer-macho.json.gz \
  --binary-root .local/live-device/developer-macho-files \
  --workdir .local/live-device/developer-objc-work \
  --output .local/live-device/developer-objc-candidate.json.gz
```

A separate named-symbol pass checked all 84 slices against the acquired file hashes and Mach-O UUIDs. It found 78,771 named records inside executable `__text` sections; three files (six slices) yielded no names. The public builder checks every symbol address against its code section and rejects private path and contact patterns before publishing searchable per-file buckets. Names overlap Objective-C methods and do not enumerate every callable function. Reproduce the private pass with:

```sh
python3 tools/catalog_live_developer_symbols.py \
  --macho-catalog catalog/ios/23A355/developer-macho.json.gz \
  --binary-root .local/live-device/developer-macho-files \
  --workdir .local/live-device/developer-symbol-work \
  --output .local/live-device/developer-symbols-candidate.json.gz
```

Swift dumps from the same 84 verified slices yielded 17,230 declarations and 2,568 member or requirement lines. Twelve slices reported no Swift info, and ten have partial parses with 126 malformed lines withheld. Nine files have no parsed declarations. The builder keeps those statuses and checks public names and counts before publishing searchable per-file results:

```sh
python3 tools/catalog_live_developer_swift.py \
  --macho-catalog catalog/ios/23A355/developer-macho.json.gz \
  --binary-root .local/live-device/developer-macho-files \
  --workdir .local/live-device/developer-swift-work \
  --output .local/live-device/developer-swift-candidate.json.gz
```

All 84 Developer slices contain a CodeDirectory and report an ad hoc signing state in `codesign`; 32 slices have parsed entitlement plists and 52 have none. The published summary retains counts and identifiers but removes raw command output and entitlement values. These are embedded metadata observations, not proof of trust or runtime acceptance:

```sh
python3 tools/catalog_live_developer_signatures.py \
  --macho-catalog catalog/ios/23A355/developer-macho.json.gz \
  --binary-root .local/live-device/developer-macho-files \
  --workdir .local/live-device/developer-signature-work \
  --output .local/live-device/developer-signatures-candidate.json.gz
```

The complete jailbreak-root scan found 6,449 regular files. A device-side GNU `file -0 -0` pass identified 464 Mach-O candidates. A separate `sha256sum -z` pass hashed those exact paths. A private tar transfer acquired those files; every local copy matched its device-side hash. The reproducible header catalog is generated with:

```sh
python3 tools/catalog_live_jailbreak_macho.py \
  --manifest .local/live-device/manifest.json \
  --file-types .local/live-device/jailbreak-file-types.nul \
  --hashes .local/live-device/jailbreak-macho-sha256.nul \
  --binary-root .local/live-device/macho-files \
  --output .local/live-device/jailbreak-macho-candidate.json.gz
```

The private file-type, hash, and acquired-byte inputs are excluded from Git. All 464 acquired files were verified; the public catalog includes 463 reviewed jailbreak paths and their derived Mach-O metadata. One filename with a device-specific RootHide random suffix is withheld. `tools/build_site.py` checks that each published path and size also appears as a public live-device file. A header or UUID is identity evidence, not a method list or proof of runtime loading.

The read-only method pass uses `ipsw class-dump --re -V` on each of the 463 published files, with `--arch` selected for universal binaries. It checkpoints against the acquired file hash and checks method IMPs against Mach-O code ranges:

```sh
python3 tools/catalog_live_jailbreak_objc.py \
  --macho-catalog catalog/ios/23A355/jailbreak-macho.json.gz \
  --binary-root .local/live-device/macho-files \
  --workdir .local/live-device/objc-work \
  --output .local/live-device/jailbreak-objc-candidate.json.gz
```

The result covers all 463 published files: 61 have 4,781 parsed Objective-C method entries, while 402 explicitly report no ObjC information. Empty ObjC output is not evidence that a file has no code or callable functions.

A separate read-only `ipsw macho info --json --loads` pass inspects every architecture slice of the same verified files. Repeated architecture labels in one fat file are extracted to private temporary thin files so each UUID is checked independently. The aggregate is produced with:

```sh
python3 tools/catalog_live_jailbreak_dependencies.py \
  --macho-catalog catalog/ios/23A355/jailbreak-macho.json.gz \
  --binary-root .local/live-device-23A355/macho-files \
  --workdir .local/live-device-23A355/dependency-work \
  --output .local/live-device-23A355/jailbreak-dependencies-candidate.json.gz
```

The published catalog covers 463 files, 493 slices, 3,070 direct dylib load commands, and 569 public runpath declarations. Three embedded build-machine user-directory runpaths are counted but withheld. The website shows load names as static declarations; `@rpath` and `@loader_path` names are not claimed as resolved runtime paths.

A second pass classifies the 4,848 direct loads across both published live Mach-O families against this build's iOS and DriverKit cache install names and the verified live files' absolute install names:

```sh
python3 tools/catalog_live_load_targets.py \
  --catalog-directory catalog/ios/23A355 \
  --output .local/live-device-23A355/live-load-targets-candidate.json.gz
```

The result records 3,476 exact iOS cache-name matches and 110 same-architecture absolute install-name matches to verified Developer files. Another 1,252 tokenized names remain unresolved; ten absolute names have no exact target in these catalogs. The published index covers all 505 files and preserves each load command and architecture. The site builder recomputes every match from the four verified Mach-O and load catalogs plus the two exact-build caches before publication. These are **static name matches**: they neither expand `@rpath` or `@loader_path` in a process nor prove that dyld loaded a target at runtime. Public paths and names passed the same private-pattern checks as the source catalogs.

A separate named-symbol pass checks every acquired file and slice again, then accepts only named records whose addresses lie inside an executable `__text` section:

```sh
python3 tools/catalog_live_jailbreak_symbols.py \
  --macho-catalog catalog/ios/23A355/jailbreak-macho.json.gz \
  --binary-root .local/live-device-23A355/macho-files \
  --workdir .local/live-device-23A355/symbol-work \
  --output .local/live-device-23A355/jailbreak-symbols-candidate.json.gz
```

The public builder checks complete file and slice coverage, exact hashes and UUIDs, code-section address ranges, and private path patterns in symbol names. The [coverage note](../research/23A355/Live-Jailbreak-Symbols.md) records totals and limits.

A Swift dump pass uses the same exact acquired file bytes and per-slice UUID checks:

```sh
python3 tools/catalog_live_jailbreak_swift.py \
  --macho-catalog catalog/ios/23A355/jailbreak-macho.json.gz \
  --binary-root .local/live-device-23A355/macho-files \
  --workdir .local/live-device-23A355/swift-work \
  --output .local/live-device-23A355/jailbreak-swift-candidate.json.gz
```

The builder checks parsed declaration and member counts, explicit no-info and partial statuses, and private path patterns before exposing per-file results. See [Swift coverage](../research/23A355/Live-Jailbreak-Swift.md).

The code-signing pass reads `LC_CODE_SIGNATURE` and `codesign -dvvv` from each exact file slice, checking UUIDs and CDHashes across the parsers:

```sh
python3 tools/catalog_live_jailbreak_signatures.py \
  --macho-catalog catalog/ios/23A355/jailbreak-macho.json.gz \
  --binary-root .local/live-device-23A355/macho-files \
  --workdir .local/live-device-23A355/signature-work \
  --output .local/live-device-23A355/jailbreak-signatures-candidate.json.gz
```

The public builder strips provenance-only fields and excludes raw signing output, certificates, and entitlement values. It retains explicit entitlement parse failures. See [code-signing coverage](../research/23A355/Live-Jailbreak-Code-Signing.md).
