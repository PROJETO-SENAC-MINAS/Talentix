document.addEventListener('DOMContentLoaded', async () => {
  const {$, esc, safeUrl, api, toast, bindTabs, bindLogout, bindCommunication} = Talentix;
  let user, company, jobs = [], recruiters = [], current = null, status = [], editedSkills = [];
  const role = document.body.dataset.painel;
  const run = fn => async event => { try { await fn(event); } catch(error) { toast(error.message, true); } };
  const labels = {1:'Rascunho',2:'Publicada',3:'Pausada',4:'Encerrada',5:'Cancelada'};
  const interviewLabels = {1:'Agendada',2:'Realizada',3:'Reagendada',4:'Cancelada',5:'Não compareceu'};
  bindLogout(); bindCommunication();

  async function voltarAdministracao() {
    await api('/auth/alternar-modo', {
      method:'POST',
      body:JSON.stringify({modo_usuario:false}),
    });
    window.location.assign('dashboard-admin.html');
  }
  bindTabs(async tab => {
    if (tab === 'vagas') await loadJobs();
    if (tab === 'candidaturas') await loadApplications();
    if (tab === 'recrutadores') await loadRecruiters();
    if (tab === 'notificacoes') await Talentix.notifications();
    if (tab === 'mensagens') await Talentix.messages();
  });
  async function loadMetrics() {
    const data = await api(`/dashboard/empresa/${company.ID_Empresas}`);
    $('#metricasEmpresa').innerHTML = [['Vagas',data.total_vagas],['Publicadas',data.vagas_publicadas],['Candidaturas',data.total_candidaturas_recebidas]].map(([name,value]) => `<div class="card metric">${esc(name)}<strong>${esc(value)}</strong></div>`).join('');
  }
  async function loadJobs() {
    jobs = await api(`/vagas?id_empresa=${company.ID_Empresas}&apenas_publicadas=false`);
    $('#listaVagasEmpresa').innerHTML = jobs.length ? jobs.map(v => `<article class="list-item"><div class="list-item__main"><h2 class="list-item__heading">${esc(v.Titulo)}</h2><p>${esc(v.Modalidade)} · ${esc(v.Localizacao)}</p><span class="badge">${esc(labels[v.ID_Status_Vaga])}</span></div><div class="list-item__actions"><button class="btn btn-secondary" data-editar="${esc(v.ID_Vagas)}">Editar</button>${v.ID_Status_Vaga !== 2 ? `<button class="btn btn-primary" data-acao="publicar" data-vaga="${esc(v.ID_Vagas)}">Publicar</button>` : `<button class="btn btn-secondary" data-acao="pausar" data-vaga="${esc(v.ID_Vagas)}">Pausar</button>`}${v.ID_Status_Vaga !== 4 ? `<button class="btn btn-secondary" data-acao="encerrar" data-vaga="${esc(v.ID_Vagas)}">Encerrar</button>` : ''}<button class="btn-danger-ghost" data-acao="excluir" data-vaga="${esc(v.ID_Vagas)}">Excluir</button></div></article>`).join('') : '<p class="empty-state">Crie a primeira vaga da empresa.</p>';
    const selected = $('#filtroVagaEmpresa').value;
    $('#filtroVagaEmpresa').innerHTML = '<option value="">Todas as vagas</option>' + jobs.map(v => `<option value="${esc(v.ID_Vagas)}">${esc(v.Titulo)}</option>`).join('');
    $('#filtroVagaEmpresa').value = selected;
  }
  async function editJob(job = {}) {
    if (job.ID_Vagas) job = await api(`/vagas/${job.ID_Vagas}`);
    editedSkills = job.habilidades || [];
    $('#formVagaEmpresa').reset(); $('#vagaId').value = job.ID_Vagas || ''; $('#tituloModalVaga').textContent = job.ID_Vagas ? 'Editar vaga' : 'Criar vaga';
    for (const [input, key] of [['vagaTitulo','Titulo'],['vagaDescricao','Descricao'],['vagaModalidade','Modalidade'],['vagaNivel','Nivel'],['vagaContrato','TipoContrato'],['vagaLocal','Localizacao'],['vagaSalarioMin','SalarioMin'],['vagaSalarioMax','SalarioMax']]) if (job[key] != null) $(`#${input}`).value = job[key];
    $('#vagaHabilidades').value = editedSkills.map(h=>h.NomeHabilidade).join(', ');
    $('#vagaConfidencial').checked = Boolean(job.SalarioConfidencial); $('#modalVagaEmpresa').showModal();
  }
  $('#novaVaga').addEventListener('click', run(async () => editJob()));
  $('#fecharVagaEmpresa').addEventListener('click', () => $('#modalVagaEmpresa').close());
  $('#formVagaEmpresa').addEventListener('submit', run(async event => {
    event.preventDefault(); const button = event.submitter; button.disabled = true;
    try {
      const data = {titulo:$('#vagaTitulo').value.trim(),descricao:$('#vagaDescricao').value.trim(),modalidade:$('#vagaModalidade').value,nivel:$('#vagaNivel').value,tipo_contrato:$('#vagaContrato').value || null,localizacao:$('#vagaLocal').value || null,salario_min:$('#vagaSalarioMin').value || null,salario_max:$('#vagaSalarioMax').value || null,salario_confidencial:$('#vagaConfidencial').checked};
      const id = $('#vagaId').value; if (!id) data.id_empresa = company.ID_Empresas;
      const names = [...new Map($('#vagaHabilidades').value.split(',').map(n=>n.trim()).filter(Boolean).map(n=>[n.toLowerCase(),n])).values()];
      if (names.some(n=>n.length>100) || names.length>30) throw new Error('Use até 30 habilidades, com no máximo 100 caracteres por nome.');
      const saved = await api(id ? `/vagas/${id}` : '/vagas', {method:id ? 'PUT' : 'POST', body:JSON.stringify(data)});
      $('#vagaId').value = saved.ID_Vagas;
      for (const previous of [...editedSkills]) {
        if (!names.some(n=>n.toLowerCase()===previous.NomeHabilidade.toLowerCase())) {
          await api(`/vagas/${saved.ID_Vagas}/habilidades/${previous.ID_Vaga_Habilidades}`, {method:'DELETE'});
          editedSkills = editedSkills.filter(h=>h.ID_Vaga_Habilidades !== previous.ID_Vaga_Habilidades);
        }
      }
      for (const name of names) {
        if (editedSkills.some(h=>h.NomeHabilidade.toLowerCase()===name.toLowerCase())) continue;
        const skill = await api('/habilidades', {method:'POST',body:JSON.stringify({nome:name})});
        const linked = await api(`/vagas/${saved.ID_Vagas}/habilidades`, {method:'POST',body:JSON.stringify({id_habilidade:skill.ID_Habilidades,obrigatoria:true,peso:1})});
        editedSkills.push({...linked,NomeHabilidade:skill.Nome});
      }
      if (!id) {
        await api(`/vagas/${saved.ID_Vagas}/publicar`, {method:'PATCH'});
      }
      $('#modalVagaEmpresa').close();
      await Promise.all([loadJobs(),loadMetrics()]);
      toast(id ? 'Vaga salva.' : 'Vaga criada e publicada para os candidatos.');
    } finally { button.disabled = false; }
  }));
  $('#listaVagasEmpresa').addEventListener('click', run(async event => {
    const button = event.target.closest('button'); if (!button) return;
    if (button.dataset.editar) { await editJob(jobs.find(v => v.ID_Vagas === button.dataset.editar)); return; }
    if (!button.dataset.acao) return;
    if (button.dataset.acao === 'excluir' && !window.confirm('Excluir esta vaga da listagem? O histórico será preservado.')) return;
    button.disabled = true;
    try { await api(`/vagas/${button.dataset.vaga}${button.dataset.acao === 'excluir' ? '' : '/'+button.dataset.acao}`, {method:button.dataset.acao === 'excluir' ? 'DELETE' : 'PATCH'}); await Promise.all([loadJobs(),loadMetrics()]); toast('Vaga atualizada.'); } finally { button.disabled = false; }
  }));
  async function loadApplications() {
    const filter = $('#filtroVagaEmpresa').value;
    const records = await api('/candidaturas' + (filter ? `?id_vaga=${filter}` : ''));
    $('#listaCandidaturasEmpresa').innerHTML = records.length ? records.map(c => `<article class="list-item"><div class="list-item__main"><h2 class="list-item__heading">${esc(c.NomeCandidato)}</h2><p>${esc(c.TituloVaga)}</p><span class="badge">${esc(status.find(s => s.ID_Status_Candidatura === c.ID_Status_Candidatura)?.Descricao)}</span><p>${c.CurriculoUrl ? `<a href="${esc(safeUrl(c.CurriculoUrl))}" target="_blank" rel="noopener">Abrir currículo anexado</a>` : 'Nenhum currículo anexado.'}</p></div><div class="list-item__actions"><button class="btn btn-primary" data-processo="${esc(c.ID_Candidaturas)}">Ver processo</button><button class="btn btn-secondary" data-conversar="${esc(c.ID_Usuario_Candidato)}" data-contexto="${esc(c.ID_Candidaturas)}">Mensagem</button></div></article>`).join('') : '<p class="empty-state">Ainda não há candidaturas.</p>';
  }
  $('#filtroVagaEmpresa').addEventListener('change', run(loadApplications));
  $('#listaCandidaturasEmpresa').addEventListener('click', run(async event => {
    const button = event.target.closest('button'); if (!button) return;
    if (button.dataset.processo) await openProcess(button.dataset.processo);
    if (button.dataset.conversar) await Talentix.conversation(button.dataset.conversar, button.dataset.contexto);
  }));
  async function openProcess(id, abrir = true) {
    current = await api(`/candidaturas/${id}`); await loadRecruiters();
    const [profile, experiences, skills] = await Promise.all([api(`/candidatos/${current.ID_Candidatos}`),api(`/candidatos/${current.ID_Candidatos}/experiencias`),api(`/candidatos/${current.ID_Candidatos}/habilidades`)]);
    $('#processoPerfil').innerHTML = `<h3>${esc(profile.TituloProfissional || 'Perfil do candidato')}</h3><p>${esc(profile.Resumo)}</p><p>${esc(skills.map(h => h.NomeHabilidade).join(', '))}</p>${experiences.map(e => `<p>${esc(e.Cargo)} — ${esc(e.Empresa)}</p>`).join('')}${current.CurriculoUrl ? `<p><a href="${esc(safeUrl(current.CurriculoUrl))}" target="_blank" rel="noopener">Currículo anexado</a></p>` : ''}${current.CartaApresentacao ? `<p>${esc(current.CartaApresentacao)}</p>` : ''}`;
    $('#processoStatus').innerHTML = status.map(s => `<option value="${s.ID_Status_Candidatura}">${esc(s.Descricao)}</option>`).join(''); $('#processoStatus').value = current.ID_Status_Candidatura;
    $('#processoEtapas').innerHTML = current.etapas.map(e => `<article class="list-item"><div>${esc(e.Ordem)}. ${esc(e.Nome)} <span class="badge">${e.ID_Status_Etapa === 3 ? 'Concluída' : 'Em andamento'}</span></div><button class="btn btn-secondary" data-etapa="${esc(e.ID_Etapas_Processo)}" data-etapa-acao="${e.ID_Status_Etapa === 3 ? 'reabrir' : 'concluir'}">${e.ID_Status_Etapa === 3 ? 'Reabrir' : 'Concluir'}</button></article>`).join('');
    $('#processoEntrevistas').innerHTML = current.entrevistas.length ? current.entrevistas.map(e => `<article class="list-item"><div><p>${esc(e.DataHora)} · ${esc(interviewLabels[e.ID_Status_Entrevista])}</p><p>${esc(e.LocalOuLink)}</p></div><div class="inline-actions">${[1,3].includes(e.ID_Status_Entrevista) ? `<button class="btn btn-secondary" data-entrevista="${esc(e.ID_Entrevistas)}" data-entrevista-acao="realizar">Marcar realizada</button><button class="btn-danger-ghost" data-entrevista="${esc(e.ID_Entrevistas)}" data-entrevista-acao="cancelar">Cancelar</button>` : ''}</div></article>`).join('') : '<p>Nenhuma entrevista agendada.</p>';
    $('#entrevistaRecrutador').innerHTML = recruiters.length ? recruiters.map(r => `<option value="${esc(r.ID_Recrutadores)}">${esc(r.Cargo || 'Recrutador')} · ${esc(r.ID_Usuarios)}</option>`).join('') : '<option value="">Adicione um recrutador na aba Equipe</option>';
    if (abrir) $('#modalProcesso').showModal();
  }
  $('#fecharProcesso').addEventListener('click', () => $('#modalProcesso').close());
  $('#salvarStatus').addEventListener('click', run(async () => { await api(`/candidaturas/${current.ID_Candidaturas}/status?id_status_candidatura=${$('#processoStatus').value}`, {method:'PATCH'}); await openProcess(current.ID_Candidaturas, false); await loadApplications(); toast('Status atualizado.'); }));
  $('#formEtapa').addEventListener('submit', run(async event => { event.preventDefault(); await api(`/candidaturas/${current.ID_Candidaturas}/etapas`, {method:'POST',body:JSON.stringify({nome:$('#etapaNome').value.trim(),ordem:Math.max(...current.etapas.map(e=>e.Ordem),0)+1})}); $('#formEtapa').reset(); await openProcess(current.ID_Candidaturas, false); }));
  $('#processoEtapas').addEventListener('click', run(async event => { if (!event.target.dataset.etapa) return; await api(`/etapas/${event.target.dataset.etapa}/${event.target.dataset.etapaAcao}`, {method:'PATCH'}); await openProcess(current.ID_Candidaturas, false); }));
  $('#formEntrevista').addEventListener('submit', run(async event => { event.preventDefault(); await api(`/candidaturas/${current.ID_Candidaturas}/entrevistas`, {method:'POST',body:JSON.stringify({id_recrutador:$('#entrevistaRecrutador').value,data_hora:$('#entrevistaData').value,tipo:'Entrevista',local_ou_link:$('#entrevistaLocal').value || null})}); $('#formEntrevista').reset(); await openProcess(current.ID_Candidaturas, false); toast('Entrevista agendada.'); }));
  $('#processoEntrevistas').addEventListener('click', run(async event => { if (!event.target.dataset.entrevista) return; await api(`/entrevistas/${event.target.dataset.entrevista}/${event.target.dataset.entrevistaAcao}`, {method:'PATCH'}); await openProcess(current.ID_Candidaturas, false); }));
  async function loadRecruiters() {
    recruiters = await api(`/empresas/${company.ID_Empresas}/recrutadores`);
    $('#listaRecrutadores').innerHTML = recruiters.length ? recruiters.map(r => `<article class="list-item"><div><h2 class="list-item__heading">${esc(r.Cargo || 'Recrutador')}</h2><p>${esc(r.ID_Usuarios)}</p></div>${user.tipo_usuario === 'empresa' ? `<button class="btn-danger-ghost" data-remover-recrutador="${esc(r.ID_Recrutadores)}">Remover vínculo</button>` : ''}</article>`).join('') : '<p class="empty-state">Nenhum recrutador vinculado.</p>';
  }
  $('#formRecrutador').addEventListener('submit', run(async event => { event.preventDefault(); await api(`/empresas/${company.ID_Empresas}/recrutadores`, {method:'POST',body:JSON.stringify({id_usuario_recrutador:$('#recrUsuario').value.trim(),cargo:$('#recrCargo').value || null})}); await loadRecruiters(); toast('Recrutador adicionado.'); }));
  $('#listaRecrutadores').addEventListener('click', run(async event => { if (!event.target.dataset.removerRecrutador) return; await api(`/recrutadores/${event.target.dataset.removerRecrutador}`, {method:'DELETE'}); await loadRecruiters(); toast('Vínculo removido.'); }));
  $('#formEmpresa').addEventListener('submit', run(async event => { event.preventDefault(); await api(`/empresas/${company.ID_Empresas}`, {method:'PUT',body:JSON.stringify({nome_fantasia:$('#empresaNome').value || null,descricao:$('#empresaDescricao').value || null,setor:$('#empresaSetor').value || null,site_url:$('#empresaSite').value || null,endereco:$('#empresaEndereco').value || null})}); toast('Perfil atualizado.'); }));
  try {
    user = await api('/auth/me');
    if (user.tipo_usuario !== role) { window.location.assign(user.tipo_usuario === 'recrutador' ? 'dashboard-recrutador.html' : user.tipo_usuario === 'empresa' ? 'dashboard-empresa.html' : 'login.html'); return; }
    company = await api('/empresas/me'); status = await api('/dominios/status-candidatura');
    $('#userName').textContent = user.Nome; $('#userAvatar').textContent = user.Nome.charAt(0); $('#tituloEmpresa').textContent = company.NomeFantasia || company.RazaoSocial;
    const btnModoAdmin = $('#btnModoAdmin');
    const adminEmModoUsuario = user.tipo_principal === 'administrador' && user.modo_usuario;
    if (btnModoAdmin) {
      btnModoAdmin.hidden = !adminEmModoUsuario;
      btnModoAdmin.onclick = adminEmModoUsuario
        ? () => voltarAdministracao().catch(error => toast(error.message, true))
        : null;
    }
    for (const [input,key] of [['empresaNome','NomeFantasia'],['empresaDescricao','Descricao'],['empresaSetor','Setor'],['empresaSite','SiteUrl'],['empresaEndereco','Endereco']]) $(`#${input}`).value = company[key] || '';
    $('#recrUsuario').value = user.ID_Usuarios;
    if (user.tipo_usuario === 'recrutador') { document.querySelectorAll('[data-responsavel]').forEach(el=>el.hidden=true); $('#formEmpresa').querySelectorAll('input,textarea').forEach(el=>el.readOnly=true); }
    await Promise.all([loadMetrics(),loadJobs()]);
  } catch(error) { toast(error.message, true); }
});
