"""End-to-end publication boundary and article regression tests."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import stat
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_library
import learning
import prepare_pages

REPO = Path(__file__).resolve().parents[1]


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ('schemas', 'templates', 'content'):
            shutil.copytree(REPO / name, self.root / name)
        (self.root / 'assets').mkdir()
        for name in ('category-index.html', 'learning.css'):
            shutil.copyfile(REPO / 'assets' / name, self.root / 'assets' / name)
        self.write('index.html', '<!doctype html><title>Fixture</title>')
        self.write('inbox.config.json', json.dumps({'directory': 'inbox', 'require_publication_review': True}))
        self.write('library.config.json', json.dumps({'categories': {'51_仕事': {'title': '仕事'}}}))
        self.folder = self.root / 'content/reactive-sputtering-pressure'
        self.meta = json.loads((self.folder / 'meta.json').read_text(encoding='utf-8'))
        # Fixtures start unpublished independently of the real article's release state.
        self.meta.update(status='draft', publish=False)
        self.save()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def save(self):
        (self.folder / 'meta.json').write_text(json.dumps(self.meta), encoding='utf-8')

    def build(self, preview=False):
        with patch.object(build_library, 'ROOT', self.root), \
             patch.object(build_library, 'CONFIG_PATH', self.root / 'library.config.json'), \
             patch.object(build_library, 'TEMPLATE_PATH', self.root / 'assets/category-index.html'):
            build_library.build()
        prepare_pages.prepare(self.root, preview)
        return self.root / ('_preview' if preview else '_site')

    def test_draft_is_absent_from_public_bytes_but_available_in_preview(self):
        site = self.build()
        self.assertFalse((site / 'content').exists())
        self.assertEqual(json.loads((site / 'library-all.json').read_text(encoding='utf-8'))['items'], [])
        preview = self.build(True)
        data = json.loads((preview / 'library-all.json').read_text(encoding='utf-8'))
        self.assertEqual(len(data['items']), 1)
        self.assertTrue((preview / data['items'][0]['url']).is_file())
        self.assertFalse((site / 'content').exists())

    def test_active_public_article_export_and_revocation(self):
        self.meta.update(status='active', publish=True)
        self.save()
        site = self.build()
        self.assertTrue((site / 'content' / self.meta['slug'] / 'index.html').is_file())
        self.assertFalse((site / 'content' / self.meta['slug'] / 'content.md').exists())
        self.assertFalse((site / 'content' / self.meta['slug'] / 'meta.json').exists())
        self.assertEqual(json.loads((site / '51_仕事/library.json').read_text(encoding='utf-8'))['items'][0]['learning_slug'], self.meta['slug'])
        self.meta.update(publish=False)
        self.save()
        self.build()
        self.assertFalse((site / 'content').exists())

    def test_registered_heading_anchors_survive_insertion(self):
        source = self.folder / 'content.md'
        before = learning.render(self.root, self.folder, self.meta)
        source.write_text('## 新しい導入\n\n導入本文。\n\n' + source.read_text(encoding='utf-8'), encoding='utf-8')
        after = learning.render(self.root, self.folder, self.meta)
        self.assertIn('<h2 id="section-1">1. 問いと到達目標</h2>', before)
        self.assertIn('<h2 id="section-1">1. 問いと到達目標</h2>', after)

    def test_invalid_publication_flags_fail_closed(self):
        for value in ('false', 1, None):
            with self.subTest(value=value):
                self.meta['publish'] = value
                self.save()
                with self.assertRaises(ValueError):
                    self.build()
        self.meta['publish'] = True
        self.save()
        with self.assertRaisesRegex(ValueError, 'active'):
            self.build()

    def test_invalid_metadata_and_duplicate_slug(self):
        for changes in ({'slug': '../escape'}, {'category': 'missing'}, {'type': 'course'},
                        {'updated': '2026-02-30'}, {'learning_time_minutes': True}, {'tags': ['a', 'a', 'b']}):
            original = copy.deepcopy(self.meta)
            self.meta.update(changes)
            self.save()
            with self.assertRaises(ValueError):
                learning.documents(self.root)
            self.meta = original
        self.save()
        shutil.copytree(self.folder, self.root / 'content/duplicate')
        with self.assertRaisesRegex(ValueError, 'slug'):
            learning.documents(self.root)

    def test_missing_case_mismatched_image_and_anchor_fail(self):
        source = self.folder / 'content.md'
        for text in ('## Test\n![image](assets/MISSING.svg)', '## Test\n[bad](#missing)', '## Test\n![image](assets/Pressure-flow.svg)'):
            source.write_text(text, encoding='utf-8')
            with self.assertRaises(ValueError):
                self.build(True)

    def test_raw_html_is_escaped_and_table_has_local_scroll(self):
        with (self.folder / 'content.md').open('a', encoding='utf-8') as stream:
            stream.write('\n<script>alert(1)</script>\n')
        site = self.build(True)
        text = (site / 'content' / self.meta['slug'] / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('<script>', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertIn('class="table-scroll"', text)
        self.assertIn('href="#section-1"', text)

    def test_second_article_is_automatically_listed(self):
        other = self.root / 'content/second-article'
        shutil.copytree(self.folder, other)
        meta = dict(self.meta, slug='second-article', title='Second article')
        (other / 'meta.json').write_text(json.dumps(meta), encoding='utf-8')
        site = self.build(True)
        data = json.loads((site / 'library-all.json').read_text(encoding='utf-8'))
        self.assertEqual(len(data['items']), 2)
        self.assertEqual(data['categories'][0]['count'], 2)

    def test_rebuild_is_byte_stable(self):
        site = self.build(True)
        before = {p.relative_to(site): p.read_bytes() for p in site.rglob('*') if p.is_file()}
        self.build(True)
        after = {p.relative_to(site): p.read_bytes() for p in site.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_failed_build_preserves_previous_preview(self):
        site = self.build(True)
        page = site / 'content' / self.meta['slug'] / 'index.html'
        before = page.read_bytes()
        (self.folder / 'content.md').write_text('## Broken\n![bad](no.png)', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.build(True)
        self.assertEqual(page.read_bytes(), before)

    @unittest.skipUnless(os.name == 'nt', 'Windows read-only directory semantics')
    def test_readonly_generated_directory_can_be_rebuilt(self):
        site = self.build(True)
        directory = site / 'content' / self.meta['slug']
        os.chmod(directory, stat.S_IREAD)
        self.build(True)
        self.assertTrue((directory / 'index.html').is_file())


if __name__ == '__main__':
    unittest.main()
