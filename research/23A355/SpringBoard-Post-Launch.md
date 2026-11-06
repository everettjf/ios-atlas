# What does SpringBoard set up after UIKit calls its launch delegate?

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`), SystemOS arm64e dyld cache UUID `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`. The inspected image is `/System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard`, Mach-O UUID `8676BE2A-9484-3492-888E-7DE10333250F`. Its local `ipsw dyld extract` derivative has SHA-256 `7732a59763b6fa34a52bfe8531d6dc0fcfa69761f6a96f438c0cda3363bb20be`; the binary is not published.

The [launch-chain note](SpringBoard.md) follows launchd to the small disk executable, and the [startup note](SpringBoard-Startup.md) follows `_SBSystemAppMain` to UIKit's `UIApplicationMain`. This note inspects one later function, `-[SpringBoard applicationDidFinishLaunching:]` at `0x21d6a1a48`, in the exact extracted image. It is a bounded static reading, not a device execution trace.

## Direct instruction evidence

- At `0x21d6a1b20`, the method directly calls `_SBCommonInitialize`.
- At `0x21d6a1cf4`, it sends `checkInPorts` to a receiver whose identity is not established by this instruction alone.
- At `0x21d6a1eac–0x21d6a1ec4`, it reloads one receiver and consecutively sends `_startSystemStatusServerAndFriends`, `_prepareBacklightServices`, and `_setUpHUDControllerAndFriends`. The register setup establishes the common receiver at these three call sites; the selector names do not establish the called methods' effects.
- At `0x21d6a1fd0–0x21d6a1fdc`, it obtains a `sharedInstance` and sends `completeStartup` to that returned object. The class of that object is not resolved here.
- Later call sites include `initWithWindowSceneManager:` at `0x21d6a2d08`, `initWithStartupOrientation:` at `0x21d6a31c0`, and `initWithDisplayManager:sceneManagerCoordinator:assertionCoordinator:powerLogReporter:` at `0x21d6a330c`. These are evidence of setup-oriented messages, not proof of which objects are constructed or which scene becomes visible.

The method also contains startup signpost literals including `SB_STARTUP_COMMON_INIT`, `SB_STARTUP_USER_SESSION_CONTROLLER`, and `SB_STARTUP_SERVICES`. The sequence of instruction addresses gives code layout and local call order. Branches, callbacks, and errors can change actual execution order; no duration or successful completion is inferred from these names.

The framework has [52,025 indexed Objective-C method entries](SpringBoard-Method-Surface.md) and 244 direct Mach-O load declarations. Its declared loads include UIKit, FrontBoardServices, BackBoardServices, Foundation, and CoreFoundation. UIKit itself re-exports UIKitCore in the [exact dependency catalog](../../catalog/ios/23A355/dyld-dependencies.json). These declarations connect the layers statically; they do not prove live loading or a safe tweak hook.

## Reproduce and limits

Use the exact cache identified in the [acquisition record](../../docs/acquisition-23A355.md), extract this image into ignored `.local` storage, verify the SHA-256 and UUID above, then run:

`xcrun llvm-objdump -m -d --dis-symname '-[SpringBoard applicationDidFinishLaunching:]' .local/rea/extracted/SpringBoard`

The selected instruction addresses above are in that output. A REA/Ghidra attempt to analyze this 96 MB image did not finish within the tool's five-minute call limit; this note makes no decompiler claim. The receivers and effects of selected messages, the full control-flow graph, actual runtime path, and hook safety remain unverified.
