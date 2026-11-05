# Live device collection and publication

Target: the currently connected `iPhone12,1` on iOS `23A355`. This workflow is read-only on the phone. It scans metadata and symlink targets, never file contents. Raw results contain private paths and remain under ignored `.local`.

## Preconditions

The USB device must report the exact product/build above, and an existing pinned root SSH connection must work. iCTRL can confirm the device and operate Relaxin's UI, but its API has no filesystem or shell method. The ordinary AFC service is limited to `/var/mobile/Media`; this phone did not expose AFC2 when checked on 2026-11-05. Do not infer root access from pairing or from a running `jailbreakd` process.

The collector validates the device identity and mount-table digest before continuing an earlier snapshot. If either changes, use a new `.local` output directory. The local USB tunnel and SSH credential paths are operator inputs; they do not enter the snapshot JSON. Example with an already working pinned key:

```sh
ipsw idev proxy -l 22326 -r 22
python3 tools/collect_live_device.py --port 22326 --identity <EXISTING_KEY> --known-hosts .local/device-known-hosts --product iPhone12,1 --build 23A355 --output-dir .local/live-device --discover-only
```

Review `.local/live-device/manifest.json` and `.local/live-device/mount.txt` privately. The manifest lists actual mount roots plus the RootHide `/rootfs` alias if present. Run a pilot with explicit roots before the full scan:

```sh
python3 tools/collect_live_device.py --port 22326 --identity <EXISTING_KEY> --known-hosts .local/device-known-hosts --product iPhone12,1 --build 23A355 --output-dir .local/live-device --only-root /rootfs
python3 tools/collect_live_device.py --port 22326 --identity <EXISTING_KEY> --known-hosts .local/device-known-hosts --product iPhone12,1 --build 23A355 --output-dir .local/live-device
```

The full pass enumerates each discovered mount independently with `find -xdev`; symlinks are not followed. Files named with newlines are preserved through a NUL-delimited protocol. Each root gets a compressed JSONL file, count, SHA-256, and `complete`/`partial` status. A partial root is retried on the next run. Local stderr files may include private paths. Duplicate namespace views remain distinct until a reviewed mapping exists. Because the phone can change during collection, the result is a time-bounded observation, not an atomic filesystem snapshot.

## Public export

Create a **private** `.local/live-device/allowlist.json` after reviewing actual mounts and paths. Its schema is `{"schema_version":1,"prefixes":["/rootfs/System"]}`. The exporter accepts only hardcoded system and jailbreak prefix families; broad `/`, `/private`, and `/var/mobile` exports are rejected. Add the actual jailbreak prefix only after inspecting it. The export strips UID/GID, inode, mount source, symlink target, and all path records outside the allowlist.

```sh
python3 tools/export_live_device.py --manifest .local/live-device/manifest.json --allowlist .local/live-device/allowlist.json --output .local/live-device/public-candidate.json.gz
```

Review the candidate's paths and counts, then copy only that reviewed file to `catalog/ios/23A355/device-live.json.gz`. `tools/build_site.py` independently revalidates every public path against the reviewed prefixes before copying it into `dist`. The website labels published scope and the number of completed snapshot roots; it must never imply that unpublished user/app paths are absent from the device.

Tests: `python3 tools/test_live_device_pipeline.py` checks NUL-safe filenames, exact symlink targets, rejection of private prefixes, and the site builder's second privacy gate.
