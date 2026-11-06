# Live device collection and publication

Target: the currently connected `iPhone12,1` on iOS `23A355`. This workflow is read-only on the phone. It scans metadata and symlink targets, never file contents. Raw results contain private paths and remain under ignored `.local`.

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

The full pass enumerates each discovered mount independently with `find -xdev`; symlinks are not followed. Files named with newlines are preserved through a NUL-delimited protocol. Each root gets a compressed JSONL file, count, SHA-256, and `complete`/`partial` status. A partial root is retried on the next run. On 2026-11-05, 10 of 12 roots completed. `/rootfs/private/var` reported 16 protected-directory errors, and `/rootfs/private/var/mobile` reported 57; their reachable entries remain private. Local stderr files include private paths and must not be published. Duplicate namespace views remain distinct until a reviewed mapping exists. Because the phone can change during collection, the result is a time-bounded observation, not an atomic filesystem snapshot.

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
