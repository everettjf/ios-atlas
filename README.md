# iOS Atlas

An independent, build-specific map of iOS system files, dyld shared-cache images, and their relationships.

The first dataset covers **iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`)**. The [static explorer](https://xnu.app/ios-atlas/) searches 452,096 filesystem entries from three official IPSW images, 4,170 iOS shared-cache images, 51 separate DriverKit cache images, 3,363 standalone Mach-O files, 83 physical cache files, and 430,719 paths in a filtered live device system view.

The **Filesystem**, **Restore RAM disks**, and **Device system paths** views also browse paths folder by folder. A folder link can be shared directly, such as [Foundation.framework in the stock filesystem](https://xnu.app/ios-atlas/#files/%2FSystem%2FLibrary%2FFrameworks%2FFoundation.framework). The stock folder view lists any logical dyld images under that directory in a separate section; these are not counted as files. Typing in the search field searches the full selected catalog.

The **Stock ↔ device** view compares exact path/type pairs within the seven filtered `/rootfs` system roots. It separates FileSystem, SystemOS, and AppOS source images and lets readers inspect 4,133 stock paths without a same-path device record. The [interpretation note](research/23A355/Stock-Device-Boundary.md) explains why these paths cannot be called jailbreak deletions or whole-device absences.

The same build also indexes every member of the restore IPSW (127 archive entries), both restore RAM disks (4,132 entries), and two kernelcache variants with 256 kext metadata records each. Restore environments and kernelcache metadata have their own views; they are not counted as files on the normally running system.

The **System services** view adds 621 stock launchd plists, their declared executable paths, 2,186 Mach service name declarations, and cryptex-aware path mapping. The [SpringBoard case study](research/23A355/SpringBoard.md) follows one declaration through its disk entry point to an in-cache framework image.

The service dependency index now connects 600 distinct launchd executables to 14,843 direct Mach-O dylib load declarations. The website links each declaration to matching shared-cache images or separate files and shows direct service-consumer counts on cache images.

The **Shared-cache images** view also indexes all 4,170 iOS cache images and their 90,837 direct Mach-O library loads. The separate **DriverKit images** view covers 51 images and 209 direct loads. Each image shows its outgoing loads and incoming cached-image loads, with weak, upward, and re-export commands identified. These are static declarations, not observed runtime calls.

Each iOS cache image now also shows its named `__text` symbols alongside its Objective-C method count. An exact-cache pass found **6,585,655 unique named records** in 3,798 images; 372 yielded no matching names. The lists load only when opened and can be searched per image. The [symbol coverage note](research/23A355/iOS-Cache-Named-Symbol-Coverage.md) explains why this symbol-table view overlaps the method catalog and does not enumerate every function.

The **Dependency reach** view follows those exact in-cache load declarations from a selected iOS image. It lists reachable images and the shortest declaration chain to each one, with separate views that exclude or include weak loads. For Foundation, the build-specific graph reaches 123 images without weak loads and 1,353 when weak loads are included. These are static graph paths, not proof that a process loaded the images.

The **Objective-C classes** view searches 216,890 class entries from the iOS cache optimization table. It links each entry to an exact in-cache image and lets visitors browse the classes associated with an image. Classes in images with duplicate basenames are resolved using their metadata addresses and Mach-O segment ranges.

The **ObjC protocols** view searches 67,351 protocol table entries. A unique image basename maps to one cached image for 49,497 entries; 17,854 entries retain their ambiguous image labels and show the candidate paths. An image-label association is not proof that the image defines or loads that protocol.

The **Swift conformances** view browses 590,036 static type-to-protocol records across 1,553 cached images. Type, protocol, and conformance descriptor addresses are checked against exact Mach-O image segments, including images with duplicate basenames. The site loads one of 64 compressed buckets when a visitor opens an image; raw symbols appear where the inspection tool provided names. This metadata does not establish runtime use.

The **Research** view renders the source-bound component notes on the site, with links to the exact catalog records and source Markdown. Notes can be opened directly by fragment, such as [the SpringBoard launch chain](https://xnu.app/ios-atlas/#research/springboard-launch-chain), [its startup function](https://xnu.app/ios-atlas/#research/springboard-startup), and a [WidgetKit library overview](https://xnu.app/ios-atlas/#research/widgetkit-library-overview) that separates documented APIs from exact-cache method and dependency evidence.

Library pages now show linked Apple Developer introductions for **218 of 227** exact top-level iOS framework images in this cache, plus the base framework in the separate DriverKit cache. The [coverage note](research/23A355/Framework-Introduction-Coverage.md) names the remaining top-level gaps. All other images retain source-derived metadata overviews while the [research TODO](docs/research-todo.md) tracks further functional descriptions. Documentation describes an API family or type, not the complete behavior of this exact binary.

The [**DriverKit images** view](https://xnu.app/ios-atlas/#driverkit) now lists 65,668 unique named `__text` function-symbol records across all 51 images in the separate DriverKit cache, with per-image search. None of those images yielded ObjC class or method declarations in the exact-cache class dump. The [DriverKit coverage note](research/23A355/DriverKit-Function-Surface.md) explains why symbol-table names are a partial view of functions.

The [**Standalone Mach-O** view](https://xnu.app/ios-atlas/#macho) indexes 3,363 physical binaries in FileSystem, SystemOS, and AppOS. Each record has its IPSW volume, path, complete-file SHA-256, Mach-O file type, architecture, and UUID. An exact-file class-dump pass adds 847,771 searchable Objective-C method entries; 334 files explicitly reported no ObjC information. A separate symbol-table pass adds 323,061 unique named `__text` records in 1,200 files. A Swift dump pass adds 282,145 declaration lines and 294,746 method or requirement lines, with 133 partial outputs called out. Lists load only when a visitor opens a file. Two mixed Metal containers with Mach-O and non-Mach-O slices are recorded as exclusions. The [file](research/23A355/Standalone-MachO-Coverage.md), [method](research/23A355/Standalone-ObjC-Method-Coverage.md), [symbol](research/23A355/Standalone-Named-Symbol-Coverage.md), and [Swift](research/23A355/Standalone-Swift-Dump-Coverage.md) notes explain the distinct sources and limits.

The [**Objective-C methods** view](https://xnu.app/ios-atlas/#methods) indexes 3,065,801 static method entries across all 4,170 exact iOS cache images. Each image page provides a brief source-derived overview and a direct link to its compressed method list. An empty method list means the class dump yielded no method entries, not that the library has no code. Ten entries have no decoded selector and remain explicitly unknown. The [coverage note](research/23A355/Method-Catalog-Coverage.md) explains the checks and limits; the [research TODO](docs/research-todo.md) tracks later functional descriptions and deeper implementation studies.

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
