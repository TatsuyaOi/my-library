"""Review fixtures use a fake AI exclusively; no production question data."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import review
from review_ci import affected

LESSON = {'lesson_id': 'lesson', 'source_path': 'study/test.html', 'title': 'Test', 'categories': ['study']}
HTML = '<html><head><style>x</style></head><body><section id="one"><h2>定義</h2><p>圧力が高いと平均自由行程は短い。</p><table><tr><th>圧力</th><th>行程</th></tr><tr><td>高い</td><td>短い</td></tr></table></section><script>secret()</script></body></html>'


class FakeAI:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def call(self, request):
        self.calls.append(request['operation'])
        if self.fail:
            raise ValueError('fixture failure')
        if request['operation'] == 'validate':
            return {'results': [{'question_id': q['question_id'], 'pass': True, 'reason': 'Test fixture only'}
                                for q in request['candidate']['questions'] if q['status'] == 'active']}
        return {'questions': [{'concept_key': 'pressure', 'revision': 1, 'type': 'true_false',
            'level': 'basic', 'difficulty': 1, 'importance': 'high', 'question': '圧力が高いと行程は短い。',
            'answer': True, 'explanation': '本文に記載。', 'tags': ['圧力'], 'status': 'active',
            'source': {'path': 'study/test.html', 'anchor': '#one', 'evidence': '圧力が高いと平均自由行程は短い。'}}]}


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.site = self.root / '_site'
        (self.site / 'study').mkdir(parents=True)
        self.source = self.site / 'study/test.html'
        self.source.write_text(HTML, encoding='utf-8')
        review.write_json(self.site / 'library-all.json', {'items': [{'url': './study/test.html'}]})
        self.config = {'schema_version': 1, 'lessons': [LESSON], 'ai': {
            'timeout_seconds': 10, 'max_input_chars': 100000, 'max_calls_per_run': 6, 'max_attempts_per_lesson': 3}}
        review.write_json(self.root / 'review.config.json', self.config)
        self.git = patch.object(subprocess, 'check_output', return_value='fixture-commit')
        self.git.start(); self.addCleanup(self.git.stop)

    def run_pipeline(self, **kwargs):
        return review.run(self.root, self.site, **kwargs)

    def test_unconfigured_ai_blocks_without_questions(self):
        with patch.dict('os.environ', {}, clear=True):
            logs = self.run_pipeline(generate=True)
        self.assertEqual(logs[0]['status'], 'blocked')
        self.assertEqual(review.load_bundle(self.root)['reviews'], {})

    def test_generation_independent_validation_and_noop(self):
        fake = FakeAI()
        self.assertEqual(self.run_pipeline(generate=True, ai=fake)[0]['status'], 'success')
        self.assertEqual(fake.calls, ['generate', 'validate'])
        old = (self.root / 'review/bundle.json').read_bytes()
        self.run_pipeline(generate=True, ai=fake)
        self.assertEqual(fake.calls, ['generate', 'validate'])
        self.assertEqual(old, (self.root / 'review/bundle.json').read_bytes())

    def test_stale_failure_keeps_previous_review(self):
        self.run_pipeline(generate=True, ai=FakeAI())
        before = review.load_bundle(self.root)['reviews']
        self.source.write_text(HTML.replace('短い。', '短いとは限らない。'), encoding='utf-8')
        fake = FakeAI(fail=True)
        logs = self.run_pipeline(generate=True, ai=fake)
        self.assertEqual(logs[0]['status'], 'stale')
        self.assertEqual(len(fake.calls), 3)
        self.assertEqual(before, review.load_bundle(self.root)['reviews'])

    def test_duplicate_lesson_stops_without_changing_bundle(self):
        self.run_pipeline(generate=True, ai=FakeAI())
        before = (self.root / 'review/bundle.json').read_bytes()
        self.config['lessons'].append(LESSON)
        review.write_json(self.root / 'review.config.json', self.config)
        with self.assertRaises(ValueError): self.run_pipeline()
        self.assertEqual(before, (self.root / 'review/bundle.json').read_bytes())

    def test_invalid_evidence_choice_and_answer_revision(self):
        self.run_pipeline(generate=True, ai=FakeAI())
        bundle = review.load_bundle(self.root)
        good = bundle['reviews']['lesson']
        for field, value in [('evidence', '架空の引用'), ('anchor', '#absent')]:
            bad = copy.deepcopy(good); bad['questions'][0]['source'][field] = value
            with self.assertRaises(ValueError): review.validate_review(bad, LESSON, review.extract(self.source))
        bad = copy.deepcopy(good); q = bad['questions'][0]
        q.update(type='choice', question_id='lesson:pressure:choice:1', answer='a', choices=[{'id':'a','text':'a'}])
        with self.assertRaises(ValueError): review.validate_review(bad, LESSON)
        class Changed(FakeAI):
            def call(self, req):
                result = super().call(req)
                if req['operation'] == 'generate': result['questions'][0]['answer'] = False
                return result
        with self.assertRaisesRegex(ValueError, 'revision'):
            review.candidate(LESSON, review.extract(self.source), good, bundle['ledger'], Changed())

    def test_deleted_and_renamed_lesson_preserve_id_ledger(self):
        self.run_pipeline(generate=True, ai=FakeAI())
        before = review.load_bundle(self.root)['ledger']
        self.source.unlink()
        self.run_pipeline()
        bundle = review.load_bundle(self.root)
        self.assertEqual(bundle['lessons'][0]['status'], 'inactive')
        self.assertEqual(bundle['ledger'], before)
        self.assertEqual(bundle['reviews']['lesson']['questions'][0]['status'], 'inactive')

    def test_meaning_hash_ignores_scripts_style_and_whitespace(self):
        first = review.extract(self.source)
        self.source.write_text(HTML.replace('<p>', '<p class="new">  ').replace('secret()', 'changed()'), encoding='utf-8')
        self.assertEqual(first['content_hash'], review.extract(self.source)['content_hash'])
        self.source.write_text(HTML.replace('高い', '低い'), encoding='utf-8')
        self.assertNotEqual(first['content_hash'], review.extract(self.source)['content_hash'])
        self.assertNotIn('secret', first['text'])
        self.assertIn('圧力 行程 高い 短い', first['text'])

    def test_ai_call_limit(self):
        ai = review.AI(self.config['ai']); ai.calls = 6
        with patch.dict('os.environ', {'REVIEW_AI_COMMAND': '["no-execution"]'}):
            with self.assertRaises(review.Blocked): ai.call({})

    def test_missing_review_recovers_from_ledger(self):
        self.run_pipeline(generate=True, ai=FakeAI())
        manifest = json.loads((self.root / 'review/bundle.json').read_text(encoding='utf-8'))
        (self.root / 'review' / manifest['reviews']['lesson']).unlink()
        self.assertEqual(self.run_pipeline(generate=True, ai=FakeAI())[0]['status'], 'success')
        self.assertEqual(set(review.load_bundle(self.root)['ledger']), {'lesson:pressure:true_false:1'})

    def test_corrupt_ledger_fails_closed(self):
        self.run_pipeline(generate=True, ai=FakeAI())
        path = self.root / 'review/bundle.json'
        bundle = json.loads(path.read_text(encoding='utf-8')); bundle['ledger'] = {}
        review.write_json(path, bundle)
        with self.assertRaisesRegex(ValueError, 'ledger'): review.load_bundle(self.root)

    def test_trigger_only_registered_sources(self):
        self.assertEqual(affected(['README.md', 'review/bundle.json', 'assets/learning.css'], [LESSON]), [])
        self.assertEqual(affected(['study/test.html'], [LESSON]), ['lesson'])
        lesson = dict(LESSON, source_path='content/a/index.html')
        self.assertEqual(affected(['content/a/content.md'], [lesson]), ['lesson'])

    def test_partial_failure_and_global_collision(self):
        second = dict(LESSON, lesson_id='second', source_path='study/second.html')
        self.config['lessons'].append(second)
        review.write_json(self.root / 'review.config.json', self.config)
        (self.site / 'study/second.html').write_text(HTML, encoding='utf-8')
        review.write_json(self.site / 'library-all.json', {'items': [{'url':'./study/test.html'}, {'url':'./study/second.html'}]})
        class Partial(FakeAI):
            def call(self, request):
                if request.get('lesson', {}).get('lesson_id') == 'second':
                    raise ValueError('Fixture second failure')
                return super().call(request)
        logs = self.run_pipeline(generate=True, ai=Partial())
        self.assertEqual([l['status'] for l in logs], ['success', 'failed'])
        before = (self.root / 'review/bundle.json').read_bytes()
        class Duplicate(FakeAI):
            def call(self, request):
                value = super().call(request)
                if request['operation'] == 'generate': value['questions'] *= 2
                return value
        with self.assertRaises(review.IntegrityError): self.run_pipeline(generate=True, force=True, ai=Duplicate())
        self.assertEqual(before, (self.root / 'review/bundle.json').read_bytes())

    def test_revoked_source_never_exports_old_questions(self):
        self.run_pipeline(generate=True, ai=FakeAI())
        review.write_json(self.site / 'library-all.json', {'items': []})
        (self.root / 'app').mkdir()
        for name in ('index.html','app.mjs','core.mjs','db.mjs','style.css','manifest.webmanifest','icon.svg'):
            (self.root / 'app' / name).write_text('fixture', encoding='utf-8')
        review.export(self.root, self.site)
        self.assertEqual(json.loads((self.site/'review/library.json').read_text(encoding='utf-8'))['lessons'], [])
        self.assertFalse((self.site/'review/lesson.json').exists())


if __name__ == '__main__': unittest.main()
