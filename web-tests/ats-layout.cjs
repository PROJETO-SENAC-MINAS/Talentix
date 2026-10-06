/* Layout + keyboard alternative + blind scorecard using deterministic API fixtures. */
const assert=require('node:assert/strict'),fs=require('node:fs'),http=require('node:http'),path=require('node:path');
const {chromium}=require('playwright');const {audit}=require('./axe.cjs');
process.env.A11Y_REPORT='ats';
const root=path.resolve(__dirname,'..'),server=http.createServer((req,res)=>{const name=path.resolve(root,'.'+new URL(req.url,'http://localhost').pathname);if(!name.startsWith(root+path.sep)){res.writeHead(404);res.end();return;}fs.readFile(name,(err,data)=>{res.writeHead(err?404:200,{'Content-Type':{'.html':'text/html','.css':'text/css','.js':'text/javascript'}[path.extname(name)]||'text/plain'});res.end(err?'':data);});});
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const front='http://127.0.0.1:'+server.address().port;const browser=await chromium.launch({executablePath:process.env.TEST_CHROMIUM_EXECUTABLE||undefined,args:['--no-sandbox']});try{
for(const width of [390,768,1280,1440]){
 const ctx=await browser.newContext({viewport:{width,height:900},reducedMotion:'reduce'}),page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 let stages=[{ID_Etapa:'s1',Nome:'Novos',Ativa:1,Ordem:0},{ID_Etapa:'s2',Nome:'Entrevista técnica',Ativa:1,Ordem:1}],card={ID_Candidaturas:'ca1',ID_Candidatos:'c1',NomeCandidato:'Candidato teste',ID_Etapa:'s1',Estado:'ativo',CandidaturaAtiva:1,Ordem:0,Versao:1,EntradaEm:'2026-12-01',Notas:null,ID_Responsavel:null,Prazo:null,Motivo:null},ratings=[];
 let models=[{ID_Modelo:'m1',Nome:'Entrevista Python',Cego:1,Criterios:[{nome:'Python',peso:3,obrigatorio:true},{nome:'Comunicação',peso:1,obrigatorio:false}]}],members=[],pool={ID_Pool:'p1',Nome:'Backend'};
 await ctx.route('http://127.0.0.1:8000/**',async route=>{const req=route.request(),url=new URL(req.url()),p=url.pathname,m=req.method(),d=req.postDataJSON();let data={};
 if(m==='OPTIONS'){await route.fulfill({status:200,headers:{'Access-Control-Allow-Origin':front,'Access-Control-Allow-Credentials':'true','Access-Control-Allow-Headers':'content-type,x-csrf-token','Access-Control-Allow-Methods':'GET,POST,PUT,DELETE'}});return;}
 if(p==='/auth/me')data={id_usuario:'u1',tipo_usuario:'empresa'};
 else if(p==='/ats/contexto')data={empresa:{ID_Empresas:'e1',NomeFantasia:'Empresa teste'},vagas:[{ID_Vagas:'v1',Titulo:'Backend',Ativo:1,ID_Status_Vaga:2}],avaliadores:[{ID_Usuarios:'u1',Nome:'RH teste'}]};
 else if(p==='/ats/pools')data=m==='GET'?[pool]:pool;
 else if(p==='/ats/talentos')data={total:1,itens:[{ID_Candidatos:'c1',Nome:'Candidato teste',TituloProfissional:'Python',Cidade:'BH',Estado:'MG'}]};
 else if(p.endsWith('/pipeline'))data={etapas:stages,cards:[card]};
 else if(p.endsWith('/card')){card={...card,ID_Etapa:d.id_etapa,Ordem:d.ordem,Versao:card.Versao+1,Estado:d.estado,Notas:d.notas,ID_Responsavel:d.responsavel,Prazo:d.prazo,Motivo:d.motivo};data=card;}
 else if(p.endsWith('/scorecards'))data=m==='GET'?models:{ID_Modelo:'m2',...d};
 else if(p.endsWith('/avaliacoes')){if(m==='POST'){ratings=[{ID_Usuarios:'u1',Avaliador:'RH teste',Notas:d.notas,Media:3.5,Parecer:d.parecer,Recomendacao:d.recomendacao,CriadoEm:'2026-12-02'}];}data=m==='GET'?{bloqueado:!ratings.length,avaliacoes:ratings,media:ratings.length?3.5:null}:{Media:3.5};}
 else if(p==='/ats/talentos/c1/historico')data={processos:[{Titulo:'Backend',Estado:'ativo',CriadaEm:'2026-12-01',scorecards:[]}],pools:members};
 else if(p.includes('/pools/p1/candidatos/')){members=m==='DELETE'?[]:[{ID_Pool:'p1',Nome:'Backend',Tags:d.tags,Favorito:d.favorito,Notas:d.notas}];}
 else if(p.endsWith('/historico'))data=[{Acao:'ats.entrada',CriadoEm:'2026-12-01',ID_Usuarios:'u1',Depois:JSON.stringify({etapa:'s1',estado:'ativo'})}];
 await route.fulfill({status:200,contentType:'application/json',headers:{'Access-Control-Allow-Origin':front,'Access-Control-Allow-Credentials':'true'},body:JSON.stringify(data)});
 });
 await page.goto(front+'/html/ats.html');await page.locator('#atsEmpresa').filter({hasText:'Empresa teste'}).waitFor();await page.locator('#atsVaga').selectOption('v1');await page.locator('[data-move="ca1"]').waitFor();
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Pipeline reflow '+width);await audit(page,'pipeline-'+width);
 await page.locator('[data-move="ca1"]').focus();await page.keyboard.press('Enter');await page.locator('#atsCardDialog[open]').waitFor();await page.locator('#atsCardEtapa').selectOption('s2');await page.locator('#atsCardNotas').fill('Observação interna');await audit(page,'card-'+width);
 await page.locator('#atsCardSalvar').focus();await page.keyboard.press('Enter');await page.locator('#atsCardDialog').waitFor({state:'hidden'});assert.equal(card.ID_Etapa,'s2');
 // Exercise the actual HTML drag/drop handlers with a browser DataTransfer.
 await page.evaluate(()=>{const item=document.querySelector('[data-card="ca1"]'),target=document.querySelector('[data-column="s1"]'),data=new DataTransfer();item.dispatchEvent(new DragEvent('dragstart',{bubbles:true,dataTransfer:data}));target.dispatchEvent(new DragEvent('dragover',{bubbles:true,cancelable:true,dataTransfer:data}));target.dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer:data}));});
 await page.waitForFunction(()=>document.querySelector('[data-column="s1"] [data-card="ca1"]'));assert.equal(card.ID_Etapa,'s1');
 await page.locator('.nav-item[data-tab="scorecards"]').click();await audit(page,'scorecards-'+width);await page.locator('#atsAvaliarCandidato').selectOption('ca1');await page.locator('#atsAvaliarAbrir').click();await page.locator('#atsScoreDialog[open]').waitFor();assert.ok((await page.locator('#atsAvaliacoes').textContent()).includes('ocultas'));
 await page.locator('#note-0').fill('4');await page.locator('#note-1').fill('2');await page.locator('#atsScoreParecer').fill('Boa base');await audit(page,'rating-'+width);await page.locator('#atsScoreEnviar').click();await page.locator('#atsAvaliacoes').filter({hasText:'3.50'}).waitFor();assert.equal(await page.locator('#atsScoreEnviar').isDisabled(),true);await page.keyboard.press('Escape');
 await page.locator('.nav-item[data-tab="talentos"]').click();await page.locator('[data-talent="c1"]').waitFor();await audit(page,'talentos-'+width);await page.locator('[data-talent="c1"]').click();await page.locator('#atsTalentDialog[open]').waitFor();await page.locator('#atsMemberPool').selectOption('p1');await page.locator('#atsMemberTags').fill('Python');await page.locator('#atsMemberNotas').fill('Potencial');await page.locator('#atsMemberForm button').click();await page.locator('#atsTalentPools').filter({hasText:'Potencial'}).waitFor();await audit(page,'talento-dialog-'+width);await page.keyboard.press('Escape');
 assert.deepEqual(errors,[]);await ctx.close();console.log('ATS layout, keyboard, drag/drop, blind review and pools passed at '+width);
}
}finally{await browser.close();await new Promise(r=>server.close(r));}})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
