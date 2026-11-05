#!/usr/bin/env python3
"""Regression checks for NUL-safe snapshots and the public privacy boundary."""

from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import build_site
from collect_live_device import PRIVATE_ROOT, private_path, records_from_chunks, scan_command
from export_live_device import export


class LiveDevicePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)

    def test_gnu_find_protocol_preserves_symlink_target(self) -> None:
        root = "/rootfs/System"
        payload = (b"/rootfs/System/link\0"
                   b"11|777|0|0|42|9|1790739622.5|l\0"
                   b"line\nbreak\0")
        rows = list(records_from_chunks([payload[:13], payload[13:]], root))
        self.assertEqual(rows, [["/rootfs/System/link", "symlink", 11, 0o777,
                                 0, 0, 42, 9, 1790739622, "line\nbreak"]])
        self.assertIn("-printf", scan_command(root))

    @unittest.skipUnless(sys.platform == "darwin", "Darwin stat protocol")
    def test_scan_keeps_newlines_and_symlink_targets(self) -> None:
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as temporary:
            root = Path(temporary).resolve()
            (root / "line\nbreak").write_bytes(b"abc")
            (root / "shortcut").symlink_to("line\nbreak")
            result = subprocess.run(["sh", "-c", scan_command(str(root), "darwin")],
                                    check=True, capture_output=True)
            rows = list(records_from_chunks([result.stdout[:7], result.stdout[7:]], str(root)))
            by_name = {Path(row[0]).name: row for row in rows}
            self.assertEqual(by_name["line\nbreak"][1:3], ["file", 3])
            self.assertEqual(by_name["shortcut"][9], "line\nbreak")
            with self.assertRaises(ValueError):
                list(records_from_chunks([result.stdout[:-1]], str(root)))

    def test_private_paths_do_not_enter_public_catalog_or_site(self) -> None:
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as temporary:
            root = Path(temporary).resolve()
            records = [
                ["/rootfs/System/Library/code", "file", 3, 0, 0, 0, 1, 1, 0, None],
                ["/private/var/mobile/secret.txt", "file", 7, 0, 0, 0, 2, 1, 0, None],
            ]
            blob = gzip.compress("".join(json.dumps(row) + "\n" for row in records).encode(), mtime=0)
            (root / "root.jsonl.gz").write_bytes(blob)
            manifest = {
                "schema_version": 1, "kind": "private_live_device_snapshot",
                "product_type": "iPhone12,1", "build": "23A355",
                "observed_at_utc": "2026-11-05T00:00:00Z", "roots": [{"path": "/"}],
                "scans": {"/": {"status": "complete", "file": "root.jsonl.gz",
                                 "sha256": hashlib.sha256(blob).hexdigest(), "entry_count": 2}},
            }
            (root / "manifest.json").write_text(json.dumps(manifest))
            (root / "allowlist.json").write_text(json.dumps({"schema_version": 1,
                                                             "prefixes": ["/rootfs/System"]}))
            public = export(root / "manifest.json", root / "allowlist.json")
            self.assertEqual(public["entries"], [["/rootfs/System/Library/code", "file", 3]])
            self.assertNotIn("secret.txt", json.dumps(public))
            candidate = root / "public.json.gz"
            candidate.write_bytes(gzip.compress(json.dumps(public).encode(), mtime=0))
            old_dist = build_site.DIST
            try:
                build_site.DIST = root / "dist"
                (build_site.DIST / "data").mkdir(parents=True)
                info = build_site.publish_live_device("23A355", "iPhone12,1", candidate)
                self.assertEqual(info["device_count"], 1)
                published = gzip.decompress((build_site.DIST / info["device_url"]).read_bytes())
                self.assertNotIn(b"secret.txt", published)
                public["entries"][0][0] = "/private/var/mobile/secret.txt"
                candidate.write_bytes(gzip.compress(json.dumps(public).encode(), mtime=0))
                with self.assertRaises(ValueError):
                    build_site.publish_live_device("23A355", "iPhone12,1", candidate)
                public["entries"][0][0] = "/rootfs/System/../../private/var/mobile/secret.txt"
                candidate.write_bytes(gzip.compress(json.dumps(public).encode(), mtime=0))
                with self.assertRaises(ValueError):
                    build_site.publish_live_device("23A355", "iPhone12,1", candidate)
            finally:
                build_site.DIST = old_dist
            (root / "allowlist.json").write_text(json.dumps({"schema_version": 1,
                                                             "prefixes": ["/private/var/mobile"]}))
            with self.assertRaises(ValueError):
                export(root / "manifest.json", root / "allowlist.json")
            with self.assertRaises(ValueError):
                private_path(root.parent.parent / "catalog" / "bad.json")
            (root / "allowlist.json").write_text(json.dumps({"schema_version": 1,
                                                             "prefixes": ["/rootfs/System"]}))
            manifest["roots"].append({"path": "/rootfs/System/Library"})
            (root / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "incomplete mount coverage"):
                export(root / "manifest.json", root / "allowlist.json")


if __name__ == "__main__":
    unittest.main()
