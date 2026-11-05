# SpringBoard lifecycle entry points in iOS 26.0.1

Target: iPhone 11 (`iPhone12,1`), build `23A355`, iOS arm64e dyld cache UUID `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`. The inspected framework is `/System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard`, Mach-O UUID `8676BE2A-9484-3492-888E-7DE10333250F`.

## Observed

- The stock `com.apple.SpringBoard` launchd plist points to the small disk executable `/System/Library/CoreServices/SpringBoard.app/SpringBoard`. Its entry thunk imports `_SBSystemAppMain` from the cached SpringBoard.framework image, as traced in the [launch-chain note](SpringBoard.md).
- The intact cache exports `_SBSystemAppMain` at `0x21d604c60`. A single-image extraction with `ipsw dyld extract` produced a local 96 MB analysis derivative, SHA-256 `7732a59763b6fa34a52bfe8531d6dc0fcfa69761f6a96f438c0cda3363bb20be`; its Mach-O UUID matches the cache image. The derivative is not a standalone file observed on the phone or in the mounted IPSW volumes.
- `ipsw class-dump` on the intact cache reports `SpringBoard` as a subclass of `UISystemShellApplication` and lists `UIApplicationDelegate` among 16 adopted protocols. This selected class dump contains 645 method declarations (4 class, 641 instance) and 93 property declarations. These counts describe metadata in this image, not a runtime call trace.
- The metadata names several startup-related entry points: `+initializeSystemServicesBeforeApplicationDidFinishLaunching` at `0x21d69fde4`, `-applicationDidFinishLaunching:` at `0x21d6a1a48`, `-_completeStartupAfterMainSceneConnect:` at `0x21d6a41d8`, `-_startBulletinBoardServer` at `0x21d6a1730`, `-_startSystemStatusServerAndFriends` at `0x21d6a38e4`, and `-_initializeDeferredItems` at `0x21d6aafc8`.
- The class's declared instance variables include `_mainWorkspace`, `_lockScreenService`, `_homeScreenService`, `_appSwitcherSystemService`, `_notificationDispatcher`, and `_restartManager`. Their names and offsets are visible in the cache metadata; this observation alone does not establish when or how they are initialized.
- The framework has 244 direct Mach-O dylib load declarations in the [dependency catalog](../../catalog/ios/23A355/dyld-dependencies.json). They describe potential load relationships, not calls from any particular startup method.

## Interpretation and open questions

The static evidence separates three levels: launchd's program declaration, the disk executable's imported entry point, and lifecycle selectors implemented in the cached framework. The method names suggest useful places to investigate service setup, scene connection, and deferred startup. A selector name is only a lead: the call graph, branch conditions, initialization order, and actual device execution still need function-body analysis or bounded runtime observation. No tweak hook is recommended from names alone.

A focused LLVM disassembly now establishes selected direct calls, conditions, and the branch from `_SBSystemAppMain` to `_UIApplicationMain`; see the [startup function note](SpringBoard-Startup.md). It does not establish the internal control flow of the lifecycle selectors listed above or which paths executed on the phone. Their function bodies and a bounded, read-only runtime trace remain follow-up work.

## Reproduce

Use the exact IPSW and intact cache family identified in [the acquisition record](../../docs/acquisition-23A355.md). The following commands keep Apple binary material under the ignored `.local` directory:

`ipsw dyld macho <MAIN_DSC> /System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard --symbols`

`ipsw class-dump <MAIN_DSC> /System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard --class '^SpringBoard$' --re -V`

`ipsw dyld extract <MAIN_DSC> /System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard --output .local/rea/extracted --slide --objc --stubs --cache <MAIN_DSC>.a2s`

The full class dump, extracted binary, and disassembly remain local. Published metadata and this note are derived from the exact build; no live execution is asserted.
