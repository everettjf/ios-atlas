# Which named code symbols are visible in the jailbreak installation?

## Exact device evidence

The [live Mach-O inventory](Live-Jailbreak-MachO.md) contains 463 publishable files acquired from the connected iPhone 11 (`iPhone12,1`, iOS 26.0.1, build `23A355`). Each acquired file matched a device-side SHA-256 hash. A device-specific randomized filename remains withheld.

The [symbol collector](../../tools/catalog_live_jailbreak_symbols.py) rechecks each acquired file hash, inspects all 493 Mach-O architecture slices, verifies each slice UUID, and runs `ipsw macho info --symbols --demangle`. It accepts named symbol-table records only when their addresses lie inside an executable `__text` section of that slice. Repeated architecture labels are handled by extracting the exact fat slice to a private temporary file. The site builder validates the complete catalog against the published Mach-O inventory and checks each symbol's address and name before publication.

## Coverage

- **181,792** named `__text` records across **493 slices** in **463 files**. Names repeated across architectures are counted per slice.
- **49 files** have no named `__text` records in any slice; **55 slices** have none.
- **168,142** `__text` rows had no name. **613** duplicate named rows were removed within slices, and **320** rows labeled as `__text` lay outside the actual code section and were excluded.
- The public browser shows each name with its architecture, address, segment, and symbol-table visibility. Names are loaded by file on demand.

A name may be an alias, generated label, or private implementation detail. A missing name does not imply absent code. This is a static inventory of symbol-table records, not every function, a runtime load trace, or a validated tweak hook. Objective-C methods and direct dylib load declarations are indexed separately.
