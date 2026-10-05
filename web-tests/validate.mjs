import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
const root=path.resolve(import.meta.dirname,'..');
const dom=new JSDOM('');globalThis.window=dom.window;globalThis.document=dom.window.document;
const {default:mermaid}=await import('mermaid');mermaid.initialize({startOnLoad:false});
const diagram=fs.readFileSync(path.join(root,'docs/diagrama_talentix.mmd'),'utf8');
assert.ok(diagram.startsWith('classDiagram'));await mermaid.parse(diagram);
let count=0;
for(const name of fs.readdirSync(path.join(root,'html')).filter(n=>n.endsWith('.html'))) {
  const file=path.join(root,'html',name),page=new JSDOM(fs.readFileSync(file,'utf8')).window.document;
  const ids=[...page.querySelectorAll('[id]')].map(el=>el.id);assert.equal(new Set(ids).size,ids.length,'IDs duplicados em '+name);
  for(const el of page.querySelectorAll('script[src],link[rel="stylesheet"],img[src]')) {
    const value=el.getAttribute('src') || el.getAttribute('href');if(/^https?:|^data:/.test(value))continue;
    const local=path.resolve(path.dirname(file),value.split(/[?#]/)[0]);assert.ok(local.startsWith(root+path.sep));assert.ok(fs.existsSync(local),`${name}: recurso ausente ${value}`);
  }
  count++;
}
console.log(`Diagrama Mermaid válido; ${count} páginas sem IDs duplicados ou recursos locais ausentes.`);
