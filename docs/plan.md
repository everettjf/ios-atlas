# Research and delivery plan

Status: the first official-firmware catalog and [public explorer](https://xnu.app/ios-atlas/) are implemented, 2026-11-05. See [the acquisition record](acquisition-23A355.md) for exact coverage.

## Initial target and known access

The Mac recognized one trusted USB device through `ipsw idev list`: iPhone 11 (`iPhone12,1`, `N104AP`, arm64e), iOS 26.0.1, build `23A355`. A root shell was verified through a locally pinned SSH key over the USB tunnel. The RootHide namespace presents `/rootfs` as the base system view while `/` is remapped for the jailbreak. The exact restore IPSW was downloaded, integrity-checked, and indexed.

The repository was cloned from `everettjf/ios-atlas` and was empty at the time of cloning. The first dataset and website are now published through GitHub Pages.

## Why dyld shared cache changes the catalog

A path under `/System/Library/Frameworks`, `/System/Library/PrivateFrameworks`, or `/usr/lib` can be the logical install name of a library whose code resides in a dyld shared cache. A directory walk alone is therefore not an inventory of system libraries. Apple's cache-layout documentation describes a shared cache as one or more files containing segments copied from source dylibs. Modern caches can have subcaches, so analysis must preserve and validate the entire cache family, not just its first file.

The catalog will keep three distinct object types:

1. **Filesystem entry:** a path actually observed in an IPSW filesystem image or on a device, with type, size, hash where appropriate, and source.
2. **Cache file:** each physical dyld cache or subcache file, with its path, size, hash, architecture, UUID or other available identity, and parent build.
3. **In-cache image:** a dylib or framework image enumerated from the cache, with its logical install name, cache membership, UUID and other available Mach-O metadata. An in-cache image is not counted as a separate on-disk file unless independently observed there.

An extracted dylib is an **analysis derivative**. Its path and hash must never be presented as the original on-device file path and hash. A library may also exist outside the cache; the catalog must not assume every dylib is in it.

References: [Apple dyld cache layout](https://github.com/apple-oss-distributions/dyld/blob/main/doc/CacheLayout.md), [ipsw documentation and examples](https://github.com/blacktop/ipsw), [Apple signed system volume](https://support.apple.com/guide/security/signed-system-volume-security-secd698747c9/web).

## Evidence and comparison rules

Every record will identify `product_type`, `build`, `architecture`, `source_kind` (`ipsw`, `device`, or `derived`), acquisition time, tool/version, and source artifact hash. A finding may be `observed`, `inferred`, or `unknown`; absence is claimed only within a named, successfully scanned source.

The official IPSW is the **stock distribution baseline**. A post-jailbreak live filesystem is a separate **device observation**. The phone has historical jailbreak state, so an IPSW-versus-device difference alone cannot prove that Relaxin created a path. User data, generated caches, mounts, firmlinks, and jailbreak additions need separate labels. A causal before/after comparison requires a true pre-jailbreak snapshot from the same device and build, which we do not currently have.

Do not commit firmware, extracted Apple binaries, cache files, device identifiers, credentials, or user data. Keep raw artifacts in a local ignored workspace; publish only derived indexes and authored research after review.

## Work phases

### 0. Fix the acquisition contract — completed

- Record the exact target identity above and the public IPSW URL in a local acquisition manifest.
- Confirm the firmware download and extraction plan, available disk space, and cache file naming from the real build.
- Verify whether the paired phone exposes a root shell; do not treat USB pairing as proof of jailbreak access.
- Define `complete`, `partial`, and `failed` states for each collection step. A failed scan must not silently appear complete.

**Done when:** the source artifact, target build, tool versions, and expected outputs are recorded before collecting data.

### 1. Index the stock firmware — archive, system, restore and kernel metadata completed

- Acquire the exact `iPhone12,1` / `23A355` restore image and verify its download hash against the distributor's metadata when available.
- Inventory the relevant filesystem images and their mount or extraction boundaries. Preserve symlinks and file types; do not follow links in a way that double-counts entries.
- Extract the complete arm64e dyld cache family. Record every cache/subcache file, then enumerate in-cache images directly from the intact cache.
- Index all 127 IPSW archive members and their BuildManifest roles. The five disk images have separate mounted-content catalogs. The two kernelcache variants have Mach-O and kext metadata catalogs. Other firmware payloads have artifact metadata but have not been decompiled; none is counted as an ordinary root filesystem file.

**Done when:** a user can search both physical files and logical in-cache images for the exact build, and the coverage report names every image or volume that was processed or skipped.

### 2. Observe the jailbroken device — filtered system-path inventory and cache identity completed

- Read only: record mounted volumes, firmlink/symlink boundaries, visible file metadata, cache identity, and the jailbreak prefix. The first published device inventory contains 430,719 paths and types from selected `/rootfs` system roots; all occur with the same type in the official IPSW indexes. File content hashes outside the cache remain pending.
- Separate Apple system locations, device-generated data, and jailbreak-owned locations. Exclude private user areas from publication.
- Compare cache identities and selected file hashes to the IPSW where the sources are truly comparable.

**Done when:** each displayed difference says what was compared and whether its origin is established or merely suspected.

### 3. Add relationships and research notes — Foundation example completed; deeper traces pending

- For selected images, index imported libraries, ObjC/Swift metadata, relevant launchd services, and process ownership.
- Follow one user-visible behavior from entry point through framework and service, confirming static hypotheses with bounded runtime observation where needed.
- Keep analysis evidence and uncertainty attached to each claim. Use REA for focused binary questions after selecting an exact artifact; do not infer execution from decompilation alone.

**Done when:** one complete, reviewable component page has source build, evidence, dependencies, and known gaps.

### 4. Publish the website — first build completed through GitHub Pages

- Build a static site with separate **Files**, **Shared-cache images**, **Components**, and **Build comparison** views.
- A library page shows its logical install name and cache membership, not a fictitious standalone file.
- Include source and coverage badges on every page; generate the site from validated catalog data.

**Done when:** a visitor can find a library absent from the ordinary file tree, see why it is absent, inspect its metadata, and trace the supporting source.

## First technical spike

The installed `ipsw` is 3.1.739. Its locally checked help advertises these operations, to be run against the exact acquired cache after validating the real paths:

```sh
ipsw dyld info --dylibs --json <MAIN_DSC>
ipsw dyld macho <MAIN_DSC> <FULL_INSTALL_NAME> --json --loads
ipsw dyld imports <MAIN_DSC> <FULL_INSTALL_NAME>
ipsw class-dump <MAIN_DSC> <FULL_INSTALL_NAME>
```

`ipsw dyld extract` is reserved for a selected image when another analysis tool needs a standalone Mach-O; the primary inventory comes from the intact cache. `ipsw idev fsyms` can retrieve device linker/cache files if firmware and live cache identity need reconciliation, but this may transfer a large amount of data and has not been run.

The first spike validated the cache parser against the intact 80-file iOS and 3-file DriverKit arm64e cache families and inspected Foundation's Mach-O metadata. The built site compares physical file presence against logical install names. Additional samples and runtime investigations are future research.
