#!/usr/bin/env python3
"""Prepare model evaluation tasks or validate evidence records. No external API calls."""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path
from typing import Any
from suite_tools import ROOT, SuiteError, atomic_write, dump_json, load_json, read_config, safe_path


def check_results(root: Path, run_file: Path) -> tuple[int, list[str]]:
    from jsonschema import Draft202012Validator
    run = load_json(run_file)
    Draft202012Validator(load_json(root/'schemas/eval-result.schema.json')).validate(run)
    cases = {load_json(p)['id']: load_json(p) for p in (root/'evals/cases').glob('*.json')}
    seen: set[str] = set()
    errors: list[str] = []
    incomplete: list[str] = []
    for result in run['cases']:
        cid = result['id']
        if cid in seen or cid not in cases:
            errors.append(f'{cid}: duplicate or unknown case')
            continue
        seen.add(cid)
        if result['result'] == 'FAIL':
            errors.append(f'{cid}: failed')
        if result['execution'] == 'EXECUTED':
            if not run['model'] or not run['environment']:
                incomplete.append(f'{cid}: actual model/tool and environment are required')
            evidence = result['evidence_file']
            if not evidence:
                incomplete.append(f'{cid}: no evidence')
            else:
                try:
                    path = safe_path(run_file.parent, evidence)
                    if not path.is_file() or path.stat().st_size == 0:
                        incomplete.append(f'{cid}: evidence is empty/not a file')
                except SuiteError as e:
                    errors.append(f'{cid}: {e}')
            if result['result'] == 'NOT_RUN':
                errors.append(f'{cid}: EXECUTED contradicts NOT_RUN result')
        elif result['result'] == 'PASS' and result['execution'] == 'NOT_RUN':
            errors.append(f'{cid}: NOT_RUN cannot PASS')
        if cases[cid]['critical'] and (result['execution'] != 'EXECUTED' or result['result'] != 'PASS'):
            incomplete.append(f'{cid}: critical behavior not demonstrated as PASS')
    for cid, case in cases.items():
        if case['critical'] and cid not in seen:
            incomplete.append(f'{cid}: critical case missing')
    if errors:
        return 1, errors + incomplete
    if incomplete:
        return 2, incomplete
    return 0, ['Required recorded results have evidence files. Reviewer must verify their content and provenance.']


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--check-results', type=Path)
    p.add_argument('--run-id')
    args = p.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.check_results:
            code, messages = check_results(root, args.check_results.resolve())
            print({0: 'RECORDED_EVIDENCE_PRESENT', 1: 'FAIL', 2: 'INCOMPLETE'}[code])
            for line in messages:
                print(line)
            return code
        if not args.run_id or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', args.run_id):
            raise SuiteError('--run-id must be a nonempty kebab-case identifier')
        dest = safe_path(root, 'evals/runs/'+args.run_id, must_exist=False)
        if dest.exists():
            raise SuiteError('run directory already exists; refusing to overwrite evidence')
        dest.mkdir(parents=True)
        cases = [load_json(p) for p in sorted((root/'evals/cases').glob('*.json'))]
        config = read_config(root)
        run = {'schema_version': '1.0', 'run_id': args.run_id, 'suite_version': config['suite_version'],
               'model': None, 'environment': None,
               'cases': [{'id': c['id'], 'execution': 'NOT_RUN', 'result': 'NOT_RUN',
                          'evidence_file': None, 'notes': 'Prepared only; no external call has been made.'} for c in cases]}
        atomic_write(dest/'run.json', dump_json(run))
        atomic_write(dest/'tasks.jsonl', ''.join(__import__('json').dumps(c, ensure_ascii=False)+'\n' for c in cases))
        print(f'PREPARED: {dest}; all {len(cases)} cases remain NOT_RUN')
        return 0
    except (OSError, ValueError, KeyError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 2
    except ImportError as e:
        print(f'ERROR: {e}; install requirements-dev.txt', file=sys.stderr)
        return 2
    except Exception as e:
        # Schema validation errors carry useful context; no network or code is executed.
        print(f'INVALID_RECORD: {e}', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
