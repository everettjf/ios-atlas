# Does GraphicsServices enter CoreFoundation's run loop?

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`), SystemOS arm64e cache UUID `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`. The inspected `/System/Library/PrivateFrameworks/GraphicsServices.framework/GraphicsServices` image has UUID `4EB73F50-CDF2-3161-94C0-0F3E7002B67C`. Its local `ipsw dyld extract` derivative has SHA-256 `fa9e9a556605ea732487ebb840986962cef09f6cbf503c48ba50d764d919ee62`; the binary is not published.

The [UIKitCore `_run` note](UIKitCore-RunLoop.md) identifies an imported `GSEventRun` call. The exact [dependency catalog](../../catalog/ios/23A355/dyld-dependencies.json) records a UIKitCore load of GraphicsServices and a GraphicsServices load of CoreFoundation. Those declarations align with, but do not replace, the instruction evidence below.

## Direct instruction evidence

- `_GSEventRun` at `0x22246e19c` sets `w0` to zero and branches to `_GSEventRunModal` at `0x22246e1a0`.
- `_GSEventRunModal` begins at `0x22246e420`. In its loop it obtains a value from an array through imported `CFArrayGetValueAtIndex` (`0x22246e484`), checks for null (`0x22246e488`), then calls imported `CFRunLoopRunInMode` at `0x22246e494`. The immediately preceding instruction sets `w1` to zero (`0x22246e490`). [Apple documents](https://developer.apple.com/documentation/corefoundation/cfrunloopruninmode%28_%3A_%3A_%3A%29) that this argument is `returnAfterSourceHandled`; the code supplies false at this site. The mode value and duration are not decoded here.
- A conditional branch at `0x22246e498` can repeat the loop. A null mode leads to a logging path. This does not prove the number of iterations or which modes the phone used.
- The imported `CFRunLoopRunInMode` stub at `0x2225af230` is identified by the derivative symbol table. The [CoreFoundation note](CoreFoundation-RunLoop.md) follows its implementation at `0x1830a3018` to `CFRunLoopGetCurrent` and `__CFRunLoopRunSpecificWithOptions`.

The resulting static call chain is `UIApplicationMain` → `UIApplication _run` → `GSEventRun` → `GSEventRunModal` → `CFRunLoopRunInMode` → CoreFoundation's internal run function. Import names, load declarations, and exact-image implementations support this path. Runtime binding, actual branch choices, callback execution, and event semantics on the connected phone remain unverified.

## Reproduce

Verify the derivative SHA-256 and image UUID above, then run `xcrun llvm-objdump -m -d --dis-symname _GSEventRun .local/rea/extracted/GraphicsServices` and the same command for `_GSEventRunModal`. Check the stub identities with `xcrun llvm-nm -n .local/rea/extracted/GraphicsServices`. The Apple binary and full disassembly stay local.
