# What do CoreFoundation's run-loop entry points do in this build?

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`), SystemOS arm64e dyld cache UUID `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`. The inspected logical image is `/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation`, Mach-O UUID `973E47E5-88F0-3367-B9D4-46D5CB999B75`. Its local `ipsw dyld extract` derivative has SHA-256 `354c2d9719cf667a034173b167fa8f009760747165c4cbc1733320bd785d8e73`; the binary is not published.

[Apple's CFRunLoop documentation](https://developer.apple.com/documentation/corefoundation/cfrunloop) describes a thread's run loop, its sources, timers, observers, and modes. This note checks the entry wrappers in the exact cached image. It does not claim that UIKit's `_run` calls these exact functions on this phone; that call path has not been traced.

## Exact-image observations

- `_CFRunLoopRun` starts at `0x1831213ec`. It calls `_CFRunLoopGetCurrent` at `0x183121418` and `__CFRunLoopRunSpecificWithOptions` at `0x183121428`. After inspecting the result and process-state flags, a conditional branch at `0x183121450` can return to the `GetCurrent` call. These instructions show an entry wrapper and a possible repeated invocation, without establishing which result values occurred at runtime.
- `_CFRunLoopRunInMode` starts at `0x1830a3018`. It retains incoming mode and duration arguments, calls `_CFRunLoopGetCurrent` at `0x1830a3058`, then branches to `__CFRunLoopRunSpecificWithOptions` at `0x1830a308c`. This is a code-path observation, not a complete reading of the internal scheduler.
- The [named-symbol catalog](../../catalog/ios/23A355/ios-cache-symbols.json.gz) records 7,977 unique named `__text` rows, including these entry points and the internal `__CFRunLoopRunSpecificWithOptions`. The [Objective-C catalog](../../catalog/ios/23A355/objc-image-methods-CoreFoundation.json.gz) separately records 2,395 methods across 141 classes and three categories. These counts overlap where names refer to the same code and do not enumerate all C functions.
- The [dependency catalog](../../catalog/ios/23A355/dyld-dependencies.json) records five direct loads for CoreFoundation, including an upward Foundation load and a `libobjc.A.dylib` re-export. Foundation declares a CoreFoundation re-export. These are static load commands, not observed runtime bindings.

The wrappers make CoreFoundation a useful next stop for studying event and timer scheduling, but this pass does not decompile `__CFRunLoopRunSpecificWithOptions`, identify the active mode on the phone, trace UIKit into it, or establish a hook point.

## Reproduce

Follow the [acquisition record](../../docs/acquisition-23A355.md), verify the image UUID and derivative hash above, then run:

`xcrun llvm-objdump -m -d --dis-symname _CFRunLoopRun .local/rea/extracted/CoreFoundation`

`xcrun llvm-objdump -m -d --dis-symname _CFRunLoopRunInMode .local/rea/extracted/CoreFoundation`

The disassembly and Apple binary stay local; only the derived observations are published.
