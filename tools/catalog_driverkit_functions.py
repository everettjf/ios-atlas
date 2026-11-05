#!/usr/bin/env python3
"""Catalog named DriverKit __text functions from one exact firmware cache."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run(*command: str) -> bytes:
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"{command[:2]} exited {result.returncode}: "
                           f"{result.stderr.decode(errors='replace')[-500:]}")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-main', type=Path, required=True)
    parser.add_argument('--dyld-catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    dyld = json.loads(args.dyld_catalog.read_text())
    if (dyld['source'] != 'official_ipsw_systemos' or
            dyld['platform'] != 'Driverkit' or
            dyld['kind'] != 'dyld_shared_cache' or
            dyld['file_count'] != len(dyld['files']) or
            dyld['image_count'] != len(dyld['images']) or
            args.cache_main.name != f"dyld_shared_cache_{dyld['architecture']}"):
        raise ValueError('not the expected complete DriverKit cache catalog')
    for item in dyld['files']:
        path = args.cache_main.parent / item['name']
        if not path.is_file() or path.stat().st_size != item['size'] or sha256(path) != item['sha256']:
            raise ValueError(f"DriverKit cache member differs from catalog: {item['name']}")

    images = []
    for index, image in enumerate(dyld['images'], 1):
        name = image.get('install_name', image.get('name'))
        print(f"[{index}/{len(dyld['images'])}] {name}", flush=True)
        macho_bytes = run('ipsw', 'dyld', 'macho', str(args.cache_main), name, '--json', '--no-color')
        macho = json.loads(macho_bytes)
        uuid = [load['uuid'] for load in macho['loads'] if load['load_cmd'] == 'LC_UUID']
        text = [load for load in macho['loads'] if load['load_cmd'] == 'LC_SEGMENT_64' and load['name'] == '__TEXT']
        if len(uuid) != 1 or uuid[0] != image['uuid'] or len(text) != 1:
            raise ValueError(f"Mach-O identity or __TEXT segment mismatch: {name}")
        sections = [section for section in text[0]['sections'] if section['name'] == '__text']
        if len(sections) > 1:
            raise ValueError(f"multiple __text sections: {name}")
        lo = sections[0]['addr'] if sections else 0
        hi = lo + sections[0]['size'] if sections else 0
        symbol_bytes = run('ipsw', 'dyld', 'macho', str(args.cache_main), name,
                           '--symbols', '--demangle', '--no-color')
        symbols = []
        for line in symbol_bytes.decode('utf-8', errors='replace').splitlines():
            if '(__TEXT,__text)' not in line:
                continue
            fields = line.split('\t')
            match = re.fullmatch(r'(0x[0-9a-f]+):\s+\(__TEXT,__text\)\s+(.+)', fields[0])
            if not match or len(fields) < 2 or not fields[1]:
                raise ValueError(f"unrecognized defined function symbol in {name}: {line[:140]}")
            addr = int(match[1], 16)
            if not lo <= addr < hi:
                raise ValueError(f"function symbol outside __text in {name}: {match[1]}")
            symbols.append([match[1], fields[1], match[2]])
        raw_symbol_count = len(symbols)
        symbols = [list(row) for row in dict.fromkeys(tuple(row) for row in symbols)]
        symbols.sort(key=lambda row: (int(row[0], 16), row[1]))
        dump_bytes = run('ipsw', 'class-dump', str(args.cache_main), name,
                         '--re', '-V', '--no-color')
        dump_text = dump_bytes.decode('utf-8', errors='replace')
        toc = {key: int(value) for key, value in re.findall(
            r'  (__objc_classlist|__objc_catlist|__objc_protolist)\s+=\s+(\d+)', dump_text[:600])}
        if dump_text and set(toc) != {'__objc_classlist', '__objc_catlist', '__objc_protolist'}:
            raise ValueError(f"incomplete Objective-C table of contents: {name}")
        if any(toc.get(key, 0) for key in ('__objc_classlist', '__objc_catlist')) or '@interface ' in dump_text:
            raise ValueError(f"Objective-C declarations need separate parsing: {name}")
        images.append({
            'install_name': name,
            'uuid': image['uuid'],
            'macho_toc_sha256': hashlib.sha256(macho_bytes).hexdigest(),
            'symbol_dump_sha256': hashlib.sha256(symbol_bytes).hexdigest(),
            'class_dump_sha256': hashlib.sha256(dump_bytes).hexdigest(),
            'class_dump_empty': not bool(dump_bytes),
            'objc_toc': toc,
            'text_address': hex(lo),
            'text_size': hi - lo,
            'named_function_count': len(symbols),
            'duplicate_symbol_table_entry_count': raw_symbol_count - len(symbols),
            'functions': symbols,
        })
    output = {
        'schema_version': 1,
        'kind': 'driverkit_named_text_functions',
        'source': 'official_ipsw_intact_cache_family',
        'tool': 'ipsw dyld macho --symbols --demangle',
        'product_type': dyld['product_type'],
        'build': dyld['build'],
        'firmware_sha256': dyld['firmware_sha256'],
        'cache_uuid': dyld['cache_uuid'],
        'cache_files_sha256': {item['name']: item['sha256'] for item in dyld['files']},
        'image_count': len(images),
        'named_function_count': sum(image['named_function_count'] for image in images),
        'images': images,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(json.dumps(output, separators=(',', ':'),
                                               sort_keys=True).encode() + b'\n', mtime=0))
    print(f"indexed {output['named_function_count']} named __text functions in {len(images)} images")


if __name__ == '__main__':
    main()
