import importlib.util,json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'agents'))
spec=importlib.util.spec_from_file_location('pi_runtime',Path(__file__).parent/'pi-worker/pi_runtime.py')
runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)

class PiExecutionTests(unittest.TestCase):
    def test_independent_pass_fail_and_zero_tests(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'abandoned-empty-project').mkdir();(root/'project').mkdir();test=root/'project/test_actual.py'
            test.write_text('import unittest\nclass Actual(unittest.TestCase):\n def test_actual(self): self.assertEqual(2+2,4)\n')
            result=runtime.verify_python_tests(root,{'PATH':os.environ['PATH']})
            self.assertTrue(result['passed']);self.assertEqual(result['test_count'],1)
            test.write_text('import unittest\nclass Actual(unittest.TestCase):\n def test_actual(self): self.fail("real failure")\n')
            self.assertFalse(runtime.verify_python_tests(root,{'PATH':os.environ['PATH']})['passed'])
            test.write_text('# No tests\n')
            self.assertFalse(runtime.verify_python_tests(root,{'PATH':os.environ['PATH']})['passed'])

    def test_output_limit_preserves_tool_evidence_but_abort_fails(self):
        events=[{'type':'tool_execution_end','toolName':'write','isError':False},
                {'type':'turn_end','message':{'role':'assistant','stopReason':'length','content':[{'type':'text','text':'unverified success claim'}],'usage':{'output':8192}}}]
        raw='\n'.join(json.dumps(e) for e in events)
        final,inputs,outputs,turns,tools=runtime.parse_pi_output(raw,True,[])
        self.assertIn('output limit',final);self.assertNotIn('unverified success claim',final)
        self.assertEqual(tools,[{'name':'write','is_error':False}]);self.assertEqual(outputs,8192)
        with self.assertRaisesRegex(RuntimeError,'stopped: length'):runtime.parse_pi_output(raw,False,[])
        events[-1]['message']['stopReason']='aborted'
        with self.assertRaisesRegex(RuntimeError,'stopped: aborted'):runtime.parse_pi_output('\n'.join(json.dumps(e) for e in events),True,[])

    def test_bundle_preserves_nested_source_and_omits_caches_links_and_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'package').mkdir();(root/'package/source.py').write_text('print(42)\n')
            (root/'__pycache__').mkdir();(root/'__pycache__/source.pyc').write_bytes(b'cache')
            (root/'outside').symlink_to('/etc/passwd');(root/'.private').write_text('private')
            runtime.bundle_source(root,[])
            with zipfile.ZipFile(root/'deliverables.zip') as archive:self.assertEqual(archive.namelist(),['package/source.py'])
            (root/'package/source.py').write_text('FAKE_PROTECTED_VALUE')
            with self.assertRaisesRegex(RuntimeError,'protected credential'):runtime.bundle_source(root,['FAKE_PROTECTED_VALUE'])

if __name__=='__main__':unittest.main()
