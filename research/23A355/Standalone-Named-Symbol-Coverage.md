# Which named code symbols are visible in standalone Mach-O files?

Target: all **3,363** physical Mach-O files in the three cataloged system images of the official iPhone 11 iOS 26.0.1 (`23A355`) IPSW, SHA-256 `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`. The [file inventory](Standalone-MachO-Coverage.md) distinguishes these files from logical dyld-cache images.

An exact-file `ipsw macho info --symbols --demangle` pass yielded **323,061 unique named `__text` symbol records** in **1,200 files**. The other 2,163 files had no names within their executable `__text` sections. The collector retained 4,116 duplicate raw rows as counts rather than displaying them twice. It excluded 332,240 unnamed text-section rows and 2,163 named rows whose addresses were outside the reported `__text` section, including header-style labels. The 35 GPU executable files have no matching executable `__text` section under this criterion.

The symbol and [Objective-C method](Standalone-ObjC-Method-Coverage.md) passes reveal different surfaces. Among the 334 files for which the class dump reported no ObjC information, **100 still have named `__text` symbols**. Conversely, 1,594 files have indexed ObjC methods but no named `__text` symbols. A missing name is therefore not evidence of missing code. Names can identify C or C++ functions, but may also be private, aliases, generated symbols, or non-function labels. This index is a **symbol-table view**, not a complete enumeration of functions, callable APIs, or runtime behavior.

Every mounted file was checked against the standalone inventory by size and complete SHA-256. The collector matched each Mach-O UUID, read executable segment load commands, and required every published address to fall within a `__text` section of the named segment. This includes kext code in `__TEXT_EXEC`, not just ordinary `__TEXT`. Raw symbol output and resumable per-file checkpoints remain outside Git. The public catalog contains derived names, addresses, section names, visibility labels, source hashes, and explicit excluded-row counts.

The [Standalone Mach-O explorer](https://xnu.app/ios-atlas/#macho) shows a per-file symbol count. Selecting **Browse named `__text` symbols** loads one of 64 compressed buckets and lets readers search names and addresses. For example, the physical `/usr/lib/dyld` file has 3,287 unique named records in this build; a small stripped app may have no named records even when its ObjC method list is nonempty.

The aggregate source catalog is [`standalone-symbols.json.gz`](../../catalog/ios/23A355/standalone-symbols.json.gz). To regenerate it with the exact mounted images:

`python3 tools/catalog_standalone_symbols.py --macho-catalog catalog/ios/23A355/standalone-macho.json.gz --filesystem-root .local/mount-fs --systemos-root .local/mount-sys --appos-root .local/mount-app --workdir .local/standalone-symbol-work --output catalog/ios/23A355/standalone-symbols.json.gz --workers 4`
