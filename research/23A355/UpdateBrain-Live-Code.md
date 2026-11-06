# Which live update binaries are visible?

Target: the connected iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`). A read-only pass on 2026-11-06 UTC found two Mach-O files in the Software Update mount view. Their physical paths are withheld because this mount is outside the reviewed public path allowlist. Both appeared in a fresh private path snapshot, were acquired separately, and matched their device-side SHA-256 values byte for byte. Neither complete-file hash nor Mach-O UUID appears in the [3,363-file official standalone inventory](../../catalog/ios/23A355/standalone-macho.json.gz). They are therefore analyzed from the **observed live bytes**, without assigning them to the stock firmware image.

- `UpdateBrainLibrary.dylib`: SHA-256 `6205e3fa64a30b66c7750b7e6dfe40a8962e01748f8bdf592faea1e3cb59d5ad`; 5,365,536 bytes; arm64 dylib; UUID `BEA4473C-3037-360E-83D6-19DD2902183C`. `ipsw class-dump --re -V` parsed 105 classes, 8 categories, 26 rendered protocols, and 1,551 Objective-C method entries; load commands declare 35 direct dylib dependencies.
- `com.apple.MobileSoftwareUpdate.UpdateBrainService`: SHA-256 `651a357801cd9626644fef741cbf0e6284dfe6de464c22dca5dc5f62018f7c84`; 91,696 bytes; arm64 executable; UUID `F09F05C1-C09F-38C4-8636-DE245CB94B53`. Its class dump yielded no ObjC classes or methods. Four direct dylib loads include `@rpath/UpdateBrainLibrary.dylib`; its runpath declaration is retained privately.

The library's class and protocol names include `MSUNRDUpdateBrainController`, `MSUBootFirmwareUpdater`, `UARPSuperBinaryBackDeploy`, and `MSUBrainInterface` with a `preflightUpdate:` selector. These names and the service's declared load suggest an update orchestration role. They do not prove that the service ran, that dyld resolved this particular library, or that any update operation executed on this phone.

## Service entry and message dispatch

A focused Ghidra 12.1.4 pass over the two **device-acquired** binaries found that the service executable's entry at `0x100000698` is one `b` instruction to its `_update_brain_service_main` import stub at `0x10000069c`. The stub loads a pointer and branches to it. Its import is named `@rpath/UpdateBrainLibrary.dylib::_update_brain_service_main`; the service has no local update workflow to describe beyond that handoff. This is a static import and branch, not a confirmed dyld resolution or process launch.

The library defines `_update_brain_service_main` at `0x37c9c` (analyzed body through `0x380fb`). The recovered call sequence opens a restore log, prepares a queue and three signal sources, installs logging and partition callbacks, probes media, calls `MSUBrainServerImpl::startListener:` at `0x2fca4`, and enters `xpc_main` with `_UpdateBrainService_event_handler` at `0x381c8`. The listener method creates an anonymous `NSXPCListener`, sets its delegate and queue, and resumes it. These are code paths visible in the binary; their effects on this phone have not been observed.

For an incoming connection, the handler sets an event block and target queue, then resumes the XPC connection. The queued block at `0x387ac` reads the `Command` key from a dictionary and passes the message to `_handle_message` at `0x44130`. That function reads `CommandParameters`, searches a seven-entry command table at `0x34d840` (seven 24-byte records), calls `_msu_client_is_entitled` at `0x44304`, and only then invokes the selected handler through a function pointer. The entitlement helper checks for a Boolean XPC entitlement value and returns false when it is absent, false, or not Boolean. An unknown command or failed entitlement leads to an error reply in the recovered control flow. Ghidra did not resolve the indirect handler call as a normal callee edge; the table mapping below comes from its initialized bytes and string records.

- `PreflightUpdate` → `_handle_MSUPreflightUpdate` at `0x38be8`.
- `PrepareUpdate` → `_handle_MSUPrepareUpdate` at `0x3941c`.
- `ApplyUpdate` → `_handle_MSUApplyUpdate` at `0x3963c`.
- `SuspendUpdate` → `_handle_MSUSuspendUpdate` at `0x39744`.
- `ResumeUpdate` → `_handle_MSUResumeUpdate` at `0x397d8`.
- `PingService` → `_handle_MSUPingService` at `0x3984c`.
- `CommitStash` → `_handle_MSUCommitStash` at `0x39a8c`.

Six entries carry the `allow-softwareupdated` entitlement string. `PingService` carries `com.apple.private.softwareupdated-helpers`. The comparison in `_handle_message` uses `strncmp` with the table command's length; whether a longer request string is accepted as a command, and how any client constructs requests, remain untested. A command name or handler address does not establish that a client invoked it, that an update ran, or that the handler is a safe tweak point.

## Evidence boundary

The first private snapshot manifest has SHA-256 `4c5abc1a7f3144c66716b1665accf51f61b7d43977f1d65b937105953e4b3876` and observation time `2026-11-06T03:21:38Z`. It recorded 2,079 reachable regular files in this mount. A type pass a few seconds later saw **2,080**: one path had appeared. Both verified Mach-O files were present, but the changing path set prevented an exhaustive candidate claim from that pass.

A second read-only snapshot at `2026-11-06T03:54:24Z` recorded **2,080** reachable regular files with no scan errors. Its private manifest has SHA-256 `7cfeb2f795fffe0cdb2c7fc9918938e0e23a388de556e940968e1cb56f2dccc2`. A subsequent `file-5.43` pass exited with no stderr and produced exactly the same **2,080 unique paths**. Its private NUL-delimited output has SHA-256 `9236b14945c2a220d09cd6a1361d17d1f9f9ffe36a71b5da3f62c08acbeadc49`. It identified exactly **two ordinary Mach-O candidates**, the same two physical paths as before. A new device-side SHA-256 pass matched both previously acquired binaries. This establishes the ordinary Mach-O candidate count for the reachable files in the second observation, subject to the mount changing again later. The site's published mount-path summary still describes an earlier snapshot with 2,055 regular files; it is not silently replaced by this later observation. The separate partial Data and Mobile data views do not establish complete access to update-related data elsewhere.

The private class-dump outputs have SHA-256 `045658dbcc1554d87fb6713115ca5a96427f279213abb18a2541b3f5cc507bd5` (library) and `2ab8a1b0d2823a531be45720e3bb40d274d786921dedbd2c178e37cb7bd5308c` (service). The private load-command JSON outputs have SHA-256 `a50f1604fc0937a0fc9189b9534b901538cf22a963eb4d616938069d0fa65b49` and `598aef13c839d5141c08b685bce35b2e1219801411bf2f7935d6439400d687e2`. They were parsed with `ipsw` 3.1.739 and checked against the verified Mach-O UUIDs and `__TEXT` address ranges; no raw binary, runpath, or physical device path is published.

The private REA evidence bundles from Ghidra 12.1.4 have SHA-256 `72c89f74504e9bfb79ea04ca777269ef41beb3c3fb673c93fcfa567af906d00b` (service) and `b21b74a674043a412e94ee70bf06c151b78f717a2bce4cc99e499bb3b2dfefdc` (library). They retain the inspected function bodies, exact addresses, command-table bytes, and tool limitations without publishing the binaries or private filesystem paths. The cited addresses use each Ghidra image's analysis coordinates; they are not live process addresses.

Next steps are to inspect the service's declared runpath against its process environment, follow selected command handlers and their clients, and validate any proposed behavior on the device before describing a tweak hook. The type pass does not rule out scripts or embedded code, and no result proves runtime loading.
