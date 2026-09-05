import copy
import itertools
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from suite_tools import SuiteError, digest, dump_json, load_json
from library_tools import OWNERSHIP, plan, published, write_build
from validate_library import validate
from check_links import inspect
from check_release_audit import check as check_release
from helpers import setup_library,make_item,save_meta

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);setup_library(self.root)
    def tearDown(self):self.temp.cleanup()
    def test_publication_requires_three_conditions(self):
        for status,visibility,pub in itertools.product(['active','draft'],['public','private'],[True,False]):
            self.assertEqual(published({'status':status,'visibility':visibility,'publish':pub}),status=='active' and visibility=='public' and pub)
    def test_public_private_projection(self):
        folder,m=make_item(self.root);make_item(self.root,'private-note',False)
        m['relations']={'parent_id':'private-note','related_ids':['private-note','sample']};save_meta(folder,m)
        library,copies,report=plan(self.root,False)
        self.assertEqual(library['stats']['total_items'],1)
        self.assertEqual(library['items'][0]['relations'],{'parent_id':None,'related_ids':['sample']})
        self.assertFalse(any('private-note' in p for p in copies))
        self.assertEqual(library['stats']['excluded_items'],0)
        self.assertEqual(len(report['excluded']),1)
    def test_stale_source_excluded(self):
        folder,m=make_item(self.root);(folder/m['files']['source']).write_text('# Changed\n',encoding='utf-8')
        self.assertEqual(plan(self.root,False)[0]['items'],[])
    def test_unknown_source_hash_excluded(self):
        folder,m=make_item(self.root);m['integrity']['source_sha256']=None;save_meta(folder,m)
        self.assertEqual(plan(self.root,False)[0]['items'],[])
    def test_duplicate_alias_rejected(self):
        make_item(self.root);f,m=make_item(self.root,'other');m['aliases']=['sample'];save_meta(f,m)
        with self.assertRaises(SuiteError):plan(self.root,False)
    def test_thumbnail_staleness_is_transitive(self):
        f,m=make_item(self.root,images=True);m['integrity']['preview_generated_from_source_sha256']='0'*64;save_meta(f,m)
        e=plan(self.root,False)[0]['items'][0]
        self.assertIsNone(e['paths']['preview']);self.assertIsNone(e['paths']['thumbnail'])
    def test_current_thumbnail_kept(self):
        make_item(self.root,images=True);e=plan(self.root,False)[0]['items'][0]
        self.assertIsNotNone(e['paths']['preview']);self.assertIsNotNone(e['paths']['thumbnail'])
    def test_tampered_preview_removed(self):
        f,m=make_item(self.root,images=True);(f/'preview.webp').write_bytes(b'altered')
        e=plan(self.root,False)[0]['items'][0]
        self.assertIsNone(e['paths']['preview']);self.assertIsNone(e['paths']['thumbnail'])
    def test_source_path_escape_rejected(self):
        f,m=make_item(self.root);m['files']['source']='../../outside.md';save_meta(f,m)
        with self.assertRaises(SuiteError):plan(self.root,False)
    def test_source_symlink_rejected(self):
        f,m=make_item(self.root);source=f/m['files']['source'];source.unlink();outside=self.root/'outside.md';outside.write_text('x')
        try:source.symlink_to(outside)
        except OSError:self.skipTest('symlinks unavailable')
        with self.assertRaises(SuiteError):plan(self.root,False)
    def test_schema_rejects_empty_title(self):
        f,m=make_item(self.root);m['title']='';save_meta(f,m)
        with self.assertRaises(SuiteError):plan(self.root,False)
    def test_deterministic_rebuild(self):
        make_item(self.root);write_build(self.root,False)
        before={p.relative_to(self.root/'site').as_posix():p.read_bytes() for p in (self.root/'site').rglob('*') if p.is_file()}
        write_build(self.root,False)
        after={p.relative_to(self.root/'site').as_posix():p.read_bytes() for p in (self.root/'site').rglob('*') if p.is_file()}
        self.assertEqual(before,after)
    def test_unowned_site_not_deleted(self):
        make_item(self.root);site=self.root/'site';site.mkdir();(site/'valuable.html').write_text('keep')
        with self.assertRaises(SuiteError):write_build(self.root,False)
        self.assertEqual((site/'valuable.html').read_text(),'keep')
    def test_unlisted_file_detected_and_cleaned_on_rebuild(self):
        make_item(self.root);write_build(self.root,False);(self.root/'site/private.txt').write_text('synthetic')
        self.assertTrue(validate(self.root,False));write_build(self.root,False)
        self.assertFalse((self.root/'site/private.txt').exists());self.assertEqual(validate(self.root,False),[])
    def test_removal_requires_explicit_override(self):
        f,m=make_item(self.root);write_build(self.root,False);m['publish']=False;save_meta(f,m)
        with self.assertRaises(SuiteError):write_build(self.root,False,allow_empty=True)
        write_build(self.root,False,allow_empty=True,allow_removals=True)
        self.assertEqual(load_json(self.root/'site/library.json')['items'],[])
        self.assertFalse((self.root/'site/items/sample').exists())
    def test_empty_build_requires_override(self):
        with self.assertRaises(SuiteError):write_build(self.root,False)
    def test_dry_plan_does_not_write_site(self):
        make_item(self.root);plan(self.root,False);self.assertFalse((self.root/'site').exists())
    def test_missing_release_audit_is_incomplete(self):
        make_item(self.root);write_build(self.root,False)
        self.assertEqual(check_release(self.root,self.root/'missing.json')[0],2)
    def test_audit_from_wrong_build_rejected(self):
        make_item(self.root);write_build(self.root,False);p=self.root/'audit.json';p.write_text(dump_json({'verdict':'PASS','build_id':'wrong','recommended_exit_code':0}))
        self.assertEqual(check_release(self.root,p)[0],2)
    def test_link_missing_detected(self):
        site=self.root/'site';site.mkdir();(site/'index.html').write_text('<a href="missing.html">x</a>')
        self.assertTrue(inspect(site))
    def test_link_javascript_rejected(self):
        site=self.root/'site';site.mkdir();(site/'index.html').write_text('<a href="javascript:alert(1)">x</a>')
        self.assertTrue(inspect(site))
    def test_link_anchor_success(self):
        site=self.root/'site';site.mkdir();(site/'index.html').write_text('<h1 id="ok">x</h1><a href="#ok">jump</a>')
        self.assertEqual(inspect(site),[])


    def test_additional_cannot_bypass_stale_preview(self):
        f,m=make_item(self.root,images=True)
        m['integrity']['preview_generated_from_source_sha256']='0'*64
        m['files']['additional']=['preview.webp'];save_meta(f,m)
        with self.assertRaises(SuiteError):plan(self.root,False)
    def test_confirmed_base_path_allowed(self):
        site=self.root/'site';site.mkdir()
        (site/'index.html').write_text('<html><a href="/demo/">Home</a></html>')
        self.assertEqual(inspect(site,'/demo/'),[])
    def test_other_base_path_rejected(self):
        site=self.root/'site';site.mkdir()
        (site/'index.html').write_text('<html><a href="/other/">Wrong</a></html>')
        self.assertTrue(inspect(site,'/demo/'))
    def test_private_report_rejected_before_write(self):
        from build_library import main
        make_item(self.root)
        code=main(['--root',str(self.root),'--data-only','--report',str(self.root/'site/report.json')])
        self.assertEqual(code,1);self.assertFalse((self.root/'site').exists())

if __name__=='__main__':unittest.main()
