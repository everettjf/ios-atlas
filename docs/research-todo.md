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
- [ ] Add source-backed functional descriptions to library pages. Apple Developer sources now cover 218 of 227 exact top-level iOS framework images and one DriverKit image; nine top-level gaps and the other cache libraries still need suitable primary evidence. Every image already has a separate metadata overview.
- [x] Verify all 3,157 firmware standalone Mach-O files observed at mapped device paths by device-side SHA-256; preserve the 206 unmatched staging-path records without claiming whole-device absence.
- [x] Record all live mounts and RootHide namespaces; capture a private, resumable metadata snapshot with per-root completeness and error counts. Ten roots completed; two data-volume roots have protected-directory errors.
- [x] Publish a privacy-reviewed catalog of live system and jailbreak installation paths, including paths absent from the stock IPSW; keep user and app data path names private.
- [x] Identify, acquire, hash, and parse Mach-O headers for all 464 files found in the jailbreak installation tree; publish 463 after withholding one randomized filename.
- [x] Run an exact-file Objective-C method pass over all 463 published jailbreak Mach-O files; retain 402 explicit no-info results and 4,781 parsed methods.
- [x] Record direct dylib load commands and runpaths for all 493 slices of those verified files; withhold three embedded build-machine user paths.
- [x] Index named `__text` symbol records across all 493 slices of the 463 published, device-hash-verified jailbreak Mach-O files; retain explicit zero-name results.
- [ ] Investigate the 73 protected-directory errors in the two data-volume views and record any remaining inaccessible scope without exposing private names.
- [ ] Run Swift and code-signing passes over the verified live Mach-O files; keep zero and unsupported results explicit. Resolve direct library loads only where exact device evidence permits.
- [ ] Discover any additional base-system standalone executables, dylibs, frameworks, and extensions absent from the firmware inventory; establish identity before reusing firmware analysis.
- [x] Make live device files the primary website view, show scan-root coverage, and remove cross-version comparison navigation.
- [ ] Add live standalone Mach-O and library analysis coverage by mount, including unsupported and failed states.

## Deeper studies, one component at a time

- [x] Trace Foundation as a cache image and document its ObjC method surface.
- [x] Trace SpringBoard's launch declaration and startup entry point; document its ObjC method surface.
- [x] Create a source-bound WidgetKit overview with documented purpose and API types, exact-image method and symbol examples, direct dependencies, and known gaps.
- [ ] Map selected public Swift APIs to exact-image metadata or exports before describing their implementation in this build.
- [ ] Follow WidgetKit's `_WidgetExtensionSession` timeline and control request methods into their immediate call sites, and distinguish its code from `ChronoServices`.
- [ ] Inspect selected method bodies and call sites in the exact image; attach addresses, disassembly, and tool versions.
- [ ] Confirm process ownership and load behavior with bounded, read-only device observation where possible.
- [ ] Record tweak ideas as hypotheses with the function, expected hook point, version constraints, and a device validation plan.

A checklist item is complete only at its stated scope. Static metadata does not prove runtime execution or a safe hook point. Use [the acquisition record](acquisition-23A355.md) and [method coverage note](../research/23A355/Method-Catalog-Coverage.md) for provenance.
