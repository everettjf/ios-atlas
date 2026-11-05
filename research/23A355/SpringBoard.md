# SpringBoard: from launchd declaration to cached framework

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`). Static evidence comes from the official restore IPSW with SHA-256 `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`.

## Observed chain

1. The FileSystem image contains `/System/Library/LaunchDaemons/com.apple.SpringBoard.plist` (SHA-256 `30a04d78624e2ec5274aacf1882470b030df1d3552a87fa37eac0428aaa19222`). Its `Label` is `com.apple.SpringBoard`, its `ProgramArguments[0]` is `/System/Library/CoreServices/SpringBoard.app/SpringBoard`, its declared user is `mobile`, and it declares 39 Mach service names. The executable path also occurs as a regular file in the FileSystem catalog.
2. That executable has SHA-256 `188cef45c06b69dba1f4cbcfb30be85faa6d1c703638ae3ec3c3371f9a03c3f3`. REA/Ghidra identifies its local `entry` at `0x100000568` as a thunk to `_SBSystemAppMain`, and that thunk points to an external `_SBSystemAppMain` imported from `/System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard`. REA Evidence: `ev_2f476096cb74b7b891103bbaa5ecc26416371499ed5fccd47bcf85c60fb82dd9`.
3. The executable has `LC_LOAD_DYLIB` commands for SpringBoard.framework, Foundation, `libobjc.A.dylib`, and `libSystem.B.dylib`. REA Evidence: `ev_4de480e295d07e8f769ab0d716989293f887c3253834445749a5db28e915ad38`.
4. The intact SystemOS arm64e dyld shared cache lists the SpringBoard.framework image at that logical install name, with UUID `8676BE2A-9484-3492-888E-7DE10333250F`. None of the three mounted installed-system images has a standalone regular file at that path. `ipsw dyld macho <MAIN_DSC> /System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard --symbols` lists external `_SBSystemAppMain` at `0x21d604c60`.
5. The [service Mach-O index](../../catalog/ios/23A355/service-macho.json) records all four direct imports of the SpringBoard executable and matches each install name to an image in the same build's iOS shared cache. This is an exact static catalog match, not an observed runtime load.

## Interpretation

The launchd plist, disk executable, and in-cache framework are three distinct objects. The disk executable is a small entry point that imports the framework function; the cache holds an image exporting that function. This is a concrete example of why locating only the on-disk app executable would miss the component code of interest.

The REA header-only dylib trace marks absolute system-library paths as `outside-target`, so it does not prove a live dyld resolution or that this job ran on the connected phone. The cache catalog independently establishes that the named framework image is present in this official build. The 39 Mach names are declarations, not observed IPC traffic.

## Reproduce

The plist and its fields are in [`launchd.json`](../../catalog/ios/23A355/launchd.json). The executable and framework-image paths are in [`filesystem.json.gz`](../../catalog/ios/23A355/filesystem.json.gz) and [`dyld.json`](../../catalog/ios/23A355/dyld.json). Follow [the acquisition record](../../docs/acquisition-23A355.md) to obtain the exact IPSW and cache. Open the mounted SpringBoard executable in REA with the Ghidra provider; run `list_procedures` and `trace_dylib_resolution`. Inspect the exact cache image with the `ipsw dyld macho` command above. The REA snapshot and Apple binaries remain local, outside Git.
