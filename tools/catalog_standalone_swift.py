#!/usr/bin/env python3
"""Resume a Swift declaration pass over exact standalone Mach-O files.

The published rows are lines reported by ipsw swift-dump, not reconstructed
Swift source, exported APIs, or proof of runtime use. Raw output stays local.
"""

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

from catalog_standalone_symbols import sha256


HEADER = re.compile(r'^(class|struct|enum|protocol|extension|actor)\s+([^\s:{]+)')
SECTIONS = {'methods', 'requirements'}


def load(path: Path) -> dict:
    with gzip.open(path, 'rt', encoding='utf-8') as source:
        return json.load(source)


def dump(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(value, separators=(',', ':'), sort_keys=True).encode() + b'\n'
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(gzip.compress(blob, mtime=0))
    temporary.replace(path)


def run(*command: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, capture_output=True, check=False)


def parse_dump(source: str) -> tuple[list[dict], Counter]:
    declarations = []
    counts = Counter()
    current = None
    section = None
    for number, line in enumerate(source.splitlines(), 1):
        if not line or line.startswith('typealias '):
            continue
        if not line[0].isspace() and line != '}':
            match = HEADER.match(line)
            if match is None or current is not None:
                # ipsw can render undecodable type strings with embedded newlines.
                # Retain a count rather than treating those bytes as declarations.
                counts['unparsed_lines'] += 1
                continue
            current = {'kind': match[1], 'name': match[2], 'members': []}
            declarations.append(current)
            counts['declarations'] += 1
            counts[match[1]] += 1
            if line.rstrip().endswith('{}'):
                current = None
            elif not line.rstrip().endswith('{'):
                counts['unparsed_lines'] += 1
                current = None
            section = None
        elif line == '}':
            if current is None:
                counts['unparsed_lines'] += 1
                continue
            current = None
            section = None
        elif current is None:
            counts['unparsed_lines'] += 1
        elif line.startswith('  /* ') and line.endswith(' */'):
            section = line[5:-3]
        elif line.startswith('    ') and section in SECTIONS:
            member = line.strip()
            if not member:
                continue
            if '\ufffd' in member or any(ord(char) < 32 for char in member):
                counts['unparsed_lines'] += 1
                continue
            current['members'].append([section, member])
            counts['members'] += 1
            counts['stripped_members'] += '<stripped>' in member
        elif line.startswith('    ') or line.startswith('  '):
            continue
        else:
            counts['unparsed_lines'] += 1
    if current is not None:
        counts['unparsed_lines'] += 1
    return declarations, counts


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
        if 'unparsed_line_count' not in saved:
            saved['unparsed_line_count'] = 0
            dump(checkpoint, saved)
        return saved
    if not path.is_file() or path.stat().st_size != item['size'] or sha256(path) != item['sha256']:
        raise ValueError(f'mounted file differs from exact inventory: {volume}:{item["path"]}')
    macho = run('ipsw', 'macho', 'info', str(path), '--json', '--loads', '--no-color')
    if macho.returncode:
        raise RuntimeError(f'Mach-O load parse failed for {volume}:{item["path"]}: '
                           f'{macho.stderr.decode(errors="replace")[-400:]}')
    info = json.loads(macho.stdout)
    uuids = [part['uuid'] for part in info['loads'] if part['load_cmd'] == 'LC_UUID']
    if len(uuids) != 1 or uuids[0] != item['slices'][0]['uuid']:
        raise ValueError(f'Mach-O UUID differs from inventory: {volume}:{item["path"]}')
    swift_sections = [[part['name'], section['name'], section['addr'], section['size']]
                      for part in info['loads'] if part['load_cmd'] == 'LC_SEGMENT_64'
                      for section in part.get('sections', [])
                      if section['name'].startswith('__swift5_')]
    result = run('ipsw', 'swift-dump', str(path), '--no-color')
    status = 'parsed'
    if result.returncode:
        if result.stdout or b'macho does not contain swift info' not in result.stderr:
            raise RuntimeError(f'Swift dump failed for {volume}:{item["path"]}: '
                               f'{result.stderr.decode(errors="replace")[-400:]}')
        status = 'no_swift_info' if not swift_sections else 'swift_sections_unparsed'
        declarations, counts = [], Counter()
    else:
        if not result.stdout.strip() and not swift_sections:
            status = 'no_swift_info'
            declarations, counts = [], Counter()
        else:
            declarations, counts = parse_dump(result.stdout.decode('utf-8', errors='replace'))
            if not swift_sections:
                status = 'dump_without_swift_sections'
            elif counts['unparsed_lines']:
                status = 'partially_parsed'
    record = {'volume': volume, 'path': item['path'], 'sha256': item['sha256'],
              'uuid': uuids[0], 'macho_loads_sha256': hashlib.sha256(macho.stdout).hexdigest(),
              'swift_dump_sha256': hashlib.sha256(result.stdout).hexdigest(),
              'swift_dump_replacement_char_count': result.stdout.decode('utf-8', errors='replace').count('\ufffd'),
              'status': status, 'swift_sections': swift_sections,
              'declaration_count': counts['declarations'],
              'member_count': counts['members'],
              'stripped_member_count': counts['stripped_members'],
              'unparsed_line_count': counts['unparsed_lines'],
              'kind_counts': {kind: counts[kind] for kind in
                              ('class', 'struct', 'enum', 'protocol', 'extension', 'actor')},
              'declarations': declarations}
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
        totals[item['status']] += 1
        totals['declarations'] += item['declaration_count']
        totals['members'] += item['member_count']
        totals['stripped_members'] += item['stripped_member_count']
        totals['unparsed_lines'] += item['unparsed_line_count']
        for kind, count in item['kind_counts'].items():
            totals[kind] += count
    output = {'schema_version': 1, 'kind': 'standalone_macho_swift_declarations',
              'source': 'official_ipsw_mounted_images', 'tool': 'ipsw swift-dump',
              'product_type': source['product_type'], 'build': source['build'],
              'firmware_sha256': source['firmware_sha256'],
              'macho_file_count': len(results), 'totals': dict(totals),
              'files': results}
    dump(args.output, output)
    print(f'complete: {len(results)} files, {totals["declarations"]} Swift declarations '
          f'-> {args.output}', flush=True)


if __name__ == '__main__':
    main()
