import importlib.util,sys,tempfile,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'agents'))
from local_agent import configured_context
spec=importlib.util.spec_from_file_location('fixed_diagnostics',Path(__file__).parent/'operations/diagnostics_probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
class ContextControlTests(unittest.TestCase):
 def test_legacy_window_is_read_each_request_and_invalid_size_refused(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'context.json';path.write_text(json.dumps({'contexts':{'paperclip-nvidia-gpu':16384}}))
   self.assertEqual(configured_context('specialist','nvidia-gpu',path),16384)
   path.write_text(json.dumps({'contexts':{'paperclip-amd-gpu':65536}}))
   with self.assertRaises(ValueError):configured_context('specialist','amd-gpu',path)
 def test_amd_sensors_preserve_pci_identity_and_convert_power_units(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);device=root/'0000:03:00.0';device.mkdir();(root/'card2').mkdir();(root/'card2/device').symlink_to(device)
   for name,value in {'vendor':'0x1002','mem_info_vram_used':'100','mem_info_vram_total':'200','gpu_busy_percent':'52'}.items():(device/name).write_text(value)
   hw=device/'hwmon/hwmon0';hw.mkdir(parents=True)
   for name,value in {'name':'amdgpu','power1_average':'42500000','power1_cap':'300000000'}.items():(hw/name).write_text(value)
   r=probe.amd_sensors(root)['cards'][0]
   self.assertEqual(r['pci_bus_id'],'0000:03:00.0');self.assertEqual(r['card'],'card2');self.assertEqual(r['power_watts'],42.5);self.assertEqual(r['power_limit_watts'],300)
 def test_installer_contains_current_fixed_probe(self):
  script=(Path(__file__).parent/'operations/install-observer.sh').read_text();self.assertIn((Path(__file__).parent/'operations/diagnostics_probe.py').read_text().strip(),script)
if __name__=='__main__':unittest.main()
