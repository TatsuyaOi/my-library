#!/usr/bin/env python3
"""Require an evidence-bearing, current-build release audit before enabling deployment."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from suite_tools import ROOT, load_json, safe_path


def check(root: Path, report_path: Path) -> tuple[int,list[str]]:
    if not report_path.is_file():
        return 2,['INCOMPLETE: release audit record missing; run 08 for the built artifact first']
    report=load_json(report_path);library=load_json(root/'site/library.json');errors=[]
    if report.get('verdict') == 'INCOMPLETE':
        return 2,['INCOMPLETE: required release checks have not completed']
    if report.get('verdict') not in {'PASS','PASS WITH WARNINGS'}:
        return 1,['release audit does not permit deployment']
    if report.get('build_id')!=library['build']['build_id']:
        return 2,['release audit is not bound to this build_id']
    if report.get('recommended_exit_code')!=0:
        return 1,['audit exit code is not zero']
    required={'schema','publication','links','content-consistency','browser-ui'}
    if (root/'site/sw.js').is_file():required.add('pwa')
    rows=report.get('checked',[])
    if not isinstance(rows,list) or any(not isinstance(c,dict) or not isinstance(c.get('id'),str) for c in rows):
        return 1,['malformed audit checked records']
    checks={c['id']:c for c in rows}
    if len(checks)!=len(rows):
        return 1,['duplicate audit check ID']
    for name in sorted(required):
        c=checks.get(name,{})
        if c.get('result')!='PASS' or c.get('execution')!='EXECUTED':
            errors.append(f'{name}: required executed PASS missing');continue
        evidence=c.get('evidence_file')
        if not isinstance(evidence,str):
            errors.append(f'{name}: evidence file missing');continue
        try:
            p=safe_path(root,evidence)
            if not p.is_file() or p.stat().st_size==0:errors.append(f'{name}: evidence empty')
        except ValueError as e:errors.append(f'{name}: {e}')
    if report.get('counts',{}).get('blocker',0)>0 or report.get('counts',{}).get('high',0)>0:
        return 1,['unresolved blocker/high findings']
    return (2,errors) if errors else (0,['Current-build audit evidence is present; provenance still requires reviewer judgment.'])


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--report',type=Path);a=p.parse_args(argv);root=a.root.resolve()
    try:
        code,messages=check(root,a.report.resolve() if a.report else root/'reports/release/github-audit-report.json')
        print('\n'.join(messages));return code
    except Exception as e:print(f'INCOMPLETE: {e}',file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
