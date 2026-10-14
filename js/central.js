document.addEventListener('DOMContentLoaded', () => {
  'use strict';
  const {$, esc, safeUrl, api, toast, bindTabs, bindLogout} = Talentix;
  let user, context, processes = [], interviews = [], templates = [], members = [], rules = [], jobs = [], editing, publicationVersion = 1;
  let agendaKey = crypto.randomUUID(), batchKey = crypto.randomUUID();
  const roleNames = {owner:'Owner',rh_admin:'Administrador de RH',recrutador:'Recrutador',hiring_manager:'Hiring Manager',entrevistador:'Entrevistador'};
  const orgId = () => $('#organizacao').value;
  const query = () => orgId() ? '?id_empresa=' + encodeURIComponent(orgId()) : '';
  const staff = () => !!context;
  const allowed = p => context?.permissoes.includes(p);
  const send = (p, method, data) => api(p, {method, ...(data === undefined ? {} : {body:JSON.stringify(data)})});
  const opt = (rows, key, name, empty = 'Selecione') => `<option value="">${esc(empty)}</option>` + rows.map(r => `<option value="${esc(r[key])}">${esc(r[name])}</option>`).join('');
  const noData = text => `<p class="empty-state">${esc(text)}</p>`;
  const card = (title, text, actions = '') => `<article class="list-item"><div class="list-item__main"><h3>${esc(title)}</h3><p>${esc(text)}</p></div><div class="list-item__actions">${actions}</div></article>`;
  const date = (value, zone) => { try { return new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short',timeZone:zone || 'America/Sao_Paulo'}).format(new Date(value)); } catch {return String(value || '');} };
  const guard = fn => async event => {
    if (event?.type === 'submit') event.preventDefault();
    const button = event?.submitter || (event?.currentTarget?.tagName === 'BUTTON' ? event.currentTarget : null);
    if (button) button.disabled = true;
    $('#centralErro').textContent = ''; $('#centralEstado').textContent = 'Processando…';
    try {await fn(event); $('#centralEstado').textContent = 'Dados atualizados.';}
    catch (error) {$('#centralErro').textContent = error.message; $('#centralEstado').textContent = ''; toast(error.message, true);}
    finally {if (button) button.disabled = false;}
  };
  const on = (selector, type, fn) => $(selector).addEventListener(type, guard(fn));
  bindLogout();
  bindTabs(tab => guard(() => loadTab(tab))());
  async function download(path, filename) {
    const response = await fetch(API_BASE_URL + path, {credentials:'include'});
    if (!response.ok) throw Error((await response.json().catch(() => null))?.detail || 'Não foi possível exportar.');
    const url = URL.createObjectURL(await response.blob()), a = document.createElement('a');
    a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
  }
  async function initialize() {
    const organizations = await api('/organizacoes', {headers:{'X-Organization-ID':''}});
    user = await api('/auth/me', {headers:{'X-Organization-ID':''}});
    $('#centralUsuario').textContent = user.Nome + ' · ' + user.tipo_usuario;
    $('#voltarPainel').href = user.tipo_usuario === 'usuario' ? 'dashboard.html' : 'dashboard-' + (user.tipo_usuario === 'administrador' ? 'admin' : user.tipo_usuario) + '.html';
    let list = organizations;
    if (user.tipo_usuario === 'administrador') list = (await api('/empresas')).map(e => ({...e,Papel:'administrador'}));
    $('#organizacao').innerHTML = '<option value="">Perfil pessoal</option>' + list.map(o => `<option value="${esc(o.ID_Empresas)}">${esc(o.NomeFantasia || o.RazaoSocial)} · ${esc(roleNames[o.Papel] || o.Papel)}</option>`).join('');
    const saved = localStorage.getItem('talentix_organizacao');
    if (saved && list.some(o => o.ID_Empresas === saved)) $('#organizacao').value = saved;
    else if (['empresa','recrutador'].includes(user.tipo_usuario) && list.length) $('#organizacao').value = list[0].ID_Empresas;
    else localStorage.removeItem('talentix_organizacao');
    $('#navAuditoria').hidden = user.tipo_usuario !== 'administrador';
    await selectOrganization();
  }
  async function selectOrganization() {
    context = null;
    if (orgId()) {localStorage.setItem('talentix_organizacao', orgId()); context = await api('/organizacoes/contexto' + query());}
    else localStorage.removeItem('talentix_organizacao');
    $('#papelAtivo').textContent = context ? roleNames[context.papel] + ' · ' + (context.empresa.NomeFantasia || context.empresa.RazaoSocial) : 'Dados e preferências do seu perfil pessoal';
    document.querySelectorAll('[data-permissao]').forEach(el => el.hidden = !allowed(el.dataset.permissao));
    document.querySelector('[data-tab="comunicacao"]').hidden = staff() && !allowed('comunicacao');
    $('#formAgenda').hidden = !allowed('entrevistas'); $('#abrirAts').hidden = !allowed('ler'); $('#comEquipe').hidden = !allowed('comunicacao');
    $('#abrirAts').href = 'ats.html' + (user.tipo_usuario === 'administrador' ? '?empresa=' + encodeURIComponent(orgId()) : '');
    await loadProcesses();
    document.querySelector('.nav-item[data-tab="processos"]').click();
  }
  async function loadProcesses() {
    processes = (staff() || user.tipo_usuario === 'candidato') && (!staff() || allowed('ler')) ? await api('/comunicacao/candidaturas' + query()) : [];
    $('#processosCentral').innerHTML = processes.map(p => card(p.Titulo, (staff() ? p.Nome + ' · ' : '') + 'Status ' + p.ID_Status_Candidatura,
      (!staff() || allowed('comunicacao')) ? `<button type="button" class="btn btn-secondary" data-conversar="${esc(p.ID_Candidaturas)}">Abrir comunicação</button>` : '')).join('') || noData('Nenhum processo disponível neste contexto.');
    $('#resumoCentral').innerHTML = `<article class="card metric"><span>Processos disponíveis</span><strong>${processes.length}</strong></article><article class="card metric"><span>Decisões de contratação</span><strong>Humanas</strong></article>`;
    for (const id of ['#agendaProcesso','#comProcesso','#iaProcesso']) $(id).innerHTML = opt(processes,'ID_Candidaturas','Titulo');
    $('#loteProcessos').innerHTML = '<legend>Processos destinatários</legend>' + processes.map((p,i) => `<label class="checkbox-row" for="lote-${i}"><input id="lote-${i}" type="checkbox" value="${esc(p.ID_Candidaturas)}"> ${esc(p.Nome)} · ${esc(p.Titulo)}</label>`).join('');
    $('#formConversa').hidden = !processes.length; $('#formAnexo').hidden = !processes.length;
    if (staff() && allowed('ler')) {
      const tasks = await api('/automacoes/registros/tarefas' + query());
      $('#tarefasCentral').innerHTML = tasks.map(t => card(t.Titulo,t.Concluida ? 'Concluída' : 'Pendente',t.Concluida || !allowed('processos') ? '' : `<button type="button" class="btn btn-secondary" data-task="${esc(t.ID_Tarefa)}">Concluir tarefa</button>`)).join('') || noData('Nenhuma tarefa.');
      jobs = await api('/vagas?apenas_publicadas=false');
      $('#analyticsVaga').innerHTML = opt(jobs,'ID_Vagas','Titulo','Todas');
      $('#publicoVaga').innerHTML = opt(jobs.filter(v => v.ID_Status_Vaga === 2),'ID_Vagas','Titulo');
      const recruiters = await api('/empresas/' + encodeURIComponent(orgId()) + '/recrutadores');
      $('#agendaRecrutador').innerHTML = opt(recruiters.map(r => ({...r,label:r.Cargo || r.ID_Usuarios})),'ID_Recrutadores','label');
      $('#analyticsResponsavel').innerHTML = opt(recruiters.map(r => ({...r,label:r.Cargo || r.ID_Usuarios})),'ID_Usuarios','label','Todos');
    } else {$('#tarefasCentral').innerHTML = noData('Tarefas são exibidas no contexto da organização.'); jobs = [];}
  }
  async function loadAgenda() {
    if (!staff() && user.tipo_usuario !== 'candidato') {$('#agendaLista').innerHTML = noData('Selecione uma organização para consultar a agenda.'); return;}
    interviews = await api('/agenda' + query());
    $('#agendaLista').innerHTML = interviews.map(en => card(en.Titulo,date(en.DataHoraUtc,en.Fuso) + ' · ' + en.Fuso + ' · ' + en.DuracaoMin + ' min\n' + (en.LocalOuLink || '') + '\nStatus: ' + ({1:'Agendada',2:'Realizada',3:'Reagendada',4:'Cancelada'}[en.ID_Status_Entrevista] || en.ID_Status_Entrevista),
      allowed('entrevistas') && [1,3].includes(en.ID_Status_Entrevista) ? ['reagendar','cancelar','realizar'].map(acao => `<button type="button" class="btn btn-secondary" data-interview="${esc(en.ID_Entrevistas)}" data-acao="${acao}">${acao === 'reagendar' ? 'Reagendar' : acao === 'cancelar' ? 'Cancelar' : 'Marcar realizada'}</button>`).join('') : '')).join('') || noData('Nenhuma entrevista registrada.');
  }
  async function loadTimeline() {
    if (!$('#comProcesso').value) {$('#timelineCentral').innerHTML = noData('Selecione um processo.');return;}
    const items = await api('/comunicacao/candidaturas/' + encodeURIComponent($('#comProcesso').value) + '/timeline');
    $('#timelineCentral').innerHTML = items.map(x => card(x.tipo + ' · ' + date(x.data),x.texto,
      x.tipo === 'anexo' ? `<button type="button" class="btn btn-secondary" data-attachment="${esc(x.url)}">Baixar anexo</button>` : x.tipo === 'mensagem' && !x.lida && x.remetente !== user.ID_Usuarios ? `<button type="button" class="btn btn-secondary" data-read="${esc(x.id)}">Marcar como lida</button>` : x.tipo === 'mensagem' ? '<span>' + (x.lida ? 'Lida' : 'Enviada') + '</span>' : '')).join('') || noData('Sem eventos.');
  }
  async function loadTemplates() {
    if (!allowed('comunicacao')) return;
    templates = await api('/comunicacao/modelos' + query());
    $('#modeloEscolhido').innerHTML = opt(templates,'ID_Modelo','Nome','Escrever mensagem');
    const batches = await api('/comunicacao/lotes' + query());
    $('#loteResultados').innerHTML = batches.map(b => card(b.Estado,`${b.total} destinatários · ${date(b.CriadoEm)}`)).join('') || noData('Nenhum lote enviado.');
  }
  const analyticsQuery = () => {const q = new URLSearchParams(); if(orgId())q.set('id_empresa',orgId()); for (const [id,key] of [['#analyticsInicio','inicio'],['#analyticsFim','fim'],['#analyticsVaga','id_vaga'],['#analyticsResponsavel','responsavel']]) if($(id).value)q.set(key,$(id).value);return '?' + q;};
  async function loadAnalytics() {
    const d = await api('/analytics' + analyticsQuery());
    const fields = {total_candidaturas:'Candidaturas',aprovadas:'Aprovadas',desistencias:'Desistências',conversao_aprovacao_percentual:'Aprovação (%)',entrevistas_realizadas:'Entrevistas realizadas',dias_ate_aprovacao_media:'Dias até aprovação'};
    $('#analyticsMetricas').innerHTML = Object.entries(fields).map(([k,label]) => `<article class="card metric"><span>${esc(label)}</span><strong>${esc(d[k] ?? 'Sem amostra')}</strong></article>`).join('');
    $('#analyticsEtapas').innerHTML = '<h3>Passagem pelas etapas</h3><div class="central-chart">' + d.etapas.map((r,i) => `<article class="card"><label for="etapa-metrica-${i}">${esc(r.nome)}<small>${esc(r.candidatos_que_passaram)} pessoas · ${esc(r.horas_media_finalizadas ?? 'Sem amostra')} horas</small></label><meter id="etapa-metrica-${i}" min="0" max="${Math.max(1,d.total_candidaturas)}" value="${r.candidatos_que_passaram}">${r.candidatos_que_passaram}</meter></article>`).join('') + '</div>';
    $('#analyticsDefinicoes').innerHTML = Object.values(d.definicoes).map(v => '<p>'+esc(v)+'</p>').join('');
  }
  async function loadTeam() {
    members = await api('/organizacoes/membros' + query());
    $('#membrosCentral').innerHTML = members.map((m,i) => card(m.Nome,m.Email + ' · ' + roleNames[m.Papel] + (m.Ativo ? '' : ' · Inativo'),
      `<label for="papel-membro-${i}">Papel de ${esc(m.Nome)}</label><select id="papel-membro-${i}" data-role-user="${esc(m.ID_Usuarios)}">${Object.entries(roleNames).map(([v,label]) => `<option value="${v}" ${v===m.Papel?'selected':''}>${label}</option>`).join('')}</select><button type="button" class="btn btn-secondary" data-member="${esc(m.ID_Usuarios)}" data-ativo="${!!m.Ativo}">Salvar papel</button><button type="button" class="btn btn-secondary" data-revoke="${esc(m.ID_Usuarios)}">${m.Ativo?'Revogar vínculo':'Reativar vínculo'}</button>`)).join('') || noData('Nenhum membro registrado.');
  }
  async function loadRules() {
    rules = await api('/automacoes' + query());
    $('#regrasCentral').innerHTML = rules.map(r => card(r.Nome,r.Gatilho + ' · ' + r.Acao + ' · ' + (r.Ativa ? 'Ativa' : 'Desativada'),`<button type="button" class="btn btn-secondary" data-rule="${esc(r.ID_Regra)}">${r.Ativa?'Desativar':'Ativar'}</button>`)).join('') || noData('Nenhuma regra criada.');
    const executions = await api('/automacoes/registros/execucoes' + query());
    $('#execucoesCentral').innerHTML = executions.map(x => card(x.Nome,x.Estado + ' · ' + date(x.CriadoEm))).join('') || noData('Nenhuma execução. O worker processa as regras ativas.');
  }
  async function loadPublication() {
    const p = await api('/publicacao/empresa' + query()); publicationVersion = p?.Versao || 1;
    $('#publicoSlug').value = p?.Slug || ''; $('#publicoAtivo').checked = !!p?.Publicada; $('#publicoCultura').value = p?.Cultura || ''; $('#publicoLocal').value = p?.Localizacao || '';
    $('#publicoBeneficios').value = (p?.Beneficios || []).join('\n'); $('#publicoTecnologias').value = (p?.Tecnologias || []).join('\n');
  }
  async function loadPrivacy() {
    const pref = await api('/comunicacao/preferencias'); $('#prefEmail').checked = !!pref.EmailAtivo; $('#prefLotes').checked = !!pref.LotesAtivos;
    const policy = await api('/privacidade/politica-operacional'); $('#politicaCentral').textContent = `Currículos arquivados sem vínculo com candidaturas: retenção de ${policy.retencao_curriculo_arquivado_dias} dias. Exclusão de conta: carência de ${policy.carencia_exclusao_dias} dias. ${policy.retencao_separada}`;
    const requests = await api('/privacidade/solicitacoes'); $('#solicitacoesCentral').innerHTML = requests.map(r => card('Solicitação de ' + r.Tipo,r.Estado + ' · processamento a partir de ' + date(r.ExecutarApos),['pendente','bloqueado'].includes(r.Estado)?`<button type="button" class="btn btn-secondary" data-cancel-request="${esc(r.ID_Solicitacao)}">Cancelar solicitação</button>`:'')).join('') || noData('Nenhuma solicitação.');
  }
  async function loadAudit() {
    const logs = await api('/analytics/auditoria'); $('#auditoriaCentral').innerHTML = logs.map(r => card(r.Acao,`${date(r.CriadoEm)} · ${r.ID_Usuarios || 'Sistema'} · ${r.Recurso} · ${r.IP || 'IP não registrado'}`)).join('') || noData('Nenhum registro.');
    const rows = await api('/publicacao/moderacao'); $('#moderacaoCentral').innerHTML = rows.map(r => card('Avaliação ' + r.Nota + '/5',r.Comentario,['aprovada','rejeitada'].map(estado => `<button type="button" class="btn btn-secondary" data-review="${esc(r.ID_Avaliacao)}" data-estado="${estado}">${estado==='aprovada'?'Aprovar':'Rejeitar'}</button>`).join(''))).join('') || noData('Nenhuma avaliação pendente.');
  }
  async function loadTab(tab) {
    const loaders = {processos:loadProcesses,agenda:loadAgenda,comunicacao:async()=>{await loadTimeline();await loadTemplates();},analytics:loadAnalytics,equipe:loadTeam,automacoes:loadRules,publicacao:loadPublication,privacidade:loadPrivacy,auditoria:loadAudit};
    if (loaders[tab]) await loaders[tab]();
  }
  on('#organizacao','change',selectOrganization); on('#atualizarCentral','click',()=>loadTab(document.querySelector('.nav-item.active[data-tab]')?.dataset.tab || 'processos'));
  on('#processosCentral','click',async event => {const b=event.target.closest('[data-conversar]');if(!b)return;$('#comProcesso').value=b.dataset.conversar;document.querySelector('[data-tab="comunicacao"]').click();await loadTimeline();});
  on('#tarefasCentral','click',async event=>{const b=event.target.closest('[data-task]');if(b){await send('/automacoes/tarefas/'+b.dataset.task+'/concluir','PATCH');await loadProcesses();}});
  on('#formAgenda','submit',async()=>{await send('/agenda','POST',{id_candidatura:$('#agendaProcesso').value,id_recrutador:$('#agendaRecrutador').value,data_hora:$('#agendaData').value,fuso:$('#agendaFuso').value,duracao_min:+$('#agendaDuracao').value,tipo:$('#agendaTipo').value,local_ou_link:$('#agendaLocal').value.trim(),observacoes:$('#agendaNotas').value.trim(),chave:agendaKey});agendaKey=crypto.randomUUID();await loadAgenda();toast('Entrevista registrada.');});
  on('#agendaLista','click',async event=>{const b=event.target.closest('[data-interview]');if(!b)return;const en=interviews.find(r=>r.ID_Entrevistas===b.dataset.interview);if(b.dataset.acao==='reagendar'){editing=en;$('#reagendarData').value='';$('#dialogReagendar').showModal();$('#reagendarData').focus();return;}if(!confirm('Confirmar: '+b.textContent+'?'))return;await send('/agenda/'+en.ID_Entrevistas,'PUT',{acao:b.dataset.acao,versao:en.Versao});await loadAgenda();});
  $('#fecharReagendar').onclick=()=>$('#dialogReagendar').close();
  on('#formReagendar','submit',async()=>{try{await send('/agenda/'+editing.ID_Entrevistas,'PUT',{acao:'reagendar',versao:editing.Versao,data_hora:$('#reagendarData').value,fuso:editing.Fuso});$('#dialogReagendar').close();await loadAgenda();}catch(e){$('#reagendarErro').textContent=e.message;throw e;}});
  on('#carregarTimeline','click',loadTimeline);on('#comProcesso','change',loadTimeline);
  on('#formConversa','submit',async()=>{const p=processes.find(p=>p.ID_Candidaturas===$('#comProcesso').value);if(!p)throw Error('Selecione um processo.');await send('/mensagens','POST',{id_destinatario:staff()?p.CandidatoUsuario:p.EmpresaUsuario,id_candidatura:p.ID_Candidaturas,conteudo:$('#comTexto').value.trim()});$('#comTexto').value='';await loadTimeline();});
  on('#timelineCentral','click',async e=>{const attachment=e.target.closest('[data-attachment]');if(attachment){await download(attachment.dataset.attachment,'anexo.pdf');return;}const b=e.target.closest('[data-read]');if(b){await send('/mensagens/'+b.dataset.read+'/marcar-lida','PATCH');await loadTimeline();}});
  on('#formAnexo','submit',async()=>{if(!$('#comProcesso').value)throw Error('Selecione um processo.');const file=$('#comAnexo').files[0];if(!file || file.size>10*1024*1024 || !file.name.toLowerCase().endsWith('.pdf'))throw Error('Escolha PDF com até 10 MB.');const body=new FormData();body.append('arquivo',file);await api('/comunicacao/candidaturas/'+$('#comProcesso').value+'/anexos',{method:'POST',body});$('#formAnexo').reset();await loadTimeline();});
  on('#formModelo','submit',async()=>{await send('/comunicacao/modelos'+query(),'POST',{nome:$('#modeloNome').value.trim(),conteudo:$('#modeloTexto').value.trim()});$('#formModelo').reset();await loadTemplates();});
  $('#modeloEscolhido').onchange=()=>{$('#loteTexto').value=templates.find(t=>t.ID_Modelo===$('#modeloEscolhido').value)?.Conteudo || '';};
  on('#formLote','submit',async()=>{const ids=[...document.querySelectorAll('#loteProcessos input:checked')].map(x=>x.value);if(!ids.length || ids.length>100)throw Error('Selecione entre 1 e 100 processos.');const r=await send('/comunicacao/lotes'+query(),'POST',{candidaturas:ids,conteudo:$('#loteTexto').value.trim(),chave:batchKey});batchKey=crypto.randomUUID();toast(`${r.enviado ?? 0} enviados; ${r.ignorado ?? 0} ignorados por preferência ou repetição.`);$('#loteConfirmacao').checked=false;await loadTemplates();});
  on('#analisarCentral','click',async()=>{const p=processes.find(p=>p.ID_Candidaturas===$('#iaProcesso').value);if(!p)throw Error('Selecione um processo.');const r=await send('/inteligencia/analises','POST',{id_candidato:p.ID_Candidatos,id_vaga:p.ID_Vagas});$('#iaResultado').innerHTML=card('Correspondência: '+r.score+' / 100',r.limites)+card('Habilidades atendidas',r.fortes.join(', ') || 'Nenhuma informada')+card('Lacunas',r.lacunas.join(', ') || 'Sem lacunas nas habilidades declaradas')+card('Critérios',`Modelo ${r.modelo} · ${r.fatores.pesos.habilidades}% habilidades · ${r.fatores.pesos.texto}% similaridade textual`)+card('Orientações',r.orientacoes.join('\n') || 'Revise os dados do perfil e os requisitos com o RH.')+card('Preparação para entrevista',r.perguntas_entrevista.join('\n'));});
  on('#formAnalytics','submit',loadAnalytics);on('#csvAnalytics','click',()=>download('/analytics/exportar/csv'+analyticsQuery(),'talentix-analytics.csv'));on('#pdfAnalytics','click',()=>download('/analytics/exportar/pdf'+analyticsQuery(),'talentix-analytics.pdf'));
  on('#formConvite','submit',async()=>{const r=await send('/organizacoes/convites'+query(),'POST',{email:$('#conviteEmail').value,papel:$('#convitePapel').value});$('#conviteCodigo').textContent='Código de uso único, válido por 7 dias: '+r.token;});
  on('#membrosCentral','click',async e=>{const b=e.target.closest('[data-member],[data-revoke]');if(!b)return;const m=members.find(m=>m.ID_Usuarios===(b.dataset.member || b.dataset.revoke));const select=[...document.querySelectorAll('[data-role-user]')].find(x=>x.dataset.roleUser===m.ID_Usuarios);if(!confirm('Confirmar alteração de permissões de '+m.Nome+'?'))return;await send('/organizacoes/membros/'+m.ID_Usuarios+query(),'PUT',{papel:select.value,ativo:b.dataset.revoke?!m.Ativo:!!m.Ativo,versao:m.Versao});await loadTeam();});
  on('#formAutomacao','submit',async()=>{await send('/automacoes'+query(),'POST',{nome:$('#regraNome').value.trim(),gatilho:$('#regraGatilho').value,dias:+$('#regraDias').value,etapa:$('#regraEtapa').value.trim(),acao:$('#regraAcao').value,destino:$('#regraDestino').value,conteudo:$('#regraTexto').value.trim(),ativa:$('#regraAtiva').checked});$('#formAutomacao').reset();await loadRules();});
  on('#regrasCentral','click',async e=>{const b=e.target.closest('[data-rule]');if(b){const r=rules.find(r=>r.ID_Regra===b.dataset.rule);await send('/automacoes/'+r.ID_Regra,'PUT',{ativa:!r.Ativa,versao:r.Versao});await loadRules();}});
  const lines=id=>$(id).value.split('\n').map(v=>v.trim()).filter(Boolean);
  const link=(id,url)=>{$(id).innerHTML='<a href="'+esc(safeUrl(url))+'" target="_blank" rel="noopener noreferrer">Abrir página publicada</a>';};
  on('#formPublicacao','submit',async()=>{const r=await send('/publicacao/empresa'+query(),'PUT',{slug:$('#publicoSlug').value,publicada:$('#publicoAtivo').checked,cultura:$('#publicoCultura').value,localizacao:$('#publicoLocal').value,beneficios:lines('#publicoBeneficios'),tecnologias:lines('#publicoTecnologias'),versao:publicationVersion});publicationVersion=r.versao;if($('#publicoAtivo').checked)link('#publicoLink',r.url);else $('#publicoLink').textContent='Página privada.';});
  on('#formPublicarVaga','submit',async()=>{const r=await send('/publicacao/vagas/'+$('#publicoVaga').value,'PUT',{slug:$('#publicoVagaSlug').value,expira_em:$('#publicoExpira').value+'T23:59:59-03:00',pais:$('#publicoPais').value});link('#publicoVagaLink',r.url);});
  on('#formPreferencias','submit',async()=>{for(const [finalidade,autorizado] of [['emails',$('#prefEmail').checked],['comunicacao_em_massa',$('#prefLotes').checked]])await send('/privacidade/consentimentos','POST',{finalidade,autorizado});toast('Preferências salvas.');});
  $('#corrigirPerfil').addEventListener('click',event=>{event.preventDefault();localStorage.removeItem('talentix_organizacao');window.location.assign($('#voltarPainel').getAttribute('href'));});
  on('#exportarMeusDados','click',()=>download('/privacidade/meus-dados','talentix-meus-dados.json'));
  on('#formAceitarConvite','submit',async()=>{await send('/organizacoes/convites/aceitar','POST',{token:$('#aceitarCodigo').value.trim()});$('#formAceitarConvite').reset();await initialize();toast('Convite aceito. Selecione a organização.');});
  on('#formExclusao','submit',async()=>{await send('/privacidade/exclusao','POST',{senha:$('#exclusaoSenha').value,confirmacao:$('#exclusaoConfirmacao').value});$('#formExclusao').reset();await loadPrivacy();});
  on('#solicitacoesCentral','click',async e=>{const b=e.target.closest('[data-cancel-request]');if(b){await send('/privacidade/solicitacoes/'+b.dataset.cancelRequest,'DELETE');await loadPrivacy();}});
  on('#moderacaoCentral','click',async e=>{const b=e.target.closest('[data-review]');if(b){await send('/publicacao/moderacao/'+b.dataset.review,'PATCH',{estado:b.dataset.estado});await loadAudit();}});
  guard(initialize)();
});
