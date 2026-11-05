# What does the per-image Objective-C method catalog cover?

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`). Source: official restore IPSW SHA-256 `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`, iOS arm64e cache family UUID `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`. The [acquisition record](../../docs/acquisition-23A355.md) identifies the exact cache family and source catalogs.

## Current coverage

- The [method explorer](https://xnu.app/ios-atlas/#methods) indexes **1,250,501 method entries** in **69 of 4,170 iOS cache images**. Its image index loads one compressed method bucket after a visitor chooses an image. The 69 catalogs contain 75,764 rendered class declarations and 2,717 categories. They are not a whole-cache method inventory.
- Each source catalog records its exact install name, image UUID, extracted analysis derivative SHA-256, full class-dump SHA-256, class and category groups, selectors where decoded, and implementation addresses. The generator checks class identities against the separate dyld Objective-C class table and checks every IMP address against the defining image's `__TEXT` segment. The site builder repeats those checks before publishing.
- UIKitCore contributes 119,797 entries, GeoServices 70,127, and SiriInstrumentation 69,691. The [Foundation](Foundation-Method-Surface.md) and [SpringBoard](SpringBoard-Method-Surface.md) notes describe two images in more detail. The [image index](../../catalog/ios/23A355/) lists the other compressed catalogs and their exact counts.
- **Three UIKitCore entries** under `_IntArray2D` have an IMP address and method kind, but `ipsw class-dump` prints no selector. They remain in the catalog with a null selector, not an invented name. Their addresses are `0x189a68010`, `0x189a67f60`, and `0x189a67fa4`.
- **58 rendered Swift-marked classes** across the indexed images are absent from the dyld Objective-C optimization class table. They are retained as class-dump records and marked as Swift. The other 75,706 class identities match the optimization table; the extra Swift classes are not misreported as table entries.
- Six full class dumps contain **71 replacement characters** when decoded as UTF-8. The raw dumps remain local and are hashed byte-for-byte. The invalid bytes occur in printed type or ivar text, which is not used as a selector or class identity. The catalog records each dump's replacement count. Protocol table-of-contents counts also exceed rendered declarations in some images; protocol declarations are excluded from method counts and both counts remain separate.
- VFX contains a raw selector printed as `setCameraEntityTransformProjection:::::::`. Its seven consecutive colon components are preserved as printed rather than converted into a guessed method signature.

## Interpretation

An entry describes static method metadata in one image of one firmware build. It does not prove that a process loaded the image, that a method ran, or which duplicate implementation wins at runtime. Metadata names are useful starting points for function-body inspection and bounded device observation; a tweak hook requires that additional evidence.

## Continue the index

The [batch collector](../../tools/batch_objc_image_methods.py) orders unindexed images by Objective-C class-table size, processes a bounded number, and keeps full dumps and extracted Mach-O analysis derivatives under ignored `.local` storage. It skips existing catalogs after checking their build, cache, image UUID, and install name; the site builder validates every catalog's full contents before publication. For the exact local cache family:

`python3 tools/batch_objc_image_methods.py --cache .local/cache/23A355__iPhone12,1/dyld_shared_cache_arm64e --a2s .local/cache/23A355__iPhone12,1/dyld_shared_cache_arm64e.a2s --segments catalog/ios/23A355/dyld-segments.json --objc-classes catalog/ios/23A355/objc-classes.json --output-dir catalog/ios/23A355 --workdir .local/rea/batch --limit 10`

Run `python3 tools/build_site.py` after reviewing new catalogs. Only derived compressed metadata belongs in Git; raw dumps, firmware, and extracted Apple binaries stay local.
