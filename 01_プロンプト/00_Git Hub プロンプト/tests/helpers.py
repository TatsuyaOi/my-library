from pathlib import Path
import copy
import json
import shutil
from suite_tools import ROOT, digest, dump_json


def setup_library(root: Path) -> None:
    (root/'config').mkdir();(root/'schemas').mkdir();(root/'content').mkdir();(root/'scripts').mkdir()
    shutil.copyfile(ROOT/'config/library.config.json',root/'config/library.config.json')
    for p in (ROOT/'schemas').glob('*.json'):shutil.copyfile(p,root/'schemas'/p.name)
    for name in ['library_tools.py','suite_tools.py']:shutil.copyfile(ROOT/'scripts'/name,root/'scripts'/name)


def make_item(root: Path, item_id: str='sample', active: bool=True, images: bool=False) -> tuple[Path,dict]:
    folder=root/'content'/item_id;folder.mkdir()
    source=folder/f'{item_id}_prompt.md';source.write_text('# Test\n\nPreserve this text.\n',encoding='utf-8')
    meta={'schema_version':'2.0','id':item_id,'slug':item_id,'aliases':[],'title':'テスト資料','type':'prompt','category':'prompts','subcategory':None,'summary':'単体テスト用の合成資料です。','tags':[],
          'status':'active' if active else 'draft','visibility':'public' if active else 'private','publish':active,'version':'1.0','language':'ja','dates':{'created':None,'updated':None},
          'files':{'source':source.name,'guide':None,'preview':None,'thumbnail':None,'additional':[]},
          'media':{role:{'alt':None,'width':None,'height':None,'bytes':None,'format':None} for role in ['preview','thumbnail']},
          'search':{'keywords':[]},'relations':{'parent_id':None,'related_ids':[]},
          'integrity':{key:None for key in ['source_sha256','guide_sha256','preview_sha256','thumbnail_sha256','guide_generated_from_source_sha256','preview_generated_from_source_sha256','thumbnail_generated_from_preview_sha256']},
          'provenance':{key:None for key in ['source_origin','guide_generator_prompt_id','guide_generator_prompt_version','guide_generated_at','preview_generator_prompt_id','preview_generator_prompt_version','preview_generated_at']}}
    meta['integrity']['source_sha256']=digest(source.read_bytes())
    if images:
        # Synthetic byte fixtures test hash linkage, NOT image decoding or visual quality.
        for role in ['preview','thumbnail']:
            p=folder/f'{role}.webp';p.write_bytes(b'SYNTHETIC_HASH_FIXTURE_'+role.encode())
            meta['files'][role]=p.name;meta['integrity'][role+'_sha256']=digest(p.read_bytes())
        meta['integrity']['preview_generated_from_source_sha256']=meta['integrity']['source_sha256']
        meta['integrity']['thumbnail_generated_from_preview_sha256']=meta['integrity']['preview_sha256']
    save_meta(folder,meta)
    return folder,meta


def save_meta(folder: Path,meta: dict) -> None:
    (folder/'meta.json').write_text(dump_json(meta),encoding='utf-8')
