# iOS Atlas research TODO

Scope: the currently jailbroken iPhone 11, iOS 26.0.1 (`23A355`). The [device-first plan](device-first-plan.md) defines the next collection and publication gates. The checks below describe completed firmware work and remaining device and library research.

## Horizontal pass

- [x] Catalog all files in the official IPSW archive and mounted restore/system images.
- [x] Catalog all 4,170 logical images in the iOS dyld shared cache, their UUIDs, segments, and direct library loads.
- [x] Catalog Objective-C class-dump results and method entries for every iOS cache image, including empty outputs and images absent from the optimization class table.
- [x] Index named `__text` symbol records for every iOS cache image, including zero-name results; keep this symbol-table view separate from Objective-C method entries.
- [x] Give every iOS cache image a brief source-derived overview and direct link to its method list.
- [x] Index the cache's ObjC class and protocol tables and Swift type conformances separately.
- [x] Index named `__text` function symbols for all 51 images in the separate DriverKit cache; verify its ObjC class dumps.
- [x] Identify and hash standalone Mach-O files across the three official mounted system images; record architecture, file type, and UUID.
- [x] Run an exact-file Objective-C class and method pass over all 3,363 standalone Mach-O files; retain inspected zero results.
- [x] Index named `__text` symbols in all 3,363 standalone Mach-O files, including explicit zero-name results.
- [x] Add Swift dump coverage for all 3,363 standalone files; preserve explicit no-info and partial-parse states. ObjC methods, named symbols, and Swift dumps are still not a complete callable surface.
- [ ] Add source-backed functional descriptions to library pages. Apple Developer sources now cover 219 of 227 exact top-level iOS framework images and one DriverKit image; eight top-level gaps and the other cache libraries still need suitable primary evidence. Every image already has a separate metadata overview.
- [x] Verify all 3,157 firmware standalone Mach-O files observed at mapped device paths by device-side SHA-256; preserve the 206 unmatched staging-path records without claiming whole-device absence.
- [x] Link the 3,117 hash-matched, reviewed base-system paths to exact firmware Mach-O analysis; show 40 cryptex hash matches without exposing their physical paths.
- [x] Record all live mounts and RootHide namespaces; capture a private, resumable metadata snapshot with per-root completeness and error counts. Ten roots completed; two data-volume roots have protected-directory errors.
- [x] Publish a privacy-reviewed catalog of live system and jailbreak installation paths, including paths absent from the stock IPSW; keep user and app data path names private.
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
- [ ] Investigate the 73 protected-directory errors in the two data-volume views and record any remaining inaccessible scope without exposing private names.
- [x] Classify all 4,848 direct loads in verified live Mach-O files by exact cache or live install name; leave tokenized and unmatched names unresolved.
- [ ] Verify selected runtime load paths with bounded, read-only device observations, including runpath expansion and weak-load behavior.
- [ ] Discover any additional base-system standalone executables, dylibs, frameworks, and extensions absent from the firmware inventory; establish identity before reusing firmware analysis. The base `/rootfs` and both cryptex file paths all appear in the corresponding official image catalogs; the separate Developer mount adds 42 verified Mach-O files. Remaining data-volume and preboot coverage is explicit in the collection note.
- [x] Make live device files the primary website view, show scan-root coverage, and remove cross-version comparison navigation.
- [x] Publish privacy-reviewed per-mount scan counts, statuses, and access-error totals without private path names.
- [x] Show byte-verified Mach-O counts by mount, distinguishing exhaustive live file-type passes from firmware-seeded hash matches and unclassified mounts.
- [x] Classify all 3,257 reachable Preboot regular files by type; confirm 40 known standalone Mach-O files and byte-match one mixed QuartzCore Metal container to the exact SystemOS firmware without exposing its physical path.
- [x] Classify all reachable regular files in the completed Hardware, Baseband, and xARTS mount scans; record zero ordinary Mach-O candidates with exact path-set checks.
- [x] Byte-verify and parse two live-only Software Update Mach-O files, preserving their private physical paths and the mount's changing-file-set limitation.
- [ ] Resnapshot the volatile Software Update mount at a stable point and reconcile all code candidates; do not infer an exhaustive total from two verified files.
- [x] Expose static analysis status by mount for verified public code, including no-info and failed Objective-C results, partial Swift results, and mounts with no code-classification pass.
- [ ] Expand live standalone Mach-O and library analysis coverage to every publishable code-bearing file on each mount, including unsupported formats and failed analyses.

## Deeper studies, one component at a time

- [x] Trace Foundation as a cache image and document its ObjC method surface.
- [x] Trace SpringBoard's launch declaration and startup entry point; document its ObjC method surface.
- [x] Create a source-bound WidgetKit overview with documented purpose and API types, exact-image method and symbol examples, direct dependencies, and known gaps.
- [x] Record a first-pass BusinessChat role from exact-image methods and focused pseudocode, distinguishing chat UI and authentication hypotheses from runtime behavior.
- [ ] Trace BusinessChat action and network-provider call sites and identify its runtime process owner.
- [ ] Map selected public Swift APIs to exact-image metadata or exports before describing their implementation in this build.
- [ ] Follow WidgetKit's `_WidgetExtensionSession` timeline and control request methods into their immediate call sites, and distinguish its code from `ChronoServices`.
- [ ] Inspect selected method bodies and call sites in the exact image; attach addresses, disassembly, and tool versions.
- [ ] Confirm process ownership and load behavior with bounded, read-only device observation where possible.
- [ ] Record tweak ideas as hypotheses with the function, expected hook point, version constraints, and a device validation plan.

A checklist item is complete only at its stated scope. Static metadata does not prove runtime execution or a safe hook point. Use [the acquisition record](acquisition-23A355.md) and [method coverage note](../research/23A355/Method-Catalog-Coverage.md) for provenance.
