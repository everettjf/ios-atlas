# Device-first plan: iPhone 11 / iOS 26.0.1 (23A355)

## Goal and boundary

Map the **currently jailbroken iPhone 11** as it is observed now: its visible files, physical dyld cache files, logical in-cache libraries, standalone Mach-O binaries, services, and a first-pass description of each library's exposed metadata. The official `23A355` IPSW remains a source of exact-build binary metadata and provenance, but the live device is the primary answer to “what is on this phone?”. No second firmware build or cross-version comparison is part of this plan. The partially acquired local `23B85` material is outside the publication pipeline.

“All files” means every traversable path in the named live filesystem namespaces at a recorded observation time, with scan failures and inaccessible areas counted explicitly. A path in a volatile or synthetic mount is labeled as such. Symlinks are recorded without following them; bind mounts, firmlinks, cryptexes, and the RootHide `/rootfs` view are documented before de-duplication. This is a repeatable **snapshot**, not a promise that mutable files cannot change during the scan.

Keep a full local metadata inventory for the owner's review. The public site contains system and jailbreak-owned paths that pass a privacy review. User and app data paths may themselves reveal private information, so publish their mount-level counts and redacted structure only; never publish their names, contents, identifiers, or hashes. Raw firmware, caches, binaries, keys, and private observations stay out of Git.

## Current evidence

- The official `23A355` firmware has 452,096 entries across FileSystem, SystemOS, and AppOS; 4,170 iOS cache images; 51 DriverKit images; and 3,363 standalone Mach-O files. The cache method and named-symbol indexes already cover every exact iOS cache image. See [acquisition](acquisition-23A355.md).
- The first published device catalog contained **only** 430,719 paths beneath seven `/rootfs` system roots. The newer private scan visited 12 views and found 531,311 path observations; two data-volume views were partial because of protected directories. Its privacy-reviewed public export contains 439,365 distinct system and jailbreak installation paths; one randomized device-specific filename is withheld. See [boundary note](../research/23A355/Stock-Device-Boundary.md) and [collection procedure](live-device-collection.md).
- All 80 iOS and three DriverKit physical cache files were previously checked against the device by SHA-256. This proves those cache bytes at that observation time, not that every other firmware file matches the running phone.
- A read-only SHA-256 pass matched all 3,157 standalone firmware Mach-O files observed at mapped device paths; 206 firmware staging paths had no same-path file record. See [identity note](../research/23A355/Live-Standalone-Identity.md).
- The 463 public, device-hash-verified jailbreak Mach-O files now have a per-slice named `__text` index: 181,792 records across 493 slices, with 49 files lacking names. See [symbol coverage](../research/23A355/Live-Jailbreak-Symbols.md).
- Swift dumps now cover all 493 slices of those same verified files, yielding 15,772 parsed declarations and 8,062 member or requirement lines; 456 slices have no Swift info and eight outputs are partial. See [Swift coverage](../research/23A355/Live-Jailbreak-Swift.md).
- All 493 verified jailbreak slices have parsed embedded CodeDirectories; the public site shows identifiers, CDHashes, signing flags, and entitlement parse counts without claiming trust. See [code-signing coverage](../research/23A355/Live-Jailbreak-Code-Signing.md).
- The site now opens with device files and no longer exposes a `Compare builds` tab. It marks the two data-volume roots as partial and lists the completed roots explicitly.
- On 2026-11-05, CopyApp's saved device-specific SSH profile authenticated this exact phone as both `mobile` and `root`. A private mount discovery found 11 kernel mount targets plus the RootHide jailbreak namespace. The first `/rootfs/System/Developer` pilot recorded 177 entries without errors.

## Work order and acceptance gates

### 1. Define and record the live namespaces

Read-only collection of product/build, observation time, mount table, APFS/cryptex layout, `/` versus `/rootfs`, jailbreak prefix, firmlinks, and cache locations. Assign each mount a stable source label. List all traversable roots and explicit exclusions before the large scan. Check that the device still reports `iPhone12,1` / `23A355`; stop if its build changed.

**Gate:** a local namespace map identifies every scanned mount, duplicate view, inaccessible root, and synthetic/volatile area. No path is silently treated as a normal on-disk file.

### 2. Capture the whole live path inventory locally

Extend the collector to enumerate path, type, size, mode, symlink target, mount ID, namespace, and scan outcome without reading file contents. Walk system volumes, cryptexes, preboot, the jailbreak prefix, and the data volume; keep user/app paths in a private local output. Use bounded batches, NUL-safe names, checkpointing, and a manifest that marks each root `complete`, `partial`, or `failed`. Do not cross mounts implicitly or follow symlinks. Review paths for personal data before deriving any public catalog.

**Gate:** every in-scope mount has an entry count and error count; all path records point to a recorded mount; interrupted scans cannot masquerade as complete. A second count pass or sampled directory checks validate the snapshot. Publication remains blocked until the privacy filter is reviewed.

### 3. Reconcile code on this device

Inventory and hash the physical iOS and DriverKit cache families in their live locations. Link their previously indexed logical images to the verified cache UUIDs/hashes. Identify every **live standalone Mach-O** from the publishable system and jailbreak paths, including executables, dylibs, bundles, frameworks, app extensions, tweak injection components, and trust/launch helpers. Record full-file hash, architecture, UUID, code-signing identity when available, and exact live path. Reuse the existing `23A355` firmware analysis only when bytes or exact binary identity justify the link; otherwise analyze the observed file separately. Keep ordinary files, physical caches, and logical images as distinct records.

**Gate:** every public code-bearing live file has a provenance and analysis status (`inspected`, `unsupported`, or `failed`); cache images do not appear as fictitious standalone files; mismatched or unverified binaries are visibly labeled.

### 4. Publish broad library and file pages

Make **Device files** the default site view. Browse the live mount tree and search by path, file type, owner category, executable/library kind, framework, service, and source. Library pages show one concise purpose sentence where supported, install name or live path, architecture/UUID, dependencies, ObjC classes and methods, named symbols, Swift metadata, associated services, and evidence links. Empty metadata results are explicit. Add a coverage dashboard with totals and gaps by mount and analysis type. Remove the `Compare builds` tab and stop treating a second build as a prerequisite. Keep firmware records as an exact-build reference, with clear source labels; the stock/device path comparison becomes a provenance note rather than the main navigation.

**Gate:** a visitor can browse every publishable live path and every verified cache image, see why a cache image may have no standalone file, and distinguish device observation from firmware-derived analysis. The site never exposes a private path through search, links, generated JSON, or build artifacts.

### 5. Add first-pass reverse-engineering notes and TODOs

Start with a horizontal inventory: short, evidence-backed introductions for library families; per-image methods/symbols/dependencies; and a category for unknown purpose. Add focused notes for the jailbreak loader/injection path, SpringBoard, Foundation, WidgetKit, and representative services. A note should cite exact binary identity, relevant declarations or disassembly addresses, observed versus inferred behavior, and open questions. Record deeper call tracing, runtime validation, and tweak hypotheses as separate TODOs. Never turn a symbol name alone into a claim about runtime behavior or a safe hook.

**Gate:** every library has at least an honest metadata overview and a visible research state; focused notes are reproducible and link back to the exact observed or byte-matched artifact.

## Immediate next implementation slice

1. Inspect the two partial data-volume scans and document their inaccessible scope; keep their reachable paths and stderr private.
2. Reconcile live standalone code against the exact-build firmware records by hash or UUID, then analyze jailbreak-only binaries separately.
3. Expand library pages from metadata overview to source-backed purpose, observed device identity, dependencies, methods, and explicit open questions.

The [research TODO](research-todo.md) tracks the remaining library-level work. The earlier [research and delivery plan](plan.md) documents the first firmware-centered implementation and its existing evidence; this document governs the next phase.
