/* Layout regressions use isolated data and never modify real accounts. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {chromium} = require('playwright');
const {audit} = require('./axe.cjs');
process.env.A11Y_REPORT = 'dashboards';
const root = path.resolve(__dirname, '..');
const out = process.env.TEST_RESULTS_DIR || path.join(root, 'test-results');
const mime = {'.html':'text/html', '.css':'text/css', '.js':'text/javascript'};
const server = http.createServer((req, res) => {
  const filename = path.resolve(root, '.' + new URL(req.url, 'http://localhost').pathname);
  if (!filename.startsWith(root + path.sep) || !mime[path.extname(filename)]) {
    res.writeHead(404); res.end(); return;
  }
  fs.readFile(filename, (error, data) => {
    res.writeHead(error ? 404 : 200, {'Content-Type':mime[path.extname(filename)]});
    res.end(error ? '' : data);
  });
});

async function checkLayout(page, name) {
  const layout = await page.evaluate(() => {
    const panel = document.querySelector('.tab-panel.active').getBoundingClientRect();
    const footer = document.querySelector('.page-footer').getBoundingClientRect();
    const main = document.querySelector('main').getBoundingClientRect();
    const app = document.querySelector('.app').getBoundingClientRect();
    return {
      overflow:document.documentElement.scrollWidth > innerWidth,
      footerGap:footer.top - panel.bottom,
      mainGap:main.bottom - footer.bottom,
      bodyGap:document.body.getBoundingClientRect().bottom - app.bottom,
      last:document.querySelector('main > :last-child').className,
      toolbar:document.querySelector('.sidebar__footer .a11y-toolbar') !== null,
    };
  });
  assert.equal(layout.overflow, false, name + ': horizontal overflow');
  assert.ok(layout.footerGap >= 0 && layout.footerGap <= 34, name + ': stretched panel ' + JSON.stringify(layout));
  assert.ok(layout.mainGap <= 24 && layout.bodyGap <= 1, name + ': blank bottom ' + JSON.stringify(layout));
  assert.equal(layout.last, 'page-footer');
  assert.equal(layout.toolbar, true);
}

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const front = 'http://127.0.0.1:' + server.address().port;
  let browser;
  const errors = [];
  const cases = [];
  fs.mkdirSync(out, {recursive:true});
  try {
    browser = await chromium.launch({executablePath:process.env.TEST_CHROMIUM_EXECUTABLE || undefined,args:['--no-sandbox']});
    for (const role of ['administrador','recrutador','empresa']) {
      for (const [width,height] of [[1440,900],[1280,600],[768,900],[390,844],[320,640]]) {
        const context = await browser.newContext({viewport:{width,height}});
        const page = await context.newPage();
        page.on('pageerror', error => errors.push(error.message));
        let effectiveRole = role;
        let alternate = 'recrutador';
        let rejectSwitch = false;
        let rejectMeOnce = false;
        const switches = [];
        const user = {ID_Usuarios:'u-test',Nome:'Pessoa de teste com nome completo',Email:'pessoa@example.com',email_confirmado:true};
        await page.route('**/*', async route => {
          const url = new URL(route.request().url());
          if (url.origin === front) return route.continue();
          if (url.origin !== 'http://127.0.0.1:8000') return route.abort();
          let data = [];
          if (url.pathname === '/auth/me' && rejectMeOnce) {
            rejectMeOnce = false;
            return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Falha temporária ao carregar perfil.'})});
          }
          if (url.pathname === '/auth/me') data = {...user,tipo_usuario:effectiveRole,tipo_principal:role === 'empresa' ? 'empresa' : 'administrador',tipo_alternativo:alternate,modo_usuario:effectiveRole === 'recrutador'};
          else if (url.pathname === '/auth/alternar-modo') {
            switches.push(route.request().postDataJSON());
            if (rejectSwitch) return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Tente novamente.'})});
            effectiveRole = switches.at(-1).modo_usuario ? alternate : 'administrador';
            data = {tipo_usuario:effectiveRole};
          } else if (url.pathname === '/dashboard/admin') data = {total_usuarios:12,total_candidatos:8,total_empresas:2,total_vagas_ativas:6,total_candidaturas:21,denuncias_abertas:0,assinaturas_ativas:2};
          else if (url.pathname === '/admin/usuarios') data = [{...user,Perfis:'Administrador, Recrutador',Ativo:true,EhUsuarioAtual:true,CriadoEm:'2026-10-01'}];
          else if (url.pathname === '/empresas/me') data = {ID_Empresas:'e-test',NomeFantasia:'Empresa de teste',Descricao:'Equipe de tecnologia e desenvolvimento.',Setor:'Tecnologia',Endereco:'Belo Horizonte, MG'};
          else if (url.pathname === '/dashboard/empresa/e-test') data = {total_vagas:1,vagas_publicadas:1,total_candidaturas_recebidas:3};
          else if (url.pathname === '/vagas') data = [{ID_Vagas:'v-test',Titulo:'Analista de desenvolvimento de sistemas',Modalidade:'Remoto',Localizacao:'Belo Horizonte, MG',ID_Status_Vaga:2}];
          else if (url.pathname === '/auth/sessoes') data = [{ID_Sessoes:'s-test',Atual:true,UserAgent:'Navegador de teste',UltimaAtividadeEm:'2026-10-01'}];
          return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
        });
        const file = role === 'administrador' ? 'admin' : role;
        await page.goto(front + '/html/dashboard-' + file + '.html');
        await page.locator('.metric').first().waitFor();
        await checkLayout(page, role + '-initial-' + width);
        await page.screenshot({path:path.join(out,role+'-'+width+'.png'),fullPage:true});
        const tabs = await page.locator('.nav-item').evaluateAll(items => items.map(el => el.dataset.tab));
        for (const tab of tabs) {
          await page.locator('[data-tab="'+tab+'"]').click();
          await page.locator('#tab-'+tab+'.active').waitFor();
          await checkLayout(page, role + '-' + tab + '-' + width);
          if (width === 390 || width === 1440) await audit(page, role + '-' + tab + '-' + width);
        }
        await page.locator('.page-footer').scrollIntoViewIfNeeded();
        await page.screenshot({path:path.join(out,role+'-bottom-'+width+'.png')});
        await page.locator('[aria-label="Alternar alto contraste"]').click();
        await checkLayout(page, role + '-contrast-' + width);
        if (width === 390) await audit(page, role + '-contrast');
        await page.locator('[aria-label="Alternar alto contraste"]').click();
        await page.locator('[aria-label="Alternar texto ampliado"]').click();
        await checkLayout(page, role + '-large-' + width);
        if (width === 390) await audit(page, role + '-large');
        await page.locator('[aria-label="Alternar texto ampliado"]').click();
        await page.locator('#settingDarkMode').check();
        if (width === 390) await audit(page, role + '-dark');
        await page.locator('#settingDarkMode').uncheck();

        if (role === 'administrador') {
          assert.equal(await page.locator('#btnModoUsuario').textContent(), 'Acessar painel do recrutador');
          await page.locator('[data-tab="metricas"]').click();
          await page.locator('[data-u-edit]').click();
          await page.locator('#modalUsuario[open]').waitFor();
          if (width === 390) await audit(page, 'admin-dialog');
          await page.keyboard.press('Escape');
          if (width === 390) {
            rejectSwitch = true;
            await page.locator('#btnModoUsuario').click();
            await page.locator('#toast').filter({hasText:'Tente novamente.'}).waitFor();
            assert.ok(page.url().endsWith('dashboard-admin.html'));
            rejectSwitch = false;
            rejectMeOnce = true;
            await page.reload();
            await page.locator('#toast').filter({hasText:'Falha temporária'}).waitFor();
            assert.equal(await page.locator('#btnModoUsuario').isEnabled(), true);
          }
          await page.locator('#btnModoUsuario').click();
          await page.waitForURL('**/dashboard-recrutador.html');
          await page.locator('#btnModoAdmin:not([hidden])').waitFor();
          await page.locator('#btnModoAdmin').click();
          await page.waitForURL('**/dashboard-admin.html');
          assert.deepEqual(switches.at(-1), {modo_usuario:false});
          if (width === 390) {
            for (const [target,label] of [['empresa','Acessar painel da empresa'],['candidato','Acessar painel do candidato'],['usuario','Acessar minha conta']]) {
              alternate = target;
              await page.reload();
              await page.locator('#btnModoUsuario:not([disabled])').waitFor();
              assert.equal(await page.locator('#btnModoUsuario').textContent(), label);
            }
          }
        } else {
          await page.locator('[data-tab="perfil"]').click();
          assert.equal(await page.locator('#formEmpresa button[type="submit"]').isVisible(), role === 'empresa');
          assert.equal(await page.locator('#empresaNome').evaluate(el => el.readOnly), role === 'recrutador');
          await page.locator('[data-tab="vagas"]').click();
          await page.locator('#novaVaga').click();
          await page.locator('#modalVagaEmpresa[open]').waitFor();
          await page.locator('#vagaConfidencial').check();
          const gap = await page.locator('#vagaConfidencial').evaluate(el => {
            const text = document.createRange();
            text.selectNodeContents(el.parentElement.lastChild);
            return text.getBoundingClientRect().left - el.getBoundingClientRect().right;
          });
          assert.ok(gap >= 8, 'Checkbox label spacing');
          if (width === 390) await audit(page, role + '-job-dialog');
          await page.screenshot({path:path.join(out,role+'-dialog-'+width+'.png')});
          await page.keyboard.press('Escape');
        }
        assert.equal(await page.locator('dialog[open]').count(), 0);
        cases.push({role,width,height,passed:true});
        await context.close();
      }
    }
    assert.deepEqual(errors, []);
    console.log('Dashboards: all tabs, 15 responsive cases, dialogs, accessibility and role switching passed.');
  } finally {
    fs.writeFileSync(path.join(out,'dashboard-layout.json'),JSON.stringify({cases,errors},null,2));
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => {console.error(error);process.exitCode=1;});
