"""Adapt new Inbox metadata while retaining the existing HTML-meta index format."""
from pathlib import Path
from inbox import checked_path, strict_json


def managed_info(path: Path, category_dir: Path):
    parent = path.parent
    while parent != category_dir:
        meta_path = parent / 'meta.json'
        if meta_path.is_file():
            meta = strict_json(meta_path)
            ingestion = meta.get('ingestion', {})
            if isinstance(ingestion, dict) and ingestion.get('tool') == 'my-library-inbox-v1':
                if ingestion.get('publication_reviewed') is not True:
                    raise ValueError(f'Publication review missing: {meta_path}')
                files = meta['files']
                guide = checked_path(parent, files['guide'])
                if not guide.is_file():
                    raise ValueError(f'Missing guide: {guide}')
                if path != guide:
                    return {'skip': True}
                media = {}
                preview = files.get('preview')
                thumbnail = files.get('thumbnail') or preview
                for key, name in [('preview', preview), ('thumbnail', thumbnail)]:
                    if name:
                        target = checked_path(parent, name)
                        if not target.is_file():
                            raise ValueError(f'Missing media: {target}')
                        media[key] = target.relative_to(category_dir).as_posix()
                if media:
                    media['thumbnail_alt'] = meta['title']
                info = {'title': meta['title'], 'description': meta.get('summary', ''),
                        'group': meta.get('subcategory') or '未分類', 'tags': meta.get('tags', [])}
                if meta.get('status') in {'draft', 'hidden'}:
                    info['hidden'] = True
                return {'skip': False, 'info': info, 'media': media}
        parent = parent.parent
        if category_dir not in (parent, *parent.parents):
            break
    return None
