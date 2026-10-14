/* Navegador e API/MySQL reais: central, consentimentos, mensagens e acessibilidade. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');const {audit}=require('./axe.cjs');
if(process.env.TALENTIX_ISOLATED_TESTS!=='1')throw Error('Exige ambiente descartável de testes.');
const out=process.env.TEST_RESULTS_DIR||path.resolve(__dirname,'../test-results');
const fixture=JSON.parse(fs.readFileSync(path.join(out,'platform-fixture.json'),'utf8'));
const front=process.env.TEST_FRONTEND_URL||'http://127.0.0.1:5500',api=process.env.TEST_API_URL||'http://127.0.0.1:8000';
process.env.A11Y_REPORT='central';
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.TEST_CHROMIUM_EXECUTABLE||undefined,args:['--no-sandbox']});
 const errors=[];
 try{
  for(const width of [1365,390,683]){
   const context=await browser.newContext({viewport:{width,height:980},reducedMotion:'reduce'});
   await context.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort());
   const login=await context.request.post(api+'/auth/login',{data:{email:fixture.email_empresa,senha:'Plataforma123!'}});assert.equal(login.status(),200);
   const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
   await page.goto(front+'/html/central.html');await page.locator('#papelAtivo').filter({hasText:'Owner'}).waitFor();
   await page.locator('#processosCentral button').first().waitFor();
   for(const tab of ['processos','agenda','comunicacao','analytics','equipe','automacoes','publicacao','privacidade']){
    await page.locator(`[data-tab="${tab}"]`).click();await page.waitForLoadState('networkidle');
    await page.locator('#centralEstado').filter({hasText:'Dados atualizados.'}).waitFor();
    assert.equal(await page.locator('#centralErro').textContent(),'','Erro na aba '+tab);
    await audit(page,`central-${tab}-${width}`);
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`central: reflow ${tab} ${width}`);
   }
   await page.locator('[data-tab="inteligencia"]').click();await page.locator('#iaProcesso').selectOption(fixture.candidatura);
   await page.locator('#analisarCentral').click();await page.locator('#iaResultado').filter({hasText:'Correspondência'}).waitFor();
   await audit(page,`central-ia-${width}`);
   if(width===1365){
    await page.locator('[data-tab="comunicacao"]').click();await page.locator('#comProcesso').selectOption(fixture.candidatura);
    await page.locator('#comTexto').fill('<img id="injetado" src=x onerror=alert(1)> Mensagem de teste');
    await page.locator('#formConversa button').click();await page.locator('#timelineCentral').filter({hasText:'Mensagem de teste'}).waitFor();
    assert.equal(await page.locator('#injetado').count(),0);
    await page.locator('[data-tab="processos"]').click();await page.locator('#centralEstado').filter({hasText:'Dados atualizados.'}).waitFor();await page.screenshot({path:path.join(out,'central-desktop.png'),fullPage:true});
   }
   if(width===390){await page.locator('[data-tab="agenda"]').click();await page.locator('#centralEstado').filter({hasText:'Dados atualizados.'}).waitFor();await page.screenshot({path:path.join(out,'central-mobile.png'),fullPage:true});}
   await context.close();
  }
  const context=await browser.newContext({viewport:{width:390,height:900}});
  const publicPage=await context.newPage();
  for(const [kind,slug] of [['empresa',fixture.slug_empresa],['vaga',fixture.slug_vaga]]){
   await publicPage.goto(api+'/p/'+kind+'/'+slug);await audit(publicPage,'publico-'+kind+'-mobile');
   assert.ok(await publicPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   if(kind==='vaga'){
    const schema=await publicPage.locator('script[type="application/ld+json"]').textContent();
    assert.equal(JSON.parse(schema)['@type'],'JobPosting');
    assert.ok(!schema.includes('9999'));
    await publicPage.locator('a.botao').click();
    assert.equal(new URL(publicPage.url()).searchParams.get('vaga'),fixture.vaga);
   }
  }
  await publicPage.close();
  const login=await context.request.post(api+'/auth/login',{data:{email:fixture.email_candidato,senha:'Plataforma123!'}});assert.equal(login.status(),200);
  const page=await context.newPage();await page.goto(front+'/html/central.html');await page.locator('#processosCentral button').first().waitFor();
  for(const privatePath of ['/python/.env','/.git/config','/sql/talentix_db.sql','/docs/updates_novembro.md'])assert.equal((await context.request.get(front+privatePath)).status(),404);
  await page.locator('[data-tab="comunicacao"]').click();await page.locator('#comProcesso').selectOption(fixture.candidatura);
  await page.locator('#carregarTimeline').click();await page.locator('#timelineCentral [data-read]').first().waitFor();
  await page.locator('#timelineCentral [data-read]').first().click();await page.waitForLoadState('networkidle');
  await audit(page,'central-candidato-mobile');
  assert.equal(await page.locator('[data-tab="equipe"]').isVisible(),false);
  await page.locator('[data-tab="privacidade"]').click();await page.waitForLoadState('networkidle');await audit(page,'central-privacidade-candidato');
  // O service worker nunca cacheia respostas privadas, mesmo após navegação autenticada.
  await page.evaluate(async()=>{if('serviceWorker'in navigator)await navigator.serviceWorker.ready;});
  const cached=await page.evaluate(async()=>{const out=[];for(const name of await caches.keys())for(const request of await(await caches.open(name)).keys())out.push(new URL(request.url).pathname);return out;});
  assert.ok(cached.every(p=>/^\/(css|js|icons)\//.test(p)||p==='/html/offline.html'),JSON.stringify(cached));
  await context.close();assert.deepEqual(errors,[]);
  console.log('Central integrada: empresa e candidato, 3 larguras, XSS escapado, leitura, cache privado e Axe aprovados.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
