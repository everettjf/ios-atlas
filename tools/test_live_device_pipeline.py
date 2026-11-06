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

    def test_live_macho_requires_a_reviewed_device_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as temporary:
            root = Path(temporary)
            device = root / "device.json.gz"
            device.write_bytes(gzip.compress(json.dumps({
                "entries": [["/usr/bin/tool", "file", 4]]
            }).encode(), mtime=0))
            record = {"path": "/usr/bin/tool", "size": 4, "sha256": "a" * 64,
                      "slices": [{"architecture": "arm64", "file_type": "executable",
                                  "uuid": None}]}
            macho = {"schema_version": 1, "kind": "live_jailbreak_macho_inventory",
                     "source": "verified_live_device_macho_bytes", "build": "23A355",
                     "product_type": "iPhone12,1", "macho_file_count": 1,
                     "failed_count": 0, "failures": [], "records": [record]}
            candidate = root / "macho.json.gz"
            candidate.write_bytes(gzip.compress(json.dumps(macho).encode(), mtime=0))
            old_dist = build_site.DIST
            try:
                build_site.DIST = root / "dist"
                (build_site.DIST / "data").mkdir(parents=True)
                info = build_site.publish_live_macho("23A355", "iPhone12,1",
                                                     candidate, device)
                self.assertEqual(info["device_macho_count"], 1)
                record["path"] = "/private/var/mobile/secret"
                candidate.write_bytes(gzip.compress(json.dumps(macho).encode(), mtime=0))
                with self.assertRaises(ValueError):
                    build_site.publish_live_macho("23A355", "iPhone12,1",
                                                  candidate, device)
                record["path"] = "/basebin/systemhook-0123456789ABCDEF.dylib"
                device.write_bytes(gzip.compress(json.dumps({
                    "entries": [[record["path"], "file", 4]]
                }).encode(), mtime=0))
                candidate.write_bytes(gzip.compress(json.dumps(macho).encode(), mtime=0))
                with self.assertRaises(ValueError):
                    build_site.publish_live_macho("23A355", "iPhone12,1",
                                                  candidate, device)
            finally:
                build_site.DIST = old_dist

    def test_developer_macho_requires_reviewed_live_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as temporary:
            root = Path(temporary)
            candidate = root / "developer.json.gz"
            device = root / "device.json.gz"
            path = "/rootfs/System/Developer/usr/libexec/testmanagerd"
            record = {"path": path, "size": 4, "sha256": "a" * 64,
                      "slices": [{"architecture": "arm64", "file_type": "executable",
                                  "uuid": "B" * 36}]}
            data = {"schema_version": 1, "kind": "live_developer_macho_inventory",
                    "source": "verified_live_developer_mount_bytes",
                    "mount_path": "/rootfs/System/Developer", "build": "23A355",
                    "product_type": "iPhone12,1", "classification_file_count": 1,
                    "macho_file_count": 1, "failed_count": 0, "failures": [],
                    "records": [record]}
            candidate.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
            device.write_bytes(gzip.compress(json.dumps({"entries": [[path, "file", 4]]}).encode(), mtime=0))
            old_dist = build_site.DIST
            try:
                build_site.DIST = root / "dist"
                (build_site.DIST / "data").mkdir(parents=True)
                info = build_site.publish_live_developer_macho(
                    "23A355", "iPhone12,1", candidate, device)
                self.assertEqual(info["developer_macho_count"], 1)
                device.write_bytes(gzip.compress(json.dumps({"entries": []}).encode(), mtime=0))
                with self.assertRaises(ValueError):
                    build_site.publish_live_developer_macho(
                        "23A355", "iPhone12,1", candidate, device)
            finally:
                build_site.DIST = old_dist

    def test_live_dependencies_reject_private_load_names(self) -> None:
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as temporary:
            root = Path(temporary)
            macho_path = root / "macho.json.gz"
            macho_path.write_bytes(gzip.compress(json.dumps({"records": [
                {"path": "/usr/bin/tool", "sha256": "a" * 64,
                 "slices": [{"architecture": "arm64", "uuid": "B" * 36}]}
            ]}).encode(), mtime=0))
            part = {"architecture": "arm64", "uuid": "B" * 36,
                    "load_dump_sha256": "c" * 64, "install_name": None,
                    "dependencies": [{"load_command": "LC_LOAD_DYLIB",
                                      "install_name": "/usr/lib/libSystem.B.dylib"}],
                    "rpaths": ["@loader_path/Frameworks"],
                    "redacted_rpath_count": 1}
            data = {"schema_version": 1,
                    "kind": "live_jailbreak_direct_dependencies",
                    "source": "verified_live_device_macho_bytes",
                    "build": "23A355", "product_type": "iPhone12,1",
                    "macho_file_count": 1,
                    "totals": {"slices": 1, "direct_loads": 1, "rpaths": 1,
                               "redacted_rpaths": 1, "without_loads": 0},
                    "files": [{"path": "/usr/bin/tool", "sha256": "a" * 64,
                               "slice_count": 1, "slices": [part]}]}
            candidate = root / "dependencies.json.gz"
            candidate.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
            old_dist = build_site.DIST
            try:
                build_site.DIST = root / "dist"
                (build_site.DIST / "data").mkdir(parents=True)
                info = build_site.publish_live_dependencies(
                    "23A355", "iPhone12,1", candidate, macho_path)
                self.assertEqual(info["device_macho_direct_load_count"], 1)
                part["rpaths"].append("/Users/person/private-build-path")
                data["totals"]["rpaths"] += 1
                candidate.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
                with self.assertRaises(ValueError):
                    build_site.publish_live_dependencies(
                        "23A355", "iPhone12,1", candidate, macho_path)
            finally:
                build_site.DIST = old_dist

    def test_live_symbols_require_verified_slice_and_public_name(self) -> None:
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as temporary:
            root = Path(temporary)
            macho_path = root / "macho.json.gz"
            symbol_path = root / "symbols.json.gz"
            original = {"path": "/usr/lib/tool.dylib", "sha256": "a" * 64,
                        "slices": [{"architecture": "arm64e", "uuid": "UUID"}]}
            macho_path.write_bytes(gzip.compress(json.dumps({"records": [original]}).encode(), mtime=0))
            slice_record = {"architecture": "arm64e", "uuid": "UUID",
                            "macho_loads_sha256": "b" * 64,
                            "symbol_dump_sha256": "c" * 64,
                            "symbol_dump_replacement_char_count": 0,
                            "text_sections": [["__TEXT", 4096, 256]],
                            "named_symbol_count": 1,
                            "duplicate_symbol_row_count": 0,
                            "unnamed_text_row_count": 0,
                            "outside_text_row_count": 0,
                            "symbols": [["0x1000", "_public_name", "external", "__TEXT"]]}
            data = {"schema_version": 1, "kind": "live_jailbreak_named_text_symbols",
                    "source": "verified_live_device_macho_bytes",
                    "build": "23A355", "product_type": "iPhone12,1",
                    "macho_file_count": 1,
                    "totals": {"slices": 1, "named_symbols": 1, "duplicate_rows": 0,
                               "unnamed_rows": 0, "outside_rows": 0,
                               "slices_without_names": 0, "files_without_names": 0},
                    "files": [{"path": original["path"], "sha256": original["sha256"],
                               "slice_count": 1, "slices": [slice_record]}]}
            old_dist = build_site.DIST
            try:
                build_site.DIST = root / "dist"
                symbol_path.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
                result = build_site.publish_live_symbols(
                    "23A355", "iPhone12,1", symbol_path, macho_path)
                self.assertEqual(result["device_macho_named_symbol_count"], 1)
                slice_record["symbols"][0][1] = "/Users/person/private"
                symbol_path.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
                with self.assertRaises(ValueError):
                    build_site.publish_live_symbols(
                        "23A355", "iPhone12,1", symbol_path, macho_path)
                slice_record["symbols"][0][1] = "_public_name"
                slice_record["symbols"][0][0] = "0x2000"
                symbol_path.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
                with self.assertRaises(ValueError):
                    build_site.publish_live_symbols(
                        "23A355", "iPhone12,1", symbol_path, macho_path)
            finally:
                build_site.DIST = old_dist

    def test_live_swift_requires_verified_slice_and_public_lines(self) -> None:
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as temporary:
            root = Path(temporary)
            macho_path = root / "macho.json.gz"
            swift_path = root / "swift.json.gz"
            original = {"path": "/usr/lib/tool.dylib", "sha256": "a" * 64,
                        "slices": [{"architecture": "arm64e", "uuid": "UUID"}]}
            macho_path.write_bytes(gzip.compress(json.dumps({"records": [original]}).encode(), mtime=0))
            declaration = {"kind": "class", "name": "Tool.Class",
                           "members": [["methods", "func run() -> ()"]]}
            part = {"architecture": "arm64e", "uuid": "UUID", "status": "parsed",
                    "macho_loads_sha256": "b" * 64, "swift_dump_sha256": "c" * 64,
                    "swift_dump_replacement_char_count": 0,
                    "swift_sections": [["__TEXT", "__swift5_types", 4096, 64]],
                    "declaration_count": 1, "member_count": 1,
                    "stripped_member_count": 0, "unparsed_line_count": 0,
                    "kind_counts": {"class": 1, "struct": 0, "enum": 0,
                                    "protocol": 0, "extension": 0, "actor": 0},
                    "declarations": [declaration]}
            totals = {"slices": 1, "parsed": 1, "declarations": 1, "members": 1,
                      "stripped_members": 0, "unparsed_lines": 0,
                      "files_without_declarations": 0, **part["kind_counts"]}
            data = {"schema_version": 1, "kind": "live_jailbreak_swift_declarations",
                    "source": "verified_live_device_macho_bytes", "build": "23A355",
                    "product_type": "iPhone12,1", "macho_file_count": 1,
                    "totals": totals,
                    "files": [{"path": original["path"], "sha256": original["sha256"],
                               "slice_count": 1, "slices": [part]}]}
            old_dist = build_site.DIST
            try:
                build_site.DIST = root / "dist"
                swift_path.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
                result = build_site.publish_live_swift(
                    "23A355", "iPhone12,1", swift_path, macho_path)
                self.assertEqual(result["device_macho_swift_declaration_count"], 1)
                declaration["members"][0][1] = "/Users/person/private"
                swift_path.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
                with self.assertRaises(ValueError):
                    build_site.publish_live_swift(
                        "23A355", "iPhone12,1", swift_path, macho_path)
                declaration["members"][0][1] = "func run() -> ()"
                part["uuid"] = "WRONG"
                swift_path.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
                with self.assertRaises(ValueError):
                    build_site.publish_live_swift(
                        "23A355", "iPhone12,1", swift_path, macho_path)
            finally:
                build_site.DIST = old_dist

    def test_live_signing_requires_verified_slice_and_safe_identity(self) -> None:
        with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT) as temporary:
            root = Path(temporary)
            macho_path = root / "macho.json.gz"
            signing_path = root / "signing.json.gz"
            original = {"path": "/usr/lib/tool.dylib", "sha256": "a" * 64,
                        "size": 1024,
                        "slices": [{"architecture": "arm64e", "uuid": "UUID"}]}
            macho_path.write_bytes(gzip.compress(json.dumps({"records": [original]}).encode(), mtime=0))
            part = {"architecture": "arm64e", "uuid": "UUID",
                    "macho_loads_sha256": "b" * 64, "status": "code_directory",
                    "signature_offset": 800, "signature_size": 200,
                    "identifier": "tool", "team_identifier": None,
                    "cdhash": "c" * 40, "hash_type": "sha256",
                    "flags": "0x2", "flags_label": "adhoc",
                    "signature_state": "adhoc", "entitlement_status": "absent",
                    "entitlement_key_count": 0}
            data = {"schema_version": 1, "kind": "live_jailbreak_code_signatures",
                    "source": "verified_live_device_macho_bytes", "build": "23A355",
                    "tool": "codesign -dvvv and ipsw macho info --json --loads",
                    "product_type": "iPhone12,1", "macho_file_count": 1,
                    "totals": {"slices": 1, "code_directory": 1, "adhoc": 1,
                               "entitlements_absent": 1, "entitlement_keys": 0},
                    "files": [{"checkpoint_schema_version": 3,
                               "path": original["path"], "sha256": original["sha256"],
                               "slice_count": 1, "slices": [part]}]}
            old_dist = build_site.DIST
            try:
                build_site.DIST = root / "dist"
                signing_path.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
                result = build_site.publish_live_signatures(
                    "23A355", "iPhone12,1", signing_path, macho_path)
                self.assertEqual(result["device_macho_code_directory_count"], 1)
                part["identifier"] = "/Users/person/private"
                signing_path.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
                with self.assertRaises(ValueError):
                    build_site.publish_live_signatures(
                        "23A355", "iPhone12,1", signing_path, macho_path)
                part["identifier"] = "tool"
                part["signature_offset"] = 900
                signing_path.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
                with self.assertRaises(ValueError):
                    build_site.publish_live_signatures(
                        "23A355", "iPhone12,1", signing_path, macho_path)
            finally:
                build_site.DIST = old_dist


if __name__ == "__main__":
    unittest.main()
