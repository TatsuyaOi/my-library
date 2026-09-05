#!/usr/bin/env python3
"""Build explicit public Library files into an owned site/ directory; no deployment."""
import argparse
import sys
from pathlib import Path
from suite_tools import ROOT, atomic_write, dump_json
from library_tools import plan, write_build


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--data-only',action='store_true',help='build index data/files without UI (never a complete deployable site)')
    p.add_argument('--allow-empty',action='store_true')
    p.add_argument('--allow-removals',action='store_true')
    p.add_argument('--report',type=Path)
    a=p.parse_args(argv)
    try:
        if a.report and a.report.resolve().is_relative_to((a.root/'site').resolve()):
            raise ValueError('report path must be outside site/')
        if a.dry_run:
            library,copies,report=plan(a.root,not a.data_only)
            report['copy_paths']=sorted(copies)
            report['build_id']=library['build']['build_id']
        else:
            report=write_build(a.root,not a.data_only,a.allow_empty,a.allow_removals)
        print(f"{'DRY_RUN' if a.dry_run else 'BUILT'}: {report['published']} public items")
        if a.report:
            # Reports are private operational details and must not go into site/.
            if a.report.resolve().is_relative_to((a.root/'site').resolve()):
                raise ValueError('report path must be outside site/')
            atomic_write(a.report,dump_json(report))
        return 0
    except Exception as e:
        print(f'FAIL: {e}',file=sys.stderr)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
