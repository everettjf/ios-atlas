# How much of Foundation's Objective-C method surface is indexed?

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`). Source: official restore IPSW SHA-256 `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`, iOS arm64e dyld cache family UUID `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`. The inspected image is `/System/Library/Frameworks/Foundation.framework/Foundation`, Mach-O UUID `0555AF54-2075-3F2D-BC40-733E55EEE95A`.

## Observed coverage

- A complete `ipsw class-dump --re -V` of this image reports 720 class declarations and 53 categories. Its table of contents reports 62 protocol entries, while the output renders 48 `@protocol` declarations. The full local dump has SHA-256 `fb73e704e1718d670886de80c7e86142d1dadd4ff5b7ef6190f45c0da6de0fd0`; it is not published. The table and rendered counts are recorded separately because this source does not explain their difference.
- The [derived method catalog](../../catalog/ios/23A355/objc-image-methods-Foundation.json.gz) contains 11,045 method entries: 10,215 under classes and 830 under categories. Each entry has a selector, class or category label, and implementation address inside this exact image's `__TEXT` segment. The catalog preserves class and category boundaries. No group contains a duplicate selector and method kind in this dump.
- All 720 class names and metadata addresses match the separate [dyld Objective-C optimization table](../../catalog/ios/23A355/objc-classes.json) for this image. All 53 category metadata addresses lie in the image's mapped segments. The extracted analysis derivative has SHA-256 `078c2898a74339d91c8a032d7f735fa4770aed75dcb69e5d3bed9a64d0c49afc`; it is not an on-device standalone executable.
- Protocol declarations are excluded from the implementation-address count. A protocol declaration is an interface record, not evidence of an implementation in this image.

## How to use it

The [Objective-C methods view](https://xnu.app/ios-atlas/#methods) lists the indexed images. Choose Foundation to search class names, category labels, selectors, and implementation addresses. The site loads its compressed method bucket only after selection. The [Foundation filesystem view](https://xnu.app/ios-atlas/#files/%2FSystem%2FLibrary%2FFrameworks%2FFoundation.framework) separately shows the framework's on-disk resources and its logical in-cache executable.

This count covers one cache image in one build. It does not cover every image in the iOS cache, methods dynamically added at runtime, generated subclasses, or method bodies. A selector and address do not prove that a process called the method; selecting a tweak hook requires function-body and runtime evidence.

## Reproduce

Follow the [acquisition record](../../docs/acquisition-23A355.md) to obtain the exact IPSW and intact cache family. Keep the full dump and extracted analysis derivative under ignored `.local` storage:

`ipsw class-dump <MAIN_DSC> /System/Library/Frameworks/Foundation.framework/Foundation --re -V --no-color > .local/rea/foundation-all-classes.txt`

`ipsw dyld extract <MAIN_DSC> /System/Library/Frameworks/Foundation.framework/Foundation --output .local/rea/extracted --slide --objc --stubs --cache <MAIN_DSC>.a2s`

`python3 tools/catalog_objc_image_methods.py --class-dump .local/rea/foundation-all-classes.txt --image .local/rea/extracted/Foundation --image-sha256 078c2898a74339d91c8a032d7f735fa4770aed75dcb69e5d3bed9a64d0c49afc --install-name /System/Library/Frameworks/Foundation.framework/Foundation --segments catalog/ios/23A355/dyld-segments.json --objc-classes catalog/ios/23A355/objc-classes.json --expected-method-count 11045 --output catalog/ios/23A355/objc-image-methods-Foundation.json.gz`

The generator checks the derivative hash and UUID, source-build identities, class-table equality, class and category counts, protocol count bounds, and every implementation address. The website builder repeats the catalog consistency and address checks before publishing derived metadata.
