# What Swift metadata is visible in the jailbreak installation?

## Evidence and method

The [live Mach-O inventory](Live-Jailbreak-MachO.md) contains 463 publishable files acquired from this iPhone 11 on iOS 26.0.1 (`23A355`), each matching a device-side SHA-256 hash. The [Swift collector](../../tools/catalog_live_jailbreak_swift.py) rechecks those exact file bytes, inspects all 493 architecture slices, verifies each slice UUID, and runs `ipsw swift-dump`. Repeated architecture labels are inspected from their exact fat slices. The site builder checks complete coverage, identity, parse counts, status consistency, and private path patterns before publishing names and member lines.

## Coverage

- **15,772** tool-reported Swift type, protocol, and extension declarations and **8,062** member or requirement lines across the 493 slices.
- **456 slices** reported no Swift information. Their empty results remain explicit. **432 files** have no parsed declarations in any slice.
- **29 slices** parsed without malformed lines; **8 slices** yielded partial parses, with **173** unparsed output lines counted rather than silently accepted.
- **3,300** member lines include a stripped label. The website loads parsed lines for a selected file on demand and labels each with its architecture.

This is a static `ipsw swift-dump` view, not reconstructed Swift source or an exhaustive public API or function list. An empty Swift result does not imply absent code. The partial outputs may omit declarations or members; runtime loading and safe tweak points require separate evidence.
