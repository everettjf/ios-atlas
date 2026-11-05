# What does the per-image Objective-C method catalog cover?

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`). Source: official restore IPSW SHA-256 `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`, iOS arm64e cache family UUID `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`. See the [acquisition record](../../docs/acquisition-23A355.md).

## Horizontal coverage

- The [method explorer](https://xnu.app/ios-atlas/#methods) has a separate catalog for **all 4,170 iOS cache images**. Together they contain **3,065,801 Objective-C method entries**, **217,455 rendered class declarations**, and **10,623 categories**. Choose an image to load its compressed method bucket. The [image explorer](https://xnu.app/ios-atlas/#images) gives each library a short, source-derived overview and a direct method link.
- **1,014 images** have zero listed methods. For **406** of these, `ipsw class-dump --re -V` succeeded but emitted an empty file. These are recorded as inspected zero-result dumps with the empty file's SHA-256; a zero is not evidence that an image has no code or no Swift or C functions.
- The dyld Objective-C optimization class table lists classes in 3,443 of the 4,170 images. We also scanned the other 727. **Sixteen** of them contain **119 method entries** in their class dumps, so class-table absence was not treated as method absence.
- The catalogs retain **565 Swift-marked class declarations** absent from the optimization class table and one category for which the dump omits the class name. **Ten method entries** have no decoded selector and remain explicitly unknown. Raw selectors with unusual punctuation remain as printed. Full dump UTF-8 decoding produced **424 replacement characters**, recorded per image rather than hidden.

## Source checks and meaning

Each catalog records the exact install name, image UUID, full class-dump SHA-256, classes, categories, selectors where decoded, and IMP addresses. Class identities are checked against the separate dyld optimization table; extra class declarations must be marked Swift. Class and category counts are checked against the dump's table of contents when present. Every IMP is checked against the defining image's `__TEXT` range from the independently collected Mach-O segment catalog. The site builder repeats these checks and rejects duplicate install names.

The first 69 catalogs were made with extracted Mach-O analysis derivatives; each records that derivative's SHA-256 and had its UUID checked against the intact cache. The other 4,101 were generated directly from the intact cache. Before each direct-cache batch, the collector verified all 80 cache-family files against the official firmware catalog by SHA-256; each new catalog also records the verified main-cache hash. An extracted image hash is therefore absent from those catalogs. Raw dumps, cache bytes, and extracted Apple binaries stay local; Git contains only compressed derived metadata.

An entry describes static metadata in this one firmware build. It does not show which process loaded an image, which method ran, or which duplicate implementation wins at runtime. The overview names prominent method groups as clues, not a verified behavioral description. [Foundation](Foundation-Method-Surface.md) and [SpringBoard](SpringBoard-Method-Surface.md) provide examples of deeper notes. The [research TODO](../../docs/research-todo.md) tracks later function-body and runtime studies.

## Reproduce or extend

With the exact local cache family, run:

`python3 tools/batch_objc_image_methods.py --cache .local/cache/23A355__iPhone12,1/dyld_shared_cache_arm64e --cache-only --dyld-catalog catalog/ios/23A355/dyld.json --segments catalog/ios/23A355/dyld-segments.json --objc-classes catalog/ios/23A355/objc-classes.json --output-dir catalog/ios/23A355 --workdir .local/rea/batch --all-images --limit 100`

The batch skips existing catalogs after checking their source identity. `--include` selects an exact install name for review. Run `python3 tools/build_site.py` to validate and rebuild the public site. The collector also supports extracted-image mode with `--a2s` for focused work.
