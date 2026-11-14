import hashlib,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from plugin import file_delivery as files

class FileDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'drafts').mkdir()
        self.patch=patch.object(files,'ROOT',self.root);self.patch.start();self.addCleanup(self.patch.stop)
        self.name='test-123456789abc.py';self.path=self.root/'drafts'/self.name;self.path.write_text('print(42)\n')

    def test_bounded_cache_only(self):
        self.assertEqual(files.resolve(self.name),self.path)
        for value in ('/etc/passwd','../test.py','test.py','doc_../../secret'):
            with self.assertRaises(ValueError):files.resolve(value)
        self.path.unlink();self.path.symlink_to('/etc/passwd')
        with self.assertRaises(ValueError):files.resolve(self.name)

    def test_oversized_file_denied(self):
        with patch.object(files,'MAX_BYTES',2):
            with self.assertRaisesRegex(ValueError,'5 MiB'):files.resolve(self.name)

    def test_only_current_explicit_tool_success_can_deliver(self):
        run=types.ModuleType('gateway.run');run._collect_auto_append_media_tags=lambda *args:([],False)
        run._tool_name_by_call_id=lambda messages:{c['id']:c['function']['name'] for m in messages for c in m.get('tool_calls',[])}
        gateway=types.ModuleType('gateway');gateway.run=run
        with patch.dict(sys.modules,{'gateway':gateway,'gateway.run':run}):files.install()
        value={'delivery_requested':True,'file_id':self.name,'delivery_path':str(self.path),'sha256':hashlib.sha256(self.path.read_bytes()).hexdigest()}
        messages=[{'role':'assistant','tool_calls':[{'id':'call','function':{'name':'hq_send_file'}}]}, {'role':'tool','tool_call_id':'call','content':json.dumps(value)}]
        collect=run._collect_auto_append_media_tags
        self.assertEqual(collect(messages)[0],['MEDIA:'+str(self.path)])
        self.assertEqual(collect(messages,2)[0],[])
        self.assertEqual(collect(messages,3)[0],[])
        self.assertEqual(collect(messages,0,{str(self.path)})[0],[])
        messages[0]['tool_calls'][0]['function']['name']='hq_research'
        self.assertEqual(collect(messages)[0],[])
        messages[0]['tool_calls'][0]['function']['name']='hq_send_file'
        self.path.write_text('changed')
        self.assertEqual(collect(messages)[0],[])

if __name__=='__main__':unittest.main()
