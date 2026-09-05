#!/usr/bin/env python3
"""Validate generated navigation and export only site roots, never the Inbox."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import tempfile
from inbox import checked_path, settings, strict_json, digest

ROOT = Path(__file__).resolve().parents[1]
MARKER = '.my-library-output'
ROOT_FILES = ('index.html', 'library-all.json', '.nojekyll', 'CNAME',
              'robots.txt', 'favicon.ico', 'manifest.webmanifest', 'sw.js')


def validate_managed(root, categories):
    ids = set()
    for category in categories:
        for path in checked_path(root, category).rglob('meta.json'):
            meta = strict_json(path)
            ingestion = meta.get('ingestion', {})
            if not isinstance(ingestion, dict) or ingestion.get('tool') != 'my-library-inbox-v1':
                continue
            if meta['id'] in ids:
                raise ValueError(f'Duplicate Inbox ID: {meta["id"]}')
            ids.add(meta['id'])
            if ingestion.get('publication_reviewed') is not True:
                raise ValueError(f'Publication was not reviewed: {path}')
            for name, sha in ingestion['output_sha256'].items():
                target = checked_path(path.parent, name)
                if not target.is_file() or digest(target.read_bytes()) != sha:
                    raise ValueError(f'Imported output changed or missing: {target}')


def validate_index(site: Path):
    index = strict_json(site / 'library-all.json')
    seen = set()
    for item in index['items']:
        if item['url'] in seen:
            raise ValueError(f'Duplicate index URL: {item["url"]}')
        seen.add(item['url'])
        for field in ('url', 'thumbnail_url', 'preview_url'):
            name = item.get(field)
            if name:
                if not isinstance(name, str) or not name.startswith('./'):
                    raise ValueError(f'Expected relative library URL: {name!r}')
                target = checked_path(site, name[2:])
                if not target.is_file():
                    raise ValueError(f'Missing indexed file: {name}')
    for category in index['categories']:
        directory = checked_path(site, category['folder'])
        data = strict_json(directory / 'library.json')
        if not (directory / 'index.html').is_file() or category['count'] != len(data['items']):
            raise ValueError(f'Category index/count mismatch: {category["folder"]}')
    return len(index['items'])


def prepare(root: Path):
    config, inbox, categories = settings(root)
    validate_managed(root, categories)
    roots = [checked_path(root, 'assets')] + [checked_path(root, n) for n in categories]
    for directory in roots:
        if directory == inbox or inbox in directory.parents or directory in inbox.parents:
            raise ValueError('Inbox overlaps a published root.')
    try:
        tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=root,
                      text=True, encoding='utf-8', stderr=subprocess.DEVNULL).split('\0'))
    except (OSError, subprocess.CalledProcessError):
        tracked = None
    generated = {f'{name}/{filename}' for name in categories for filename in ('index.html', 'library.json')}
    with tempfile.TemporaryDirectory(prefix='.pages-stage-', dir=root) as tmp:
        stage = Path(tmp) / 'site'
        stage.mkdir()
        for name in ROOT_FILES:
            path = root / name
            if path.is_symlink():
                raise ValueError(f'Symlink is not publishable: {name}')
            if path.is_file():
                shutil.copy2(path, stage / name)
        for directory in roots:
            if not directory.is_dir():
                raise ValueError(f'Missing site directory: {directory.name}')
            for path in directory.rglob('*'):
                name = path.relative_to(root)
                if any(part.startswith('.') for part in name.parts):
                    continue
                if path.is_symlink():
                    raise ValueError(f'Symlink is not publishable: {name}')
                if not path.is_file():
                    continue
                if tracked is not None and name.as_posix() not in tracked and name.as_posix() not in generated:
                    continue
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        count = validate_index(stage)
        (stage / MARKER).write_text('my-library-pages-v1\n', encoding='utf-8')
        destination = root / '_site'
        if destination.is_symlink():
            raise ValueError('_site must not be a symlink.')
        if destination.exists():
            if not (destination / MARKER).is_file():
                raise ValueError('Existing _site is not managed by this script; leave it untouched.')
            shutil.rmtree(destination)
        stage.rename(destination)
    return {'items': count, 'output': '_site', 'inbox_exported': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.root.resolve()), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f'Pages validation error: {exc}\n')
