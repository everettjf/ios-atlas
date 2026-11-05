#!/usr/bin/env python3
"""Resume an Objective-C method inventory for every cataloged standalone Mach-O.

The mounted firmware files and raw command outputs stay outside Git. Each
checkpoint is tied to a full-file SHA-256; only a complete aggregate is
published. An ipsw "no objc info" diagnostic is an inspected zero result.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from catalog_objc_image_methods import parse_dump, sha256


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
    arch_flags = (('--arch', item['slices'][0]['architecture'])
                  if len(item['slices']) > 1 else ())
    result = run('ipsw', 'class-dump', str(path), '--re', '-V', '--no-color',
                 *arch_flags)
    source_hash = hashlib.sha256(result.stdout).hexdigest()
    record = {'volume': volume, 'path': item['path'], 'sha256': item['sha256'],
              'uuid': item['slices'][0]['uuid'], 'class_dump_sha256': source_hash,
              'class_dump_replacement_char_count': 0,
              'status': None, 'class_count': 0, 'category_count': 0,
              'method_count': 0, 'unknown_selector_count': 0,
              'rendered_protocol_count': 0, 'toc_protocol_count': 0,
              'unlisted_swift_class_count': 0, 'groups': [], 'records': []}
    if result.returncode:
        if result.stdout or b'macho does not contain objc info' not in result.stderr:
            raise RuntimeError(f'class-dump failed for {volume}:{item["path"]}: '
                               f'{result.stderr.decode(errors="replace")[-400:]}')
        record['status'] = 'no_objc_info'
    else:
        text = result.stdout.decode('utf-8', errors='replace')
        record['class_dump_replacement_char_count'] = text.count('\ufffd')
        macho = run('ipsw', 'macho', 'info', str(path), '--json', '--loads',
                    '--no-color', *arch_flags)
        if macho.returncode:
            raise RuntimeError(f'Mach-O load parse failed for {volume}:{item["path"]}: '
                               f'{macho.stderr.decode(errors="replace")[-400:]}')
        info = json.loads(macho.stdout)
        uuids = [part['uuid'] for part in info['loads'] if part['load_cmd'] == 'LC_UUID']
        segments = [part for part in info['loads'] if part['load_cmd'] == 'LC_SEGMENT_64']
        text_segments = [part for part in segments if part['name'] == '__TEXT']
        if len(uuids) != 1 or uuids[0] != record['uuid'] or len(text_segments) != 1:
            raise ValueError(f'Mach-O UUID or __TEXT mismatch: {volume}:{item["path"]}')
        ranges = [(part.get('addr', 0), part.get('addr', 0) + part.get('memsz', 0))
                  for part in segments if part['name'] != '__LINKEDIT']
        code_start = text_segments[0].get('addr', 0)
        code_range = (code_start, code_start + text_segments[0].get('memsz', 0))
        groups, methods, protocols, toc_protocols, extra_swift = parse_dump(
            text, None, ranges, code_range)
        record.update(status='parsed', class_count=sum(group['category_name'] is None
                                                       for group in groups),
                      category_count=sum(group['category_name'] is not None
                                         for group in groups),
                      method_count=len(methods),
                      unknown_selector_count=sum(row[2] is None for row in methods),
                      rendered_protocol_count=protocols,
                      toc_protocol_count=toc_protocols,
                      unlisted_swift_class_count=extra_swift,
                      groups=groups, records=methods,
                      macho_loads_sha256=hashlib.sha256(macho.stdout).hexdigest(),
                      text_address=hex(code_range[0]),
                      text_size=code_range[1] - code_range[0])
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
    parser.add_argument('--limit', type=int, default=0,
                        help='Inspect at most this many new files; zero means all')
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
                result = future.result()
                if number % 100 == 0 or number == len(selected):
                    print(f'inspected {number}/{len(selected)} new files; '
                          f'last {result["volume"]}:{result["path"]}', flush=True)
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
        totals['classes'] += item['class_count']
        totals['categories'] += item['category_count']
        totals['methods'] += item['method_count']
        totals['unknown_selectors'] += item['unknown_selector_count']
    output = {'schema_version': 1, 'kind': 'standalone_macho_objc_methods',
              'source': 'official_ipsw_mounted_images',
              'tool': 'ipsw class-dump --re -V; ipsw macho info --json --loads',
              'product_type': source['product_type'], 'build': source['build'],
              'firmware_sha256': source['firmware_sha256'],
              'macho_file_count': len(results), 'totals': dict(totals),
              'files': results}
    dump(args.output, output)
    print(f'complete: {len(results)} files, {totals["methods"]} ObjC method entries '
          f'-> {args.output}', flush=True)


if __name__ == '__main__':
    main()
