# What function names are visible in the DriverKit cache?

Target: the separate DriverKit arm64e cache from the official iPhone 11 iOS 26.0.1 (`23A355`) restore IPSW, SHA-256 `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`. Cache family UUID: `5CC15334-F5B0-3971-93BB-4FDDCE6F4BE7`.

The [DriverKit image explorer](https://xnu.app/ios-atlas/#driverkit) covers all **51** logical images. `ipsw dyld macho --symbols --demangle` yielded **65,668 unique named `__TEXT,__text` symbol records** across them. The original symbol output contained 5,296 additional rows identical in address, name, and visibility; the derived index records these duplicate counts instead of presenting them as additional names. Two images have no matching named records. Each image page lists its names and addresses, with local search and progressive display.

This is a **symbol-table view**, not an enumeration of every function, C++ method, or callable API. A name may be private, an alias, or compiler generated; a record does not prove runtime execution. The command demangles C++ names where possible. All recorded addresses were checked against the image's own Mach-O `__text` section, and every image UUID was checked against the independent DriverKit cache inventory. Before scanning, all three physical cache-family files were checked by SHA-256 against that inventory. The catalog retains the SHA-256 of each raw symbol output, Mach-O table of contents, and class dump; raw cache bytes and command outputs remain local.

`ipsw class-dump --re -V` succeeded for all 51 images. None yielded an Objective-C class, category, or method declaration; 48 returned an empty file and the other three reported zero class/category counts. This bounded result does not mean the images have no callable functions. The separate iOS dyld cache has its own [ObjC method catalog](Method-Catalog-Coverage.md).

To regenerate from the exact extracted local cache:

`python3 tools/catalog_driverkit_functions.py --cache-main .local/driverkit/23A355__iPhone12,1/dyld_shared_cache_arm64e --dyld-catalog catalog/ios/23A355/driverkit-dyld.json --output catalog/ios/23A355/driverkit-functions.json.gz`
