# Which libraries do standalone firmware binaries declare?

The [Standalone Mach-O explorer](https://xnu.app/ios-atlas/#macho) now records direct Mach-O load commands for **all 3,363** regular standalone binaries in the exact iPhone 11 iOS 26.0.1 (`23A355`) FileSystem, SystemOS, and AppOS images. The 3,363 architecture slices declare **73,257 direct library loads**. The catalog also retains 1,802 runpaths; 53 slices have no direct loads. Each file page shows the load-command kind, declared install name, own install name where present, and runpaths. A library-name link searches the iOS cache; a search result is not proof that dyld chose that image at runtime.

The source is the official IPSW with SHA-256 `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`. The collector checked each mounted file's complete SHA-256 against the existing standalone inventory before running `ipsw macho info --json --loads`; it also checked the returned `LC_UUID` against the header inventory. The site builder requires an exact match for all 3,363 volume/path/file-hash/slice-UUID tuples, recalculates totals, and rejects private or malformed load names. Raw IPSW bytes and inspection checkpoints remain local. No runpath required redaction in this pass.

These are **direct static declarations**, including weak, re-export, upward, and lazy loads. They do not establish which process launched a file, whether a weak load resolved, how `@rpath` expanded, whether the target was supplied by a cache, or whether the same bytes are currently on the device. The separate [live identity pass](Live-Standalone-Identity.md) verified 3,157 standalone firmware files by device-side SHA-256; the other 206 remain firmware-reference records. Runtime resolution and function-body tracing are in the [research TODO](../../docs/research-todo.md).

Reproduce from read-only mounted images:

`python3 tools/catalog_standalone_dependencies.py --macho-catalog catalog/ios/23A355/standalone-macho.json.gz --filesystem-root .local/mount-fs --systemos-root .local/mount-sys --appos-root .local/mount-app --workdir .local/standalone-dependency-work --output .local/standalone-dependencies.json.gz`
