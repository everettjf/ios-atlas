#!/usr/bin/env python3
"""Check static load-name classifications and the public rebuild gate."""

import gzip
import json
import tempfile
import unittest
from pathlib import Path

import build_site
from catalog_live_load_targets import catalog


BUILD = "23A355"
PRODUCT = "iPhone12,1"


def fixtures():
    ios = {"kind": "dyld_shared_cache", "platform": "iOS", "build": BUILD,
           "product_type": PRODUCT, "cache_uuid": "I" * 32, "image_count": 1,
           "images": [{"install_name": "/usr/lib/libCache.dylib", "uuid": "C" * 32}]}
    driverkit = {"kind": "dyld_shared_cache", "platform": "Driverkit", "build": BUILD,
                 "product_type": PRODUCT, "cache_uuid": "D" * 32, "image_count": 0,
                 "images": []}

    def source(family, source_name, install_name, loads):
        path = f"/rootfs/System/Developer/{family}.dylib" if family == "developer" else "/usr/lib/jailbreak.dylib"
        sha = "a" * 64 if family == "developer" else "b" * 64
        part = {"architecture": "arm64e", "uuid": "U" * 32}
        macho = {"kind": f"live_{family}_macho_inventory", "source": source_name,
                 "build": BUILD, "product_type": PRODUCT, "macho_file_count": 1,
                 "records": [{"path": path, "sha256": sha, "slices": [part]}]}
        dependencies = {"kind": f"live_{family}_direct_dependencies",
                        "source": source_name, "build": BUILD, "product_type": PRODUCT,
                        "macho_file_count": 1,
                        "files": [{"path": path, "sha256": sha, "slice_count": 1,
                                   "slices": [{**part, "install_name": install_name,
                                               "dependencies": [{"install_name": name,
                                                                 "load_command": "LC_LOAD_DYLIB"}
                                                                for name in loads]}]}]}
        return macho, dependencies

    sources = {
        "developer": source("developer", "verified_live_developer_mount_bytes",
                            "/System/Developer/libLive.dylib", ["/usr/lib/libCache.dylib",
                            "@rpath/libLive.dylib", "/usr/lib/missing.dylib"]),
        "jailbreak": source("jailbreak", "verified_live_device_macho_bytes",
                            "@rpath/libLive.dylib", ["/System/Developer/libLive.dylib"]),
    }
    return ios, driverkit, sources


class StaticLoadTargetTests(unittest.TestCase):
    def test_exact_names_are_links_but_tokenized_names_remain_unresolved(self):
        ios, driverkit, sources = fixtures()
        result = catalog(ios, driverkit, sources)
        self.assertEqual(result["totals"], {"files": 2, "loads": 4,
                         "cache_install_name": 1, "live_install_name": 1,
                         "tokenized_name": 1, "no_exact_match": 1})
        developer = result["files"][0]["slices"][0]["loads"]
        jailbreak = result["files"][1]["slices"][0]["loads"]
        self.assertEqual(developer[0]["targets"][0]["kind"], "ios_cache")
        self.assertEqual(developer[1]["targets"], [])
        self.assertEqual(developer[2]["targets"], [])
        self.assertEqual(jailbreak[0]["targets"][0]["family"], "developer")
        sources["developer"][1]["files"][0]["sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "hash"):
            catalog(ios, driverkit, sources)

    def test_public_builder_recomputes_and_rejects_tampered_match(self):
        ios, driverkit, sources = fixtures()
        with tempfile.TemporaryDirectory() as name:
            base = Path(name)
            for filename, value in (("dyld.json", ios),
                                    ("driverkit-dyld.json", driverkit)):
                (base / filename).write_text(json.dumps(value))
            for family, (macho, dependencies) in sources.items():
                for suffix, value in (("macho", macho), ("dependencies", dependencies)):
                    (base / f"{family}-{suffix}.json.gz").write_bytes(
                        gzip.compress(json.dumps(value).encode(), mtime=0))
            expected = catalog(ios, driverkit, sources)
            candidate = base / "live-load-targets.json.gz"
            candidate.write_bytes(gzip.compress(json.dumps(expected).encode(), mtime=0))
            previous = build_site.DIST
            try:
                build_site.DIST = base / "dist"
                info = build_site.publish_live_load_targets(BUILD, PRODUCT, base)
                self.assertEqual(info["live_load_target_count"], 4)
                self.assertTrue((build_site.DIST / info["live_load_target_url"]).is_file())
                expected["files"][0]["slices"][0]["loads"][1]["status"] = "live_install_name"
                candidate.write_bytes(gzip.compress(json.dumps(expected).encode(), mtime=0))
                with self.assertRaisesRegex(ValueError, "differs"):
                    build_site.publish_live_load_targets(BUILD, PRODUCT, base)
            finally:
                build_site.DIST = previous


if __name__ == "__main__":
    unittest.main()
