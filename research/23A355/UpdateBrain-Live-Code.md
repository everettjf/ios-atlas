# Which live update binaries are visible?

Target: the connected iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`). A read-only pass on 2026-11-06 UTC found two Mach-O files in the Software Update mount view. Their physical paths are withheld because this mount is outside the reviewed public path allowlist. Both appeared in a fresh private path snapshot, were acquired separately, and matched their device-side SHA-256 values byte for byte. Neither complete-file hash nor Mach-O UUID appears in the [3,363-file official standalone inventory](../../catalog/ios/23A355/standalone-macho.json.gz). They are therefore analyzed from the **observed live bytes**, without assigning them to the stock firmware image.

| Reviewed basename | Verified file identity | Static first pass |
| --- | --- | --- |
| `UpdateBrainLibrary.dylib` | SHA-256 `6205e3fa64a30b66c7750b7e6dfe40a8962e01748f8bdf592faea1e3cb59d5ad`; 5,365,536 bytes; arm64 dylib; UUID `BEA4473C-3037-360E-83D6-19DD2902183C` | `ipsw class-dump --re -V` parsed 105 classes, 8 categories, 26 rendered protocols, and 1,551 Objective-C method entries; load commands declare 35 direct dylib dependencies. |
| `com.apple.MobileSoftwareUpdate.UpdateBrainService` | SHA-256 `651a357801cd9626644fef741cbf0e6284dfe6de464c22dca5dc5f62018f7c84`; 91,696 bytes; arm64 executable; UUID `F09F05C1-C09F-38C4-8636-DE245CB94B53` | The class dump yielded no ObjC classes or methods. Four direct dylib loads include `@rpath/UpdateBrainLibrary.dylib`. The runpath declaration is retained privately. |

The library's class and protocol names include `MSUNRDUpdateBrainController`, `MSUBootFirmwareUpdater`, `UARPSuperBinaryBackDeploy`, and `MSUBrainInterface` with a `preflightUpdate:` selector. These names and the service's declared load suggest an update orchestration role. They do not prove that the service ran, that dyld resolved this particular library, or that any update operation executed on this phone.

## Evidence boundary

The fresh private snapshot manifest has SHA-256 `4c5abc1a7f3144c66716b1665accf51f61b7d43977f1d65b937105953e4b3876` and observation time `2026-11-06T03:21:38Z`. It recorded 2,079 reachable regular files in this mount. A type pass a few seconds later saw **2,080**: one path had appeared. Both verified Mach-O files were present in the snapshot, but the changing path set prevents a claim that the two files exhaustively cover all code in this mount. The earlier published mount snapshot had 2,055 regular files. The separate partial Data and Mobile data views also do not establish complete access to update-related data elsewhere.

The private class-dump outputs have SHA-256 `045658dbcc1554d87fb6713115ca5a96427f279213abb18a2541b3f5cc507bd5` (library) and `2ab8a1b0d2823a531be45720e3bb40d274d786921dedbd2c178e37cb7bd5308c` (service). The private load-command JSON outputs have SHA-256 `a50f1604fc0937a0fc9189b9534b901538cf22a963eb4d616938069d0fa65b49` and `598aef13c839d5141c08b685bce35b2e1219801411bf2f7935d6439400d687e2`. They were parsed with `ipsw` 3.1.739 and checked against the verified Mach-O UUIDs and `__TEXT` address ranges; no raw binary, runpath, or physical device path is published.

Next steps are to resnapshot this volatile mount at a stable observation point, inspect the service's declared runpath against its process environment, and trace selected library methods before describing implementation behavior or a tweak hook.
