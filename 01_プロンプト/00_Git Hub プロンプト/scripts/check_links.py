#!/usr/bin/env python3
"""Check literal local HTML/CSS/JS/manifest links. Dynamic JS and external URLs need browser review."""
from __future__ import annotations
import argparse
from html.parser import HTMLParser
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
from suite_tools import ROOT, load_json

class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[];self.ids=set()
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        for k in ['href','src']:
            if k in d:self.links.append(d[k])
        if 'id' in d:self.ids.add(d['id'])


def inspect(site: Path, base_path: str | None = None) -> list[str]:
    site=site.resolve();errors=[]
    if base_path is not None and (not base_path.startswith('/') or not base_path.endswith('/') or '..' in base_path or '\\' in base_path or '?' in base_path or '#' in base_path):
        return ['invalid configured base_path; use a known /repo/ or /']
    if not site.is_dir():return ['site directory missing']
    for p in site.rglob('*'):
        if not p.is_file() or p.suffix not in {'.html','.css','.js','.webmanifest'}:continue
        text=p.read_text(encoding='utf-8');urls=[]
        if p.suffix=='.html':
            parser=Links();parser.feed(text);urls+=parser.links
        if p.suffix=='.webmanifest':
            m=load_json(p);urls += [i['src'] for i in m.get('icons',[])]
            urls += [m[k] for k in ['start_url','scope'] if k in m]
        urls += re.findall(r"url\(\s*['\"]?([^'\"\)]+)",text)
        urls += re.findall(r"(?:fetch|register)\(\s*['\"]([^'\"]+)['\"]",text)
        for url in urls:
            url=url.strip();parts=urlsplit(url)
            if parts.scheme in {'http','https','mailto','tel'}:continue
            if parts.scheme=='data' and url.startswith('data:image/'):continue
            if parts.scheme or parts.netloc:
                errors.append(f'{p.name}: unsafe scheme or protocol-relative URL');continue
            decoded=unquote(parts.path)
            if '\\' in decoded:
                errors.append(f'{p.name}: Windows path: {url}');continue
            if decoded.startswith('/'):
                if base_path is None or not decoded.startswith(base_path):
                    errors.append(f'{p.name}: root path outside configured base: {url}');continue
                target=(site/decoded[len(base_path):]).resolve()
            else:
                target=(p.parent/decoded).resolve() if decoded else p
            if not target.is_relative_to(site):
                errors.append(f'{p.name}: local path escaped site: {url}');continue
            if target.is_dir():target=target/'index.html'
            if not target.is_file():errors.append(f'{p.name}: missing local target: {url}');continue
            if parts.fragment and target.suffix=='.html':
                ids=Links();ids.feed(target.read_text(encoding='utf-8'))
                if unquote(parts.fragment) not in ids.ids:
                    errors.append(f'{p.name}: missing anchor: {url}')
    return sorted(set(errors))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--site',type=Path,default=ROOT/'site');p.add_argument('--base-path');a=p.parse_args(argv)
    try:
        base_path=a.base_path
        config_path=ROOT/'config/library.config.json'
        if base_path is None and config_path.is_file():
            base_path=load_json(config_path).get('site',{}).get('base_path')
        errors=inspect(a.site,base_path)
        if errors:print('\n'.join(errors));return 1
        print('PASS: literal local links. External URLs, dynamic JS, deep 404 and browser behavior NOT_RUN.');return 0
    except Exception as e:print(f'FAIL: {e}',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
