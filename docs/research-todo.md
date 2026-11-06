# iOS Atlas research TODO

Scope: the jailbroken iPhone 11, iOS 26.0.1 (`23A355`). The [device-first plan](device-first-plan.md) records collection and publication gates. The checks below describe completed firmware work and possible later device and library research.

The [23A355 handoff](handoff-23A355.md) closes the current horizontal delivery pass with explicit coverage boundaries. Further function-body tracing, runtime behavior, and tweak hypotheses are selected on demand. Cache-image pages mark components without a focused note as **Awaiting analysis**.

## Horizontal pass

- [x] Catalog all files in the official IPSW archive and mounted restore/system images.
- [x] Catalog all 4,170 logical images in the iOS dyld shared cache, their UUIDs, segments, and direct library loads.
- [x] Catalog Objective-C class-dump results and method entries for every iOS cache image, including empty outputs and images absent from the optimization class table.
- [x] Index named `__text` symbol records for every iOS cache image, including zero-name results; keep this symbol-table view separate from Objective-C method entries.
- [x] Give every iOS cache image a brief source-derived overview and direct link to its method list.
- [x] Index the cache's ObjC class and protocol tables and Swift type conformances separately.
- [x] Index named `__text` function symbols for all 51 images in the separate DriverKit cache; verify its ObjC class dumps.
- [x] Identify and hash standalone Mach-O files across the three official mounted system images; record architecture, file type, and UUID.
- [x] Record direct dylib load commands, install names, and runpaths for every one of the 3,363 standalone firmware Mach-O files; verify exact source hashes and slice UUIDs, and keep runtime resolution unknown.
- [x] Run an exact-file Objective-C class and method pass over all 3,363 standalone Mach-O files; retain inspected zero results.
- [x] Index named `__text` symbols in all 3,363 standalone Mach-O files, including explicit zero-name results.
- [x] Add Swift dump coverage for all 3,363 standalone files; preserve explicit no-info and partial-parse states. ObjC methods, named symbols, and Swift dumps are still not a complete callable surface.
- [x] Verify all 3,157 firmware standalone Mach-O files observed at mapped device paths by device-side SHA-256; preserve the 206 unmatched staging-path records without claiming whole-device absence.
- [x] Link the 3,117 hash-matched, reviewed base-system paths to exact firmware Mach-O analysis; show 40 cryptex hash matches without exposing their physical paths.
- [x] Record all live mounts and RootHide namespaces; capture a private, resumable metadata snapshot with per-root completeness and error counts. Ten roots completed; two data-volume roots have protected-directory errors.
- [x] Publish a privacy-reviewed catalog of live system and jailbreak installation paths, including paths absent from the stock IPSW; keep user and app data path names private.
- [x] Assign fixed, privacy-reviewed content-format labels to all 225,778 published live regular files from complete base-root, jailbreak, and Developer type passes; keep raw descriptions and private App paths local.
- [x] Identify, acquire, hash, and parse Mach-O headers for all 464 files found in the jailbreak installation tree; publish 463 after withholding one randomized filename.
- [x] Run an exact-file Objective-C method pass over all 463 published jailbreak Mach-O files; retain 402 explicit no-info results and 4,781 parsed methods.
- [x] Record direct dylib load commands and runpaths for all 493 slices of those verified files; withhold three embedded build-machine user paths.
- [x] Index named `__text` symbol records across all 493 slices of the 463 published, device-hash-verified jailbreak Mach-O files; retain explicit zero-name results.
- [x] Check Swift metadata across those same 493 slices; retain no-info and partial-parse states and link parsed lines to verified file bytes.
- [x] Read embedded CodeDirectory metadata across all 493 verified slices; distinguish ad hoc and no-CMS reports and keep entitlement parse failures explicit without publishing raw values.
- [x] Identify and verify all 42 Mach-O files in the separately mounted Developer image: classify all 117 regular files, match device-side SHA-256 to acquired bytes, and index 84 architecture slices.
- [x] Index direct dylib loads and runpaths across all 84 verified Developer slices; retain weak-load and architecture distinctions without claiming runtime resolution.
- [x] Index arm64e Objective-C methods for all 42 verified Developer binaries, preserving 40 parsed, one no-info, and one failed class-dump outcome. The failed file's method count remains unknown.
- [x] Index named `__text` symbols across all 84 verified Developer Mach-O slices, including three files with no names; keep symbol records distinct from Objective-C methods.
- [x] Check Swift dump metadata across all 84 Developer slices; preserve 12 no-info and 10 partial-parse slice results.
- [x] Read embedded CodeDirectory metadata across all 84 Developer slices; keep entitlement values and raw signing output private and distinguish metadata from trust.
- [x] Classify all 4,848 direct loads in verified live Mach-O files by exact cache or live install name; leave tokenized and unmatched names unresolved.
- [x] Classify all 219,216 reachable base-root regular files by type, reconcile all 3,117 ordinary Mach-O files with byte-verified firmware identities, and verify the one mixed Metal container against exact FileSystem bytes. The Preboot and Developer mounts have separate type passes; data-volume and volatile mounts retain explicit gaps.
- [x] Make live device files the primary website view, show scan-root coverage, and remove cross-version comparison navigation.
- [x] Publish privacy-reviewed per-mount scan counts, statuses, and access-error totals without private path names.
- [x] Show byte-verified Mach-O counts by mount, distinguishing exhaustive live file-type passes from firmware-seeded hash matches and unclassified mounts.
- [x] Classify all 3,257 reachable Preboot regular files by type; confirm 40 known standalone Mach-O files and byte-match one mixed QuartzCore Metal container to the exact SystemOS firmware without exposing its physical path.
- [x] Classify all reachable regular files in the completed Hardware, Baseband, and xARTS mount scans; record zero ordinary Mach-O candidates with exact path-set checks.
- [x] Byte-verify and parse two live-only Software Update Mach-O files, preserving their private physical paths and the mount's time-bounded observation limit.
- [x] Resnapshot the volatile Software Update mount and reconcile all 2,080 reachable file paths with a complete type pass; recheck both ordinary Mach-O candidates by device SHA-256.
- [x] Classify all reachable files from a later partial Data snapshot by type: 23,490 paths matched exactly, with 303 private Mach-O signatures. Observe three Mobile data candidates while retaining its 34-path churn and 57 protected-directory limit. Keep all private app and mobile paths out of the public site.
- [x] Hash all 306 reachable Data and Mobile data Mach-O type candidates on the exact device with a NUL-safe, read-only pass; keep every path and digest private, and retain the older type-scan and protected-directory limits.
- [x] Acquire all 306 reachable private data-volume Mach-O candidates, match every local byte stream to its device-side hash, and parse 312 architecture slices without publishing app paths, hashes, or binaries.
- [x] Inspect all 306 byte-verified private data-volume Mach-O candidates for direct loads, named symbols, Swift metadata, and embedded signing structures; inspect Objective-C where applicable. Keep per-file results private and publish only reviewed mount-level counts, including three failed ObjC results and five dSYM exclusions.
- [x] Classify the three private Objective-C failures: all three on-disk binaries declare `LC_ENCRYPTION_INFO_64` with `crypt_id=1`, and encrypted ranges overlap Objective-C sections. Preserve unknown method counts without attempting decryption in this atlas pass.
- [x] Expose static analysis status by mount for verified public code, including no-info and failed Objective-C results, partial Swift results, and mounts with no code-classification pass.
- [x] Reconcile all 3,623 published Mach-O-like regular-file paths to 3,622 exact device-hash-verified ordinary binaries and one byte-matched mixed Metal container. This completes the reviewed public Mach-O-like path set, not protected directories, private data paths, or embedded/generated code.
- [x] Give all 99 published script/makefile labels and six ELF labels fixed, privacy-reviewed subtype details from the complete type passes. This is signature metadata, not script-body analysis, an independent ELF parse, or evidence of execution.

## Completed first-pass component studies

- [x] Trace Foundation as a cache image and document its ObjC method surface.
- [x] Trace SpringBoard's launch declaration and startup entry point; document its ObjC method surface.
- [x] Inspect selected calls inside SpringBoard's `applicationDidFinishLaunching:` and keep untraced receivers and runtime effects explicit.
- [x] Trace UIKitCore's exact `UIApplicationMain` entry through preparations and `_run`, and document its bounded method surface.
- [x] Trace CoreFoundation's two public run-loop entry wrappers to the shared internal function.
- [x] Trace the exact SpringBoard embedded-scene delegate through superclass setup, a retained configuration block, and a candidate startup-completion send; leave callback timing and runtime dispatch open.
- [x] Trace UIKitCore's `_run` through event-source installation and GraphicsServices' `GSEventRun` to CoreFoundation's `CFRunLoopRunInMode`; leave live branch choices and run-loop mode open.
- [x] Create a source-bound WidgetKit overview with documented purpose and API types, exact-image method and symbol examples, direct dependencies, and known gaps.
- [x] Trace the live UpdateBrain service entry into its device-acquired library; record the XPC listener, entitlement gate, and seven static command dispatch targets with Ghidra addresses and private evidence bundles.
- [x] Record a first-pass BusinessChat role from exact-image methods and focused pseudocode, distinguishing chat UI and authentication hypotheses from runtime behavior.
- [x] Record a first-pass Twitter role from the exact cache image's 23 Objective-C method entries, keeping runtime loading and service availability unknown.
- [x] Record first-pass exact-cache evidence for CoreServices, RealityFoundation, StickerFoundation, StickerKit, and SwiftUICore. Keep StickerFoundation's specific role unknown; method and symbol names in the others support bounded static inferences only.
New component studies begin when a specific library, method, or question is selected. Each study records its exact-image evidence and remaining unknowns. Static metadata does not prove runtime execution or a safe hook point. Use [the acquisition record](acquisition-23A355.md) and [method coverage note](../research/23A355/Method-Catalog-Coverage.md) for provenance.
