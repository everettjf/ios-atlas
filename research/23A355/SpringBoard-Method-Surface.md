# How much of SpringBoard.framework's Objective-C method surface is indexed?

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`). Source: official restore IPSW SHA-256 `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`, iOS arm64e dyld cache family UUID `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`. The inspected image is `/System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard`, Mach-O UUID `8676BE2A-9484-3492-888E-7DE10333250F`.

## Observed coverage

- A complete `ipsw class-dump --re -V` of that cache image reports 2,633 class declarations, 108 categories, and 1,317 protocol declarations. The full local dump has SHA-256 `43494a07674ac0462bc1241f9f5896111a8d53d7bc8d7de9271a301d47222725`; it is not published.
- The [derived method catalog](../../catalog/ios/23A355/objc-image-methods-SpringBoard.json.gz) contains 52,025 method entries: 51,636 under classes and 389 under categories. Every entry has a selector, class or category label, and implementation address inside this exact image's `__TEXT` segment. The `SpringBoard` class contributes 645 of these entries.
- All 2,633 class names and metadata addresses match the separate [dyld Objective-C optimization table](../../catalog/ios/23A355/objc-classes.json) for this image. All 108 category metadata addresses are within this image's mapped segments. The class dump's own table-of-contents counts match the parsed class, category, and protocol declaration counts.
- Five class method sets contain a selector repeated with two different implementation addresses. Both entries are preserved. This static dump does not establish which one wins at runtime.
- The 1,317 protocol declarations are excluded from the implementation-address count. A protocol's method declaration is a requirement or optional interface, not an implementation in this image.

## How to use it

The [Objective-C methods view](https://xnu.app/ios-atlas/#methods) lists indexed images and searches class names there. Choose SpringBoard.framework to search its class names, category labels, selectors, and implementation addresses. For example, [SpringBoard's own methods](https://xnu.app/ios-atlas/#methods/class%3ASpringBoard) show `applicationDidFinishLaunching:` at `0x21d6a1a48`. The [class table](https://xnu.app/ios-atlas/#objc) links its exact `SpringBoard` entry to that filtered list. This supports targeted reverse engineering and candidate discovery; selecting a tweak hook still requires function-body and runtime evidence.

The count is for one cache image in one build. The site also indexes [other image method surfaces](Method-Catalog-Coverage.md), but these catalogs do not cover every class in the 4,170-image iOS cache, categories in other images, dynamically added methods, generated runtime subclasses, or methods whose metadata is unavailable to the dumps. A selector name or IMP address does not prove a method was called on the connected phone.

## Reproduce

Follow the [acquisition record](../../docs/acquisition-23A355.md) to obtain the exact IPSW and intact cache family. Keep the full class dump and extracted analysis derivative under ignored `.local` storage:

`ipsw class-dump <MAIN_DSC> /System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard --re -V --no-color > .local/rea/springboard-all-classes.txt`

`ipsw dyld extract <MAIN_DSC> /System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard --output .local/rea/extracted --slide --objc --stubs --cache <MAIN_DSC>.a2s`

`python3 tools/catalog_objc_image_methods.py --class-dump .local/rea/springboard-all-classes.txt --image .local/rea/extracted/SpringBoard --image-sha256 7732a59763b6fa34a52bfe8531d6dc0fcfa69761f6a96f438c0cda3363bb20be --install-name /System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard --segments catalog/ios/23A355/dyld-segments.json --objc-classes catalog/ios/23A355/objc-classes.json --expected-method-count 52025 --output catalog/ios/23A355/objc-image-methods-SpringBoard.json.gz`

The generator checks the derivative SHA-256 and UUID, source-build identities, class-table equality, declaration counts, and every implementation address. The website builder repeats the catalog consistency and address checks before publishing derived metadata.
