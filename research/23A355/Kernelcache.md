# Two kernelcache variants in the iPhone 11 restore IPSW

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`). Source: the official restore IPSW with SHA-256 `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`.

## Observed

- The IPSW contains both `kernelcache.release.iphone12b` and `kernelcache.research.iphone12b`. These are two archive artifacts, not two observed running kernels.
- After decompression, both parse as arm64e Mach-O `FILESET` images. Both report Darwin `25.0.0` and XNU `12377.2.9~1`. Their Mach-O UUIDs differ: release `FF7B4C89-4C36-6E92-9771-FB767E41C476`; research `F55B37F0-CAF2-BA23-7810-89585562057B`.
- Each fileset contains 239 `LC_FILESET_ENTRY` load commands. The `ipsw kernel kexts --json` parser returns 256 unique extension metadata records for each variant. These counts describe different structures and should not be treated as equal.
- An extension record includes a bundle identifier, version, optional bundle path, and declared bundle dependencies. It is metadata parsed from the kernelcache; it does not establish that a standalone `.kext` file exists on the installed filesystem or that the extension is loaded at runtime.

## Interpretation and next question

The restore package provides two kernelcache variants for the same target build. The `research` label is an IPSW archive filename, not evidence that this device booted it. To identify the running variant, compare a trustworthy on-device kernel identity with the published UUID and build metadata. To understand an individual extension's behavior, select its exact fileset image for focused static analysis and, when appropriate, confirm a hypothesis on the device.

## Reproduce

The archive membership and hashes are in [`firmware-archive.json`](../../catalog/ios/23A355/firmware-archive.json); parsed kernel metadata is in [`kernel.json`](../../catalog/ios/23A355/kernel.json). The exact extraction, decompression, and parser commands appear in [the acquisition record](../../docs/acquisition-23A355.md). Neither kernelcache binary is committed.
