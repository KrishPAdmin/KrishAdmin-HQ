import importlib.util,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('n8n_backup',Path(__file__).with_name('backup.py'))
backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)

class BackupFailureTests(unittest.TestCase):
    def test_dump_failure_resumes_only_previously_running_services(self):
        calls=[]
        def compose(*args,**kw):
            calls.append(args)
            if args[0]=='ps':return subprocess.CompletedProcess(args,0,stdout='postgres\nn8n\n')
            if args[0]=='exec':raise subprocess.CalledProcessError(1,args)
            return subprocess.CompletedProcess(args,0)
        with tempfile.TemporaryDirectory() as d,patch.object(backup,'ROOT',Path(d)),patch.object(backup,'compose',side_effect=compose):
            with self.assertRaises(subprocess.CalledProcessError):backup.main()
        self.assertEqual([c for c in calls if c[0] in ('stop','start')],[('stop','n8n'),('start','n8n')])

    def test_database_unavailable_does_not_stop_apps(self):
        with tempfile.TemporaryDirectory() as d,patch.object(backup,'ROOT',Path(d)),patch.object(backup,'compose',return_value=subprocess.CompletedProcess([],0,stdout='n8n\n')) as compose:
            with self.assertRaises(SystemExit):backup.main()
            self.assertEqual(compose.call_count,1)

if __name__=='__main__':unittest.main()
