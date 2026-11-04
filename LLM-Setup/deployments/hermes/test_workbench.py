"""Regression tests for public collection and default compute boundaries."""
import unittest
import json
from unittest.mock import patch
import broker,web_research

class WorkbenchTests(unittest.TestCase):
    def test_binary_documents_skip_syntax_without_decoding_or_execution(self):
        import tempfile,file_service
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'sample.docx';p.write_bytes(b'PK\x00\xff')
            result=file_service.validate_syntax(p)
        self.assertEqual(result['status'],'not_supported');self.assertFalse(result['executed'])

    def test_model_contexts_match_installed_capacity(self):
        self.assertEqual(broker.context_length(broker.TEAM['jessica']['model'],'amd-gpu'),65536)
        self.assertEqual(broker.context_length(broker.BACKENDS['amd-gpu'][3],'amd-gpu'),32768)
        self.assertEqual(broker.context_length(broker.TEAM['harvey']['model'],'amd-gpu'),8192)

    def test_long_history_is_not_rejected_at_old_character_limit(self):
        body={'model':broker.BACKENDS['nvidia-gpu'][3],'messages':[{'role':'user','content':'a'*110000}]}
        self.assertEqual(broker.validate_inference('concierge',body),'nvidia-gpu')
        body['messages'][0]['content']='a'*610000
        with self.assertRaises(ValueError):broker.validate_inference('concierge',body)

    def test_amd_gpu_compaction_route_is_strictly_tool_free(self):
        body={'model':broker.TEAM['jessica']['model'],'messages':[{'role':'user','content':'Summarize this history'}]}
        self.assertEqual(broker.validate_inference('concierge',body),'amd-gpu')
        body['tools']=[{'function':{'name':'hq_status'}}]
        with self.assertRaises(PermissionError):broker.validate_inference('concierge',body)

    def test_weather_resolves_country_and_keeps_timestamp_units_source(self):
        geo={'raw':json.dumps({'results':[{'name':'Toronto','country':'Canada','latitude':43.7,'longitude':-79.4}]}).encode()}
        report={'raw':json.dumps({'current':{'time':'2026-11-04T01:00','temperature_2m':12},'current_units':{'temperature_2m':'°C'}}).encode(),'fetched_at':'now'}
        with patch('web_research.fetch',side_effect=[geo,report]) as fetch:
            result=web_research.weather('Toronto','CA')
        self.assertIn('countryCode=CA',fetch.call_args_list[0].args[0])
        self.assertEqual(result['current']['time'],'2026-11-04T01:00')
        self.assertEqual(result['current_units']['temperature_2m'],'°C')
        self.assertTrue(result['source_url'].startswith('https://api.open-meteo.com/'))

    def test_public_research_without_sources_never_infers(self):
        p={'status':'no_source_evidence','sources':[],'search':{},'evidence_sha256':'x'}
        with patch('broker.collect_web',return_value=p),patch('broker.audit'),patch('broker.run_worker') as run:
            result=broker.research_request({'question':'Find current release notes'})
        self.assertIsNone(result['analysis']);run.assert_not_called()

    def test_public_research_uses_amd_gpu_and_keeps_source_identity(self):
        p={'status':'sources_collected','sources':[{'url':'https://example.org/release','excerpt':'Release 42','body_sha256':'hash'}],'search':{},'evidence_sha256':'x'}
        with patch('broker.collect_web',return_value=p),patch('broker.audit'),patch('broker.run_worker',return_value={'backend':'amd-gpu','run_id':'verified'}) as run:
            result=broker.research_request({'question':'Summarize the release'})
        self.assertEqual(run.call_args.args[0],'analyst')
        self.assertEqual(result['evidence']['sources'][0]['body_sha256'],'hash')

    def test_mcp_schema_allowlist_does_not_open_arbitrary_tools(self):
        body={'model':broker.BACKENDS['nvidia-gpu'][3],'messages':[{'role':'user','content':'test'}],'tools':[{'function':{'name':'mcp__research__search'}}]}
        self.assertEqual(broker.validate_inference('concierge',body),'nvidia-gpu')
        body['tools'][0]['function']['name']='mcp__filesystem__write_file'
        with self.assertRaises(PermissionError):broker.validate_inference('concierge',body)

    def test_amd_gpu_still_has_no_tool_schemas(self):
        body={'model':broker.BACKENDS['amd-gpu'][3],'messages':[{'role':'user','content':'test'}],'tools':[{'function':{'name':'mcp__research__search'}}]}
        with self.assertRaises(PermissionError):broker.validate_inference('analyst',body)

    def test_checker_rejects_shell_and_non_enrolled_hosts_before_execution(self):
        with patch('broker.diagnostics') as run:
            for body in [{'target':'example.com','checks':['gpu']},{'target':'amd-gpu','checks':['gpu; id']},{'target':'nvidia-gpu','checks':['gpu']*4}]:
                with self.assertRaises(ValueError):broker.workbench({'action':'check_system',**body})
        run.assert_not_called()

    def test_failed_check_remains_unknown_in_analysis(self):
        with patch('broker.diagnostics',side_effect=OSError),patch('broker.analyze',return_value={}) as run:
            result=broker.workbench({'action':'check_system','target':'amd-gpu','checks':['gpu']})
        self.assertEqual(result['checks'][0]['status'],'unavailable')
        self.assertIn('unavailable',run.call_args.args[0]['text']);self.assertFalse(result['changes_made'])

    def test_read_page_pagination_find_and_private_boundary(self):
        page={'url':'https://example.org','raw':b'<main>Intro. TaskGroup documented. More text.</main>','fetched_at':'now','download_truncated':False}
        with patch('web_research.fetch',return_value=page):
            result=web_research.read_page(page['url'],limit=9,find='TaskGroup')
            self.assertEqual(result['text'],'TaskGroup');self.assertIsNotNone(result['next_offset'])
            self.assertEqual(web_research.read_page(page['url'],find='Absent')['status'],'text_not_found')
        with patch('web_research.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),patch('web_research.socket.socket') as socket:
            with self.assertRaises(ValueError):web_research.read_page('https://example.org')
            socket.assert_not_called()

    def test_long_page_excerpt_includes_subject_beyond_intro(self):
        page={'url':'https://example.org/taskgroup','raw':('<main>'+'Introduction '*300+' TaskGroup cancels remaining tasks on failure. '+('more '*300)+'</main>').encode(),'fetched_at':'now','download_truncated':False}
        with patch('web_research.fetch',return_value=page):r=web_research.collect('TaskGroup',urls=[page['url']])
        self.assertIn('TaskGroup cancels',r['sources'][0]['excerpt']);self.assertTrue(r['sources'][0]['truncated'])

if __name__=='__main__':unittest.main()
