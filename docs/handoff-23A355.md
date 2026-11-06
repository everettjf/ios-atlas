# iOS Atlas 23A355 handoff

Status: delivery handoff, 2026-11-06.

This document closes the current delivery pass for the **jailbroken iPhone 11 (`iPhone12,1`) on iOS 26.0.1 (`23A355`)**. The [public explorer](https://xnu.app/ios-atlas/) is the delivered artifact. Its snapshot and static indexes are time-bounded observations, not a claim to have read every file on the phone or traced every implementation.

## Delivered scope

- The private snapshot visited 12 live filesystem views. Ten completed; two Data views remained partial. The public, privacy-reviewed catalog contains **439,365 distinct system and jailbreak installation paths**, with fixed format labels for all **225,778** published regular files. User and app path names, one randomized device-specific filename, and raw device data are withheld.
- The code atlas indexes **4,170 iOS dyld shared-cache images**, **51 DriverKit cache images**, and **3,363 standalone Mach-O files from the exact-build IPSW**. It distinguishes logical cache images from physical files and labels firmware-derived and device-observed evidence separately.
- All **3,623 published Mach-O-like live file paths** reconcile to **3,622 device-hash-verified ordinary binaries** and **one byte-matched mixed Metal container**. Objective-C, named-symbol, Swift, direct-load, and signing metadata are available where inspected; empty, partial, and failed outcomes remain explicit.
- The website has **37 research notes**. Every iOS cache image has a static metadata overview and method entry point. Apple Developer sources support functional introductions for **221 of 227 top-level iOS framework images** and one DriverKit image. The other six top-level frameworks have first-pass exact-image notes but no direct Apple functional introduction.
- The site presents one device and build, with no version comparison workflow. The [Coverage view](https://xnu.app/ios-atlas/#coverage) shows scan status and errors without disclosing private paths.

## Boundary at handoff

The two partial Data views encountered **73 distinct directories** that denied traversal. The owner confirmed the phone was unlocked. Root SSH `stat`/`find` and a calibrated native-path `getattrlist` probe still returned `EPERM` for all 73; parent enumeration found the directory names without returning target flags. [The evidence note](../research/23A355/Data-Volume-Type-Boundary.md) records the RootHide path-view calibration and why Data Vault remains a hypothesis rather than an identified cause. Their descendant counts and contents are unknown. Consequently, **whole-device file coverage cannot be expressed as 100%**.

The live snapshot may change over time. Static declarations, symbols, and method lists do not establish runtime loading, complete callable behavior, or safe tweak hook points. Three private encrypted app binaries have unknown Objective-C method counts. Deeper call tracing and runtime validation are [future research](research-todo.md), outside this delivered horizontal pass.

## Rebuild and resume

Run `PYTHONDONTWRITEBYTECODE=1 python3 tools/build_site.py` from the repository root. The resulting `dist/` is ignored by Git; GitHub Pages runs the same build plus privacy checks. The [collection procedure](live-device-collection.md) and [acquisition record](acquisition-23A355.md) provide provenance. Private snapshots, error paths, acquired app binaries, and probe records remain under ignored `.local/`; they must not enter the public catalog without a separate privacy review.

If work resumes, first confirm the exact device and build again, then choose a new timestamped observation. Keep the 73-directory limit explicit until a read-only access route has been verified. The [research TODO](research-todo.md) preserves remaining questions without treating them as a condition of this handoff.
