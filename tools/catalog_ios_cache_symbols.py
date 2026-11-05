#!/usr/bin/env python3
"""Resume a named __text symbol-table pass over every exact iOS cache image.

The cache family is verified against the official IPSW catalog. Raw command
output and checkpoints stay outside Git; only a complete aggregate is public.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from catalog_standalone_symbols import sha256


TEXT_LINE = re.compile(r'(0x[0-9a-f]+):\s+\(([^,()]+),__text\)\s+(.+)')
OBJC_METHOD = re.compile(r'^[+-]\[.+\]$')


def load(path: Path) -> dict:
    with gzip.open(path, 'rt', encoding='utf-8') as source:
        return json.load(source)


def dump(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(value, separators=(',', ':'), sort_keys=True).encode() + b'\n'
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(gzip.compress(blob, mtime=0))
    temporary.replace(path)


def run(*command: str) -> bytes:
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f'{command[:3]} exited {result.returncode}: '
                           f'{result.stderr.decode(errors="replace")[-500:]}')
    return result.stdout


def parse_symbols(path: Path, sections: list[list]) -> tuple[list[list], Counter]:
    ranges = defaultdict(list)
    for segment, address, length in sections:
        ranges[segment].append((address, address + length))
    records = []
    counts = Counter()
    with path.open('rb') as source:
        for line in source:
            if b',__text)' not in line:
                continue
            text = line.decode('utf-8', errors='replace').rstrip('\r\n')
            fields = text.split('\t')
            match = TEXT_LINE.fullmatch(fields[0])
            if match is None or len(fields) < 2:
                raise ValueError(f'unrecognized __text symbol row: {text[:180]}')
            if not fields[1]:
                counts['unnamed_rows'] += 1
                continue
            address = int(match[1], 16)
            segment = match[2]
            if not any(lo <= address < hi for lo, hi in ranges.get(segment, [])):
                counts['outside_rows'] += 1
                continue
            records.append([match[1], fields[1], match[3], segment])
            counts['raw_named_rows'] += 1
            counts['replacement_chars'] += text.count('\ufffd')
    records = [list(row) for row in dict.fromkeys(tuple(row) for row in records)]
    records.sort(key=lambda row: (int(row[0], 16), row[1], row[2]))
    counts['named_symbols'] = len(records)
    counts['duplicate_rows'] = counts['raw_named_rows'] - len(records)
    counts['objc_method_names'] = sum(bool(OBJC_METHOD.fullmatch(row[1])) for row in records)
    return records, counts


def inspect(image: dict, cache_main: Path, checkpoint_dir: Path) -> dict:
    name = image['install_name']
    key = hashlib.sha256(name.encode()).hexdigest()
    checkpoint = checkpoint_dir / f'{key}.json.gz'
    if checkpoint.exists():
        saved = load(checkpoint)
        if (saved['install_name'], saved['uuid']) != (name, image['uuid']):
            raise ValueError(f'checkpoint identity differs: {checkpoint}')
        return saved
    macho_bytes = run('ipsw', 'dyld', 'macho', str(cache_main), name,
                      '--json', '--no-color')
    macho = json.loads(macho_bytes)
    uuids = [part['uuid'] for part in macho['loads'] if part['load_cmd'] == 'LC_UUID']
    if len(uuids) != 1 or uuids[0] != image['uuid']:
        raise ValueError(f'Mach-O UUID differs from exact cache inventory: {name}')
    sections = [[part['name'], section['addr'], section['size']]
                for part in macho['loads'] if part['load_cmd'] == 'LC_SEGMENT_64'
                and 'x' in part.get('prot', '')
                for section in part.get('sections', []) if section['name'] == '__text']
    raw_path = checkpoint_dir / f'{key}.symbols.raw'
    with raw_path.open('wb') as output:
        result = subprocess.run(['ipsw', 'dyld', 'macho', str(cache_main), name,
                                 '--symbols', '--demangle', '--no-color'],
                                stdout=output, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(f'symbol dump failed for {name}: '
                           f'{result.stderr.decode(errors="replace")[-500:]}')
    symbols, counts = parse_symbols(raw_path, sections)
    record = {'install_name': name, 'uuid': uuids[0],
              'macho_toc_sha256': hashlib.sha256(macho_bytes).hexdigest(),
              'symbol_dump_sha256': sha256(raw_path),
              'text_sections': sections, 'symbols': symbols,
              **{key: counts[key] for key in
                 ('named_symbols', 'raw_named_rows', 'duplicate_rows',
                  'unnamed_rows', 'outside_rows', 'replacement_chars',
                  'objc_method_names')}}
    dump(checkpoint, record)
    raw_path.unlink()
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-main', type=Path, required=True)
    parser.add_argument('--dyld-catalog', type=Path, required=True)
    parser.add_argument('--workdir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    if args.workers < 1 or args.limit < 0:
        parser.error('--workers must be positive and --limit nonnegative')
    dyld = json.loads(args.dyld_catalog.read_text())
    if (dyld['source'] != 'official_ipsw_systemos' or dyld['platform'] != 'iOS' or
            dyld['kind'] != 'dyld_shared_cache' or
            dyld['file_count'] != len(dyld['files']) or
            dyld['image_count'] != len(dyld['images']) or
            args.cache_main.name != f"dyld_shared_cache_{dyld['architecture']}"):
        parser.error('not the expected complete iOS cache catalog')
    for item in dyld['files']:
        path = args.cache_main.parent / item['name']
        if not path.is_file() or path.stat().st_size != item['size'] or sha256(path) != item['sha256']:
            raise ValueError(f'cache member differs from official inventory: {item["name"]}')
    args.workdir.mkdir(parents=True, exist_ok=True)
    pending = [image for image in dyld['images'] if not
               (args.workdir / f'{hashlib.sha256(image["install_name"].encode()).hexdigest()}.json.gz').exists()]
    selected = pending[:args.limit] if args.limit else pending
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(inspect, image, args.cache_main, args.workdir): image
                   for image in selected}
        for number, future in enumerate(as_completed(futures), 1):
            image = futures[future]
            try:
                future.result()
                if number % 100 == 0 or number == len(selected):
                    print(f'inspected {number}/{len(selected)} new cache images', flush=True)
            except Exception as error:
                failures.append((image['install_name'], str(error)))
                print(f'FAILED {image["install_name"]}: {error}', file=sys.stderr, flush=True)
    if failures:
        raise SystemExit(f'{len(failures)} cache image(s) failed; inspect and retry')
    if len(selected) != len(pending):
        print(f'partial pass: {len(selected)} new images; {len(pending)-len(selected)} remain',
              flush=True)
        return
    images = [inspect(image, args.cache_main, args.workdir) for image in dyld['images']]
    totals = Counter()
    for image in images:
        for key in ('named_symbols', 'raw_named_rows', 'duplicate_rows',
                    'unnamed_rows', 'outside_rows', 'replacement_chars',
                    'objc_method_names'):
            totals[key] += image[key]
        totals['images_with_names'] += bool(image['symbols'])
        totals['images_without_names'] += not bool(image['symbols'])
    output = {'schema_version': 1, 'kind': 'ios_cache_named_text_symbols',
              'source': 'official_ipsw_intact_cache_family',
              'tool': 'ipsw dyld macho --symbols --demangle',
              'product_type': dyld['product_type'], 'build': dyld['build'],
              'firmware_sha256': dyld['firmware_sha256'],
              'cache_uuid': dyld['cache_uuid'],
              'cache_files_sha256': {item['name']: item['sha256'] for item in dyld['files']},
              'image_count': len(images), 'totals': dict(totals), 'images': images}
    dump(args.output, output)
    print(f'complete: {len(images)} images, {totals["named_symbols"]} named __text '
          f'symbols -> {args.output}', flush=True)


if __name__ == '__main__':
    main()
