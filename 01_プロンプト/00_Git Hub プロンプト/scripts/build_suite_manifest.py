#!/usr/bin/env python3
"""Regenerate suite metadata on a work branch, or compare without changing files."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from suite_tools import ROOT, SuiteError, atomic_write, dump_json, expected_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--write', action='store_true', help='update README managed table and manifest')
    group.add_argument('--check', action='store_true', help='read-only check (the default)')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        manifest, readme = expected_manifest(root)
        intended = {'README.md': readme, 'SUITE_MANIFEST.json': dump_json(manifest)}
        stale = [name for name, data in intended.items()
                 if not (root/name).exists() or (root/name).read_bytes() != data.encode('utf-8')]
        if args.write:
            for name in stale:
                atomic_write(root/name, intended[name])
            print('SYNCED: ' + (', '.join(stale) or 'already current'))
            return 0
        if stale:
            print('FAIL: stale generated metadata: ' + ', '.join(stale), file=sys.stderr)
            print('Run --write on the work branch; do not repair metadata inside CI.', file=sys.stderr)
            return 1
        print('PASS: manifest and README are current (read-only check)')
        return 0
    except (OSError, ValueError, KeyError, UnicodeError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
