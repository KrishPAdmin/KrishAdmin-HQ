import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import broker,context_settings as settings,contextctl,gpu_telemetry as gpu

class ContextTests(unittest.TestCase):
    def test_invalid_values_and_unknown_targets_fail_closed(self):
        for target,tokens in [('louis',65536),('harvey',16384),('concierge',32768),('mike',True),('rachel',65000),('jessica',0)]:
            c=settings.defaults();c['contexts'][target]=tokens
            with self.assertRaises(ValueError):settings.validate(c)
        c=settings.defaults();c['contexts']['unknown']=8192
        with self.assertRaises(ValueError):settings.validate(c)
    def test_experimental_native_max_and_prompt_budget(self):
        c=settings.defaults();c['contexts']['mike']=131072
        with self.assertRaisesRegex(ValueError,'experimental'):settings.validate(c)
        c['experimental']=['mike'];settings.validate(c)
        c['contexts']['louis']=8192
        self.assertEqual(settings.prompt_budget('louis',c),6144)
        c['contexts']['jessica']=32768
        self.assertEqual(settings.compression(c)['threshold_tokens'],16384)
    def test_per_identity_windows_and_compaction_route(self):
        self.assertEqual(settings.target_for('concierge','mixtral','amd-gpu'),'jessica')
        self.assertEqual(settings.target_for('mike','qwen','nvidia-gpu'),'mike')
        self.assertEqual(settings.target_for('operator','qwen','nvidia-gpu'),'concierge')
    def test_original_discord_context_prompt_requires_real_tool_result(self):
        b={'model':'qwen3.5:9b','tools':[{'function':{'name':'hq_status'}}],
           'messages':[{'role':'user','content':'what is the current context window sitting at?'}]}
        r=broker.context_reply(b);message=r['choices'][0]['message'];call=message['tool_calls'][0]
        self.assertEqual(json.loads(call['function']['arguments']),{'view':'context'})
        with patch.object(broker,'gpu',return_value={'loaded_models':[]}):status=broker.context_status()
        b['messages'] += [message,{'role':'tool','tool_call_id':call['id'],'content':json.dumps(status)}]
        text=broker.context_reply(b)['choices'][0]['message']['content']
        self.assertIn('65,536 tokens',text);self.assertIn('not measured',text);self.assertNotIn('8K–32K',text)
        b['messages'].append({'role':'user','content':'Change my context window to 32K'})
        self.assertIsNone(broker.context_reply(b))
    def test_atomic_apply_and_rollback_on_write_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'hermes';(root/'config').mkdir(parents=True)
            before=settings.defaults();contextctl.atomic(root/'config/context-windows.json',contextctl.encoded(before))
            candidate=settings.defaults();candidate['contexts']['louis']=16384
            stamp=contextctl.commit(candidate,before,root,restart=False)
            self.assertEqual(settings.load(root/'config/context-windows.json'),candidate)
            self.assertEqual(settings.load(root/'backups/context-settings'/stamp/'context-windows.json'),before)
            self.assertEqual(settings.load(root.parent/'paperclip/data/hq-hermes/context-windows.json'),candidate)

    def test_mid_write_failure_restores_previous_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'hermes';(root/'config').mkdir(parents=True)
            before=settings.defaults();path=root/'config/context-windows.json';contextctl.atomic(path,contextctl.encoded(before))
            candidate=settings.defaults();candidate['contexts']['louis']=16384
            atomic=contextctl.atomic;failed=[]
            def write(target,data):
                if target==root.parent/'paperclip/data/hq-hermes/context-windows.json' and not failed:
                    failed.append(True);raise OSError('synthetic write failure')
                atomic(target,data)
            with patch.object(contextctl,'atomic',side_effect=write):
                with self.assertRaises(OSError):contextctl.commit(candidate,before,root,restart=False)
            self.assertEqual(settings.load(path),before)

class GPUTests(unittest.TestCase):
    def test_nvidia_units_and_missing_power(self):
        r=gpu.parse('nvidia-gpu',{'checks':{'nvidia':{'status':'observed','output':'0, NVIDIA-GPU GPU, driver, bus, 42, 37 %, 1024 MiB, 16384 MiB, 52.5 W'}}})[0]
        self.assertEqual(r['utilization_percent'],37);self.assertEqual(r['memory_used_bytes'],1073741824)
        self.assertEqual(r['power_watts'],52.5);self.assertEqual(r['memory_percent'],6.25)
        self.assertIsNone(gpu.number('N/A'));self.assertIsNone(gpu.percentage('611993571'))
    def test_amd_uses_documented_utilization_and_exact_bytes(self):
        value={'checks':{'amd':{'output':json.dumps({'card0':{'PCI Bus':'0000:03:00.0','GPU use (%)':'0','GFX Activity':'611993571','Temperature (Sensor edge) (C)':'33'}})},
                         'amd_sensors':{'cards':[{'card':'card1','pci_bus_id':'0000:03:00.0','memory_used_bytes':100,'memory_total_bytes':200,'power_watts':42}]}}}
        r=gpu.parse('amd-gpu',value)[0]
        self.assertEqual(r['utilization_percent'],0);self.assertEqual(r['memory_percent'],50);self.assertEqual(r['power_watts'],42)
        self.assertEqual(r['drm_card'],'card1');self.assertEqual(r['card'],'card0')
        del value['checks']['amd'];r=gpu.parse('amd-gpu',value)[0]
        self.assertIsNone(r['utilization_percent']);self.assertEqual(r['status'],'partial')
    def test_failed_collection_never_becomes_zero(self):
        rows=gpu.parse('amd-gpu',{'status':'unavailable'})
        self.assertEqual(len(rows),2)
        for row in rows:self.assertEqual(row['status'],'unavailable');self.assertIsNone(row.get('power_watts'))
    def test_stale_cache_marked_and_refresh_not_duplicated(self):
        live=gpu.LiveGPU(lambda target:{});live.value={'status':'observed','cards':[]};live.updated=1;live.running=True
        with patch.object(gpu.time,'monotonic',return_value=45):result=live.get()
        self.assertEqual(result['status'],'stale');self.assertEqual(result['age_seconds'],44)

if __name__=='__main__':unittest.main()
