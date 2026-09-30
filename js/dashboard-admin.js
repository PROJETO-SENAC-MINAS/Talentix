document.addEventListener('DOMContentLoaded', async () => {
  const {$, esc, safeUrl, api, toast, bindTabs, bindLogout, bindCommunication} = Talentix;
  let courses = [];
  const run = fn => async event => { try { await fn(event); } catch(error) { toast(error.message,true); } };
  bindLogout(); bindCommunication();
  async function metrics() {
    const data = await api('/dashboard/admin');
    const labels = {total_usuarios:'Usuários',total_candidatos:'Candidatos',total_empresas:'Empresas',total_vagas_ativas:'Vagas publicadas',total_candidaturas:'Candidaturas',denuncias_abertas:'Denúncias abertas',assinaturas_ativas:'Assinaturas ativas'};
    $('#metricasAdmin').innerHTML = Object.entries(data).map(([key,value]) => `<div class="card metric">${esc(labels[key])}<strong>${esc(value)}</strong></div>`).join('');
  }
  async function companies() { const data = await api('/empresas'); $('#empresasAdmin').innerHTML = data.length ? data.map(e => `<article class="list-item"><div><h3>${esc(e.NomeFantasia || e.RazaoSocial)}</h3><p>${esc(e.Cnpj)} · ${esc(e.Setor)}</p></div>${e.Verificada ? '<span class="badge">Verificada</span>' : `<button class="btn btn-primary" data-verificar="${esc(e.ID_Empresas)}">Verificar empresa</button>`}</article>`).join('') : '<p class="empty-state">Nenhuma empresa cadastrada.</p>'; }
  async function reports() { const data = await api('/denuncias'); const labels = {1:'Aberta',2:'Em análise',3:'Resolvida',4:'Rejeitada'}; $('#denunciasAdmin').innerHTML = data.length ? data.map(d => `<article class="list-item"><div class="list-item__main"><h3>${esc(d.Motivo)}</h3><p>${esc(d.Descricao)}</p><span class="badge">${esc(labels[d.ID_Status_Denuncia])}</span></div>${[1,2].includes(d.ID_Status_Denuncia) ? `<div class="inline-actions"><button class="btn btn-primary" data-denuncia="${esc(d.ID_Denuncias)}" data-status="3">Resolver</button><button class="btn btn-secondary" data-denuncia="${esc(d.ID_Denuncias)}" data-status="4">Rejeitar</button></div>` : ''}</article>`).join('') : '<p class="empty-state">Nenhuma denúncia.</p>'; }
  async function catalog() {
    const [data,languages] = await Promise.all([api('/cursos'),api('/idiomas')]); courses = data;
    $('#cursosAdmin').innerHTML = data.length ? data.map(c => `<article class="list-item"><div><h3>${esc(c.Titulo)}</h3><p>${esc(c.Plataforma)} · ${esc(c.Categoria)}</p>${c.Url ? `<a href="${esc(safeUrl(c.Url))}" target="_blank" rel="noopener">Abrir curso</a>` : ''}</div><div class="inline-actions"><button class="btn btn-secondary" data-editar-curso="${esc(c.ID_Cursos)}">Editar</button><button class="btn-danger-ghost" data-excluir-curso="${esc(c.ID_Cursos)}">Desativar</button></div></article>`).join('') : '<p class="empty-state">Nenhum curso cadastrado.</p>';
    $('#idiomasAdmin').textContent = languages.map(l => l.Nome).join(', ') || 'Nenhum idioma cadastrado.';
  }
  async function contacts() { const data = await api('/contato'); $('#contatosAdmin').innerHTML = data.length ? data.map(c => `<article class="list-item"><div class="list-item__main"><h3>${esc(c.Assunto)}</h3><p>${esc(c.Nome)} · ${esc(c.Email)}</p><p>${esc(c.Mensagem)}</p></div>${c.Lido ? '<span class="badge">Lido</span>' : `<button class="btn btn-secondary" data-contato="${esc(c.ID_Contatos)}">Marcar como lido</button>`}</article>`).join('') : '<p class="empty-state">Nenhuma mensagem de contato.</p>'; }
  bindTabs(async tab => { const functions = {metricas:metrics,empresas:companies,denuncias:reports,catalogo:catalog,contatos:contacts,notificacoes:Talentix.notifications,mensagens:Talentix.messages}; await functions[tab]?.(); });
  $('#empresasAdmin').addEventListener('click', run(async event => { if (!event.target.dataset.verificar) return; await api(`/empresas/${event.target.dataset.verificar}/verificar`,{method:'PATCH'}); await companies(); toast('Empresa verificada.'); }));
  $('#denunciasAdmin').addEventListener('click', run(async event => { if (!event.target.dataset.denuncia) return; await api(`/denuncias/${event.target.dataset.denuncia}/resolver`,{method:'PATCH',body:JSON.stringify({id_status_denuncia:Number(event.target.dataset.status)})}); await reports(); toast('Denúncia atualizada.'); }));
  $('#contatosAdmin').addEventListener('click', run(async event => { if (!event.target.dataset.contato) return; await api(`/contato/${event.target.dataset.contato}/marcar-lido`,{method:'PATCH'}); await contacts(); }));
  $('#limparCurso').addEventListener('click', () => { $('#formCursoAdmin').reset(); $('#cursoId').value = ''; });
  $('#formCursoAdmin').addEventListener('submit', run(async event => {
    event.preventDefault(); const data = {titulo:$('#cursoTitulo').value.trim(),descricao:$('#cursoDescricao').value || null,plataforma:$('#cursoPlataforma').value || null,categoria:$('#cursoCategoria').value || null,url:$('#cursoUrl').value || null}; const id = $('#cursoId').value;
    await api(id ? `/cursos/${id}` : '/cursos', {method:id ? 'PUT' : 'POST',body:JSON.stringify(data)}); $('#formCursoAdmin').reset(); $('#cursoId').value=''; await catalog(); toast('Curso salvo.');
  }));
  $('#cursosAdmin').addEventListener('click', run(async event => {
    if (event.target.dataset.editarCurso) { const c = courses.find(c => c.ID_Cursos === event.target.dataset.editarCurso); $('#cursoId').value = c.ID_Cursos; for (const [input,key] of [['cursoTitulo','Titulo'],['cursoDescricao','Descricao'],['cursoPlataforma','Plataforma'],['cursoCategoria','Categoria'],['cursoUrl','Url']]) $(`#${input}`).value=c[key] || ''; $('#cursoTitulo').focus(); }
    if (event.target.dataset.excluirCurso) { await api(`/cursos/${event.target.dataset.excluirCurso}`,{method:'DELETE'}); await catalog(); }
  }));
  $('#formIdiomaAdmin').addEventListener('submit', run(async event => { event.preventDefault(); await api('/idiomas',{method:'POST',body:JSON.stringify({nome:$('#idiomaNome').value.trim()})}); $('#formIdiomaAdmin').reset(); await catalog(); toast('Idioma adicionado.'); }));
  try { const user = await api('/auth/me'); if (user.tipo_usuario !== 'administrador') { window.location.assign('login.html'); return; } $('#userName').textContent=user.Nome; $('#userAvatar').textContent=user.Nome.charAt(0); await metrics(); } catch(error) { toast(error.message,true); }
});
