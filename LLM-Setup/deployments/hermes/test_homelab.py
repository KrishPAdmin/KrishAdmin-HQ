import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import homelab
from homelab_monitor import changes,states
class HomelabTests(unittest.TestCase):
 def test_explicit_action_required(self):
  p={'id':'a'*20,'digest':'b'*64,'action':'restart','service':'npm_app'}
  for message in ['status npm_app','do not restart npm_app','explain how to restart npm_app','restart npm_db']:
   self.assertFalse(homelab.authorized(p,message),message)
  self.assertTrue(homelab.authorized(p,'please restart npm_app'))
  self.assertTrue(homelab.authorized(p,'homelab apply '+'a'*20+' '+'b'*12))
 def test_deployment_matches_target_app_and_port(self):
  p={'id':'a'*20,'digest':'b'*64,'action':'deploy','app':'nginx','target':'Pi-Cluster-02','published_port':8080}
  for m in ['install nginx on Pi-Cluster-03 port 8080','install nginx on Pi-Cluster-02','show nginx on Pi-Cluster-02 port 8080']:
   self.assertFalse(homelab.authorized(p,m))
  self.assertTrue(homelab.authorized(p,'install nginx on 192.0.2.91 port 8080'))
 def test_scope_rejects_shell_and_wrong_service(self):
  with self.assertRaises(ValueError):homelab.execute({'_service':'homelab','action':'status','command':'id'},'owner','')
  with self.assertRaises(PermissionError):homelab.execute({'action':'status'},'owner','')
  with patch.object(homelab,'services',return_value=[{'name':'npm_app'}]):
   with self.assertRaises(ValueError):homelab.execute({'_service':'homelab','action':'prepare_restart','service':'npm_app;id'},'owner','')
 def test_redis_publish_rejected(self):
  with self.assertRaises(ValueError):homelab.execute({'_service':'homelab','action':'prepare_deploy','app':'redis','target':'Pi-Cluster-01','published_port':6379},'owner','')
 def test_uncertain_mutation_not_repeated(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(homelab,'STATE',Path(folder)),patch.object(homelab,'services',return_value=[{'id':'s','name':'npm_app','image':'image'}]),patch.object(homelab,'run',side_effect=TimeoutError) as run:
   p=homelab.execute({'_service':'homelab','action':'prepare_restart','service':'npm_app'},'owner','')
   request={'_service':'homelab','action':'apply','proposal_id':p['id']}
   self.assertTrue(homelab.execute(request,'owner','status npm_app')['authorization_required']);run.assert_not_called()
   self.assertEqual(homelab.execute(request,'owner','restart npm_app')['status'],'uncertain')
   self.assertEqual(homelab.execute(request,'owner','restart npm_app')['status'],'uncertain');self.assertEqual(run.call_count,1)
   with self.assertRaises(PermissionError):homelab.execute(request,'stranger','restart npm_app')
 def test_change_notifier_ignores_time_and_ping(self):
  a={'hosts':[{'target':'Pi-Cluster-01','status':'observed'}],'swarm_nodes':[],'swarm_services':[],'uptime_kuma':{'monitors':[{'name':'node','active':True,'status':1,'ping_ms':2}]}}
  b=json.loads(json.dumps(a));b['uptime_kuma']['monitors'][0]['ping_ms']=3
  self.assertEqual(changes(states(a),states(b)),[])
  b['uptime_kuma']['monitors'][0]['status']=0
  self.assertEqual(len(changes(states(a),states(b))),1)
if __name__=='__main__':unittest.main()

class OriginTests(unittest.TestCase):
 def test_signed_owner_required_and_replay_rejected(self):
  import github_service as service
  import hashlib,hmac,sqlite3,uuid
  with tempfile.TemporaryDirectory() as folder,patch.object(service,'ROOT',Path(folder)):
   root=Path(folder);(root/'access').mkdir();(root/'access/github-origin').write_text('test-key')
   (root/'profiles/concierge').mkdir(parents=True)
   (root/'profiles/concierge/discord-enrollment.json').write_text(json.dumps({'owner_id':'owner','channel_id':'900000000000000007','application_id':'bot'}))
   mid=str((int(time.time()*1000)-1420070400000)<<22)
   db=sqlite3.connect(':memory:');db.execute('CREATE TABLE nonces(nonce TEXT PRIMARY KEY,created REAL)')
   def envelope(user):
    e={'request':{'_service':'homelab','action':'status'},'origin':{'platform':'discord','user_id':user,'chat_id':'900000000000000007','message_id':mid},'issued_at':time.time(),'nonce':uuid.uuid4().hex}
    e['signature']=hmac.new(b'test-key',service.canonical(e),hashlib.sha256).hexdigest();return e
   with patch.object(service,'discord',return_value={'author':{'id':'owner'},'mentions':[{'id':'bot'}],'content':'show Pi status'}):
    with self.assertRaises(PermissionError):service.authenticate(envelope('friend'),db)
    e=envelope('owner');self.assertEqual(service.authenticate(e,db)[0],'owner')
    with self.assertRaises(PermissionError):service.authenticate(e,db)
    e=envelope('owner');e['request']['action']='apply'
    with self.assertRaises(PermissionError):service.authenticate(e,db)
