#!/usr/bin/env python3
"""Copy reviewed Inbox material into existing categories; never execute input.

Python 3.10+, standard library only. Classification is performed by Codex,
not this script. The default `apply` is a dry run; --write opts in to changes.
"""
from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
TEXT = {'.md', '.txt'}
HTML = {'.html', '.htm'}
SUPPORT = {'.css', '.js', '.json', '.woff', '.woff2', '.ttf', '.otf'}
RESERVED = {'agents.md', 'agents.override.md', 'meta.json', '_library_view.html'}


def strict_json(path: Path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def relative_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError(f'Invalid relative path: {value!r}')
    p = PurePosixPath(value)
    if p.is_absolute() or any(x in {'', '.', '..'} for x in value.split('/')):
        raise ValueError(f'Path traversal or ambiguous path: {value!r}')
    if any(re.search(r'[<>:"|?*\x00-\x1f]', x) or x.endswith(('.', ' ')) for x in p.parts):
        raise ValueError(f'Not a portable path: {value!r}')
    if any(x.startswith('.') or x in {'_processed', '_site'} for x in p.parts):
        raise ValueError(f'Internal path is not importable: {value!r}')
    if any(re.fullmatch(r'(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', x, re.I) for x in p.parts):
        raise ValueError(f'Reserved Windows filename: {value!r}')
    return p


def checked_path(base: Path, name: str) -> Path:
    p = relative_path(name)
    current = base
    if base.is_symlink():
        raise ValueError(f'Symlink root is not allowed: {base.name}')
    for part in p.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f'Symlink is not allowed: {name}')
    current.resolve().relative_to(base.resolve())
    return current


def settings(root: Path):
    config = strict_json(root / 'inbox.config.json')
    inbox = checked_path(root, config['directory'])
    categories = strict_json(root / 'library.config.json')['categories']
    if config.get('require_publication_review') is not True:
        raise ValueError('Publication review must remain enabled.')
    return config, inbox, categories


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PageInfo(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []
        self.meta = {}
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'title':
            self.in_title = True
        if tag == 'base':
            raise ValueError('<base> requires manual review; automatic import is stopped.')
        if tag == 'meta' and attrs.get('name'):
            self.meta[attrs['name'].lower()] = attrs.get('content', '')
        for key in ('src', 'href', 'poster', 'data'):
            if attrs.get(key):
                self.references.append(attrs[key])
        if attrs.get('srcset'):
            # Data-URI srcsets are ambiguous to a comma splitter: require review.
            if 'data:' in attrs['srcset']:
                raise ValueError('Data URI srcset requires manual review.')
            self.references.extend(x.strip().split()[0] for x in attrs['srcset'].split(',') if x.strip())
        if attrs.get('style'):
            self.references.extend(css_references(attrs['style']))

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)


def css_references(text: str) -> list[str]:
    refs = re.findall(r'''url\(\s*["']?([^\s\)"']+)["']?\s*\)''', text, re.I)
    refs += re.findall(r'''@import\s+["']([^"']+)["']''', text, re.I)
    return refs


def local_reference(parent: PurePosixPath, ref: str) -> str | None:
    if not ref or ref.startswith('#'):
        return None
    if '\\' in ref or re.search(r'[\x00-\x1f]', ref):
        raise ValueError(f'Invalid URL: {ref!r}')
    parts = urlsplit(ref)
    if parts.scheme in {'https', 'http', 'mailto', 'tel', 'data'} or ref.startswith('//'):
        return None
    if parts.scheme or parts.path.startswith('/'):
        raise ValueError(f'Local/absolute/unsupported URL: {ref!r}')
    if not parts.path:
        return None
    # Resolve ../ without permitting a link to escape the new document bundle.
    stack = list(parent.parts) if str(parent) != '.' else []
    for part in unquote(parts.path).split('/'):
        if part in {'', '.'}:
            continue
        if part == '..':
            if not stack:
                raise ValueError(f'Link escapes document bundle: {ref!r}')
            stack.pop()
        else:
            stack.append(part)
    return '/'.join(stack)


def check_links(files: dict[str, bytes]):
    for name, content in files.items():
        ext = PurePosixPath(name).suffix.lower()
        refs = []
        if ext in HTML:
            text = content.decode('utf-8-sig')
            parser = PageInfo()
            parser.feed(text)
            refs = parser.references + css_references(text)
            if re.search(r'''(?:[A-Za-z]:[\\/]|file:///|sandbox:/mnt/)''', text):
                raise ValueError(f'Local-only reference found in {name}')
        elif ext == '.css':
            refs = css_references(content.decode('utf-8-sig'))
        for ref in refs:
            target = local_reference(PurePosixPath(name).parent, ref)
            if target is not None and target not in files and f'{target}/index.html' not in files:
                raise ValueError(f'Missing bundled dependency: {name} -> {ref}')


def processed_sources(root: Path, categories: dict) -> dict[str, set[str]]:
    result = {}
    for category in categories:
        directory = checked_path(root, category)
        if not directory.exists():
            continue
        for path in directory.rglob('meta.json'):
            if path.is_symlink():
                continue
            meta = strict_json(path)
            ingestion = meta.get('ingestion', {})
            if isinstance(ingestion, dict) and ingestion.get('tool') == 'my-library-inbox-v1':
                for name, sha in ingestion.get('source_sha256', {}).items():
                    result.setdefault(name, set()).add(sha)
    return result


def scan(root: Path) -> dict:
    config, inbox, categories = settings(root)
    done = processed_sources(root, categories)
    records = []
    if not inbox.exists():
        return {'directory': config['directory'], 'files': [], 'note': 'Inbox does not exist yet.'}
    for path in sorted(inbox.rglob('*')):
        name = path.relative_to(inbox).as_posix()
        if name == 'README.md' or any(x.startswith('.') or x == '_processed' for x in PurePosixPath(name).parts):
            continue
        try:
            checked_path(inbox, name)
            if path.is_dir():
                continue
            if path.stat().st_size > config['max_file_mb'] * 1024 * 1024:
                raise ValueError('File exceeds max_file_mb; review separately.')
            data = path.read_bytes()
            sha = digest(data)
            state = 'processed' if sha in done.get(name, set()) else 'pending'
            record = {'path': name, 'sha256': sha, 'bytes': len(data), 'state': state}
            if path.suffix.lower() in HTML:
                parser = PageInfo()
                parser.feed(data.decode('utf-8-sig'))
                record['title'] = parser.meta.get('library-title') or ''.join(parser.title).strip() or path.stem
            records.append(record)
        except (ValueError, UnicodeError, OSError) as exc:
            records.append({'path': name, 'state': 'hold', 'reason': str(exc)})
    return {'directory': config['directory'], 'files': records}


def viewer(title: str, files: dict[str, bytes], entry: str | None) -> bytes:
    def url(name):
        return html.escape(quote(name, safe='/'), quote=True)
    if entry and PurePosixPath(entry).suffix.lower() in TEXT:
        # Preserve all source text; rendering Markdown is deliberately not lossy.
        body = '<pre>' + html.escape(files[entry].decode('utf-8-sig')) + '</pre>'
    else:
        images = [name for name in files if PurePosixPath(name).suffix.lower() in IMAGES]
        if not images:
            raise ValueError('No HTML, text, or supported image to display.')
        body = ''.join(f'<figure><a href="{url(n)}"><img src="{url(n)}" alt="{html.escape(PurePosixPath(n).name, quote=True)}" loading="lazy"></a></figure>' for n in images)
    downloads = ''.join(f'<li><a href="{url(n)}" download>{html.escape(n)}</a></li>' for n in files)
    return (f'<!doctype html>\n<html lang="ja"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>'
            'body{font:18px/1.7 "Meiryo UI",Meiryo,sans-serif;margin:0;padding:20px;overflow-wrap:anywhere}'
            'main{max-width:900px;margin:auto}img{max-width:100%;height:auto}figure{margin:18px 0}'
            'pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}a{display:inline-block;padding:8px 0}'
            '</style></head><body><main><a href="../index.html">← カテゴリ</a>'
            f'<h1>{html.escape(title)}</h1>{body}<details><summary>原本ファイル</summary>'
            f'<ul>{downloads}</ul></details></main></body></html>\n').encode('utf-8')


def prepare_item(root: Path, item: dict, config: dict, inbox: Path, categories: dict):
    if item.get('publish') is not True or item.get('reviewed') is not True:
        raise ValueError('publish:true and reviewed:true are required; hold sensitive/unknown material.')
    category = item['category']
    if category not in categories:
        raise ValueError(f'Unknown category: {category}')
    slug = item['id']
    if len(relative_path(slug).parts) != 1 or len(slug) > 100:
        raise ValueError('id must be one portable folder name, at most 100 characters.')
    folder = item.get('folder', slug)
    if len(relative_path(folder).parts) != 1 or len(folder) > 100:
        raise ValueError('folder must be one portable folder name, at most 100 characters.')
    destination = checked_path(root, f'{category}/{folder}')
    if not isinstance(item.get('title'), str) or not item['title'].strip():
        raise ValueError('title is required.')
    names = item.get('files')
    hashes = item.get('sha256', {})
    if not isinstance(names, list) or not names or len(set(names)) != len(names):
        raise ValueError('files must be a nonempty, duplicate-free list.')
    files = {}
    seen = set()
    for name in names:
        path = checked_path(inbox, name)
        if name.casefold() in seen:
            raise ValueError(f'Case-insensitive filename collision: {name}')
        seen.add(name.casefold())
        if path.name.lower() in RESERVED or path.suffix.lower() not in (IMAGES | HTML | TEXT | SUPPORT):
            raise ValueError(f'Unsupported or reserved input: {name}')
        if not path.is_file() or path.stat().st_size > config['max_file_mb'] * 1024 * 1024:
            raise ValueError(f'Missing or oversized input: {name}')
        data = path.read_bytes()
        if digest(data) != hashes.get(name):
            raise ValueError(f'Input changed or SHA-256 is missing: {name}; scan/review again.')
        files[name] = data
    entry = item.get('entry')
    if entry is not None and entry not in files:
        raise ValueError('entry must be one of files.')
    if entry is None and any(PurePosixPath(n).suffix.lower() in HTML | TEXT for n in files):
        raise ValueError('Select an explicit entry for HTML/text documents.')
    if entry and PurePosixPath(entry).suffix.lower() not in HTML | TEXT | IMAGES:
        raise ValueError('Unsupported entry format.')
    check_links(files)
    tags = item.get('tags', [])
    if not isinstance(tags, list) or any(not isinstance(x, str) for x in tags):
        raise ValueError('tags must be an array of strings.')
    for field in ('summary', 'group', 'type'):
        if field in item and not isinstance(item[field], str):
            raise ValueError(f'{field} must be a string.')
    semantic = {k: item.get(k) for k in ('id', 'category', 'title', 'summary', 'group', 'type', 'tags', 'entry')}
    for key in ('folder', 'guide'):
        if key in item:
            semantic[key] = item[key]
    semantic['sha256'] = {name: digest(data) for name, data in sorted(files.items())}
    fingerprint = digest(json.dumps(semantic, ensure_ascii=False, sort_keys=True).encode('utf-8'))
    original_html = entry and PurePosixPath(entry).suffix.lower() in HTML
    guide = entry if original_html else item.get('guide', '_library_view.html')
    if original_html and 'guide' in item and item['guide'] != entry:
        raise ValueError('Original HTML entry must not be renamed by guide.')
    if not original_html:
        guide_path = relative_path(guide)
        if len(guide_path.parts) != 1 or guide_path.suffix.lower() not in HTML:
            raise ValueError('guide must be one portable HTML filename.')
        if guide.casefold() in seen:
            raise ValueError('Generated guide collides with an input file.')
    source_names = list(files)
    if not original_html:
        files[guide] = viewer(item['title'], files, entry)
    preview = next((n for n in source_names if PurePosixPath(n).suffix.lower() in IMAGES), None)
    meta = {
        'schema_version': '1.0', 'id': slug, 'title': item['title'],
        'type': item.get('type', 'reference'), 'category': category,
        'subcategory': item.get('group') or None, 'summary': item.get('summary', ''),
        'tags': tags, 'status': 'active', 'version': None, 'language': 'ja',
        'dates': {'created': None, 'updated': None},
        'files': {'source': entry or source_names[0], 'guide': guide, 'preview': preview,
                  'additional': [n for n in source_names if n not in {entry, preview}]},
        'search': {'keywords': []}, 'relations': {'parent_id': None, 'related_ids': []},
        'ingestion': {'tool': 'my-library-inbox-v1', 'fingerprint': fingerprint,
                      'publication_reviewed': True, 'source_sha256': semantic['sha256'],
                      'output_sha256': {n: digest(b) for n, b in files.items()}}
    }
    files['meta.json'] = (json.dumps(meta, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if destination.exists():
        if not destination.is_dir():
            raise ValueError(f'Destination is not a directory: {destination.name}')
        # Every byte must match: repeated processing cannot silently overwrite edits.
        if all(checked_path(destination, n).is_file() and checked_path(destination, n).read_bytes() == b for n, b in files.items()):
            return destination, files, 'already_processed'
        raise ValueError(f'Destination already exists with different content: {category}/{slug}')
    return destination, files, 'ready'


def apply_plan(root: Path, plan: dict, write: bool = False) -> dict:
    config, inbox, categories = settings(root)
    if plan.get('version') != 1 or not isinstance(plan.get('items'), list):
        raise ValueError('Expected version:1 and items:[...].')
    existing_ids = {}
    for category in categories:
        directory = checked_path(root, category)
        if directory.exists():
            for meta_path in directory.rglob('meta.json'):
                meta = strict_json(meta_path)
                if isinstance(meta.get('id'), str) and meta['id']:
                    existing_ids.setdefault(meta['id'].casefold(), set()).add(meta_path.parent)
    prepared = []
    targets = set()
    batch_ids = set()
    total = 0
    for item in plan['items']:
        if item.get('hold') is True:
            continue
        destination, files, state = prepare_item(root, item, config, inbox, categories)
        document_id = item['id'].casefold()
        if document_id in batch_ids or any(p != destination for p in existing_ids.get(document_id, set())):
            raise ValueError(f'Duplicate document ID: {item["id"]}')
        batch_ids.add(document_id)
        if destination.parent.exists() and any(p.name.casefold() == destination.name.casefold() and p != destination for p in destination.parent.iterdir()):
            raise ValueError('Case-insensitive destination collision.')
        key = str(destination.relative_to(root)).casefold()
        if key in targets:
            raise ValueError('Duplicate destination in this batch.')
        targets.add(key)
        total += sum(len(x) for x in files.values())
        if total > config['max_batch_mb'] * 1024 * 1024:
            raise ValueError('Batch exceeds max_batch_mb.')
        prepared.append((destination, files, state))
    # Preflight all items before writing anything. Originals are always retained.
    created = []
    if write:
        try:
            for destination, files, state in prepared:
                if state == 'already_processed':
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix='.inbox-stage-', dir=destination.parent) as tmp:
                    staging = Path(tmp) / 'document'
                    staging.mkdir()
                    for name, data in files.items():
                        p = staging / name
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_bytes(data)
                    if destination.exists():
                        raise ValueError('Destination appeared during import; refusing overwrite.')
                    staging.rename(destination)
                    created.append(destination)
        except Exception:
            for directory in reversed(created):
                shutil.rmtree(directory)  # Only directories created by this invocation.
            raise
    return {'mode': 'written' if write else 'dry-run',
            'documents': [{'path': p.relative_to(root).as_posix(), 'state': state,
                           'file_count': len(files)} for p, files, state in prepared],
            'held': sum(x.get('hold') is True for x in plan['items']),
            'originals': 'retained'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('scan')
    apply = sub.add_parser('apply')
    apply.add_argument('plan', type=Path)
    apply.add_argument('--write', action='store_true')
    args = parser.parse_args()
    try:
        root = args.root.resolve()
        result = scan(root) if args.command == 'scan' else apply_plan(root, strict_json(args.plan), args.write)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, UnicodeError) as exc:
        parser.exit(1, f'Inbox error: {exc}\n')


if __name__ == '__main__':
    main()
