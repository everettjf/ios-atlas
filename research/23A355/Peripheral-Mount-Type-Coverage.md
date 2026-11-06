# Which small live mounts received a file-type pass?

Target: the connected iPhone 11 (`iPhone12,1`), iOS 26.0.1 (`23A355`). On 2026-11-06 UTC, the device still reported the same build and mount-table SHA-256 as the [private live snapshot](../../docs/live-device-collection.md). A read-only `file-5.43` pass classified every regular-file path in three small, completed mount views. Each NUL-delimited result set matched its corresponding private snapshot path set exactly, with no duplicate path, command failure, or stderr output. Raw results and paths remain under ignored `.local`.

| Reviewed mount label | Reachable regular files classified | Mach-O or universal-binary candidates | Private type-output SHA-256 |
| --- | ---: | ---: | --- |
| Hardware data volume | 85 / 85 | 0 | `abb7d947ba979ca751ca0d7d9b365fcf9ae6c255b92ab922feca25e4c7306005` |
| Baseband data volume | 3 / 3 | 0 | `97e73bb17c89745b637988a48e5c811a0786d1f7d57cf3ddaa92b3436211f83f` |
| xARTS volume | 1 / 1 | 0 | `6b285024f8477c64913da883b6fa0d25b20bd990944aa01dbfee18509d72b817` |

Zero candidates means this `file` pass found no **ordinary Mach-O or universal-binary signature** in the reachable regular files. It does not rule out scripts, encrypted or embedded code, behavior behind device nodes, or files outside these mount views. The two partial data-volume views still have unknown descendants. A later [Software Update follow-up](UpdateBrain-Live-Code.md) reconciled a 2,080-file snapshot with its type pass and rechecked its two ordinary Mach-O candidates; that mount can change again.

To reproduce, use the pinned read-only SSH route to this exact device and run `find <MOUNT> -xdev -type f -exec file -0 -0 -- {} +` for each named mount. Keep raw output private, verify its path set against the corresponding root's compressed JSONL scan in the private manifest, then count only descriptions containing Mach-O or universal-binary signatures. The public [mount coverage catalog](../../catalog/ios/23A355/live-coverage.json) supplies reviewed labels and the earlier regular-file counts, not the private paths.
