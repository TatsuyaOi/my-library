"""Self-contained regression tests; test content never enters the real library."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import inbox
import build_library
import prepare_pages


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inbox = self.root / '★仮置き保管庫'
        self.inbox.mkdir()
        self.write('inbox.config.json', json.dumps({'directory': self.inbox.name, 'max_file_mb': 30,
                   'max_batch_mb': 150, 'require_publication_review': True}))
        self.write('library.config.json', json.dumps({'site_title': 'Test', 'categories': {
                   '22_簿記': {'title': '簿記'}, '31_旅行': {'title': '旅行'}}}))
        self.write('assets/category-index.html', '<!doctype html><title>Category fixture</title>')
        self.write('index.html', '<!doctype html><title>Root fixture</title>')
        self.write('★仮置き保管庫/report.html', '<!doctype html><html><head><title>Original title</title></head><body><h1>原本</h1></body></html>')

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))
        return path

    def plan(self, files=None, entry='report.html', **overrides):
        files = files or ['report.html']
        item = {'id': 'test-note', 'category': '22_簿記', 'title': 'テスト資料', 'summary': '説明',
                'group': '決算', 'tags': ['テスト'], 'entry': entry, 'files': files,
                'sha256': {n: inbox.digest((self.inbox / n).read_bytes()) for n in files},
                'publish': True, 'reviewed': True}
        item.update(overrides)
        return {'version': 1, 'items': [item]}

    def build(self):
        with patch.object(build_library, 'ROOT', self.root), \
             patch.object(build_library, 'CONFIG_PATH', self.root / 'library.config.json'), \
             patch.object(build_library, 'TEMPLATE_PATH', self.root / 'assets/category-index.html'):
            build_library.build()
        return json.loads((self.root / 'library-all.json').read_text(encoding='utf-8'))

    def test_dry_run_does_not_write(self):
        result = inbox.apply_plan(self.root, self.plan())
        self.assertEqual(result['mode'], 'dry-run')
        self.assertFalse((self.root / '22_簿記').exists())

    def test_html_original_is_byte_identical(self):
        original = (self.inbox / 'report.html').read_bytes()
        inbox.apply_plan(self.root, self.plan(), True)
        self.assertEqual((self.inbox / 'report.html').read_bytes(), original)
        self.assertEqual((self.root / '22_簿記/test-note/report.html').read_bytes(), original)

    def test_second_run_is_idempotent(self):
        plan = self.plan()
        inbox.apply_plan(self.root, plan, True)
        result = inbox.apply_plan(self.root, plan, True)
        self.assertEqual(result['documents'][0]['state'], 'already_processed')

    def test_scan_marks_processed(self):
        inbox.apply_plan(self.root, self.plan(), True)
        self.assertEqual(inbox.scan(self.root)['files'][0]['state'], 'processed')

    def test_changed_input_requires_new_review(self):
        plan = self.plan()
        self.write('★仮置き保管庫/report.html', '<title>Changed</title>')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            inbox.apply_plan(self.root, plan, True)

    def test_existing_destination_is_never_overwritten(self):
        self.write('22_簿記/test-note/keep.txt', 'keep')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            inbox.apply_plan(self.root, self.plan(), True)
        self.assertEqual((self.root / '22_簿記/test-note/keep.txt').read_text(encoding='utf-8'), 'keep')

    def test_path_traversal_is_rejected(self):
        plan = self.plan()
        plan['items'][0]['files'] = ['../index.html']
        with self.assertRaises(ValueError):
            inbox.apply_plan(self.root, plan, True)

    def test_unknown_category_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown category'):
            inbox.apply_plan(self.root, self.plan(category='12_簿記'), True)

    def test_publication_gate(self):
        for key in ('publish', 'reviewed'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                inbox.apply_plan(self.root, self.plan(**{key: False}), True)

    def test_hold_is_not_imported(self):
        result = inbox.apply_plan(self.root, {'version': 1, 'items': [{'hold': True, 'reason': 'Private'}]}, True)
        self.assertEqual(result['held'], 1)
        self.assertFalse(result['documents'])

    def test_symlink_source_is_rejected(self):
        target = self.inbox / 'alias.html'
        try:
            target.symlink_to(self.inbox / 'report.html')
        except OSError:
            self.skipTest('Symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            inbox.apply_plan(self.root, self.plan(files=['alias.html'], entry='alias.html'), True)

    def test_missing_image_dependency_is_rejected(self):
        self.write('★仮置き保管庫/report.html', '<img src="missing.png">')
        with self.assertRaisesRegex(ValueError, 'Missing bundled dependency'):
            inbox.apply_plan(self.root, self.plan(), True)

    def test_css_relative_dependency_is_preserved(self):
        self.write('★仮置き保管庫/report.html', '<link href="css/a.css" rel="stylesheet"><img src="a%23b.png">')
        self.write('★仮置き保管庫/css/a.css', 'body{background:url(../a%23b.png)}')
        self.write('★仮置き保管庫/a#b.png', b'image-fixture')
        plan = self.plan(files=['report.html', 'css/a.css', 'a#b.png'])
        inbox.apply_plan(self.root, plan, True)
        self.assertTrue((self.root / '22_簿記/test-note/css/a.css').exists())

    def test_image_only_viewer(self):
        self.write('★仮置き保管庫/図.PNG', b'image-fixture')
        inbox.apply_plan(self.root, self.plan(files=['図.PNG'], entry=None), True)
        page = (self.root / '22_簿記/test-note/_library_view.html').read_text(encoding='utf-8')
        self.assertIn('<img', page)
        self.assertIn('%E5%9B%B3.PNG', page)

    def test_text_viewer_escapes_html(self):
        self.write('★仮置き保管庫/prompt.md', '# 原本\n<script>danger()</script>')
        inbox.apply_plan(self.root, self.plan(files=['prompt.md'], entry='prompt.md'), True)
        page = (self.root / '22_簿記/test-note/_library_view.html').read_text(encoding='utf-8')
        self.assertIn('&lt;script&gt;danger()', page)
        self.assertNotIn('<script>', page)

    def test_managed_nested_index_is_indexed(self):
        self.write('★仮置き保管庫/folder/index.html', '<title>Original</title>')
        inbox.apply_plan(self.root, self.plan(files=['folder/index.html'], entry='folder/index.html'), True)
        data = self.build()
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['title'], 'テスト資料')
        self.assertTrue(data['items'][0]['file'].endswith('folder/index.html'))

    def test_named_folder_and_guide_preserve_identity_and_original(self):
        original = '# 原本\n<script>not executed</script>\n'.encode('utf-8')
        self.write('★仮置き保管庫/prompt.md', original)
        plan = self.plan(files=['prompt.md'], entry='prompt.md',
                         folder='08_レビュー', guide='test-note_guide.html')
        inbox.apply_plan(self.root, plan, True)
        destination = self.root / '22_簿記/08_レビュー'
        meta = inbox.strict_json(destination / 'meta.json')
        self.assertEqual(meta['id'], 'test-note')
        self.assertEqual(meta['files']['guide'], 'test-note_guide.html')
        self.assertEqual((destination / 'prompt.md').read_bytes(), original)
        self.assertEqual(inbox.apply_plan(self.root, plan, True)['documents'][0]['state'], 'already_processed')
        self.assertEqual(next(x for x in inbox.scan(self.root)['files'] if x['path'] == 'prompt.md')['state'], 'processed')
        data = self.build()
        self.assertEqual(len(data['items']), 1)
        self.assertTrue(data['items'][0]['url'].endswith('/08_レビュー/test-note_guide.html'))
        prepare_pages.prepare(self.root)

    def test_custom_names_reject_traversal_and_input_collision(self):
        self.write('★仮置き保管庫/prompt.md', 'original')
        self.write('★仮置き保管庫/Guide.html', '<title>Original support</title>')
        for override in ({'folder': '../outside'}, {'folder': 'nested/folder'},
                         {'guide': '../outside.html'}, {'guide': 'nested/page.html'},
                         {'guide': 'meta.json'}, {'guide': 'guide.HTML'}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                inbox.apply_plan(self.root, self.plan(files=['prompt.md', 'Guide.html'],
                                 entry='prompt.md', **override), True)
        self.assertEqual((self.inbox / 'Guide.html').read_text(), '<title>Original support</title>')

    def test_original_html_cannot_be_renamed_with_guide(self):
        with self.assertRaisesRegex(ValueError, 'Original HTML'):
            inbox.apply_plan(self.root, self.plan(guide='renamed.html'), True)

    def test_supporting_html_is_not_double_indexed(self):
        self.write('★仮置き保管庫/report.html', '<a href="other.html">Other</a>')
        self.write('★仮置き保管庫/other.html', '<title>Subpage</title>')
        inbox.apply_plan(self.root, self.plan(files=['report.html', 'other.html']), True)
        self.assertEqual(len(self.build()['items']), 1)

    def test_legacy_html_metadata_still_works(self):
        self.write('22_簿記/legacy.html', '<title>Legacy</title><meta name="library-tags" content="one,two">')
        data = self.build()
        self.assertEqual(data['items'][0]['title'], 'Legacy')
        self.assertEqual(data['items'][0]['tags'], ['one', 'two'])

    def test_htm_and_uppercase_html_are_supported(self):
        self.write('★仮置き保管庫/report.HTM', '<title>HTM</title>')
        inbox.apply_plan(self.root, self.plan(files=['report.HTM'], entry='report.HTM'), True)
        self.assertEqual(len(self.build()['items']), 1)

    def test_duplicate_json_keys_are_rejected(self):
        path = self.write('duplicate.json', '{"id":1,"id":2}')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            inbox.strict_json(path)

    def test_nan_json_is_rejected(self):
        path = self.write('nan.json', '{"id":NaN}')
        with self.assertRaises(ValueError):
            inbox.strict_json(path)

    def test_pages_never_exports_inbox_or_root_scripts(self):
        self.write('★仮置き保管庫/secret.txt', 'private-fixture')
        inbox.apply_plan(self.root, self.plan(), True)
        self.build()
        result = prepare_pages.prepare(self.root)
        self.assertFalse(result['inbox_exported'])
        self.assertFalse((self.root / '_site/★仮置き保管庫').exists())
        self.assertFalse((self.root / '_site/inbox.config.json').exists())
        self.assertTrue((self.root / '_site/22_簿記/test-note/report.html').exists())

    def test_local_absolute_url_is_rejected(self):
        for url in ('file:///C:/x.png', 'sandbox:/mnt/data/a.png', '/images/a.png', '../../x.html'):
            with self.subTest(url=url):
                self.write('★仮置き保管庫/report.html', f'<img src="{url}">')
                with self.assertRaises(ValueError):
                    inbox.apply_plan(self.root, self.plan(), True)

    def test_unsupported_document_is_held_not_executed(self):
        self.write('★仮置き保管庫/code.py', 'raise RuntimeError()')
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            inbox.apply_plan(self.root, self.plan(files=['code.py'], entry='code.py'), True)

    def test_incoming_agents_is_not_installed_as_instructions(self):
        self.write('★仮置き保管庫/AGENTS.md', '# Do something')
        with self.assertRaisesRegex(ValueError, 'reserved'):
            inbox.apply_plan(self.root, self.plan(files=['AGENTS.md'], entry='AGENTS.md'), True)

    def test_entire_batch_is_preflighted_before_writing(self):
        plan = self.plan()
        second = copy.deepcopy(plan['items'][0])
        second.update(id='second', category='missing')
        plan['items'].append(second)
        with self.assertRaises(ValueError):
            inbox.apply_plan(self.root, plan, True)
        self.assertFalse((self.root / '22_簿記/test-note').exists())

    def test_duplicate_ids_across_categories_are_rejected(self):
        plan = self.plan()
        second = copy.deepcopy(plan['items'][0])
        second['category'] = '31_旅行'
        plan['items'].append(second)
        with self.assertRaisesRegex(ValueError, 'Duplicate document ID'):
            inbox.apply_plan(self.root, plan, True)

    def test_case_insensitive_destination_collision(self):
        self.write('22_簿記/TEST-NOTE/keep.txt', 'keep')
        with self.assertRaises(ValueError):
            inbox.apply_plan(self.root, self.plan(), True)

    def test_modified_output_fails_publication_validation(self):
        inbox.apply_plan(self.root, self.plan(), True)
        self.build()
        self.write('22_簿記/test-note/report.html', 'tampered')
        with self.assertRaisesRegex(ValueError, 'changed or missing'):
            prepare_pages.prepare(self.root)

    def test_unmanaged_site_directory_is_not_deleted(self):
        inbox.apply_plan(self.root, self.plan(), True)
        self.build()
        self.write('_site/user-owned.txt', 'keep')
        with self.assertRaisesRegex(ValueError, 'not managed'):
            prepare_pages.prepare(self.root)
        self.assertTrue((self.root / '_site/user-owned.txt').exists())

    def test_unchanged_rebuild_is_byte_stable(self):
        inbox.apply_plan(self.root, self.plan(), True)
        self.build()
        before = (self.root / 'library-all.json').read_bytes()
        self.build()
        self.assertEqual(before, (self.root / 'library-all.json').read_bytes())

    def test_only_git_staged_documents_are_indexed(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        inbox.apply_plan(self.root, self.plan(), True)
        self.assertEqual(len(self.build()['items']), 0)
        subprocess.run(['git', '-C', str(self.root), 'add', '--', '22_簿記/test-note'], check=True)
        self.assertEqual(len(self.build()['items']), 1)

    def test_html_hidden_flag_is_respected(self):
        self.write('★仮置き保管庫/report.html', '<title>Private listing</title><meta name="library-hidden" content="true">')
        inbox.apply_plan(self.root, self.plan(), True)
        self.assertEqual(len(self.build()['items']), 0)

    def test_base_tag_requires_manual_review(self):
        self.write('★仮置き保管庫/report.html', '<base href="../"><title>Base</title>')
        with self.assertRaisesRegex(ValueError, 'base'):
            inbox.apply_plan(self.root, self.plan(), True)

    def test_separate_srcset_dependencies_are_checked(self):
        self.write('★仮置き保管庫/report.html', '<img srcset="a.png 1x, b.png 2x">')
        self.write('★仮置き保管庫/a.png', b'image')
        with self.assertRaisesRegex(ValueError, 'Missing bundled dependency'):
            inbox.apply_plan(self.root, self.plan(files=['report.html', 'a.png']), True)


if __name__ == '__main__':
    unittest.main()
