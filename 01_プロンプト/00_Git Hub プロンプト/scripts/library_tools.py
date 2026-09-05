"""Deterministic Library Contract 2.0 build planning, with explicit publication boundaries."""
from __future__ import annotations
import copy
import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any
from jsonschema import Draft202012Validator, FormatChecker
from suite_tools import SuiteError, digest, dump_json, load_json, safe_path

OWNERSHIP = '.library-build-owned.json'


def schema_validate(root: Path, schema: str, value: Any) -> None:
    doc = load_json(root/'schemas'/schema)
    Draft202012Validator.check_schema(doc)
    errors = list(Draft202012Validator(doc, format_checker=FormatChecker()).iter_errors(value))
    if errors:
        raise SuiteError('; '.join(e.message for e in errors[:4]))


def published(meta: dict[str, Any]) -> bool:
    return meta.get('status') == 'active' and meta.get('visibility') == 'public' and meta.get('publish') is True


def file_for(folder: Path, name: str | None) -> Path | None:
    if name is None:
        return None
    p = safe_path(folder, name)
    if not p.is_file():
        raise SuiteError(f'not a file: {name}')
    return p


def plan(root: Path, include_ui: bool = True) -> tuple[dict[str, Any], dict[str, Path], dict[str, Any]]:
    root = root.resolve()
    config = load_json(root/'config/library.config.json')
    if config.get('contract_version') != '2.0':
        raise SuiteError('Library Contract 2.0 is required')
    source_root = safe_path(root, config['paths']['content_root'])
    categories = config['categories']
    cat_ids = {c['id'] for c in categories}
    if len(cat_ids) != len(categories):
        raise SuiteError('duplicate category ID')
    entries = []
    copies: dict[str, Path] = {}
    warnings: list[str] = []
    excluded: list[dict[str, str]] = []
    identifiers: dict[str, str] = {}
    input_hashes: dict[str, str] = {'config/library.config.json': digest((root/'config/library.config.json').read_bytes())}
    for path in sorted(source_root.rglob('meta.json')):
        safe_path(source_root, path.relative_to(source_root).as_posix())
        meta = load_json(path)
        try:
            schema_validate(root, 'meta.schema.json', meta)
        except SuiteError as e:
            # Strict starter policy: fail, rather than silently deploy a possibly unintended subset.
            raise SuiteError(f'{path.relative_to(root)}: metadata schema invalid: {e}') from e
        if meta['category'] not in cat_ids:
            raise SuiteError(f"unknown category for {meta['id']}")
        for identifier in set([meta['id'], meta['slug'], *meta['aliases']]):
            owner = identifiers.get(identifier)
            if owner and owner != path.as_posix():
                raise SuiteError(f'duplicate ID/slug/alias: {identifier}')
            identifiers[identifier] = path.as_posix()
        if not published(meta):
            excluded.append({'id': meta['id'], 'reason': 'publication not explicitly allowed'})
            continue
        folder = path.parent
        try:
            source = file_for(folder, meta['files']['source'])
        except SuiteError as e:
            raise SuiteError(f"unsafe or missing source for {meta['id']}: {e}") from e
        if source is None:
            excluded.append({'id': meta['id'], 'reason': 'missing source'})
            continue
        source_hash = digest(source.read_bytes())
        if source_hash != meta['integrity']['source_sha256']:
            excluded.append({'id': meta['id'], 'reason': 'stale metadata source hash'})
            continue
        if source.suffix.lower() != '.md':
            raise SuiteError('source must be Markdown in this strict Contract 2.0 starter')
        entry = {k: copy.deepcopy(meta[k]) for k in ['id','slug','aliases','title','type','category','subcategory','summary','tags','version','language','dates','search','relations']}
        entry['paths'] = {'source': None, 'guide': None, 'preview': None, 'thumbnail': None}
        entry['media'] = {role: {'alt': None, 'width': None, 'height': None} for role in ['preview','thumbnail']}
        good_files: dict[str, Path] = {'source': source}
        for role in ['guide','preview','thumbnail']:
            name = meta['files'][role]
            if not name:
                continue
            try:
                actual = file_for(folder, name)
            except SuiteError as e:
                warnings.append(f"{meta['id']} {role}: {e}")
                continue
            if actual is None:
                continue
            integrity = meta['integrity']
            good = digest(actual.read_bytes()) == integrity[role+'_sha256']
            if role == 'thumbnail':
                preview = good_files.get('preview')
                good = good and preview is not None and integrity['thumbnail_generated_from_preview_sha256'] == digest(preview.read_bytes())
            else:
                good = good and integrity[role+'_generated_from_source_sha256'] == source_hash
            if not good:
                warnings.append(f"{meta['id']} {role}: stale or unknown provenance")
                continue
            good_files[role] = actual
        for role, file in good_files.items():
            rel = file.relative_to(folder).as_posix()
            if role != 'source' and file == source:
                raise SuiteError('derived file must not alias source')
            target = f"items/{meta['slug']}/{rel}"
            if target in copies and copies[target] != file:
                raise SuiteError('public path collision: '+target)
            copies[target] = file
            entry['paths'][role] = target
            if role in entry['media']:
                entry['media'][role] = {k: meta['media'][role][k] for k in ['alt','width','height']}
        # Additional files cannot bypass the integrity decision for a managed derivative.
        reserved_derivatives = {meta['files'][role] for role in ['guide','preview','thumbnail'] if meta['files'][role]}
        # Additional files are explicitly listed by the owner, never a directory-wide copy.
        for name in meta['files']['additional']:
            if name in reserved_derivatives:
                raise SuiteError('derived file must not be duplicated in additional: '+name)
            file = file_for(folder, name)
            if file is None:
                continue
            if file.name.startswith('.') or file.name == 'meta.json' or file.suffix.lower() in {'.key','.pem'}:
                raise SuiteError('private/metadata file cannot be published as additional: '+name)
            target = f"items/{meta['slug']}/{file.relative_to(folder).as_posix()}"
            if target in copies and copies[target] != file:
                raise SuiteError('additional file path collision: '+target)
            copies[target] = file
        entries.append(entry)
        input_hashes[path.relative_to(root).as_posix()] = digest(path.read_bytes())
    public_ids = {e['id'] for e in entries}
    for entry in entries:
        relations = entry['relations']
        relations['related_ids'] = [i for i in relations['related_ids'] if i in public_ids]
        if relations['parent_id'] not in public_ids:
            relations['parent_id'] = None
    if include_ui:
        ui = safe_path(root, config['paths']['ui_root'])
        for required in ['index.html','404.html']:
            safe_path(ui, required)
        allowed = {'index.html','404.html','manifest.webmanifest','sw.js','offline.html','CNAME'}
        for file in sorted(ui.rglob('*')):
            rel = file.relative_to(ui).as_posix()
            if file.is_symlink():
                raise SuiteError('symlink in UI source')
            if not file.is_file() or (rel not in allowed and not rel.startswith('icons/')):
                continue
            safe_path(ui, rel)
            copies[rel] = file
    order = {c['id']: c['order'] for c in categories}
    # Stable multi-pass ordering: category, newest date, title, ID.
    entries.sort(key=lambda e:(e['title'], e['id']))
    entries.sort(key=lambda e:e['dates']['updated'] or '', reverse=True)
    entries.sort(key=lambda e:order[e['category']])
    for target, path in copies.items():
        input_hashes['public/'+target] = digest(path.read_bytes())
    for name in ['library_tools.py','suite_tools.py']:
        path = root/'scripts'/name
        if path.is_file():
            input_hashes['scripts/'+name] = digest(path.read_bytes())
    for name in ['meta.schema.json','library.schema.json']:
        input_hashes['schemas/'+name] = digest((root/'schemas'/name).read_bytes())
    build_id = digest(dump_json(dict(sorted(input_hashes.items()))).encode('utf-8'))
    counts = {c['id']: sum(e['category'] == c['id'] for e in entries) for c in categories}
    library = {'schema_version':'2.0','build':{'build_id':build_id,'generated_at':None,'source_schema_version':'2.0'},
               'library':config['library'], 'facets':{'categories':[{**c,'count':counts[c['id']]} for c in categories]},
               'stats':{'total_items':len(entries),'excluded_items':0,'stale_guides':0,'stale_previews':0,'stale_thumbnails':0,'warnings':0,'categories':counts},
               'items':entries}
    # Internal exclusion and warning details are deliberately not included in public stats.
    schema_validate(root, 'library.schema.json', library)
    return library, copies, {'excluded':excluded,'warnings':warnings,'published':len(entries),'input_hashes':input_hashes,
                             'note':'This is a structural build; content correctness, secrets and browser behavior need separate review.'}


def write_build(root: Path, include_ui: bool = True, allow_empty: bool = False, allow_removals: bool = False) -> dict[str, Any]:
    root = root.resolve()
    config = load_json(root/'config/library.config.json')
    content = safe_path(root, config['paths']['content_root'])
    output_rel = config['paths']['site_root']
    # This starter owns exactly site/. Arbitrary deletion targets are not configurable.
    if output_rel != 'site':
        raise SuiteError('starter build requires a dedicated site/ output; adapt explicitly for another layout')
    output = safe_path(root, output_rel, must_exist=False)
    if output == root or output.is_relative_to(content) or content.is_relative_to(output):
        raise SuiteError('output overlaps source or repository root')
    library, copies, report = plan(root, include_ui)
    if not library['items'] and not allow_empty:
        raise SuiteError('no publishable items; refusing an empty build without --allow-empty')
    if output.exists():
        marker = output/OWNERSHIP
        if not marker.is_file() or load_json(marker).get('owner') != 'prompt-library-build':
            raise SuiteError('existing site is not owned by this builder; refusing overwrite')
        old = load_json(output/'library.json') if (output/'library.json').exists() else {'items':[]}
        removed = {e['id'] for e in old['items']} - {e['id'] for e in library['items']}
        if removed and not allow_removals:
            raise SuiteError('published items would be removed; review and use --allow-removals: '+', '.join(sorted(removed)))
    staging = Path(tempfile.mkdtemp(prefix='.library-stage-', dir=root))
    try:
        for target, source in copies.items():
            dest = safe_path(staging, target, must_exist=False)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            if digest(dest.read_bytes()) != report['input_hashes']['public/'+target]:
                raise SuiteError('input changed during build: '+target)
        (staging/'library.json').write_text(dump_json(library), encoding='utf-8', newline='\n')
        (staging/OWNERSHIP).write_text(dump_json({'owner':'prompt-library-build','build_id':library['build']['build_id']}), encoding='utf-8')
        # Rename the old owned output first; restore it if installation fails.
        backup = root/(staging.name+'-previous')
        if output.exists():
            output.replace(backup)
        try:
            staging.replace(output)
        except OSError:
            if backup.exists() and not output.exists():
                backup.replace(output)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return report
