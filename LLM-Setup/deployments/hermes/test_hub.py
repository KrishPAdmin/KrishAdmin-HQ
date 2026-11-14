import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import hub_store as store
import hub_sandbox as sandbox

class HubTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        for agent in store.AGENTS:
            for area in store.AREAS:(self.root/'agents'/agent/area).mkdir(parents=True)
        self.mock = patch.object(store, 'HUB', self.root); self.mock.start()
    def tearDown(self):self.mock.stop(); self.temp.cleanup()
    def test_read_and_save_without_overwriting_input(self):
        (self.root/'agents/louis/inbox/example.py').write_text('print(123)\n')
        self.assertEqual(store.read('louis','inbox/example.py')['text'],'print(123)\n')
        store.write('louis','deliverables/review.md','Reviewed')
        with self.assertRaises(FileExistsError):store.write('louis','deliverables/review.md','Overwrite')
        with self.assertRaises(ValueError):store.write('louis','inbox/example.py','Overwrite')
    def test_traversal_unknown_agent_runtime_and_credentials_refused(self):
        for agent,path in [('stranger','inbox/a'),('louis','../mike/a'),('louis','runtime/auth.json'),('louis','inbox/.env'),('louis','inbox/private.key'),('louis','inbox/../mike/a')]:
            with self.assertRaises(ValueError):store.parts(agent,path)
    def test_symlink_and_hardlink_do_not_expose_other_files(self):
        private=self.root/'private.md'; private.write_text('do not expose')
        (self.root/'agents/louis/inbox/link.md').symlink_to(private)
        os.link(private,self.root/'agents/louis/inbox/hard.md')
        for name in ('link.md','hard.md'):
            with self.assertRaises((OSError,ValueError)):store.read('louis','inbox/'+name)
        self.assertEqual(store.listing('louis')['files'],[])
    def test_symlink_parent_write_refused(self):
        (self.root/'agents/louis/workspace/other').symlink_to(self.root/'agents/mike/workspace',target_is_directory=True)
        with self.assertRaises(OSError):store.write('louis','workspace/other/test.py','print(1)')
    def test_large_file_and_fifo_refused(self):
        base=self.root/'agents/louis/inbox'
        with (base/'large.txt').open('wb') as file:file.truncate(store.MAX_BYTES+1)
        os.mkfifo(base/'fifo.txt')
        for name in ('large.txt','fifo.txt'):
            with self.assertRaises(ValueError):store.read('louis','inbox/'+name)
    def test_slices_disclose_remainder(self):
        (self.root/'agents/mike/inbox/text.md').write_text('abcdefgh')
        result=store.read('mike','inbox/text.md',offset=2,limit=3)
        self.assertEqual((result['text'],result['next_offset']),('cde',5))
    def test_sandbox_mounts_only_named_workspace_without_network(self):
        (self.root/'agents/louis/workspace/test.py').write_text('print(1)')
        with patch.object(sandbox,'ROOT',self.root/'agents'):
            command=sandbox.command({'agent':'louis','path':'workspace/test.py'},'test')
            self.assertEqual(command.count('--mount'),1)
            self.assertIn('none',command); self.assertIn('--read-only',command)
            self.assertIn('ALL',command); self.assertNotIn('/run/secrets',' '.join(command))
            for body in ({'agent':'louis','path':'inbox/test.py'},{'agent':'louis','path':'workspace/../other.py'},{'agent':'louis','path':'workspace/test.py','command':'id'}):
                with self.assertRaises(ValueError):sandbox.command(body,'test')

if __name__=='__main__':unittest.main()
