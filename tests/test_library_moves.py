"""Publication compatibility and fail-closed checks for category moves."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from library_moves import export_legacy_urls


class LibraryMoveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.site = self.root / '_site'
        self.site.mkdir()
        self.moves = [{'from': 'work/book', 'to': 'study/book'}]
        self.write(self.root / 'library.config.json', {'categories': {'work': {}, 'study': {}}})
        self.write(self.site / 'library-all.json', {'items': [{'url': './study/book/guide.html'}]})
        folder = self.site / 'study/book'
        folder.mkdir(parents=True)
        (folder / 'guide.html').write_bytes(b'<section id="chapter"><img src="figure.png"></section>')
        (folder / 'figure.png').write_bytes(b'fixture-bytes')

    def write(self, path, data):
        path.write_text(json.dumps(data), encoding='utf-8')

    def export(self):
        self.write(self.root / 'library-moves.json', {'schema_version': 1, 'moves': self.moves})
        export_legacy_urls(self.root, self.site)

    def test_exact_bytes_assets_and_fragment_survive_without_duplicate_index(self):
        before = (self.site / 'library-all.json').read_bytes()
        self.export()
        for name in ('guide.html', 'figure.png'):
            self.assertEqual((self.site / 'work/book' / name).read_bytes(),
                             (self.site / 'study/book' / name).read_bytes())
        self.assertEqual((self.site / 'library-all.json').read_bytes(), before)
        self.assertFalse((self.root / 'work/book').exists())

    def test_revoked_guide_is_not_exposed_via_old_url(self):
        self.write(self.site / 'library-all.json', {'items': []})
        self.export()
        self.assertFalse((self.site / 'work/book').exists())

    def test_collision_stops_without_overwriting(self):
        target = self.site / 'work/book'
        target.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'collision'):
            self.export()

    def test_traversal_and_noncategory_targets_fail(self):
        for target in ('study/../private', 'inbox/book', 'study'):
            with self.subTest(target=target):
                self.moves[0]['to'] = target
                with self.assertRaises(ValueError):
                    self.export()

    def test_chain_and_duplicate_fail_before_any_copy(self):
        self.moves.append({'from': 'study/book', 'to': 'work/other'})
        with self.assertRaisesRegex(ValueError, 'Duplicate or chained'):
            self.export()
        self.assertFalse((self.site / 'work/book').exists())

    def test_missing_published_folder_fails(self):
        self.moves[0]['to'] = 'study/missing'
        self.write(self.site / 'library-all.json', {'items': [{'url': './study/missing/guide.html'}]})
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.export()


if __name__ == '__main__':
    unittest.main()
