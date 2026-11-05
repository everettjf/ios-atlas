# Mach-O files in the live jailbreak installation tree

## What was observed

On 2026-11-05, the connected iPhone 11 reported iOS 26.0.1 (`23A355`). A pinned, device-specific SSH key authenticated the same phone over USB. The RootHide SSH namespace exposes the base system at `/rootfs` and a separate jailbreak installation tree at `/`. A read-only `find -xdev` walk completed for the jailbreak tree with 8,485 entries, including 6,449 regular files. The [collection procedure](../../docs/live-device-collection.md) records the mount mapping and the two protected data-volume gaps.

GNU `file` identified 464 Mach-O files in that jailbreak tree. A device-side SHA-256 pass covered all 464. The same 464 paths were copied into a private local archive; every extracted file matched its device-side hash. A bounded Mach-O header and load-command parser then read all files without an error. The public index contains paths, sizes, hashes, architecture, file type, and `LC_UUID` where present. Executable bytes remain private.

The 464 private files contain 495 Mach-O slices: **323 executable**, **143 dylib**, and **29 bundle** slices. One filename contains a device-specific RootHide random suffix, so the public index withholds that file and publishes **463 files / 493 slices**. Fat binaries account for the difference between file and slice counts. These are files in the jailbreak installation namespace; they do not include the 4,170 logical iOS shared-cache images or every Mach-O in the base system. A `.dylib` filename count would miss shared-library slices inside other containers.

## What the index does not establish

- A file's presence and load commands do not prove that a running process loaded it.
- Hash and UUID identify these acquired bytes at the observation time; the device may change after collection.
- An exact-file class dump now covers all 463 published files. It found 4,781 static Objective-C method entries in 61 files; 402 files reported no ObjC information. Named symbols, Swift declarations, direct dependencies, and code-signing identities remain unindexed for this live set.
- The data-volume scan was partial because of protected directories. This note does not claim every possible executable on the phone was readable.

Next: run the remaining horizontal metadata passes on these verified files, link their direct dependencies to cache images and other live files, and give libraries short source-backed descriptions before tracing selected method bodies. The [research TODO](../../docs/research-todo.md) tracks that work.
