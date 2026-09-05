#!/usr/bin/env python3
"""Recompute expected Library data and verify the built public artifact without repairs."""
import argparse
import sys
from pathlib import Path
from suite_tools import ROOT, digest, load_json
from library_tools import OWNERSHIP, plan


def validate(root: Path, include_ui: bool = True) -> list[str]:
    expected,copies,report=plan(root,include_ui)
    site=root/'site'
    errors=[]
    if load_json(site/'library.json')!=expected:
        errors.append('site/library.json differs from current input; rebuild required')
    allowed=set(copies)|{'library.json',OWNERSHIP}
    for f in site.rglob('*'):
        if f.is_symlink():errors.append('symlink in site: '+f.relative_to(site).as_posix())
        elif f.is_file() and f.relative_to(site).as_posix() not in allowed:
            errors.append('unlisted file in site: '+f.relative_to(site).as_posix())
    for target,source in copies.items():
        dest=site/target
        if not dest.is_file() or digest(dest.read_bytes())!=digest(source.read_bytes()):
            errors.append('missing or altered public file: '+target)
    return errors


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--data-only',action='store_true')
    a=p.parse_args(argv)
    try:
        errors=validate(a.root.resolve(),not a.data_only)
        if errors:
            print('\n'.join(errors));return 1
        print('PASS: Library structural consistency; browser/content/security review is separate')
        return 0
    except Exception as e:
        print(f'FAIL: {e}',file=sys.stderr);return 1

if __name__=='__main__':
    raise SystemExit(main())
