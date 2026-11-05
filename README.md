# iOS Atlas

An independent, build-specific map of iOS system files, dyld shared-cache images, and their relationships.

The first dataset covers **iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`)**. The [static explorer](https://xnu.app/ios-atlas/) searches 452,096 filesystem entries from three official IPSW images, 4,170 iOS shared-cache images, 51 separate DriverKit cache images, 83 physical cache files, and 430,719 paths in a filtered live device system view.

The same build also indexes every member of the restore IPSW (127 archive entries), both restore RAM disks (4,132 entries), and two kernelcache variants with 256 kext metadata records each. Restore environments and kernelcache metadata have their own views; they are not counted as files on the normally running system.

The **System services** view adds 621 stock launchd plists, their declared executable paths, 2,186 Mach service name declarations, and cryptex-aware path mapping. The [SpringBoard case study](research/23A355/SpringBoard.md) follows one declaration through its disk entry point to an in-cache framework image.

The service dependency index now connects 600 distinct launchd executables to 14,843 direct Mach-O dylib load declarations. The website links each declaration to matching shared-cache images or separate files and shows direct service-consumer counts on cache images.

The **Shared-cache images** view also indexes all 4,170 iOS cache images and their 90,837 direct Mach-O library loads. Each image shows its outgoing loads and incoming cached-image loads, with weak, upward, and re-export commands identified. These are static declarations, not observed runtime calls.

The [research and delivery plan](docs/plan.md) explains why a filesystem walk alone misses many system libraries. The [acquisition record](docs/acquisition-23A355.md) identifies exact inputs and coverage, including a read-only device check: all 83 cache files match the live device by SHA-256, and the published device paths and types occur in the official IPSW indexes. The [Foundation example](research/23A355/Foundation.md) shows why its framework directory and executable image must be distinct records; the [kernelcache note](research/23A355/Kernelcache.md) distinguishes archive variants, fileset entries, and kext metadata.

## Build locally

```sh
python3 tools/build_site.py
python3 -m http.server 8000 --directory dist
```

Open `http://localhost:8000/`. GitHub Pages uses the same build script.

## Repository areas

- `catalog/`: versioned, machine-readable indexes and coverage reports, including restore artifacts, kernel metadata, and a separate filtered device observation.
- `research/`: evidence-backed component and behavior notes.
- `tools/`: reproducible, read-only collection and validation tools.
- `site/`: a searchable static website built from the public catalog.

Raw firmware, dyld caches, extracted Apple binaries, and private device data stay outside Git. Published results contain derived metadata, provenance, and original analysis. The official IPSW is a stock **distribution** baseline, while the live jailbroken device is a separate observation; this project does not imply a clean before/after jailbreak comparison.
