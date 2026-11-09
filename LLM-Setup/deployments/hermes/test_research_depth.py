"""Answer coverage, semantic extraction and isolated rendering regressions."""
import json,unittest
from unittest.mock import patch
import broker,web_research

class ResearchDepthTests(unittest.TestCase):
    def test_completed_report_is_delivered_without_factual_rewrite(self):
        body={'model':'qwen3.5:9b','messages':[{'role':'user','content':'Research the documented failure behavior'},
            {'role':'assistant','tool_calls':[{'id':'call_test','function':{'name':'hq_research'}}]},
            {'role':'tool','tool_call_id':'call_test','content':json.dumps({'status':'completed','analysis':{
                'text':'Verified specialist report with exceptions preserved.','compute_receipt':{'run_id':'actual-amd-gpu-run','backend':'amd-gpu'}}})}]}
        with patch('broker.audit'):
            result=broker.completed_research_reply(body)
        self.assertEqual(result['choices'][0]['message']['content'],'Verified specialist report with exceptions preserved.')
        self.assertEqual(result['hq_receipt']['run_id'],'actual-amd-gpu-run')
        body['messages'][0]['content']='Research the behavior then create a plan'
        self.assertIsNone(broker.completed_research_reply(body))
        body['messages'][0]['content']='Research the behavior'
        data=json.loads(body['messages'][-1]['content']);data['status']='partial';body['messages'][-1]['content']=json.dumps(data)
        self.assertIsNone(broker.completed_research_reply(body))

    def test_excerpt_keeps_preceding_conditions_with_best_match(self):
        text='Introduction '+('irrelevant '*400)+'Critical prerequisite: never discard the associated exception. '+('alpha beta gamma delta '*90)+' End.'
        page={'url':'https://example.org/reference','raw':b'<title>Reference version 4</title>','text':text,'fetched_at':'now','download_truncated':False}
        with patch('web_research.document',return_value=page):r=web_research.collect('alpha beta gamma delta',urls=[page['url']])
        self.assertIn('Critical prerequisite',r['sources'][0]['excerpt'][:4000])
        self.assertEqual(r['sources'][0]['title'],'Reference version 4')
    def test_candidate_primary_url_is_fetched_before_it_is_evidence(self):
        first={'status':'sources_collected','search':{},'sources':[{'url':'https://example.org','excerpt':'Homepage'}],'fetch_failures':[],'evidence_sha256':'one'}
        next_page={'status':'sources_collected','search':{},'sources':[{'url':'https://docs.example.org/reference','excerpt':'Relevant verified text'}],'fetch_failures':[],'evidence_sha256':'two'}
        replies=[{'text':json.dumps({'sufficient':False,'queries':['specific reference'],'urls':['https://docs.example.org/reference']})},
                 {'text':'{"sufficient":true,"queries":[]}'},{'text':'Draft with fetched evidence','backend':'amd-gpu','run_id':'draft'},
                 {'text':'Answer with fetched evidence','backend':'amd-gpu','run_id':'verified'}]
        with patch('broker.collect_web',side_effect=[first,next_page,next_page]) as collect,patch('broker.run_worker',side_effect=replies),patch('broker.audit'):
            result=broker.research_request({'question':'Explain the reference'})
        self.assertEqual(collect.call_args_list[1].args,('Explain the reference',['https://docs.example.org/reference']))
        self.assertEqual(result['status'],'completed')
    def test_youtube_uses_primary_header_not_recommended_channel(self):
        data={'metadata':{'channelMetadataRenderer':{'title':'Example Lab','externalId':'UC-example'}},
              'header':{'pageHeaderViewModel':{'metadataRows':[{'content':'2.34M subscribers'},{'accessibilityLabel':'2.34 million subscribers'}]}},
              'contents':{'recommended':{'subscriberCountText':{'simpleText':'999M subscribers'}}}}
        raw=('<script>var ytInitialData = '+json.dumps(data)+';</script>').encode()
        text=web_research.structured_text(raw,'https://www.youtube.com/@example/about')
        self.assertIn('Example Lab',text);self.assertIn('2.34M subscribers',text)
        self.assertNotIn('999M',text);self.assertIn('approximate',text)
        self.assertNotIn('PRIMARY CHANNEL',web_research.structured_text(raw,'https://example.org/fake'))

    def test_missing_channel_count_does_not_take_recommendation(self):
        data={'metadata':{'channelMetadataRenderer':{'title':'Example Lab'}},'contents':{'simpleText':'999M subscribers'}}
        text=web_research.structured_text(('<script>ytInitialData = '+json.dumps(data)+'</script>').encode(),'https://youtube.com/@example')
        self.assertIn('"subscriber_count_display": []',text);self.assertNotIn('999M',text)

    def test_truncated_javascript_is_not_readable_evidence(self):
        self.assertEqual(web_research.clean(b'<main>Visible</main><script>secret_not_evidence'), 'Visible')

    def test_jsonld_and_page_description_survive_script_removal(self):
        raw=b'<meta name="description" content="Example launch"><script type="application/ld+json">{"@type":"Product","name":"Example","offers":{"price":"42.50","priceCurrency":"CAD"}}</script>'
        text=web_research.structured_text(raw,'https://example.org')
        for value in ('Example launch','42.50','CAD'):self.assertIn(value,text)

    def test_unicode_channel_excerpt_obeys_byte_budget(self):
        text='YouTube PRIMARY CHANNEL HEADER: example '+('界'*7000)
        page={'url':'https://youtube.com/@example','raw':b'fixture','text':text,'fetched_at':'now','download_truncated':False}
        with patch('web_research.document',return_value=page):
            result=web_research.collect('example',urls=[page['url']])
        self.assertLessEqual(len(result['sources'][0]['excerpt'].encode()),6500)
        self.assertTrue(result['sources'][0]['truncated'])

    def test_renderer_failure_is_explicit_and_html_retained(self):
        page={'url':'https://example.org','raw':b'<main>Readable fallback</main>','download_truncated':False,'fetched_at':'now'}
        with patch('web_research.fetch',return_value=page),patch.dict('os.environ',{'HQ_RENDER_URL':'http://renderer/render'}),patch('urllib.request.urlopen',side_effect=TimeoutError):
            result=web_research.read_page(page['url'],render=True)
        self.assertEqual(result['text'],'Readable fallback');self.assertEqual(result['render_error'],'TimeoutError')
        self.assertEqual(result['browser_receipt'],{})

    def test_missing_fact_triggers_search_and_reassessment(self):
        def packet(url,text):return {'status':'sources_collected','search':{},'sources':[{'url':url,'excerpt':text,'body_sha256':'body'}],'fetch_failures':[],'evidence_sha256':'initial'}
        first=packet('https://example.org/intro','Company introduction')
        second=packet('https://example.org/stats','Subscribers: about 2.34 million')
        replies=[{'text':json.dumps({'sufficient':False,'missing':'Subscriber count','queries':['Example Lab subscriber statistics']})},
                 {'text':json.dumps({'sufficient':True,'missing':'','queries':[]})},
                 {'text':'About 2.34 million','backend':'amd-gpu','run_id':'draft'},
                 {'text':'About 2.34 million','backend':'amd-gpu','run_id':'checked'}]
        with patch('broker.collect_web',side_effect=[first,second]) as collect,patch('broker.run_worker',side_effect=replies),patch('broker.audit'):
            result=broker.research_request({'question':'Example Lab subscriber count'})
        self.assertEqual(collect.call_count,2);self.assertEqual(result['status'],'completed')
        self.assertEqual(result['evidence']['research_status'],'supported')
        self.assertEqual(len(result['evidence']['search_attempts']),2)
        self.assertTrue(result['evidence']['search_summary']['coverage']['sufficient'])

    def test_unanswered_research_is_partial_not_completed(self):
        p={'status':'sources_collected','search':{},'sources':[{'url':'https://example.org','excerpt':'Introduction'}],'fetch_failures':[],'evidence_sha256':'initial'}
        replies=[{'text':'{"sufficient":false,"missing":"Count","queries":["Example statistics"]}'},
                 {'text':'{"sufficient":false,"missing":"Count","queries":[]}'},
                 {'text':'Count remains unavailable','backend':'amd-gpu','run_id':'checked'}]
        with patch('broker.collect_web',return_value=p),patch('broker.run_worker',side_effect=replies),patch('broker.audit'):
            result=broker.research_request({'question':'Example count'})
        self.assertEqual(result['status'],'partial');self.assertEqual(result['evidence']['research_status'],'partial')

if __name__=='__main__':unittest.main()
