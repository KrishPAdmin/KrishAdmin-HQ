const routes=[
 ['overview','GET','/overview','board-or-agent'],['codex-status','GET','/codex/status','board'],['codex-login','POST','/codex/login','board'],['policy','PATCH','/policy','board'],
 ['certificate','POST','/certificate','board'],['save-system','POST','/systems','board'],
 ['remove-system','DELETE','/systems/:systemId','board'],['inspect','POST','/systems/:systemId/inspect','board'],
 ['agent-inspect','POST','/issues/:issueId/inspect/:systemId','board-or-agent'],
 ['resolve-action','POST','/actions/:actionId/resolve','board'],['enrollment','GET','/enrollment','board']
].map(([routeKey,method,path,auth])=>({routeKey,method,path,auth,capability:'api.routes.register',checkoutPolicy:routeKey==='agent-inspect'?'always-for-agent':'none',companyResolution:routeKey==='agent-inspect'?{from:'issue',param:'issueId'}:{from:'query',key:'companyId'}}));
export default {id:'krishadmin.control-center',apiVersion:1,version:'0.1.2',displayName:'KrishAdmin Control Center',description:'Agent controls, local systems, privacy policies and access reviews.',author:'KrishAdmin',categories:['ui','connector','automation'],
 capabilities:['ui.sidebar.register','ui.page.register','api.routes.register','agents.read','issues.read','activity.log.write','secrets.read-ref'],
 entrypoints:{worker:'./dist/worker.js',ui:'./dist/ui'},apiRoutes:routes,
 ui:{slots:[{type:'page',id:'control-center-page',displayName:'Control Center',exportName:'ControlCenter',routePath:'control-center'},
 {type:'sidebar',id:'control-center-sidebar',displayName:'Control Center',exportName:'ControlCenterSidebar'}]}};
