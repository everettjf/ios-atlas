# Foundation in the iOS 26.0.1 shared cache

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`), arm64e.

## Observed

- The official FileSystem image contains `/System/Library/Frameworks/Foundation.framework` as a directory, but no regular file at `/System/Library/Frameworks/Foundation.framework/Foundation`.
- The SystemOS dyld shared cache lists that latter path as an in-cache image. Its UUID is `0555AF54-2075-3F2D-BC40-733E55EEE95A`, and the cache UUID is `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`.
- `ipsw dyld macho <cache> /System/Library/Frameworks/Foundation.framework/Foundation --json --loads` reports `DylibInCache` in the Mach-O flags. Its load commands include reexports of `/usr/lib/libobjc.A.dylib` and `/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation`.

## Interpretation

The framework bundle path and the executable image are different catalog objects. A filesystem-only explorer would show the bundle while missing its executable code; a cache-only explorer would miss the resources in the bundle. The Atlas links both under the same logical install name without inventing an on-disk executable.

The [Foundation.framework directory in the Atlas](https://xnu.app/ios-atlas/#files/%2FSystem%2FLibrary%2FFrameworks%2FFoundation.framework) shows its observed resource files and the logical Foundation cache image in separate sections.

The [Foundation method-surface note](Foundation-Method-Surface.md) traces 11,045 Objective-C method entries back to this same cache image and its exact build.

This is a static observation of the official firmware. It does not establish which Foundation methods a particular process executes at runtime.

## Reproduce

The published indexes are [`filesystem.json.gz`](../../catalog/ios/23A355/filesystem.json.gz) and [`dyld.json`](../../catalog/ios/23A355/dyld.json). The extraction command, exact firmware hash, and tool version are recorded in [the acquisition notes](../../docs/acquisition-23A355.md). The source IPSW and full cache stay local.
