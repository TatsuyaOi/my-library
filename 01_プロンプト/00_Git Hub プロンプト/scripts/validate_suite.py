#!/usr/bin/env python3
"""Validate suite structure. This does NOT execute prompts or prove model quality."""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import re
import sys
from pathlib import Path
from typing import Any
from suite_tools import (ROOT, TEXT_SUFFIXES, SuiteError, atomic_write, component_metadata,
                         digest, dump_json, expected_manifest, fence_errors, json_examples,
                         load_json, managed_files, read_config, safe_path, strict_json)

VERSION = '1.0'


def strict_yaml(text: str) -> Any:
    import yaml
    class UniqueLoader(yaml.SafeLoader):
        pass
    def mapping(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
        result: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in result:
                raise SuiteError(f'duplicate YAML key: {key}')
            result[key] = loader.construct_object(value_node, deep=deep)
        return result
    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    return yaml.load(text, Loader=UniqueLoader)


def validate(root: Path) -> dict[str, Any]:
    root = root.resolve()
    checks: list[dict[str, str]] = []
    def record(name: str, ok: bool, detail: str = '') -> None:
        checks.append({'id': name, 'execution': 'EXECUTED', 'result': 'PASS' if ok else 'FAIL', 'evidence': detail})
    try:
        config = read_config(root)
        components = component_metadata(root, config)
        record('components-00-09-and-headers', True, '10 authoritative headers match config')
        listed = {Path(c['path']).name for c in components}
        actual = {p.name for p in (root/config['prompt_directory']).glob('*.md')}
        record('no-unregistered-prompt-md', listed == actual, 'difference: '+str(sorted(listed ^ actual)))
        expected, readme = expected_manifest(root)
        record('readme-managed-table', (root/'README.md').read_bytes() == readme.encode('utf-8'))
        try:
            record('manifest-freshness', load_json(root/'SUITE_MANIFEST.json') == expected,
                   'independently recomputed raw bytes, versions and hashes')
        except (OSError, ValueError) as e:
            record('manifest-freshness', False, str(e))
        files = managed_files(root, config)
        for path in files:
            rel = path.relative_to(root).as_posix()
            data = path.read_bytes()
            is_text = path.suffix in TEXT_SUFFIXES or path.name in {'.gitattributes','.gitignore','.editorconfig'}
            if not is_text:
                continue
            try:
                text = data.decode('utf-8')
                record('text:'+rel, bool(data) and b'\r' not in data and not data.startswith(b'\xef\xbb\xbf') and data.endswith(b'\n'),
                       'nonempty UTF-8, no BOM, LF, trailing newline')
                if path.suffix == '.md':
                    errs = fence_errors(text)
                    record('fences:'+rel, not errs, '; '.join(errs))
                    for line, example in json_examples(text):
                        try:
                            strict_json(example)
                            record(f'json-example:{rel}:{line}', True)
                        except (ValueError, TypeError) as e:
                            record(f'json-example:{rel}:{line}', False, str(e))
                if path.suffix == '.json':
                    strict_json(text)
                    record('json:'+rel, True, 'strict: duplicate keys/NaN/Infinity rejected')
                if path.suffix in {'.yml','.yaml'}:
                    doc = strict_yaml(text)
                    record('yaml:'+rel, isinstance(doc, dict), 'strict duplicate key check; on key is quoted in workflows')
                    if rel.startswith('.github/workflows/'):
                        permissions = doc.get('permissions', {})
                        record('workflow-readonly:'+rel, permissions == {'contents': 'read'})
                        events = doc.get('on', {})
                        record('workflow-events:'+rel, isinstance(events, dict) and 'pull_request_target' not in events)
                        for use in re.findall(r'^\s*-?\s*uses:\s*([^\s#]+)', text, re.M):
                            record('action-pin:'+rel+':'+use, bool(re.fullmatch(r'actions/[a-z0-9-]+@[0-9a-f]{40}', use)))
                if path.suffix == '.py':
                    ast.parse(text, filename=rel)
                    record('python-syntax:'+rel, True)
            except (OSError, ValueError, SyntaxError, UnicodeError, TypeError) as e:
                record('parse:'+rel, False, str(e))
        from jsonschema import Draft202012Validator, FormatChecker
        schemas: dict[str, dict[str, Any]] = {}
        for p in sorted((root/'schemas').glob('*.json')):
            schema = load_json(p)
            Draft202012Validator.check_schema(schema)
            schemas[p.name] = schema
            record('schema-definition:'+p.name, True)
        validation_pairs = [('suite-manifest.schema.json', root/'SUITE_MANIFEST.json')]
        validation_pairs += [('eval-case.schema.json', p) for p in sorted((root/'evals/cases').glob('*.json'))]
        for name, p in validation_pairs:
            errors = list(Draft202012Validator(schemas[name], format_checker=FormatChecker()).iter_errors(load_json(p)))
            record('schema-instance:'+p.relative_to(root).as_posix(), not errors,
                   '; '.join(e.message for e in errors[:5]))
        case_ids = [load_json(p)['id'] for p in (root/'evals/cases').glob('*.json')]
        record('eval-case-ids-unique', len(case_ids) == len(set(case_ids)))
        rubric = load_json(root/'evals/rubric.json')
        record('rubric-total-100', sum(d['max_score'] for d in rubric['dimensions']) == 100)
        trace = load_json(root/'docs/requirements.json')
        requirements = trace['requirements']
        record('requirement-ids-unique', len({r['id'] for r in requirements}) == len(requirements))
        unit_source='\n'.join(p.read_text(encoding='utf-8') for p in (root/'tests').glob('test_*.py'))
        for req in requirements:
            ref=req.get('test_case','')
            valid_ref=(ref=='STATIC_ONLY' or ref in case_ids or (ref.startswith('UNIT:') and ('def '+ref[5:]+'(') in unit_source))
            record('requirement-test-ref:'+req['id'],valid_ref,ref)
            target = safe_path(root, req['final_path']).read_text(encoding='utf-8')
            ok = all(term in target for term in req['required_fragments'])
            record('requirement-map:'+req['id'], ok, req['final_path']+'; structural existence only, not semantic proof')
        changelog = (root/'CHANGELOG.md').read_text(encoding='utf-8')
        for c in components:
            record('changelog:'+c['id'], f"{c['id']}：" in changelog and f"→ {c['version']}" in changelog)
        record('agents-routing-present', 'プロンプト一覧/' in (root/'AGENTS.md').read_text(encoding='utf-8'))
        input_hash = digest(dump_json(expected).encode('utf-8'))
    except ImportError as e:
        return {'validator_version': VERSION, 'scope': 'suite structure', 'verdict': 'INCOMPLETE', 'exit_code': 2,
                'checks': checks, 'unverified': [str(e), 'Install requirements-dev.txt'], 'behavioral_tests': 'NOT_RUN'}
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as e:
        record('suite-configuration', False, str(e))
        input_hash = None
    failures = [c for c in checks if c['result'] == 'FAIL']
    return {'validator_version': VERSION, 'scope': 'suite structure and syntax; not generated content or live GitHub',
            'verdict': 'FAIL' if failures else 'PASS', 'exit_code': 1 if failures else 0,
            'input_manifest_sha256': input_hash, 'checked_at': datetime.now(timezone.utc).isoformat(),
            'counts': {'total': len(checks), 'passed': len(checks)-len(failures), 'failed': len(failures)},
            'checks': checks, 'behavioral_tests': 'NOT_RUN',
            'unverified': ['Independent model A/B results', 'Existing repository settings', 'Live Pages deployment', 'Android device/PWA behavior']}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--report-dir', type=Path, help='optional output folder; inputs are never repaired')
    args = parser.parse_args(argv)
    report = validate(args.root)
    print(f"{report['verdict']}: suite structure; model behavior NOT_RUN")
    for c in report.get('checks', []):
        if c['result'] == 'FAIL':
            print(f"  FAIL {c['id']}: {c['evidence']}")
    if args.report_dir:
        atomic_write(args.report_dir/'suite-validation.json', dump_json(report))
        lines = ['# Suite構造検証レポート', '', f"- 判定：{report['verdict']}", f"- 範囲：{report['scope']}",
                 '- 実モデルによる生成性能評価：NOT_RUN', '', '## 実行結果', '',
                 '| 検査 | 結果 | 証拠 |', '|---|---|---|']
        lines += [f"| `{c['id']}` | {c['result']} | {c['evidence'].replace('|','/')} |" for c in report.get('checks', [])]
        lines += ['', '## 未確認', ''] + ['- '+x for x in report['unverified']]
        atomic_write(args.report_dir/'suite-validation.md', '\n'.join(lines)+'\n')
    return report['exit_code']

if __name__ == '__main__':
    raise SystemExit(main())
