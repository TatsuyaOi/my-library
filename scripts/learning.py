"""Opt-in article generation; legacy and Inbox metadata retain their own schemas."""
from datetime import date
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
from string import Template
from urllib.parse import unquote, urlsplit

from inbox import checked_path, strict_json

def documents(root):
    directory = checked_path(root, 'content')
    if not directory.exists():
        return []
    categories = strict_json(root / 'library.config.json')['categories']
    schema = strict_json(root / 'schemas/learning-meta.schema.json')
    result, seen = [], set()
    for folder in sorted(directory.iterdir()):
        if not folder.is_dir():
            raise ValueError(f'Unexpected content entry: {folder}')
        checked_path(root, folder.relative_to(root).as_posix())
        meta = strict_json(checked_path(folder, 'meta.json'))
        for key in schema['required']:
            if key not in meta:
                raise ValueError(f'{folder.name}: missing {key}')
        if set(meta) - set(schema['properties']):
            raise ValueError(f'{folder.name}: unknown metadata field')
        for key, rule in schema['properties'].items():
            value = meta[key]
            valid_type = {'string': str, 'integer': int, 'boolean': bool, 'array': list}[rule['type']]
            if type(value) is not valid_type:
                raise ValueError(f'{folder.name}: invalid type for {key}')
            if 'const' in rule and value != rule['const'] or 'enum' in rule and value not in rule['enum']:
                raise ValueError(f'{folder.name}: invalid {key}')
            if isinstance(value, str) and (not value.strip() or 'pattern' in rule and not re.fullmatch(rule['pattern'], value)):
                raise ValueError(f'{folder.name}: invalid {key}')
            if 'minimum' in rule and value < rule['minimum']:
                raise ValueError(f'{folder.name}: invalid {key}')
            if key == 'tags' and (not 3 <= len(value) <= 8 or len(set(map(str, value))) != len(value) or any(type(v) is not str or not v.strip() for v in value)):
                raise ValueError(f'{folder.name}: invalid tags')
        slug = meta['slug']
        if slug in seen or slug != folder.name:
            raise ValueError(f'Duplicate slug or folder mismatch: {slug}')
        seen.add(slug)
        if meta['category'] not in categories:
            raise ValueError(f'Unknown category: {meta["category"]}')
        if date.fromisoformat(meta['updated']) < date.fromisoformat(meta['created']):
            raise ValueError(f'{slug}: updated precedes created')
        if meta['publish'] and meta['status'] != 'active':
            raise ValueError(f'{slug}: publish requires active status')
        source = checked_path(folder, 'content.md')
        if not source.is_file():
            raise ValueError(f'Missing Markdown: {source}')
        result.append((folder, meta))
    return result


def selected(meta, preview=False):
    return preview or (meta['publish'] is True and meta['status'] == 'active')


def item(meta):
    return {'title': meta['title'], 'description': meta['summary'],
            'group': '学習教材', 'tags': meta['tags'], 'pinned': False,
            'order': 999999, 'updated': meta['updated'],
            'file': f'../content/{meta["slug"]}/index.html', 'learning_slug': meta['slug']}


def category_items(root, category, preview=False):
    return [item(meta) for _, meta in documents(root)
            if meta['category'] == category and selected(meta, preview)]


def render(root, folder, meta):
    from markdown_it import MarkdownIt
    parser = MarkdownIt('commonmark', {'html': False}).enable('table')
    tokens = parser.parse((folder / 'content.md').read_text(encoding='utf-8'))
    anchors_path = folder / 'anchors.json'
    anchors = strict_json(anchors_path) if anchors_path.exists() else None
    used_anchors = set()
    toc, headings = [], 0
    for i, token in enumerate(tokens):
        if token.type == 'heading_open':
            if token.tag == 'h1':
                raise ValueError(f'{folder.name}: use H2 or deeper; title comes from meta.json')
            headings += 1
            title = tokens[i + 1].content
            anchor = (anchors.get(title) or 'section-' + sha256(title.encode()).hexdigest()[:12]) if anchors is not None else f'section-{headings}'
            if not isinstance(anchor, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', anchor) or anchor in used_anchors:
                raise ValueError(f'{folder.name}: duplicate or invalid heading anchor')
            used_anchors.add(anchor)
            token.attrSet('id', anchor)
            if token.tag == 'h2':
                toc.append(f'<li><a href="#{anchor}">{escape(tokens[i + 1].content)}</a></li>')
    body = parser.renderer.render(tokens, parser.options, {})
    body = body.replace('<table>', '<div class="table-scroll" role="region" aria-label="比較表" tabindex="0"><table>')
    body = body.replace('</table>', '</table></div>')
    template = Template((root / 'templates/article.html').read_text(encoding='utf-8'))
    return template.substitute(title=escape(meta['title']), summary=escape(meta['summary']),
        status='下書きプレビュー' if not selected(meta) else '学習教材',
        updated=escape(meta['updated']), minutes=meta['learning_time_minutes'],
        toc=''.join(toc), body=body)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if key in attrs:
                self.links.append(attrs[key])


def validate_links(site, page):
    parser = Links()
    parser.feed(page.read_text(encoding='utf-8'))
    for link in parser.links:
        url = urlsplit(link)
        if url.scheme in ('https', 'http') and url.netloc:
            continue
        if url.scheme or url.netloc or url.path.startswith('/') or '\\' in unquote(url.path):
            raise ValueError(f'Unsupported article URL: {link}')
        # resolve() canonicalizes case on Windows and would hide wrong-case URLs.
        target = Path(os.path.abspath(page.parent / unquote(url.path))) if url.path else page.absolute()
        try:
            relative = target.relative_to(site.absolute())
        except ValueError:
            raise ValueError(f'Link escapes site: {link}')
        current = site
        for part in relative.parts:
            if part not in {p.name for p in current.iterdir()}:
                raise ValueError(f'Missing or case-mismatched link: {link}')
            current /= part
        if not target.is_file():
            raise ValueError(f'Missing article link: {link}')
        if url.fragment and target.suffix == '.html':
            other = Links()
            other.feed(target.read_text(encoding='utf-8'))
            if unquote(url.fragment) not in other.ids:
                raise ValueError(f'Missing anchor: {link}')


def export(root, stage, preview=False):
    pages = []
    for folder, meta in documents(root):
        # Validate drafts as well; no draft bytes are exported in public mode.
        html = render(root, folder, meta)
        if not selected(meta, preview):
            continue
        destination = stage / 'content' / meta['slug']
        destination.mkdir(parents=True)
        page = destination / 'index.html'
        page.write_text(html, encoding='utf-8', newline='\n')
        pages.append(page)
        assets = checked_path(folder, 'assets')
        if assets.exists():
            import shutil
            for asset in assets.rglob('*'):
                checked_path(folder, asset.relative_to(folder).as_posix())
                if asset.is_file():
                    if asset.suffix.lower() not in {'.svg', '.png', '.jpg', '.jpeg', '.webp', '.gif'}:
                        raise ValueError(f'Unsupported article asset: {asset}')
                    target = destination / asset.relative_to(folder)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(asset, target)
    for page in pages:
        validate_links(stage, page)


def add_preview_items(root, stage):
    """Only the isolated preview manifests receive unpublished articles."""
    global_data = strict_json(stage / 'library-all.json')
    for category in global_data['categories']:
        path = stage / category['folder'] / 'library.json'
        data = strict_json(path)
        for _, meta in documents(root):
            if meta['category'] != category['folder'] or selected(meta):
                continue
            entry = item(meta)
            data['items'].append(entry)
            global_data['items'].append(dict(entry, category_folder=category['folder'],
                category_title=category['title'], category_icon=category['icon'],
                url=f'./content/{meta["slug"]}/index.html'))
        category['count'] = len(data['items'])
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    (stage / 'library-all.json').write_text(json.dumps(global_data, ensure_ascii=False, indent=2), encoding='utf-8')
