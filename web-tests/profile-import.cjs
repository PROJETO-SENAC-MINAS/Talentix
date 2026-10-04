/* Regressões da revisão: grupos, itens, consentimento, erros e reflow. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {chromium} = require('playwright');
const {audit} = require('./axe.cjs');
process.env.A11Y_REPORT = 'profile';
const root = path.resolve(__dirname, '..');
const out = process.env.TEST_RESULTS_DIR || path.join(root, 'test-results');
const mime = {'.html':'text/html', '.css':'text/css', '.js':'text/javascript'};
const server = http.createServer((req, res) => {
  const filename = path.resolve(root, '.' + new URL(req.url, 'http://localhost').pathname);
  if (!filename.startsWith(root + path.sep) || !mime[path.extname(filename)]) {
    res.writeHead(404); res.end(); return;
  }
  fs.readFile(filename, (error, data) => {
    res.writeHead(error ? 404 : 200, {'Content-Type': mime[path.extname(filename)]});
    res.end(error ? '' : data);
  });
});
const controls = ['impPerfil', 'impExperiencias', 'impFormacoes', 'impHabilidades', 'impIdiomas'];
const fixture = {
  perfil: {titulo_profissional:'Analista de qualidade', cidade:'Contagem', estado:'MG', github_url:'https://github.com/exemplo', portfolio_url:'https://novo.example.com'},
  experiencias: [{empresa:'Empresa A',cargo:'Assistente',data_inicio:'2025-01-01'}, {empresa:'Empresa B',cargo:'Analista',data_inicio:'2026-01-01',atual:true}],
  formacoes: [{instituicao:'Escola A',curso:'Sistemas'}, {instituicao:'Escola B',curso:'Testes'}],
  habilidades: [{nome:'Python'}, {nome:'SQL'}],
  idiomas: [{idioma:'Inglês',nivel:'intermediario'}, {idioma:'Espanhol',nivel:'basico'}],
};

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const front = 'http://127.0.0.1:' + server.address().port;
  let browser;
  const errors = [];
  const cases = [];
  fs.mkdirSync(out, {recursive:true});
  try {
    browser = await chromium.launch({executablePath:process.env.TEST_CHROMIUM_EXECUTABLE || undefined, args:['--no-sandbox']});
    for (const [width, height] of [[1440,900], [768,900], [390,844], [683,450]]) {
      const context = await browser.newContext({viewport:{width,height}});
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      let extracted = structuredClone(fixture);
      const applied = [];
      let reject = false;
      const candidate = {ID_Candidatos:'c-ui',ID_Usuarios:'u-ui',Disponivel:true,PortfolioUrl:'https://atual.example.com'};
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.origin === front) return route.continue();
        if (url.origin !== 'http://127.0.0.1:8000') return route.abort();
        let data = [];
        if (url.pathname === '/auth/me') data = {id_usuario:'u-ui',tipo_usuario:'candidato',Nome:'Candidato de teste'};
        else if (url.pathname === '/candidatos/me') data = candidate;
        else if (url.pathname === '/candidatos/c-ui/profissional') data = {
          perfil:candidate,completude:27,itens:[],idiomas:[],faltantes:[
            {campo:'Foto de perfil',peso:5},{campo:'Experiência profissional',peso:10},
            {campo:'Formação acadêmica',peso:10},{campo:'Idioma',peso:3},
          ],
        };
        else if (url.pathname === '/candidatos/c-ui/curriculos') data = [{ID_Curriculos:'cv-ui',Titulo:'Currículo de teste',ArquivoUrl:'/uploads/curriculos/teste.pdf',Principal:true,ImportacaoStatus:3}];
        else if (url.pathname === '/curriculos/cv-ui/importacao') data = {ID_Status_Processamento_IA:3,DadosExtraidos:extracted};
        else if (url.pathname === '/curriculos/cv-ui/importacao/aplicar') {
          const payload = route.request().postDataJSON();
          applied.push(payload);
          if (reject) return route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({detail:'Revise o dado identificado antes de confirmar.'})});
          const map = {titulo_profissional:'TituloProfissional',cidade:'Cidade',estado:'Estado',github_url:'GithubUrl',portfolio_url:'PortfolioUrl'};
          for (const key of payload.selecionados.perfil) {
            if (payload.sobrescrever_perfil || !candidate[map[key]]) candidate[map[key]] = extracted.perfil[key];
          }
          data = {importados:{perfil:payload.selecionados.perfil.length}};
        } else if (url.pathname === '/vagas/busca') data = {resultados:[],total:0,pagina:1,total_paginas:1};
        return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
      });
      await page.goto(front + '/html/dashboard-candidato.html');
      await page.locator('#completudeTexto').filter({hasText:'27%'}).waitFor();
      await page.locator('[data-revisar-importacao]').first().waitFor();
      assert.equal(await page.locator('#formCurriculo').count(), 1);
      assert.equal(await page.locator('#tab-curriculo,#tab-formacao').count(), 0);
      assert.equal(await page.locator('#tab-perfil > .card').first().getAttribute('id'), 'secaoCurriculos');
      assert.equal(await page.locator('main > :last-child').getAttribute('class'), 'page-footer');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      const boxes = await page.locator('#perfilFaltantes li').evaluateAll(items => items.map(item => item.getBoundingClientRect().toJSON()));
      assert.equal(boxes[0].top, boxes[1].top, 'Pendências ficam lado a lado.');
      const photo = await page.locator('#formFoto').evaluate(form => ({
        gap:form.querySelector('button').getBoundingClientRect().top - form.querySelector('input').getBoundingClientRect().bottom,
        next:document.querySelector('#formPerfil').getBoundingClientRect().top - form.getBoundingClientRect().bottom,
      }));
      assert.ok(photo.gap >= 16 && photo.next >= 20, 'Foto e próximo formulário têm espaço.');
      await page.locator('.page-footer').scrollIntoViewIfNeeded();
      const bottom = await page.evaluate(() => ({gap:document.documentElement.scrollHeight - (document.querySelector('.page-footer').getBoundingClientRect().bottom + scrollY),height:document.documentElement.scrollHeight,body:document.body.scrollHeight,scrollY,rects:['.app','.sidebar','.content','.page-footer'].map(s=>({s,rect:document.querySelector(s).getBoundingClientRect().toJSON()}))}));
      await page.screenshot({path:path.join(out,'perfil-bottom-'+width+'.png')});
      assert.ok(bottom.gap <= 32, 'Sem rolagem vazia depois do rodapé: '+JSON.stringify(bottom));
      await page.evaluate(() => window.scrollTo({top:0,behavior:'instant'}));
      await page.screenshot({path:path.join(out,'perfil-final-'+width+'.png')});
      if (width === 1440 || width === 390) await audit(page, 'perfil-organizado-'+width);
      if (width === 390) {
        const normalBackground = await page.locator('#gerarCurriculoTalentix').evaluate(el => getComputedStyle(el).backgroundColor);
        await page.locator('[aria-label="Alternar alto contraste"]').click();
        await audit(page, 'perfil-alto-contraste');
        await page.locator('[aria-label="Alternar alto contraste"]').click();
        assert.equal(await page.locator('#gerarCurriculoTalentix').evaluate(el => getComputedStyle(el).backgroundColor), normalBackground, 'O contraste dos botões deve voltar imediatamente após trocar a preferência.');
        await page.locator('[aria-label="Alternar texto ampliado"]').click();
        await audit(page, 'perfil-texto-ampliado');
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.locator('[aria-label="Alternar texto ampliado"]').click();
      }

      await page.locator('[data-revisar-importacao]').first().click();
      await page.locator('#modalImportarCurriculo[open]').waitFor();
      assert.equal(await page.locator('#curriculoImportacaoId').inputValue(), 'cv-ui');
      for (const id of controls) assert.equal(await page.locator('#'+id).isChecked(), true);
      const github = page.locator('input[data-campo="github_url"]');
      await github.uncheck();
      assert.equal(await page.locator('#impPerfil').evaluate(el => el.indeterminate), true);
      await page.locator('#impPerfil').check();
      assert.equal(await github.isChecked(), true);
      await page.locator('#impPerfil').uncheck();
      assert.equal(await page.locator('input[data-secao="perfil"]:checked').count(), 0);
      await github.focus(); await page.keyboard.press('Space');
      assert.equal(await github.isChecked(), true);
      assert.equal(await page.locator('#impPerfil').evaluate(el => el.indeterminate), true);
      await page.locator('input[data-secao="habilidades"][data-indice="0"]').uncheck();
      assert.equal(await page.locator('#impHabilidades').evaluate(el => el.indeterminate), true);
      await page.locator('#impFormacoes').uncheck();
      const before = await page.locator('#pGithub').inputValue();
      assert.equal(before, '', 'Nenhum dado aplicado sem confirmação.');
      await page.screenshot({path:path.join(out,'revisao-final-'+width+'.png')});
      if (width === 1440 || width === 390) await audit(page, 'revisao-seletiva-'+width);
      const buttonBox = await page.locator('#btnAplicarCurriculo').boundingBox();
      assert.ok(buttonBox.y >= 0 && buttonBox.y + buttonBox.height <= height, 'A confirmação permanece acessível na janela.');
      reject = true;
      await page.locator('#btnAplicarCurriculo').click();
      await page.locator('#curriculoImportacaoErro').filter({hasText:'Revise o dado'}).waitFor();
      assert.equal(await page.locator('#modalImportarCurriculo').isVisible(), true);
      assert.equal(await github.isChecked(), true);
      assert.equal(await page.locator('#btnAplicarCurriculo').isEnabled(), true);
      const payload = applied[0];
      assert.deepEqual(payload.selecionados, {perfil:['github_url'],experiencias:[0,1],formacoes:[],habilidades:[1],idiomas:[0,1]});
      assert.equal(payload.importar_perfil, true, 'Grupo parcial também importa seus itens.');
      assert.equal(payload.importar_formacoes, false);
      reject = false;
      await page.locator('#btnAplicarCurriculo').click();
      await page.locator('#modalImportarCurriculo').waitFor({state:'hidden'});
      await page.waitForFunction(() => document.querySelector('#pGithub').value === 'https://github.com/exemplo');
      assert.equal(await page.locator('#pPortfolio').inputValue(), 'https://atual.example.com');

      await page.locator('[data-revisar-importacao]').first().click();
      await page.locator('#modalImportarCurriculo[open]').waitFor();
      for (const id of controls) await page.locator('#'+id).uncheck();
      assert.equal(await page.locator('#btnAplicarCurriculo').isDisabled(), true);
      const sent = applied.length;
      await page.locator('#formAplicarCurriculo').evaluate(form => form.requestSubmit());
      assert.equal(applied.length, sent, 'Não envia importação vazia.');
      await page.locator('#cancelarImportacaoCurriculo').click();
      extracted.idiomas = [];
      await page.locator('[data-revisar-importacao]').first().click();
      await page.locator('#modalImportarCurriculo[open]').waitFor();
      assert.equal(await page.locator('#impIdiomas').isDisabled(), true);
      assert.equal(await page.locator('#impIdiomas').isChecked(), false);
      assert.equal(await page.locator('#impSobrescrever').isChecked(), false);
      assert.equal(await page.locator('#curriculoImportacaoErro').isHidden(), true);
      await page.locator('#btnAplicarCurriculo').click();
      await page.locator('#modalImportarCurriculo').waitFor({state:'hidden'});
      const complete = applied.at(-1);
      assert.deepEqual(complete.selecionados.experiencias, [0,1]);
      assert.deepEqual(complete.selecionados.formacoes, [0,1]);
      assert.deepEqual(complete.selecionados.habilidades, [0,1]);
      assert.equal(complete.importar_perfil, true);
      assert.equal(complete.importar_idiomas, false);
      await page.locator('[data-tab="notificacoes"]').click();
      await page.locator('#listaNotificacoes .empty-state').waitFor();
      assert.ok(await page.evaluate(() => document.querySelector('.page-footer').getBoundingClientRect().top - document.querySelector('#tab-notificacoes').getBoundingClientRect().bottom < 40));
      await page.locator('[data-tab="seguranca"]').click();
      assert.equal(await page.locator('main > :last-child').getAttribute('class'), 'page-footer');
      await context.close();
      cases.push({width,height,passed:true});
    }
    assert.deepEqual(errors, []);
    console.log('Perfil e importação: grupos e itens sincronizados, confirmação, erros, teclado e quatro tamanhos aprovados.');
  } finally {
    fs.writeFileSync(path.join(out,'profile-import.json'), JSON.stringify({cases,errors}, null, 2));
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
