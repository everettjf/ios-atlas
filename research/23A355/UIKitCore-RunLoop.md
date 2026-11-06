# What does `UIApplication _run` install before entering the event loop?

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`), SystemOS arm64e cache UUID `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`. The inspected `/System/Library/PrivateFrameworks/UIKitCore.framework/UIKitCore` image has UUID `C98EAB32-B273-3430-B0C5-46522C904CBB`. The locally extracted analysis derivative has SHA-256 `fa0602d08391372c60d63aac6e3af356c14b95da25674e28e014489b749ad112`; the binary is not published.

The [entry note](UIKitCore-ApplicationMain.md) establishes an `_run` message from `UIApplicationMain`. The exact class dump lists `-[UIApplication _run]` at `0x188a1cac4`, and the extracted image contains the matching function body.

## Direct instruction evidence

- The first portion sends a series of registration messages, including user-default, time, language, locale, key-bag, and keyboard-layout notifications (`0x188a1cb50–0x188a1cba0`). These call sites do not show which notifications were posted on the connected phone.
- At `0x188a1cc80`, `_run` calls the imported `CFRunLoopGetMain`. At `0x188a1cc8c`, it passes that result to `-[UIEventDispatcher _installEventRunLoopSources:]`.
- `-[UIEventDispatcher _installEventRunLoopSources:]` begins at `0x189d92d90` and returns immediately for a null receiver. For the non-null path, it calls imported `CFRunLoopSourceCreate` at `0x189d92e18` and `0x189d92e64`, then `CFRunLoopAddSource` at `0x189d92e38` and `0x189d92e78`. The first source creation is bypassed when `_UIUpdateCycleEnabled` returns true (`0x189d92de4–0x189d92df8`); the second remains in the shown path. [Apple's API reference](https://developer.apple.com/documentation/corefoundation/cfrunloopaddsource%28_%3A_%3A_%3A%29) explains what adding a source means in public CoreFoundation terms.
- `_run` has a conditional system-app/FrontBoard path that can send `_runWithMainScene:transitionContext:completion:` (`0x188a1ccf4–0x188a1cd40`), plus other branches for a system UI service or extension behavior. These branches prevent treating the method as one linear startup sequence.
- At `0x188a1cdd8`, `_run` calls imported `GSEventRun`. The exact UIKitCore image declares a direct load of GraphicsServices; the [next note](GraphicsServices-Event-Run.md) follows that symbol into the cached GraphicsServices image and its `CFRunLoopRunInMode` call.

This establishes a static bridge from UIKitCore's application runner to CoreFoundation run-loop source setup and GraphicsServices event running. It does not establish which startup branch executed, the identity of every callback attached to the sources, the live run-loop mode, event delivery order, or hook safety.

## Reproduce

Verify the derivative SHA-256 and image UUID above, then run `xcrun llvm-objdump -m -d --dis-symname '-[UIApplication _run]' .local/rea/extracted/UIKitCore` and the same command for `-[UIEventDispatcher _installEventRunLoopSources:]`. Imported function names were cross-checked with `xcrun llvm-nm -n` on the same derivative. The binary and full disassembly stay local.
