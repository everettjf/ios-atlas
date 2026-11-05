#!/usr/bin/env python3
"""Resume a named __text symbol-table pass over exact standalone Mach-O files."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


TEXT_LINE = re.compile(r'(0x[0-9a-f]+):\s+\(([^,()]+),__text\)\s+(.+)')


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


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


def parse_symbols(data: bytes, sections: list[list]) -> tuple[list[list], int, int, int]:
    by_segment = {}
    for segment, address, size in sections:
        by_segment.setdefault(segment, []).append((address, address + size))
    symbols = []
    unnamed = 0
    outside = 0
    for line in data.decode('utf-8', errors='replace').splitlines():
        if ',__text)' not in line:
            continue
        fields = line.split('\t')
        match = TEXT_LINE.fullmatch(fields[0])
        if match is None or len(fields) < 2:
            raise ValueError(f'unrecognized __text symbol row: {line[:180]}')
        address = int(match[1], 16)
        segment = match[2]
        if not fields[1]:
            unnamed += 1
            continue
        if not any(lo <= address < hi for lo, hi in by_segment.get(segment, [])):
            # Some symbol tables label a Mach-O header as (__TEXT,__text).
            # It is not inside the actual code section, so do not call it a function.
            outside += 1
            continue
        symbols.append([match[1], fields[1], match[3], segment])
    raw = len(symbols)
    symbols = [list(row) for row in dict.fromkeys(tuple(row) for row in symbols)]
    symbols.sort(key=lambda row: (int(row[0], 16), row[1], row[2]))
    return symbols, raw - len(symbols), unnamed, outside


def inspect(item: dict, roots: dict[str, Path], checkpoint_dir: Path) -> dict:
    volume = item['volume']
    relative = Path(item['path'].lstrip('/'))
    if not relative.parts or '..' in relative.parts:
        raise ValueError(f'unsafe catalog path: {volume}:{item["path"]}')
    path = roots[volume] / relative
    key = hashlib.sha256(f'{volume}\0{item["path"]}'.encode()).hexdigest()
    checkpoint = checkpoint_dir / f'{key}.json.gz'
    if checkpoint.exists():
        saved = load(checkpoint)
        if (saved['volume'], saved['path'], saved['sha256']) != (
                volume, item['path'], item['sha256']):
            raise ValueError(f'checkpoint identity differs: {checkpoint}')
        return saved
    if not path.is_file() or path.stat().st_size != item['size'] or sha256(path) != item['sha256']:
        raise ValueError(f'mounted file differs from exact inventory: {volume}:{item["path"]}')
    macho_bytes = run('ipsw', 'macho', 'info', str(path), '--json', '--loads', '--no-color')
    macho = json.loads(macho_bytes)
    uuids = [load['uuid'] for load in macho['loads'] if load['load_cmd'] == 'LC_UUID']
    if len(uuids) != 1 or uuids[0] != item['slices'][0]['uuid']:
        raise ValueError(f'Mach-O UUID differs from inventory: {volume}:{item["path"]}')
    sections = [[load['name'], part['addr'], part['size']]
                for load in macho['loads'] if load['load_cmd'] == 'LC_SEGMENT_64'
                and 'x' in load.get('prot', '')
                for part in load.get('sections', []) if part['name'] == '__text']
    symbol_bytes = run('ipsw', 'macho', 'info', str(path), '--symbols', '--demangle',
                       '--no-color')
    symbols, duplicates, unnamed, outside = parse_symbols(symbol_bytes, sections)
    record = {'volume': volume, 'path': item['path'], 'sha256': item['sha256'],
              'uuid': uuids[0], 'macho_loads_sha256': hashlib.sha256(macho_bytes).hexdigest(),
              'symbol_dump_sha256': hashlib.sha256(symbol_bytes).hexdigest(),
              'symbol_dump_replacement_char_count': symbol_bytes.decode('utf-8', errors='replace').count('\ufffd'),
              'text_sections': sections, 'named_symbol_count': len(symbols),
              'duplicate_symbol_row_count': duplicates,
              'unnamed_text_row_count': unnamed,
              'outside_text_row_count': outside,
              'symbols': symbols}
    dump(checkpoint, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--macho-catalog', type=Path, required=True)
    parser.add_argument('--filesystem-root', type=Path, required=True)
    parser.add_argument('--systemos-root', type=Path, required=True)
    parser.add_argument('--appos-root', type=Path, required=True)
    parser.add_argument('--workdir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    if args.workers < 1 or args.limit < 0:
        parser.error('--workers must be positive and --limit nonnegative')
    source = load(args.macho_catalog)
    if (source['kind'] != 'standalone_macho_file_inventory' or
            source['source'] != 'official_ipsw_mounted_images' or
            source['macho_file_count'] != len(source['records']) or
            any(len(item['slices']) != 1 or item['slices'][0]['uuid'] is None
                for item in source['records'])):
        parser.error('standalone Mach-O inventory is incomplete or unsupported')
    roots = {'FileSystem': args.filesystem_root, 'SystemOS': args.systemos_root,
             'AppOS': args.appos_root}
    args.workdir.mkdir(parents=True, exist_ok=True)
    pending = []
    for item in source['records']:
        key = hashlib.sha256(f'{item["volume"]}\0{item["path"]}'.encode()).hexdigest()
        if not (args.workdir / f'{key}.json.gz').exists():
            pending.append(item)
    selected = pending[:args.limit] if args.limit else pending
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(inspect, item, roots, args.workdir): item
                   for item in selected}
        for number, future in enumerate(as_completed(futures), 1):
            item = futures[future]
            try:
                future.result()
                if number % 100 == 0 or number == len(selected):
                    print(f'inspected {number}/{len(selected)} new files', flush=True)
            except Exception as error:
                failures.append((item['volume'], item['path'], str(error)))
                print(f'FAILED {item["volume"]}:{item["path"]}: {error}',
                      file=sys.stderr, flush=True)
    if failures:
        raise SystemExit(f'{len(failures)} file(s) failed; inspect checkpoint and retry')
    if len(selected) != len(pending):
        print(f'partial pass: {len(selected)} new files; {len(pending) - len(selected)} remain',
              flush=True)
        return
    results = [inspect(item, roots, args.workdir) for item in source['records']]
    totals = Counter()
    for item in results:
        totals['named_symbols'] += item['named_symbol_count']
        totals['duplicate_rows'] += item['duplicate_symbol_row_count']
        totals['unnamed_rows'] += item['unnamed_text_row_count']
        totals['outside_rows'] += item['outside_text_row_count']
        totals['files_without_names'] += not bool(item['symbols'])
    output = {'schema_version': 1, 'kind': 'standalone_macho_named_text_symbols',
              'source': 'official_ipsw_mounted_images',
              'tool': 'ipsw macho info --symbols --demangle',
              'product_type': source['product_type'], 'build': source['build'],
              'firmware_sha256': source['firmware_sha256'],
              'macho_file_count': len(results), 'totals': dict(totals),
              'files': results}
    dump(args.output, output)
    print(f'complete: {len(results)} files, {totals["named_symbols"]} named __text '
          f'symbols -> {args.output}', flush=True)


if __name__ == '__main__':
    main()
