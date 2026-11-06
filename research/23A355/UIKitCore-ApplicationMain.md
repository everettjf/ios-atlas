# How does this UIKitCore image enter the application event cycle?

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`), SystemOS arm64e dyld cache UUID `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`. The inspected logical image is `/System/Library/PrivateFrameworks/UIKitCore.framework/UIKitCore`, Mach-O UUID `C98EAB32-B273-3430-B0C5-46522C904CBB`. Its local `ipsw dyld extract` derivative has SHA-256 `fa0602d08391372c60d63aac6e3af356c14b95da25674e28e014489b749ad112`; the binary is not published.

[Apple documents `UIApplicationMain`](https://developer.apple.com/documentation/uikit/uiapplicationmain%28_%3A_%3A_%3A_%3A%29-1yub7) as creating the application and delegate and starting the event cycle. The exact cache gives a narrower, build-specific view of its implementation. The [SpringBoard startup note](SpringBoard-Startup.md) identifies a branch to an imported `_UIApplicationMain` symbol; the [dependency catalog](../../catalog/ios/23A355/dyld-dependencies.json) shows that the public UIKit image re-exports this UIKitCore image. The import stub address in SpringBoard's extracted image is not UIKitCore's implementation address.

## Exact-image observations

- `_UIApplicationMain` begins at `0x1889c19bc` in UIKitCore's extracted image. At `0x1889c1ae4–0x1889c1af4`, it restores saved `argc` and `argv` to `x0` and `x1`, passes two values returned by earlier helper calls in `x2` and `x3`, and directly calls `__UIApplicationMainPreparations` at `0x1889c2368`. The meaning of those helper results is not resolved here.
- At `0x1889c1b04–0x1889c1b08`, it reads an object pointer from image data and sends `_run`. This is a static message-send site; the receiver class and later event-dispatch path are not established by these instructions alone.
- The path after that send references a literal saying that returning from `UIApplicationMain()` violates the application contract (`0x1889c1b10`). This matches Apple's documented expectation that the function does not normally return; it does not prove what happened on the connected phone.
- The [per-image method catalog](../../catalog/ios/23A355/objc-image-methods-UIKitCore.json.gz) records 119,797 Objective-C method entries across 5,533 classes and 101 categories. Selected class groups include `UIApplication` (862 methods), `UIScene` (204), `UIWindowScene` (206), `UIView` (1,546), `UIViewController` (950), and `UIGestureRecognizer` (150). These are metadata counts, not an execution trace or a complete callable surface.
- The [named-symbol catalog](../../catalog/ios/23A355/ios-cache-symbols.json.gz) records 140,315 unique named `__text` rows in this image. These overlap the Objective-C catalog and must not be added to its method count. Its 102 direct Mach-O loads include FrontBoardServices, BackBoardServices, Foundation, CoreFoundation, QuartzCore, and GraphicsServices; 16 are weak loads.

This supports a concrete entry sequence from `UIApplicationMain` into preparations and `_run`, while the broad class inventory shows where scene, view, and input work can be investigated next. It does not resolve delegate creation, `_run` internals, event routing, runtime ownership of every class, or a tweak hook.

## Reproduce

Follow the [acquisition record](../../docs/acquisition-23A355.md), verify the image UUID and derivative hash above, then run:

`xcrun llvm-objdump -m -d --dis-symname _UIApplicationMain .local/rea/extracted/UIKitCore`

The method, symbol, and dependency counts come from the linked exact-build catalogs. The disassembly and Apple binary stay local.
