/* Fluxo de apresentação inteiro, com contas fictícias e MySQL da suíte de integração. */
const {chromium} = require('playwright');
const {audit} = require('./axe.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {spawnSync} = require('node:child_process');
const path = require('node:path');
if (process.env.TALENTIX_ISOLATED_TESTS !== '1') throw new Error('Use somente o ambiente descartável de testes.');
const FRONT = process.env.TEST_FRONTEND_URL || 'http://127.0.0.1:5500';
const API = process.env.TEST_API_URL || 'http://127.0.0.1:8000';
const OUT = process.env.TEST_RESULTS_DIR || path.join(__dirname,'../test-results');
fs.mkdirSync(OUT,{recursive:true});
const cases = [], errors = [], screenshots = [];
const nonce = Date.now().toString();
const companyName = 'Empresa navegador '+nonce;
const password = 'Navegador123!';
async function test(name,fn) {
  try { await fn(); cases.push({case:name,passed:true}); }
  catch(error) { cases.push({case:name,passed:false,error:error.message}); throw error; }
}
(async () => {
  const browser = await chromium.launch({headless:true,executablePath:process.env.TEST_CHROMIUM_EXECUTABLE || undefined,args:['--no-sandbox']});
  const contexts = [];
  async function page() {
    const context = await browser.newContext(); contexts.push(context);
    await context.route('**/*',route => { const hostname=new URL(route.request().url()).hostname; return ['127.0.0.1','localhost'].includes(hostname) ? route.continue() : route.abort(); });
    const p=await context.newPage();p.on('pageerror',error=>errors.push(error.message));p.on('dialog',d=>d.accept());
    return p;
  }
  async function tab(p,id) { await p.locator(`.nav-item[data-tab="${id}"]`).click(); }
  async function submit(p,selector,route,method='POST') {
    const [response]=await Promise.all([p.waitForResponse(r=>r.url().includes(route) && r.request().method()===method),p.locator(selector).click()]);
    assert.ok(response.ok(),`${method} ${route}: HTTP ${response.status()}`);return response.json();
  }
  async function signup(p,role,name,email,destination) {
    await p.goto(FRONT+'/html/login.html?modo=cadastro');
    await p.locator(`label[for="cadRole${role}"]`).click();
    await p.locator('#cadNome').fill(name);await p.locator('#cadEmail').fill(email);
    if(role==='Empresa') await p.locator('#cadCnpj').fill(nonce.padStart(14,'0'));
    await p.locator('#cadSenha').fill(password);await p.locator('#cadConfirmarSenha').fill(password);await p.locator('#aceitarTermos').check();
    await p.locator('#btnCadastroSubmit').click();await p.waitForURL('**/'+destination);await p.waitForLoadState('networkidle');
  }
  let failure=null;
  try {
    const company=await page(),candidate=await page(),recruit=await page(),admin=await page(),contact=await page();
    await test('cadastro de empresa abre painel existente',async()=> { await signup(company,'Empresa',companyName,`empresa-${nonce}@browser.example.com`,'dashboard-empresa.html');await company.locator('#tituloEmpresa').filter({hasText:companyName}).waitFor(); });
    await test('cadastro de recrutador aguarda vinculo',async()=> { await signup(recruit,'Recrutador','Recrutador navegador',`rh-${nonce}@browser.example.com`,'dashboard.html');assert.ok((await recruit.locator('#idConta').textContent()).length===36);await audit(recruit,'usuario-aguardando-vinculo'); });
    await test('empresa vincula recrutador pela tela',async()=> { await tab(company,'recrutadores');await company.locator('#recrUsuario').fill(await recruit.locator('#idConta').textContent());await company.locator('#recrCargo').fill('RH navegador');await submit(company,'#formRecrutador button[type="submit"]','/recrutadores');await company.locator('#listaRecrutadores').filter({hasText:'RH navegador'}).waitFor();await recruit.locator('#atualizarVinculo').click();await recruit.waitForURL('**/dashboard-recrutador.html');await recruit.waitForLoadState('networkidle'); });
    let jobId;
    await test('empresa cria e publica vaga pelo painel',async()=> {
      await tab(company,'vagas');await company.locator('#novaVaga').click();
      await company.locator('#vagaTitulo').fill('Vaga navegador '+nonce);await company.locator('#vagaDescricao').fill('Desenvolvimento Python, SQL e testes de API.');await company.locator('#vagaModalidade').selectOption('Remoto');await company.locator('#vagaLocal').fill('Belo Horizonte');await company.locator('#vagaHabilidades').fill('Python, SQL');
      const job=await submit(company,'#formVagaEmpresa button[type="submit"]','/vagas');jobId=job.ID_Vagas;
      await company.locator('#modalVagaEmpresa').waitFor({state:'hidden'});
      await company.locator(`[data-acao="pausar"][data-vaga="${jobId}"]`).waitFor();
      const visible = await candidate.context().request.get(API+'/vagas/'+jobId);
      assert.equal(visible.status(),200,'Vaga recém-criada está pública para candidatos.');
      await company.locator('#listaVagasEmpresa').filter({hasText:'Publicada'}).waitFor();
    });
    await test('cadastro candidato abre painel',async()=> { await signup(candidate,'Candidato','Candidato navegador',`candidato-${nonce}@browser.example.com`,'dashboard-candidato.html');assert.equal(await candidate.locator('#userName').textContent(),'Candidato navegador'); });
    await test('perfil concentra curriculo e formacao sem abas duplicadas',async()=> {
      assert.equal(await candidate.locator('.sidebar__nav [data-tab="curriculo"],.sidebar__nav [data-tab="formacao"]').count(),0);
      assert.ok(await candidate.locator('#tab-perfil #formCurriculo').isVisible());assert.ok(await candidate.locator('#tab-perfil #formFormacao').isVisible());
      assert.ok(await candidate.locator('#tab-perfil #formExperiencia').isVisible());assert.ok(await candidate.locator('#tab-perfil #listaCertificados').isVisible());
    });
    await test('perfil candidato salva e reaparece apos recarregar',async()=> {
      await candidate.locator('#pTituloProfissional').fill('Desenvolvedor Python');await candidate.locator('#pCidade').fill('Belo Horizonte');await candidate.locator('#pEstado').fill('MG');
      await submit(candidate,'#btnSalvarPerfil','/candidatos/','PUT');await candidate.reload();await candidate.waitForLoadState('networkidle');assert.equal(await candidate.locator('#pTituloProfissional').inputValue(),'Desenvolvedor Python');
    });
    await test('candidato registra habilidade pela interface',async()=> {
      await candidate.locator('#hNome').fill('Python');await candidate.locator('#hNivel').selectOption('3');
      await submit(candidate,'#formHabilidade button[type="submit"]','/candidatos/');await candidate.locator('#listaHabilidades').filter({hasText:'Python'}).waitFor();
    });
    await test('perfil 2.0 tem preferencias, foto e completude automatica',async()=> {
      await candidate.locator('#completudeTexto').filter({hasText:'%'}).waitFor();
      const before=await candidate.locator('#completudeBarra').getAttribute('value');
      await candidate.locator('[name="pModalidade"][value="remoto"]').check();await candidate.locator('[name="pContrato"][value="CLT"]').check();
      await candidate.locator('#pSoftSkills').fill('Comunicação, Colaboração');await candidate.locator('#pPreferencias').fill('Tecnologia e trabalho remoto');await candidate.locator('#pResumo').fill('Apresentação profissional revisada pelo candidato.');
      await submit(candidate,'#btnSalvarPerfil','/candidatos/','PUT');
      const image=spawnSync(process.env.TEST_PYTHON || 'python',['-c','from PIL import Image; from io import BytesIO; import sys; b=BytesIO(); Image.new("RGB",(20,20),"blue").save(b,"PNG"); sys.stdout.buffer.write(b.getvalue())']);assert.equal(image.status,0);
      await candidate.locator('#fotoArquivo').setInputFiles({name:'foto.png',mimeType:'image/png',buffer:image.stdout});await submit(candidate,'#formFoto button','/foto-perfil');
      await candidate.locator('#fotoProfissional').waitFor({state:'visible'});await candidate.waitForFunction(old=>Number(document.querySelector('#completudeBarra').value)>Number(old),before);
      assert.ok(await candidate.locator('#tab-perfil #formExperiencia').isVisible());assert.ok(await candidate.locator('#tab-perfil #formFormacao').isVisible());
    });
    await test('cursos projetos e idiomas editaveis na mesma tela',async()=> {
      await candidate.locator('#itemTitulo').fill('Projeto de testes acessíveis');await candidate.locator('#itemUrl').fill('https://example.com/projeto');await submit(candidate,'#formItemProfissional button[type="submit"]','/itens');
      await candidate.locator('#listaItensProfissionais [data-editar-item]').first().click();await candidate.locator('#itemTitulo').fill('Projeto revisado');await submit(candidate,'#formItemProfissional button[type="submit"]','/itens-profissionais/','PUT');
      await candidate.locator('#listaItensProfissionais').filter({hasText:'Projeto revisado'}).waitFor();
      const language=await candidate.locator('#idiomaCatalogo option').nth(1).getAttribute('value');await candidate.locator('#idiomaCatalogo').selectOption(language);await candidate.locator('#idiomaNivel').selectOption('fluente');await submit(candidate,'#formIdioma button','/idiomas');
      await candidate.locator('#listaIdiomasProfissionais').filter({hasText:'fluente'}).waitFor();
    });
    await test('curriculo PDF Talentix gera pre-visao e aguarda confirmacao manual',async()=> {
      await tab(candidate,'perfil');await candidate.locator('#secaoCurriculos').scrollIntoViewIfNeeded();const cv=await submit(candidate,'#gerarCurriculoTalentix','/curriculo-talentix');
      assert.ok(cv?.ID_Curriculos&&cv.ArquivoUrl,'A geração deve retornar o currículo persistido com arquivo próprio.');
      await candidate.reload();await candidate.waitForLoadState('networkidle');await candidate.locator(`[data-analisar-curriculo="${cv.ID_Curriculos}"]`).waitFor();await submit(candidate,`[data-analisar-curriculo="${cv.ID_Curriculos}"]`,'/analisar');
      const result=spawnSync(process.env.TEST_PYTHON || 'python',['-m','app.worker_profissional','--once'],{cwd:path.join(__dirname,'../python'),env:process.env,encoding:'utf8',timeout:120000});assert.equal(result.status,0,result.stderr);
      await candidate.locator(`#listaCurriculos [data-revisar-importacao="${cv.ID_Curriculos}"]`).waitFor({timeout:15000});
      if(!(await candidate.locator('#modalImportarCurriculo').evaluate(dialog=>dialog.open)))await candidate.locator(`#listaCurriculos [data-revisar-importacao="${cv.ID_Curriculos}"]`).click();
      await candidate.locator('#modalImportarCurriculo[open]').waitFor();assert.ok(await candidate.locator('#curriculoImportacaoResumo input[data-secao="perfil"]:checked').count()>0);await audit(candidate,'curriculo-importacao-seletiva');
      const checkbox=candidate.locator('#curriculoImportacaoResumo input[data-secao="perfil"]').first();await checkbox.check();await submit(candidate,'#btnAplicarCurriculo','/importacao/aplicar');await candidate.locator('#modalImportarCurriculo').waitFor({state:'hidden'});
    });
    let cvUrl;
    await test('upload analisa, sugere preenchimento e só altera após confirmação',async()=> {
      await tab(candidate,'perfil');await candidate.locator('#secaoCurriculos').scrollIntoViewIfNeeded();await candidate.locator('#cvTitulo').fill('Currículo da apresentação');await candidate.locator('#cvPrincipal').check();
      const pdf=spawnSync(process.env.TEST_PYTHON || 'python',['-c',"from io import BytesIO; from reportlab.pdfgen import canvas; import sys; out=BytesIO(); c=canvas.Canvas(out); lines=['Camila Reis','Analista de Qualidade','Contagem - MG','https://portfolio.example.com','Resumo','Profissional de QA com testes automatizados.']; [c.drawString(72,800-i*24,line) for i,line in enumerate(lines)]; c.save(); sys.stdout.buffer.write(out.getvalue())"]);assert.equal(pdf.status,0,pdf.stderr);
      await candidate.locator('#cvArquivo').setInputFiles({name:'curriculo.pdf',mimeType:'application/pdf',buffer:pdf.stdout});
      const cv=await submit(candidate,'#btnEnviarCurriculo','/curriculos');assert.ok(cv?.ID_Curriculos);cvUrl=cv.ArquivoUrl;
      const worker=spawnSync(process.env.TEST_PYTHON || 'python',['-m','app.worker_profissional','--once'],{cwd:path.join(__dirname,'../python'),env:process.env,encoding:'utf8',timeout:120000});assert.equal(worker.status,0,worker.stderr);
      await candidate.locator('#modalImportarCurriculo[open]').waitFor({timeout:20000});
      const portfolioSuggestion=candidate.locator('#curriculoImportacaoResumo input[data-campo="portfolio_url"]');assert.equal(await portfolioSuggestion.isChecked(),true);
      const summarySuggestion=candidate.locator('#curriculoImportacaoResumo input[data-campo="resumo"]');assert.equal(await summarySuggestion.isChecked(),true);
      assert.equal(await candidate.locator('#pResumo').inputValue(),'','O perfil não é alterado antes da confirmação do candidato.');
      assert.equal(await candidate.locator('#pPortfolio').inputValue(),'https://example.com/projeto','Campos já preenchidos são preservados antes da confirmação.');
      await candidate.locator('#modalImportarCurriculo').evaluate(dialog=>{dialog.scrollTop=dialog.scrollHeight});await candidate.locator('#btnAplicarCurriculo').scrollIntoViewIfNeeded();
      await submit(candidate,'#btnAplicarCurriculo','/importacao/aplicar');assert.equal(await candidate.locator('#pResumo').inputValue(),'Profissional de QA com testes automatizados.');
      assert.equal(await candidate.locator('#pPortfolio').inputValue(),'https://example.com/projeto','A importação padrão preserva campos que já estavam preenchidos.');
      await candidate.locator('#listaCurriculos').filter({hasText:'Currículo da apresentação'}).waitFor();
    });
    let applicationId;
    await test('candidato seleciona e anexa curriculo ao se candidatar',async()=> {
      await tab(candidate,'vagas');await candidate.locator('#fvTitulo').fill('Vaga navegador '+nonce);await candidate.locator('#formFiltroVagas button[type="submit"]').first().click();await candidate.locator(`[data-candidatar="${jobId}"]`).waitFor();await candidate.locator(`[data-candidatar="${jobId}"]`).click();
      await candidate.locator('#modalCandidatura[open]').waitFor();await audit(candidate,'candidatura-dialog');assert.equal(await candidate.locator('#candidaturaCurriculo').inputValue(),cvUrl);await candidate.locator('#candidaturaCarta').fill('Estou interessado nesta oportunidade.');
      const application=await submit(candidate,'#formCandidatura button[type="submit"]','/candidaturas');assert.equal(application.CurriculoUrl,cvUrl);applicationId=application.ID_Candidaturas;
    });
    await test('filtros URL buscas salvas historico e autocomplete persistem',async()=> {
      await tab(candidate,'vagas');assert.equal(await candidate.locator('#painelFiltrosVagas').isVisible(),false);await candidate.locator('#btnFiltrosVagas').click();assert.equal(await candidate.locator('#btnFiltrosVagas').getAttribute('aria-expanded'),'true');await candidate.locator('#fvTitulo').fill('Vaga navegador '+nonce);await candidate.locator('#fvModalidade').selectOption('Remoto');
      await submit(candidate,'#formFiltroVagas button[type="submit"].btn-primary','/buscas-historico');await candidate.locator(`[data-ver-vaga="${jobId}"]`).waitFor();
      assert.ok(new URL(candidate.url()).searchParams.get('palavra_chave').includes(nonce));
      await candidate.locator('#nomeBusca').fill('Minha oportunidade');await candidate.locator('#alertaBusca').check();await submit(candidate,'#formSalvarBusca button','/buscas');await candidate.locator('#buscasSalvas').filter({hasText:'Alertas ativos'}).waitFor();
      await submit(candidate,'#buscasSalvas [data-alerta-busca]','/buscas/','PUT');await candidate.locator('#buscasSalvas').filter({hasText:'Alertas desativados'}).waitFor();
      await candidate.reload();await candidate.waitForLoadState('networkidle');await candidate.locator('#btnFiltrosVagas').waitFor();assert.equal(await candidate.locator('#btnFiltrosVagas').getAttribute('aria-expanded'),'true');assert.equal(await candidate.locator('#fvModalidade').inputValue(),'Remoto');await candidate.locator(`[data-ver-vaga="${jobId}"]`).waitFor();await audit(candidate,'busca-avancada-persistente');
    });
    await test('empresa ve inscricao e abre somente o curriculo anexado',async()=> {
      await tab(company,'candidaturas');const link=company.locator('#listaCandidaturasEmpresa a').filter({hasText:'Abrir currículo anexado'});await link.waitFor();assert.ok((await link.getAttribute('href')).endsWith(cvUrl));const response=await company.context().request.get(API+cvUrl);assert.equal(response.status(),200);assert.ok((await response.body()).toString().startsWith('%PDF'));
    });
    await test('recrutador ve processo da empresa vinculada',async()=> { await tab(recruit,'candidaturas');await recruit.locator(`[data-processo="${applicationId}"]`).click();await recruit.locator('#modalProcesso[open]').waitFor();await audit(recruit,'processo-dialog');assert.ok((await recruit.locator('#processoPerfil').textContent()).includes('Desenvolvedor Python'));await recruit.locator('#fecharProcesso').click(); });
    await test('empresa adiciona etapa e agenda entrevista pela tela',async()=> {
      await company.locator(`[data-processo="${applicationId}"]`).click();await company.locator('#modalProcesso[open]').waitFor();await company.locator('#etapaNome').fill('Entrevista técnica');await submit(company,'#formEtapa button','/etapas');
      await company.locator('#entrevistaData').fill('2026-12-10T14:00');await company.locator('#entrevistaLocal').fill('Sala de entrevistas do Senac');await submit(company,'#formEntrevista button','/entrevistas');await company.locator('#processoEntrevistas').filter({hasText:'Sala de entrevistas do Senac'}).waitFor();
      await company.locator('#processoStatus').selectOption('4');await submit(company,'#salvarStatus','/status?','PATCH');await company.locator('#fecharProcesso').click();
      await company.waitForLoadState('networkidle');assert.equal(await company.locator('#modalProcesso').isVisible(),false,'Atualização assíncrona não reabre o processo fechado.');
    });
    await test('candidato acompanha status etapas e entrevista',async()=> {
      await tab(candidate,'candidaturas');await candidate.locator('#listaCandidaturas').filter({hasText:'Entrevista'}).waitFor();await candidate.locator(`[data-acompanhar="${applicationId}"]`).click();await candidate.locator('#modalAcompanhamento[open]').waitFor();assert.ok((await candidate.locator('#acompanhamentoConteudo').textContent()).includes('Entrevista técnica'));assert.ok((await candidate.locator('#acompanhamentoConteudo').textContent()).includes('Sala de entrevistas do Senac'));await candidate.locator('#fecharAcompanhamento').click();
    });
    await test('notificacao da entrevista aparece para o candidato',async()=> { await tab(candidate,'notificacoes');await candidate.locator('#listaNotificacoes').filter({hasText:'Entrevista agendada'}).waitFor();const button=candidate.locator('#listaNotificacoes [data-notificacao]').first();const [response]=await Promise.all([candidate.waitForResponse(r=>r.url().includes('/marcar-lida')),button.click()]);assert.equal(response.status(),200); });
    await test('compatibilidade real aparece no painel do candidato',async()=> {
      await tab(candidate,'candidaturas');await candidate.locator(`[data-acompanhar="${applicationId}"]`).click();
      await submit(candidate,'#acompanhamentoConteudo [data-solicitar-analise]','/analises-ia');await candidate.locator('#fecharAcompanhamento').click();
      const result=spawnSync(process.env.TEST_PYTHON || 'python',['-m','app.worker_ia','--once'],{cwd:path.join(__dirname,'../python'),env:process.env,encoding:'utf8',timeout:90000});assert.equal(result.status,0,result.stderr);
      await tab(candidate,'recomendacoes');await candidate.locator('#listaAnalises').filter({hasText:'Concluída'}).waitFor();
      const text=await candidate.locator('#listaAnalises').textContent();assert.ok(text.includes('Python'));assert.ok(text.includes('SQL'));assert.ok(text.includes('% de compatibilidade'));
    });
    await test('mensagem contextualizada circula entre empresa e candidato',async()=> {
      await tab(company,'candidaturas');await company.locator(`[data-contexto="${applicationId}"][data-conversar]`).click();await company.locator('#msgConteudo').fill('Sua entrevista está confirmada.');await submit(company,'#formMensagem button','/mensagens');await company.locator('#fecharMensagem').click();
      await tab(candidate,'mensagens');await candidate.locator('#listaMensagens').filter({hasText:'Sua entrevista está confirmada.'}).waitFor();await candidate.locator('#listaMensagens [data-responder]').first().click();await candidate.locator('#modalMensagem[open]').waitFor();await candidate.locator('#msgConteudo').fill('Obrigado, confirmo minha presença.');await submit(candidate,'#formMensagem button','/mensagens');await candidate.locator('#fecharMensagem').click();
      await tab(company,'mensagens');await company.locator('#listaMensagens').filter({hasText:'Obrigado, confirmo minha presença.'}).waitFor();
    });
    await test('contato mostra falha sem simular sucesso',async()=> {
      await contact.goto(FRONT+'/html/contato.html');await contact.locator('#contatoNome').fill('Visitante navegador');await contact.locator('#contatoEmail').fill('contato@browser.example.com');await contact.locator('#contatoAssunto').selectOption('outro');await contact.locator('#contatoMensagem').fill('Contato da apresentação '+nonce);
      await contact.route(API+'/contato',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Serviço indisponível no teste'})}));await contact.locator('#btnContatoSubmit').click();await contact.locator('#contatoFalha').filter({hasText:'Serviço indisponível'}).waitFor();assert.ok(!(await contact.locator('#contatoSucesso').getAttribute('class')).includes('show'));await contact.unroute(API+'/contato');
    });
    await test('contato grava mensagem real e confirma sucesso',async()=> { await submit(contact,'#btnContatoSubmit','/contato');await contact.locator('#contatoSucesso.show').waitFor(); });
    await test('login de administrador abre painel existente',async()=> { await admin.goto(FRONT+'/html/login.html');await admin.locator('#loginEmail').fill('admin@audit.example.com');await admin.locator('#loginSenha').fill('Auditoria123!');await admin.locator('#btnLoginSubmit').click();await admin.waitForURL('**/dashboard-admin.html');await admin.locator('#metricasAdmin .metric').first().waitFor(); });
    await test('administrador consulta contato persistido',async()=> { await tab(admin,'contatos');await admin.locator('#contatosAdmin').filter({hasText:'Contato da apresentação '+nonce}).waitFor(); });
    await test('administrador verifica empresa pela tela',async()=> { await tab(admin,'empresas');const row=admin.locator('#empresasAdmin tr').filter({hasText:companyName});await row.waitFor();const verify=row.locator('[data-e-check]');await verify.waitFor();await submit(admin,`#empresasAdmin tr:has-text("${companyName}") [data-e-check]`,'/verificar','PATCH');await row.filter({hasText:'Verificada'}).waitFor(); });
    await test('administrador cria curso de preparacao',async()=> { await tab(admin,'catalogo');await admin.locator('#cursoTitulo').fill('Python para entrevistas '+nonce);await admin.locator('#cursoDescricao').fill('Pratique Python e testes de API.');await admin.locator('#cursoPlataforma').fill('Senac');await admin.locator('#cursoCategoria').fill('Python');await submit(admin,'#formCursoAdmin button[type="submit"]','/cursos');await admin.locator('#cursosAdmin').filter({hasText:'Python para entrevistas '+nonce}).waitFor(); });
    await test('administrador resolve denuncia pela interface',async()=> {
      const csrf=(await candidate.context().cookies(API)).find(cookie=>cookie.name==='talentix_csrf');
      assert.ok(csrf?.value,'Cookie CSRF ausente no contexto autenticado do candidato.');
      const response=await candidate.context().request.post(API+'/denuncias',{headers:{'X-CSRF-Token':csrf.value},data:{id_vaga:jobId,motivo:'Denúncia fictícia '+nonce,descricao:'Teste de moderação da apresentação.'}});assert.equal(response.status(),201);const id=(await response.json()).ID_Denuncias;
      await tab(admin,'denuncias');await admin.locator(`[data-denuncia="${id}"][data-status="3"]`).waitFor();await submit(admin,`[data-denuncia="${id}"][data-status="3"]`,'/resolver','PATCH');await admin.locator('#denunciasAdmin').filter({hasText:'Resolvida'}).waitFor();
    });
    await test('painel de candidato funciona em tela de celular',async()=> { await candidate.setViewportSize({width:390,height:844});await tab(candidate,'candidaturas');assert.ok(await candidate.locator('#listaCandidaturas').isVisible());assert.equal(await candidate.locator('.nav-item.active').getAttribute('data-tab'),'candidaturas');assert.ok(await candidate.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)); });
    for (const [p,name] of [[candidate,'candidato'],[company,'empresa'],[admin,'administrador']]) {
      if(name==='candidato') await candidate.setViewportSize({width:1365,height:900});
      const file=path.join(OUT,`painel-${name}.png`);await p.screenshot({path:file,fullPage:true});screenshots.push(file);
    }
    await test('Axe e teclado em todos os painéis autenticados',async()=> {
      const auditErrors=[];
      const scan=async(p,name)=>{try {await audit(p,name);} catch(error){auditErrors.push(error.message);}};
      for(const [p,role] of [[candidate,'candidato'],[company,'empresa'],[recruit,'recrutador'],[admin,'admin']]) {
        await p.setViewportSize({width:1365,height:900});
        const ids=await p.locator('.nav-item[data-tab]').evaluateAll(items=>items.map(el=>el.dataset.tab));
        for(const id of ids) {
          await tab(p,id);await p.waitForLoadState('networkidle');await scan(p,role+'-'+id);
        }
        const first=p.locator('[role="tab"]').first();
        await first.focus();await p.keyboard.press('End');
        assert.equal(await p.locator('[role="tab"]').last().evaluate(el=>el===document.activeElement),true);
        await p.keyboard.press('Home');await p.keyboard.press('Enter');
        assert.equal(await first.getAttribute('aria-selected'),'true');
        await p.setViewportSize({width:390,height:844});await scan(p,role+'-mobile');
        await p.locator('[aria-label="Alternar alto contraste"]').click();await scan(p,role+'-alto-contraste');
        await p.locator('[aria-label="Alternar alto contraste"]').click();
        await p.locator('[aria-label="Alternar texto ampliado"]').click();await scan(p,role+'-texto-ampliado');
        const overflow=await p.evaluate(()=>({width:document.documentElement.scrollWidth,viewport:innerWidth,elements:[...document.querySelectorAll('body *')].map(el=>({tag:el.tagName,id:el.id,cls:typeof el.className==='string'?el.className:'',right:Math.round(el.getBoundingClientRect().right),width:Math.round(el.getBoundingClientRect().width)})).filter(el=>el.right>innerWidth+1).slice(0,8)}));
        assert.ok(overflow.width<=overflow.viewport,`${role} com texto ampliado: ${JSON.stringify(overflow)}`);
        await p.locator('[aria-label="Alternar texto ampliado"]').click();
      }
      assert.deepEqual(auditErrors,[]);
    });
    await test('logout encerra a sessao',async()=> { await candidate.locator('#btnLogout').click();await candidate.waitForURL('**/login.html');assert.equal((await candidate.context().request.get(API+'/auth/me')).status(),401); });
    await test('nenhum erro de JavaScript nos paineis',async()=> {assert.deepEqual(errors,[]);});
  } catch(error) { failure=error.message;console.error(error); }
  finally {
    for(const context of contexts)await context.close();await browser.close();
    const summary={cases:cases.length,passed:cases.filter(c=>c.passed).length,failed:cases.filter(c=>!c.passed).length,execution_error:failure,javascript_errors:errors};
    fs.writeFileSync(path.join(OUT,'browser-tests.json'),JSON.stringify({summary,cases},null,2));console.log(JSON.stringify(summary,null,2));process.exitCode=failure ? 1 : 0;
  }
})();
