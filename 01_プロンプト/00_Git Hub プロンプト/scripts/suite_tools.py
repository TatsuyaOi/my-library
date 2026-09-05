"""Shared deterministic, read-only inspection utilities for the prompt suite."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {'.md', '.json', '.jsonl', '.yml', '.yaml', '.py', '.html', '.js', '.css', '.txt', '.toml', '.diff'}
BEGIN = '<!-- SUITE_COMPONENTS:BEGIN -->'
END = '<!-- SUITE_COMPONENTS:END -->'

class SuiteError(ValueError):
    """Invalid or unsafe suite input."""


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SuiteError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def strict_json(text: str) -> Any:
    def reject_constant(value: str) -> None:
        raise SuiteError(f'non-standard JSON constant: {value}')
    return json.loads(text, object_pairs_hook=_unique, parse_constant=reject_constant)


def load_json(path: Path) -> Any:
    return strict_json(path.read_text(encoding='utf-8'))


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(root: Path, relative: str, must_exist: bool = True) -> Path:
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise SuiteError(f'unsafe relative path: {relative!r}')
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts:
        raise SuiteError(f'path traversal/absolute path rejected: {relative!r}')
    root = root.resolve()
    candidate = root / rel
    for part in [candidate, *candidate.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise SuiteError(f'symlink rejected: {relative}')
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise SuiteError(f'path escaped root: {relative}')
    if must_exist and not resolved.exists():
        raise SuiteError(f'missing: {relative}')
    return resolved


def read_config(root: Path) -> dict[str, Any]:
    config = load_json(root / 'config/suite.config.json')
    if config.get('prompt_directory') != 'プロンプト一覧':
        raise SuiteError('prompt_directory must be プロンプト一覧')
    components = config.get('components', [])
    if [c.get('order') for c in components] != list(range(10)):
        raise SuiteError('exactly 00 through 09, in order, are required')
    if len({c.get('id') for c in components}) != 10:
        raise SuiteError('component IDs must be unique')
    paths = [c.get('path') for c in components]
    if len(set(paths)) != 10:
        raise SuiteError('component paths must be unique')
    for c in components:
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', c.get('id', '')):
            raise SuiteError('component ID must be kebab-case')
        expected = f"プロンプト一覧/{c['order']:02d}_{c['id']}_master-prompt.md"
        if c['path'] != expected:
            raise SuiteError(f'unstable or unexpected component path: {c["path"]}')
        safe_path(root, c['path'])
    return config


def component_metadata(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for c in config['components']:
        data = safe_path(root, c['path']).read_bytes()
        text = data.decode('utf-8')
        header = '\n'.join(text.splitlines()[:14])
        ver = re.search(r'^\*\*Version (\d+(?:\.\d+)+) —', header, re.M)
        cid = re.search(r'^\*\*Component ID：([^*]+)\*\*$', header, re.M)
        contract = re.search(r'^\*\*Library Contract Version：([^*]+)\*\*$', header, re.M)
        suite = re.search(r'^\*\*Suite Version：([^*]+)\*\*$', header, re.M)
        if not ver or not cid or not contract or not suite:
            raise SuiteError(f'missing authoritative header: {c["path"]}')
        if cid[1] != c['id'] or contract[1] != config['contract_version'] or suite[1] != config['suite_version']:
            raise SuiteError(f'header/config mismatch: {c["path"]}')
        result.append({**c, 'version': ver[1], 'bytes': len(data), 'sha256': digest(data)})
    return result


def component_table(components: list[dict[str, Any]]) -> str:
    rows = ['| 番号 | ファイル | Version | 役割 |', '|---:|---|---|---|']
    rows += [f"| {c['order']:02d} | [{Path(c['path']).name}]({c['path']}) | {c['version']} | {c['description']} |" for c in components]
    return '\n'.join(rows)


def synchronized_readme(root: Path, components: list[dict[str, Any]]) -> str:
    text = (root / 'README.md').read_text(encoding='utf-8')
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise SuiteError('README needs exactly one managed components section')
    start = text.index(BEGIN) + len(BEGIN)
    end = text.index(END)
    if end < start:
        raise SuiteError('README markers in wrong order')
    return text[:start] + '\n\n' + component_table(components) + '\n\n' + text[end:]


def managed_files(root: Path, config: dict[str, Any]) -> list[Path]:
    excluded = config.get('manifest_exclusions', [])
    found: dict[str, Path] = {}
    for item in config['managed_paths']:
        p = safe_path(root, item)
        paths = sorted(p.rglob('*')) if p.is_dir() else [p]
        for f in paths:
            rel = f.relative_to(root).as_posix()
            if any(rel == e or rel.startswith(e + '/') for e in excluded):
                continue
            if '__pycache__' in f.parts or f.suffix == '.pyc' or f.name == '.DS_Store':
                continue
            if f.is_symlink():
                raise SuiteError(f'symlink in managed tree: {rel}')
            if f.is_file():
                found[rel] = safe_path(root, rel)
    return [found[key] for key in sorted(found)]


def expected_manifest(root: Path) -> tuple[dict[str, Any], str]:
    root = root.resolve()
    config = read_config(root)
    components = component_metadata(root, config)
    readme = synchronized_readme(root, components)
    entries = []
    for f in managed_files(root, config):
        rel = f.relative_to(root).as_posix()
        data = readme.encode('utf-8') if rel == 'README.md' else f.read_bytes()
        entries.append({'path': rel, 'bytes': len(data), 'sha256': digest(data)})
    return {
        'schema_version': '1.0',
        'suite_version': config['suite_version'],
        'contract_version': config['contract_version'],
        'released_on': config['released_on'],
        'hash_policy': 'raw-file-bytes; UTF-8-without-BOM and LF required for text',
        'scope': 'managed_paths only; excludes manifest, reports, model-run outputs and generated site',
        'components': components,
        'files': entries,
    }, readme


def fence_errors(text: str) -> list[str]:
    """Check Markdown fences; an outer four-backtick block can contain triple fences."""
    opened: tuple[str, int, int] | None = None
    errors = []
    for number, line in enumerate(text.splitlines(), 1):
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if not match:
            continue
        fence, rest = match.groups()
        if opened is None:
            if fence[0] == '`' and '`' in rest:
                continue
            opened = (fence[0], len(fence), number)
        elif fence[0] == opened[0] and len(fence) >= opened[1] and not rest.strip():
            opened = None
    if opened:
        errors.append(f'unclosed Markdown fence at line {opened[2]}')
    return errors


def json_examples(text: str) -> list[tuple[int, str]]:
    # Intentionally also inspect inner JSON examples in a copyable long prompt.
    pattern = r'^ {0,3}`{3}json\s*\n(.*?)^ {0,3}`{3}\s*$'
    return [(text[:m.start()].count('\n') + 1, m[1]) for m in re.finditer(pattern, text, re.M | re.S)]


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(content, encoding='utf-8', newline='\n')
    temporary.replace(path)
