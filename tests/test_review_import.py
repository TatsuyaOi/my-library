"""Editorial import remains grounded, explicit, atomic and revision-safe."""
import copy
import unittest
import test_review as fixtures
from test_review import FakeAI, LESSON, HTML
import review


class ReviewedImportTests(unittest.TestCase):
    setUp = fixtures.ReviewTests.setUp
    run_pipeline = fixtures.ReviewTests.run_pipeline
    def package(self):
        source = review.extract(self.source)
        data = review.candidate(LESSON, source, None, {}, FakeAI())
        for q in data['questions']:
            q['manual_override'] = True
        data['quality'].update(method='source-reviewed', reviewer='Test fixture',
                               limitations='Same-author review, no independent model call')
        for result, q in zip(data['quality']['results'], data['questions']):
            result['question_hash'] = review.digest(q)
        return {'reviews': [data]}

    def test_reviewed_import_reuses_on_normal_run(self):
        package = self.package()
        result = review.import_reviewed(self.root, self.site, package)
        self.assertEqual(result, {'lessons': 1, 'questions': 1})
        fake = FakeAI(fail=True)
        logs = self.run_pipeline(generate=True, ai=fake)
        self.assertEqual(logs[0]['status'], 'success')
        self.assertEqual(fake.calls, [])
        self.assertEqual(review.load_bundle(self.root)['reviews']['lesson']['quality']['method'], 'source-reviewed')

    def test_reviewed_import_rejects_changed_answer_and_source(self):
        package = self.package()
        review.import_reviewed(self.root, self.site, package)
        before = (self.root / 'review/bundle.json').read_bytes()
        bad = copy.deepcopy(package)
        bad['reviews'][0]['questions'][0]['answer'] = False
        with self.assertRaises(ValueError): review.import_reviewed(self.root, self.site, bad)
        self.source.write_text(HTML.replace('短い。', '長い。'), encoding='utf-8')
        with self.assertRaises(ValueError): review.import_reviewed(self.root, self.site, package)
        self.assertEqual(before, (self.root / 'review/bundle.json').read_bytes())

    def test_reviewed_import_rejects_unpublished_or_held(self):
        package = self.package()
        self.config['lessons'] = [dict(LESSON, generation_hold='Needs extraction')]
        review.write_json(self.root / 'review.config.json', self.config)
        with self.assertRaises(ValueError): review.import_reviewed(self.root, self.site, package)
        self.config['lessons'] = [LESSON]
        review.write_json(self.root / 'review.config.json', self.config)
        review.write_json(self.site / 'library-all.json', {'items': []})
        with self.assertRaises(ValueError): review.import_reviewed(self.root, self.site, package)
        self.assertFalse((self.root / 'review/bundle.json').exists())

    def test_bad_second_lesson_does_not_publish_first(self):
        package = self.package()
        package['reviews'].append(copy.deepcopy(package['reviews'][0]))
        with self.assertRaises(ValueError): review.import_reviewed(self.root, self.site, package)
        self.assertFalse((self.root / 'review/bundle.json').exists())

    def test_source_change_marks_reviewed_questions_stale(self):
        review.import_reviewed(self.root, self.site, self.package())
        self.source.write_text(HTML.replace('短い。', '長い。'), encoding='utf-8')
        self.assertEqual(self.run_pipeline()[0]['status'], 'stale')

    def test_incomplete_or_duplicate_assessment_rejected(self):
        for modification in ('missing', 'duplicate', 'unreviewed'):
            package = self.package()
            quality = package['reviews'][0]['quality']
            if modification == 'missing': quality['results'] = []
            elif modification == 'duplicate': quality['results'] *= 2
            else: quality['method'] = 'unreviewed'
            with self.assertRaises(ValueError): review.import_reviewed(self.root, self.site, package)
