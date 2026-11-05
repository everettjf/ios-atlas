# iOS Atlas research TODO

Scope: iPhone 11, iOS 26.0.1 (`23A355`). This list separates the completed horizontal inventory from questions that need implementation or device evidence.

## Horizontal pass

- [x] Catalog all files in the official IPSW archive and mounted restore/system images.
- [x] Catalog all 4,170 logical images in the iOS dyld shared cache, their UUIDs, segments, and direct library loads.
- [x] Catalog Objective-C class-dump results and method entries for every iOS cache image, including empty outputs and images absent from the optimization class table.
- [x] Give every iOS cache image a brief source-derived overview and direct link to its method list.
- [x] Index the cache's ObjC class and protocol tables and Swift type conformances separately.
- [ ] Add comparable method and metadata coverage for the separate DriverKit cache and non-cache Mach-O files.
- [ ] Add source-backed functional descriptions to library pages. The current overviews describe location and metadata; they do not claim to explain behavior.
- [ ] Hash and compare selected live device files outside the cache to the official firmware, with exact namespace and path mapping.

## Deeper studies, one component at a time

- [x] Trace Foundation as a cache image and document its ObjC method surface.
- [x] Trace SpringBoard's launch declaration and startup entry point; document its ObjC method surface.
- [ ] Pick a library with a clear user-visible function; document purpose, key types, exported APIs, and its immediate dependencies with cited evidence.
- [ ] Inspect selected method bodies and call sites in the exact image; attach addresses, disassembly, and tool versions.
- [ ] Confirm process ownership and load behavior with bounded, read-only device observation where possible.
- [ ] Compare the same library across two firmware builds before describing changes.
- [ ] Record tweak ideas as hypotheses with the function, expected hook point, version constraints, and a device validation plan.

A checklist item is complete only at its stated scope. Static metadata does not prove runtime execution or a safe hook point. Use [the acquisition record](acquisition-23A355.md) and [method coverage note](../research/23A355/Method-Catalog-Coverage.md) for provenance.
