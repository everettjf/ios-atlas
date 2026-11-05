# Reading Foundation's static dependency reach

Target: iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`). The source is the official IPSW with SHA-256 `2773217713e94b81fbbaa6ecb6b7e87fb176f58f5edefdb868d8d71ec6547bd2`, iOS cache UUID `C0A7E671-35E1-3E6C-842D-FCE4E0A08C7E`.

## Observed paths

- The cached Foundation image (`/System/Library/Frameworks/Foundation.framework/Foundation`, UUID `0555AF54-2075-3F2D-BC40-733E55EEE95A`) declares 29 direct Mach-O dylib loads, including two `LC_LOAD_WEAK_DYLIB` commands.
- Following only exact in-cache install-name matches and excluding weak commands reaches 123 other images. Including weak commands at every step reaches 1,353. The count excludes Foundation itself. These are graph reachability counts, not images observed in one process.
- One two-step chain without weak loads is Foundation `LC_LOAD_DYLIB` → CFNetwork `LC_LOAD_DYLIB` → `/usr/lib/libsqlite3.dylib`. Both edges occur in the [direct-load catalog](../../catalog/ios/23A355/dyld-dependencies.json).
- One direct weak edge is Foundation `LC_LOAD_WEAK_DYLIB` → `/System/Library/PrivateFrameworks/CoreAutoLayout.framework/CoreAutoLayout`. It appears in the [interactive dependency view](https://xnu.app/ios-atlas/#reach/%2FSystem%2FLibrary%2FFrameworks%2FFoundation.framework%2FFoundation) only when weak loads are included.

## Interpretation

The large difference between 123 and 1,353 illustrates how optional edges can expand a transitive static graph. A shortest path answers *which declared chain connects these cached install names* under the selected edge rule. It does not establish that dyld followed the chain, that a weak target resolved, that Foundation called the target's code, or that all reachable images were loaded in one process. Other paths to the same image can exist; the website displays one shortest chain.

## Reproduce

The [dependency catalog](../../catalog/ios/23A355/dyld-dependencies.json) records every image UUID and its direct load commands. [The graph logic](../../site/reach.mjs) performs breadth-first search, ignores nonmatching install names, and guards against cycles. `node tools/test_reach.mjs` checks cycle, weak-load, unmatched-target, and shortest-path behavior on a small graph. The website computes reachability from the validated catalog in the browser; no extracted Apple binary is published.
