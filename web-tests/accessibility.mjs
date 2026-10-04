import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {chromium} from 'playwright';
import {audit} from './axe.cjs';
const root=path.resolve(import.meta.dirname,'..');
for(const name of fs.readdirSync(path.join(root,'html')).filter(n=>n.endsWith('.html'))) {
  const src=fs.readFileSync(path.join(root,'html',name),'utf8');
  const doc=new JSDOM(src).window.document;
  assert.equal(doc.documentElement.lang.toLowerCase(),'pt-br',name+': lang');
  assert.ok(doc.querySelector('meta[name="viewport"]'),name+': viewport');
  assert.ok(doc.querySelector('main'),name+': main');
  assert.equal(doc.querySelectorAll('img:not([alt])').length,0,name+': alt explícito');
  assert.ok(src.includes('../css/acessibilidade.css'),name+': css');
  assert.ok(src.includes('../js/acessibilidade.js'),name+': js');
}
process.env.A11Y_REPORT='public';
const browser=await chromium.launch({executablePath:process.env.TEST_CHROMIUM_EXECUTABLE || undefined,args:['--no-sandbox']});
const base=process.env.TEST_FRONTEND_URL || 'http://127.0.0.1:5500';
const errors=[];
try {
  for(const width of [1365,390,683]) {
    const context=await browser.newContext({viewport:{width,height:900},reducedMotion:'reduce'});
    await context.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort());
    const page=await context.newPage();
    for(const name of ['index','login','contato','termos','privacidade']) {
      await page.goto(`${base}/html/${name}.html`);
      await page.waitForLoadState('networkidle');
      try {await audit(page,`${name}-${width}`);} catch(e) {errors.push(e.message);}
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`${name}: reflow ${width}`);
      await page.keyboard.press('Tab');
      assert.equal(await page.locator(':focus').getAttribute('class'),'skip-link');
      await page.keyboard.press('Enter');
      assert.equal(await page.locator(':focus').evaluate(el=>el.tagName),'MAIN');
      if(name==='contato') {
        await page.locator('#btnContatoSubmit').click();
        assert.equal(await page.locator('#contatoNome').getAttribute('aria-invalid'),'true');
        try {await audit(page,`contato-erros-${width}`);} catch(e) {errors.push(e.message);}
      }
      if(name==='login') {
        await page.locator('#btnLoginSubmit').click();
        assert.equal(await page.locator('#loginEmail').getAttribute('aria-invalid'),'true');
        try {await audit(page,`login-erros-${width}`);} catch(e) {errors.push(e.message);}

        await page.locator('label[for="modeCadastro"]').click();
        try {await audit(page,`cadastro-${width}`);} catch(e) {errors.push(e.message);}
        await page.locator('label[for="modeLogin"]').click();
        await page.locator('#abrirRecuperarSenha').click();
        const dialog=page.locator('#modalRecuperar');
        await dialog.locator('input').focus();
        try {await audit(page,`recuperacao-dialog-${width}`);} catch(e) {errors.push(e.message);}
        const controls=dialog.locator('button:visible,input:visible');
        await controls.last().focus();await page.keyboard.press('Tab');
        assert.equal(await controls.first().evaluate(el=>el===document.activeElement),true);
        await page.keyboard.press('Escape');
        assert.equal(await dialog.isVisible(),false);
        assert.equal(await page.locator(':focus').getAttribute('id'),'abrirRecuperarSenha');
      }
    }
    await page.locator('[aria-label="Alternar alto contraste"]').click();
    assert.equal(await page.locator('[aria-label="Alternar alto contraste"]').getAttribute('aria-pressed'),'true');
    try {await audit(page,`alto-contraste-${width}`);} catch(e) {errors.push(e.message);}
    await page.locator('[aria-label="Alternar texto ampliado"]').click();
    try {await audit(page,`texto-ampliado-${width}`);} catch(e) {errors.push(e.message);}
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await context.close();
  }
} finally {await browser.close();}
assert.deepEqual(errors,[]);
console.log('Axe WCAG 2.2 A/AA + teclado/reflow nas páginas públicas: aprovado.');
