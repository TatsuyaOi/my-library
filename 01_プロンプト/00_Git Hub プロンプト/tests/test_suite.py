import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from suite_tools import (ROOT, SuiteError, dump_json, expected_manifest, fence_errors,
                         load_json, safe_path, strict_json)
from validate_suite import validate, strict_yaml
from run_evals import main as run_evals_main, check_results

class ParserTests(unittest.TestCase):
    def test_valid_json(self):self.assertEqual(strict_json('{"a":1}'),{'a':1})
    def test_duplicate_json_rejected(self):
        with self.assertRaises(ValueError):strict_json('{"a":1,"a":2}')
    def test_nonstandard_numbers_rejected(self):
        for word in ['NaN','Infinity','-Infinity']:
            with self.subTest(word=word):
                with self.assertRaises(ValueError):strict_json('{"a":'+word+'}')
    def test_yaml_duplicate_rejected(self):
        with self.assertRaises(ValueError):strict_yaml('name: first\nname: second\n')
    def test_nested_fence_valid(self):self.assertEqual(fence_errors('````text\n```json\n{}\n```\n````\n'),[])
    def test_unclosed_fence_rejected(self):self.assertTrue(fence_errors('```json\n{}\n'))
    def test_unsafe_paths_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for rel in ['../x','/etc/passwd','C:\\temp','https://example.test/x']:
                with self.subTest(path=rel):
                    with self.assertRaises(ValueError):safe_path(Path(d),rel,False)
    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'inside').write_text('x')
            try:(root/'link').symlink_to(root/'inside')
            except OSError:self.skipTest('symlinks unavailable')
            with self.assertRaises(ValueError):safe_path(root,'link')

class SuiteTests(unittest.TestCase):
    def copy_suite(self,d):
        target=Path(d)/'repo'
        shutil.copytree(ROOT,target,ignore=shutil.ignore_patterns('__pycache__','site','.venv'))
        return target
    def test_current_suite_valid(self):
        result=validate(ROOT)
        self.assertEqual(result['exit_code'],0,[c for c in result['checks'] if c['result']=='FAIL'])
    def test_manifest_deterministic(self):self.assertEqual(expected_manifest(ROOT)[0],expected_manifest(ROOT)[0])
    def test_changed_prompt_fails_readonly(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.copy_suite(d);p=next((root/'プロンプト一覧').glob('01*'))
            p.write_text(p.read_text()+'\nAdditional untracked change.\n',encoding='utf-8')
            before=(root/'SUITE_MANIFEST.json').read_bytes()
            r=validate(root)
            self.assertEqual(r['exit_code'],1)
            self.assertEqual((root/'SUITE_MANIFEST.json').read_bytes(),before)
    def test_readme_drift_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.copy_suite(d);p=root/'README.md';s=p.read_text();s=s.replace('| 1.3 |','| 1.2 |')
            self.assertNotEqual(s,p.read_text());p.write_text(s,encoding='utf-8')
            self.assertEqual(validate(root)['exit_code'],1)
    def test_crlf_rejected_even_with_synced_hash(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.copy_suite(d);p=next((root/'プロンプト一覧').glob('02*'))
            p.write_bytes(p.read_bytes().replace(b'\n',b'\r\n'))
            m,_=expected_manifest(root);(root/'SUITE_MANIFEST.json').write_text(dump_json(m),encoding='utf-8')
            result=validate(root);self.assertEqual(result['exit_code'],1)
            self.assertTrue(any(c['id'].startswith('text:プロンプト一覧/02') and c['result']=='FAIL' for c in result['checks']))
    def test_missing_09_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.copy_suite(d);next((root/'プロンプト一覧').glob('09*')).unlink()
            self.assertEqual(validate(root)['exit_code'],1)
    def test_extra_old_prompt_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=self.copy_suite(d);p=next((root/'プロンプト一覧').glob('03*'))
            shutil.copyfile(p,p.with_name('03_old_v2.3.md'))
            self.assertEqual(validate(root)['exit_code'],1)

class EvalTests(unittest.TestCase):
    def test_prepare_is_not_execution(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'repo';shutil.copytree(ROOT,root,ignore=shutil.ignore_patterns('__pycache__','site','.venv'))
            self.assertEqual(run_evals_main(['--root',str(root),'--prepare','--run-id','unit-run']),0)
            run=root/'evals/runs/unit-run/run.json';data=load_json(run)
            self.assertTrue(all(c['execution']=='NOT_RUN' for c in data['cases']))
            self.assertEqual(check_results(root,run)[0],2)
    def test_not_run_cannot_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'run.json';data={'schema_version':'1.0','run_id':'unit','suite_version':'2.1.0','model':None,'environment':None,
                 'cases':[{'id':'E-001','execution':'NOT_RUN','result':'PASS','evidence_file':None,'notes':''}]}
            p.write_text(dump_json(data),encoding='utf-8');self.assertEqual(check_results(ROOT,p)[0],1)
    def test_evidence_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'run.json';data={'schema_version':'1.0','run_id':'unit','suite_version':'2.1.0','model':'synthetic-test','environment':'local',
                 'cases':[{'id':'E-001','execution':'EXECUTED','result':'PASS','evidence_file':'../outside.txt','notes':'synthetic fixture'}]}
            p.write_text(dump_json(data),encoding='utf-8');self.assertEqual(check_results(ROOT,p)[0],1)

if __name__=='__main__':unittest.main()
