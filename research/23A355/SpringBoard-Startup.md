# What happens before SpringBoard enters UIKit?

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`). Source: official restore IPSW SHA-256 `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`, SystemOS arm64e dyld cache family UUID `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`. This note inspects `_SBSystemAppMain` in the cache's `/System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard` image, Mach-O UUID `8676BE2A-9484-3492-888E-7DE10333250F`.

The framework was extracted for local analysis with `ipsw dyld extract`. That 96 MB derivative has SHA-256 `7732a59763b6fa34a52bfe8531d6dc0fcfa69761f6a96f438c0cda3363bb20be`. It is not a standalone file observed on the phone or in a mounted installed-system image. The [launch-chain note](SpringBoard.md) identifies the preceding launchd declaration and disk executable.

## Observed instructions

`_SBSystemAppMain` begins at `0x21d604c60` in this extracted image. These instruction addresses and call targets were checked with [`verify_springboard_startup.py`](../../tools/verify_springboard_startup.py), using Apple's `llvm-objdump`, `llvm-nm`, and `dwarfdump` from `xcrun`.

- `0x21d604c88–0x21d604c8c`: Saves incoming `x1` and `w0` to stack slots, later reloaded as `argv` and `argc` by the usual arm64 calling convention.
- `0x21d605c20`: Branches past a version-comparison block when `x19` is zero.
- `0x21d605c30–0x21d605c5c`: Calls `compareBuildVersion:withPrecision:`; a conditional branch can bypass `deleteAllSystemSnapshots` and `_setClearSystemAppSnapshotsWhenLoaded:`. These calls are present in the code, not proven to run on every start.
- `0x21d605c70–0x21d605cb4`: Two `compareBuildVersionString:withPrecision:` calls each have a branch around `_setClearAllLegacySnapshotsWhenLoaded:`.
- `0x21d605cd8`: Calls `migrateAndRemoveOldDefaults`.
- `0x21d605d2c`, `0x21d605ec4`: Contains calls to `setLastSystemBuildVersion:` and `setLastRestoreIdentifier:` later in the function. Their runtime paths require further tracing.
- `0x21d606054–0x21d606064`: Calls `removeAllImagesWithCompletion:` on a session cache, then `earlyInitialization`.
- `0x21d6060f8–0x21d606104`: Reloads saved `argc` into `w0` and `argv` into `x1`, then branches to `0x2225247a0`. The extracted image's symbol table names that exact target `_UIApplicationMain`.

## Interpretation and limits

The direct static path reaches UIKit's `_UIApplicationMain` after SpringBoard-specific setup and migration instructions. The conditional version and snapshot calls suggest different startup behavior according to stored state. This is a statement about the code in this exact build: no device trace establishes which branches the connected phone took, whether snapshot deletion occurred, or how long initialization took. The calls' side effects also cannot be established from selector names alone.

The branch target is an imported address in the extracted derivative. The symbol match identifies the target, but this analysis does not inspect UIKit's implementation or prove live dyld binding. The `x2`/`x3` values passed to `_UIApplicationMain` have not been resolved here. SpringBoard's later application delegate and scene lifecycle methods remain separate questions in the [lifecycle note](SpringBoard-Lifecycle.md). This analysis is not yet enough to choose a reliable tweak hook.

## Reproduce

Follow the [acquisition record](../../docs/acquisition-23A355.md) to obtain and verify the exact IPSW and intact cache. Extract only the SpringBoard.framework image into ignored `.local` storage as shown in the [lifecycle note](SpringBoard-Lifecycle.md), then run:

`python3 tools/verify_springboard_startup.py .local/rea/extracted/SpringBoard`

The script refuses a different SHA-256 or Mach-O UUID, verifies 19 address-specific instructions, and checks that the direct branch target is named `_UIApplicationMain`. Apple binaries and full disassembly remain local; this note publishes only derived observations.
