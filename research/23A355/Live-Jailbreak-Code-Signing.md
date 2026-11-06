# What code-signing metadata is embedded in the jailbreak files?

## Exact file scope

The [live Mach-O inventory](Live-Jailbreak-MachO.md) contains 463 publishable files acquired from this iPhone 11 on iOS 26.0.1 (`23A355`), each matched to a device-side SHA-256 hash. The [signing collector](../../tools/catalog_live_jailbreak_signatures.py) rechecks those bytes and all 493 slice UUIDs. It compares `codesign -dvvv`'s selected CDHash with a CodeDirectory parsed from that slice's `LC_CODE_SIGNATURE`. Repeated architecture labels are inspected from exact thin slices. The site builder validates the complete catalog again before publication.

## Observed metadata

- **493 of 493 slices** contain a parseable embedded CodeDirectory.
- `codesign` reports **486 ad hoc** signatures. On **7 slices**, a CodeDirectory exists but `codesign` reports **no CMS signature**. Those seven are not labeled as fully unsigned or as trusted.
- **321 slices** have a parseable entitlement plist, **170** have none in the parsed signature structure, and **2 slices** of `/basebin/opainject` have entitlement text that the plist parser cannot read. The public site shows only entitlement key counts and parse status, not values.
- The parsed `TeamIdentifier` field is unset on all 493 slices. Per-slice CodeDirectory identifiers, CDHashes, hash algorithms, and flags are available on the file detail page.

These fields describe structures inside the exact acquired files. Neither `codesign -d` nor a matching CDHash in two parsers establishes cryptographic validity, certificate trust, AMFI acceptance, or whether a process loaded the file. The code-signing pass does not publish raw signing output, certificates, or entitlement values.
