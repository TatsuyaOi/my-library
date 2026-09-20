"""Keep old document URLs usable without duplicating the editable sources."""
import shutil
from pathlib import PurePosixPath
from inbox import checked_path, strict_json


def export_legacy_urls(root, site):
    manifest = root / 'library-moves.json'
    if not manifest.exists():
        return
    data = strict_json(manifest)
    if data.get('schema_version') != 1 or not isinstance(data.get('moves'), list):
        raise ValueError('Invalid library moves manifest')
    categories = strict_json(root / 'library.config.json')['categories']
    public = {i['url'].removeprefix('./') for i in strict_json(site / 'library-all.json')['items']}
    paths, pending = [], []
    for move in data['moves']:
        old, new = move['from'], move['to']
        for name in (old, new):
            parts = PurePosixPath(name).parts
            if len(parts) != 2 or parts[0] not in categories:
                raise ValueError('Move must name a document folder in a configured category')
            checked_path(root, name)
            folded = name.casefold()
            if folded in paths:
                raise ValueError('Duplicate or chained library move')
            paths.append(folded)
        if checked_path(root, old).exists():
            raise ValueError('Legacy folder must not duplicate editable sources')
        destination = checked_path(site, old)
        if destination.exists():
            raise ValueError('Legacy URL collision')
        # A removed/hidden guide must not be republished through its old URL.
        if not any(url.startswith(new + '/') for url in public):
            continue
        source = checked_path(site, new)
        if not source.is_dir():
            raise ValueError('Published move destination missing')
        for path in source.rglob('*'):
            checked_path(site, path.relative_to(site).as_posix())
        pending.append((source, destination))
    # Only already-exported public bytes; never read arbitrary repository inputs.
    # Exact copies retain fragment anchors, downloads and relative asset links.
    for source, destination in pending:
        shutil.copytree(source, destination)
