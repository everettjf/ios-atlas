#!/usr/bin/env python3
"""Inventory real Mach-O files in exact mounted official IPSW volumes."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import struct
import uuid
from collections import Counter
from pathlib import Path

MAGICS = {bytes.fromhex(value) for value in (
    'feedface', 'cefaedfe', 'feedfacf', 'cffaedfe',
    'cafebabe', 'bebafeca', 'cafebabf', 'bfbafeca')}
THIN_MAGICS = {bytes.fromhex(value) for value in ('feedface', 'cefaedfe', 'feedfacf', 'cffaedfe')}
FAT_MAGICS = MAGICS - THIN_MAGICS
FILE_TYPES = {1: 'object', 2: 'executable', 3: 'fixed_vm_library', 4: 'core',
              5: 'preload', 6: 'dylib', 7: 'dynamic_linker', 8: 'bundle',
              9: 'dylib_stub', 10: 'dsym', 11: 'kext_bundle', 12: 'fileset',
              13: 'gpu_executable'}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        return json.load(stream)


def fat_slices(path: Path) -> list[tuple[int, int, str]]:
    with path.open('rb') as stream:
        magic = stream.read(4)
        endian = '>' if magic in (bytes.fromhex('cafebabe'), bytes.fromhex('cafebabf')) else '<'
        is_64 = magic in (bytes.fromhex('cafebabf'), bytes.fromhex('bfbafeca'))
        count = struct.unpack(endian + 'I', stream.read(4))[0]
        if count < 1 or count > 100:
            raise ValueError(f'invalid fat architecture count in {path}')
        result = []
        for _ in range(count):
            data = stream.read(32 if is_64 else 20)
            values = struct.unpack(endian + ('iiQQII' if is_64 else 'iiIII'), data)
            offset, size = values[2], values[3]
            if offset + size > path.stat().st_size or size < 4:
                raise ValueError(f'invalid fat slice range in {path}')
            here = stream.tell()
            stream.seek(offset)
            result.append((offset, size, stream.read(4).hex()))
            stream.seek(here)
        return result


def architecture(cpu: int, subtype: int) -> str:
    if cpu == 0x0100000c:
        return 'arm64e' if subtype & 0x00ffffff == 2 else 'arm64'
    if cpu == 0x01000007:
        return 'x86_64'
    if cpu == 12:
        return 'arm'
    if cpu == 7:
        return 'x86'
    return f'cpu:{cpu}:subtype:{subtype}'


def parse_thin(path: Path, offset: int, size: int) -> dict:
    with path.open('rb') as stream:
        stream.seek(offset)
        magic = stream.read(4)
        if magic not in THIN_MAGICS:
            raise ValueError(f'fat slice is not Mach-O: {path}@{offset}')
        endian = '<' if magic in (bytes.fromhex('cefaedfe'), bytes.fromhex('cffaedfe')) else '>'
        is_64 = magic in (bytes.fromhex('feedfacf'), bytes.fromhex('cffaedfe'))
        header_size = 32 if is_64 else 28
        if size < header_size:
            raise ValueError(f'truncated Mach-O header: {path}@{offset}')
        stream.seek(offset)
        values = struct.unpack(endian + ('IiiIIIII' if is_64 else 'IiiIIII'),
                               stream.read(header_size))
        _, cpu, subtype, filetype, command_count, commands_size, _, *rest = values
        if command_count > 10000 or commands_size > size - header_size:
            raise ValueError(f'invalid Mach-O command range: {path}@{offset}')
        command_end = offset + header_size + commands_size
        uuids = []
        for _ in range(command_count):
            here = stream.tell()
            if here + 8 > command_end:
                raise ValueError(f'truncated Mach-O load command: {path}@{offset}')
            command, command_size = struct.unpack(endian + 'II', stream.read(8))
            if command_size < 8 or here + command_size > command_end:
                raise ValueError(f'invalid Mach-O load command size: {path}@{offset}')
            if command == 0x1b:
                if command_size < 24:
                    raise ValueError(f'truncated UUID command: {path}@{offset}')
                uuids.append(str(uuid.UUID(bytes=stream.read(16))).upper())
            stream.seek(here + command_size)
        if stream.tell() != command_end or len(uuids) > 1:
            raise ValueError(f'Mach-O command size or UUID count mismatch: {path}@{offset}')
        return {'architecture': architecture(cpu, subtype), 'cpu_type': cpu,
                'cpu_subtype': subtype,
                'file_type': FILE_TYPES.get(filetype, f'type:{filetype}'),
                'uuid': uuids[0] if uuids else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ipsw', type=Path, required=True)
    parser.add_argument('--filesystem-catalog', type=Path, required=True)
    parser.add_argument('--systemos-catalog', type=Path, required=True)
    parser.add_argument('--appos-catalog', type=Path, required=True)
    parser.add_argument('--filesystem-root', type=Path, required=True)
    parser.add_argument('--systemos-root', type=Path, required=True)
    parser.add_argument('--appos-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sources = [(args.filesystem_catalog, args.filesystem_root, 'FileSystem'),
               (args.systemos_catalog, args.systemos_root, 'SystemOS'),
               (args.appos_catalog, args.appos_root, 'AppOS')]
    catalogs = [(load(path), root, volume) for path, root, volume in sources]
    first = catalogs[0][0]
    if (not args.ipsw.is_file() or sha256(args.ipsw) != first['firmware_sha256'] or
            any(not catalog['complete'] or catalog['errors'] or
                catalog['volume'] != volume or
                any(catalog[key] != first[key] for key in
                    ('build', 'product_type', 'firmware_sha256'))
                for catalog, _, volume in catalogs)):
        raise ValueError('firmware or mounted-volume catalog identities differ')
    print('verified official IPSW SHA-256', flush=True)
    records = []
    excluded = []
    counts = Counter()
    for catalog, root, volume in catalogs:
        for item in catalog['entries']:
            if item['type'] != 'file' or (item.get('size') or 0) < 4:
                continue
            relative = Path(item['path'].lstrip('/'))
            if '..' in relative.parts:
                raise ValueError(f'unsafe catalog path: {item["path"]}')
            path = root / relative
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                magic = os.read(fd, 4)
                actual_size = os.fstat(fd).st_size
            finally:
                os.close(fd)
            if actual_size != item['size']:
                raise ValueError(f'file size differs from catalog: {volume}:{item["path"]}')
            counts[f'{volume}_files_checked'] += 1
            if magic not in MAGICS:
                continue
            counts[f'{volume}_header_candidates'] += 1
            if magic in FAT_MAGICS:
                fat = fat_slices(path)
                slice_magics = [value for _, _, value in fat]
                if not any(bytes.fromhex(value) in THIN_MAGICS for value in slice_magics):
                    excluded.append({'volume': volume, 'path': item['path'],
                                     'size': actual_size, 'header_magic': magic.hex(),
                                     'slice_magics': slice_magics,
                                     'reason': 'fat_header_without_macho_slices'})
                    continue
                if not all(bytes.fromhex(value) in THIN_MAGICS for value in slice_magics):
                    excluded.append({'volume': volume, 'path': item['path'],
                                     'size': actual_size, 'header_magic': magic.hex(),
                                     'slice_magics': slice_magics,
                                     'reason': 'fat_header_with_mixed_non_macho_slices'})
                    continue
            slices = ([parse_thin(path, offset, size) for offset, size, _ in fat]
                      if magic in FAT_MAGICS else [parse_thin(path, 0, actual_size)])
            if not slices:
                raise ValueError(f'no Mach-O slices: {path}')
            records.append({'volume': volume, 'path': item['path'],
                            'size': actual_size, 'sha256': sha256(path),
                            'header_magic': magic.hex(), 'slices': slices})
            counts[f'{volume}_macho_files'] += 1
            if len(records) % 500 == 0:
                print(f'indexed {len(records)} Mach-O files', flush=True)
        print(f'finished {volume}', flush=True)
    records.sort(key=lambda item: (item['volume'], item['path']))
    output = {'schema_version': 1, 'kind': 'standalone_macho_file_inventory',
              'source': 'official_ipsw_mounted_images',
              'tool': 'Mach-O header/LC_UUID parser and SHA-256',
              'product_type': first['product_type'], 'build': first['build'],
              'firmware_sha256': first['firmware_sha256'],
              'volume_images': {catalog['volume']: catalog['image_name']
                                for catalog, _, _ in catalogs},
              'scan_counts': dict(counts), 'macho_file_count': len(records),
              'excluded_candidates': excluded, 'records': records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(json.dumps(output, sort_keys=True,
                                               separators=(',', ':')).encode() + b'\n', mtime=0))
    print(f'indexed {len(records)} Mach-O files; excluded {len(excluded)} non-Mach-O fat containers')


if __name__ == '__main__':
    main()
