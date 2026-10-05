document.addEventListener('DOMContentLoaded', async () => {
  const {$, esc, safeUrl, api, toast, bindTabs, bindLogout} = Talentix;
  let usuarios = [], empresas = [], cursos = [];

  const run = fn => async event => { try { await fn(event); } catch (error) { toast(error.message, true); } };
  const dataBR = value => {
    if (!value) return '—';
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('pt-BR');
  };
  const vazio = (n, texto) => '<tr><td colspan="' + n + '" class="empty-cell">' + esc(texto) + '</td></tr>';
  const badgeAtivo = ativo => '<span class="badge ' + (ativo ? '' : 'badge-muted') + '">' + (ativo ? 'Ativo' : 'Inativo') + '</span>';

  bindLogout();
  $('#btnModoUsuario')?.addEventListener('click', run(async () => {
    const button = $('#btnModoUsuario');
    if (button.disabled) return;
    button.disabled = true;
    try {
      await api('/auth/alternar-modo', {
        method: 'POST',
        body: JSON.stringify({modo_usuario: true}),
      });
      window.location.assign('dashboard.html');
    } finally {
      button.disabled = false;
    }
  }));

  async function metricas() {
    const data = await api('/dashboard/admin');
    const labels = {total_usuarios:'Usuários',total_candidatos:'Candidatos',total_empresas:'Empresas',total_vagas_ativas:'Vagas publicadas',total_candidaturas:'Candidaturas',denuncias_abertas:'Denúncias abertas',assinaturas_ativas:'Assinaturas ativas'};
    $('#metricasAdmin').innerHTML = Object.entries(data).map(([k,v]) => '<div class="card metric"><span>' + esc(labels[k] || k) + '</span><strong>' + esc(v) + '</strong></div>').join('');
  }

  function renderUsuarios(lista) {
    $('#usuariosAdmin').innerHTML = lista.length ? lista.map(u =>
      '<tr><td><strong>' + esc(u.Nome) + '</strong>' + (u.EhUsuarioAtual ? '<span class="mini-label">Você</span>' : '') + '<small>' + esc(u.ID_Usuarios) + '</small></td>' +
      '<td>' + esc(u.Email) + '<small>' + esc(u.Telefone || 'Sem telefone') + '</small></td>' +
      '<td>' + esc(u.Perfis) + '</td><td>' + badgeAtivo(Boolean(u.Ativo)) + '</td><td>' + esc(dataBR(u.CriadoEm)) + '</td>' +
      '<td><div class="table-actions"><button class="btn btn-secondary btn-small" data-u-edit="' + esc(u.ID_Usuarios) + '">Editar</button>' +
      (u.EhUsuarioAtual ? '' : '<button class="btn btn-secondary btn-small" data-u-status="' + esc(u.ID_Usuarios) + '" data-ativo="' + (u.Ativo ? '0' : '1') + '">' + (u.Ativo ? 'Desativar' : 'Ativar') + '</button><button class="btn-danger-ghost btn-small" data-u-del="' + esc(u.ID_Usuarios) + '">Excluir</button>') +
      '</div></td></tr>'
    ).join('') : vazio(6,'Nenhum usuário encontrado.');
  }

  async function carregarUsuarios() {
    usuarios = await api('/admin/usuarios?incluir_inativos=true');
    renderUsuarios(usuarios);
  }

  function filtrarUsuarios() {
    const t = $('#buscaUsuarios').value.trim().toLowerCase();
    renderUsuarios(!t ? usuarios : usuarios.filter(u => [u.Nome,u.Email,u.Perfis,u.Telefone].some(v => String(v || '').toLowerCase().includes(t))));
  }

  function renderEmpresas(lista) {
    $('#empresasAdmin').innerHTML = lista.length ? lista.map(e =>
      '<tr><td><strong>' + esc(e.NomeFantasia || e.RazaoSocial) + '</strong><small>' + esc(e.RazaoSocial) + '</small></td>' +
      '<td>' + esc(e.Cnpj) + '</td><td class="cell-wrap">' + esc(e.Descricao || '—') + '</td>' +
      '<td>' + esc(e.FuncionariosCadastrados ?? 0) + '<small>' + esc(e.VagasAtivas ?? 0) + ' vaga(s) ativa(s)</small></td>' +
      '<td class="cell-wrap">' + esc(e.Endereco || '—') + '</td>' +
      '<td><strong>' + esc(e.NomeResponsavel) + '</strong><small>' + esc(e.EmailResponsavel) + (e.TelefoneResponsavel ? ' · ' + esc(e.TelefoneResponsavel) : '') + '</small></td>' +
      '<td>' + (e.Verificada ? '<span class="badge">Verificada</span>' : '<span class="badge badge-warning">Não verificada</span>') + ' ' + badgeAtivo(Boolean(e.Ativo)) + '</td>' +
      '<td><div class="table-actions"><button class="btn btn-secondary btn-small" data-e-edit="' + esc(e.ID_Empresas) + '">Editar</button>' +
      (e.Verificada ? '' : '<button class="btn btn-primary btn-small" data-e-check="' + esc(e.ID_Empresas) + '">Verificar</button>') +
      '<button class="btn btn-secondary btn-small" data-e-status="' + esc(e.ID_Empresas) + '" data-ativo="' + (e.Ativo ? '0' : '1') + '">' + (e.Ativo ? 'Desativar' : 'Ativar') + '</button>' +
      '<button class="btn-danger-ghost btn-small" data-e-del="' + esc(e.ID_Empresas) + '">Excluir</button></div></td></tr>'
    ).join('') : vazio(8,'Nenhuma empresa encontrada.');
  }

  async function carregarEmpresas() {
    empresas = await api('/admin/empresas?incluir_inativas=true');
    renderEmpresas(empresas);
  }

  function filtrarEmpresas() {
    const t = $('#buscaEmpresas').value.trim().toLowerCase();
    renderEmpresas(!t ? empresas : empresas.filter(e => [e.NomeFantasia,e.RazaoSocial,e.Cnpj,e.NomeResponsavel,e.EmailResponsavel,e.Setor,e.Endereco].some(v => String(v || '').toLowerCase().includes(t))));
  }

  async function denuncias() {
    const data = await api('/admin/denuncias');
    $('#denunciasAdmin').innerHTML = data.length ? data.map(d =>
      '<tr><td><strong>' + esc(d.Motivo) + '</strong><small>' + esc(d.Descricao || 'Sem descrição') + '</small></td>' +
      '<td>' + esc(d.DenuncianteNome) + '<small>' + esc(d.DenuncianteEmail) + '</small></td>' +
      '<td>' + esc(d.AlvoNome || '—') + '<small>' + esc(d.AlvoEmail || '') + '</small></td><td>' + esc(d.VagaTitulo || '—') + '</td>' +
      '<td><span class="badge ' + ([3,4].includes(d.ID_Status_Denuncia) ? 'badge-muted' : 'badge-warning') + '">' + esc(d.StatusDescricao) + '</span></td>' +
      '<td>' + esc(dataBR(d.CriadaEm)) + '</td><td>' +
      ([1,2].includes(d.ID_Status_Denuncia) ? '<div class="table-actions"><button class="btn btn-primary btn-small" data-denuncia="' + esc(d.ID_Denuncias) + '" data-status="3">Resolver</button><button class="btn btn-secondary btn-small" data-denuncia="' + esc(d.ID_Denuncias) + '" data-status="4">Rejeitar</button></div>' : esc(d.AdministradorNome || 'Concluída')) +
      '</td></tr>'
    ).join('') : vazio(7,'Nenhuma denúncia registrada.');
  }

  async function contatos() {
    const data = await api('/contato');
    $('#contatosAdmin').innerHTML = data.length ? data.map(c =>
      '<tr><td><strong>' + esc(c.Nome) + '</strong><small>' + esc(c.Email) + '</small></td><td>' + esc(c.Assunto) + '</td><td class="cell-wrap">' + esc(c.Mensagem) + '</td><td>' + esc(dataBR(c.CriadoEm)) + '</td><td>' +
      (c.Lido ? '<span class="badge">Lido</span>' : '<span class="badge badge-warning">Novo</span>') + '</td><td>' +
      (c.Lido ? '—' : '<button class="btn btn-secondary btn-small" data-contato="' + esc(c.ID_Contatos) + '">Marcar como lido</button>') + '</td></tr>'
    ).join('') : vazio(6,'Nenhuma mensagem de contato.');
  }

  async function notificacoes() {
    const data = await api('/admin/notificacoes?limite=500');
    $('#notificacoesAdmin').innerHTML = data.length ? data.map(n =>
      '<tr><td><strong>' + esc(n.UsuarioNome) + '</strong><small>' + esc(n.UsuarioEmail) + '</small></td><td>' + esc(n.Titulo) + '</td><td class="cell-wrap">' + esc(n.Mensagem) + '</td><td>' + esc(n.Tipo || '—') + '</td><td>' +
      (n.Lida ? '<span class="badge">Lida</span>' : '<span class="badge badge-warning">Pendente</span>') + '</td><td>' + esc(dataBR(n.CriadaEm)) + '</td></tr>'
    ).join('') : vazio(6,'Nenhuma notificação registrada.');
  }

  async function mensagens() {
    const data = await api('/admin/mensagens?limite=500');
    $('#mensagensAdmin').innerHTML = data.length ? data.map(m =>
      '<tr><td><strong>' + esc(m.RemetenteNome) + '</strong><small>' + esc(m.RemetenteEmail) + '</small></td><td><strong>' + esc(m.DestinatarioNome) + '</strong><small>' + esc(m.DestinatarioEmail) + '</small></td><td class="cell-wrap">' + esc(m.Conteudo) + '</td><td>' + esc(m.ID_Candidaturas || 'Mensagem direta') + '</td><td>' +
      (m.Lida ? '<span class="badge">Lida</span>' : '<span class="badge badge-warning">Não lida</span>') + '</td><td>' + esc(dataBR(m.EnviadaEm)) + '</td></tr>'
    ).join('') : vazio(6,'Nenhuma mensagem registrada.');
  }

  async function catalogo() {
    const [data,idiomas] = await Promise.all([api('/cursos'),api('/idiomas')]); cursos=data;
    $('#cursosAdmin').innerHTML = data.length ? data.map(c => '<article class="list-item"><div><h2 class="list-item__heading">' + esc(c.Titulo) + '</h2><p>' + esc(c.Plataforma) + ' · ' + esc(c.Categoria) + '</p>' + (c.Url ? '<a href="' + esc(safeUrl(c.Url)) + '" target="_blank" rel="noopener">Abrir curso</a>' : '') + '</div><div class="inline-actions"><button class="btn btn-secondary" data-editar-curso="' + esc(c.ID_Cursos) + '">Editar</button><button class="btn-danger-ghost" data-excluir-curso="' + esc(c.ID_Cursos) + '">Desativar</button></div></article>').join('') : '<p class="empty-state">Nenhum curso cadastrado.</p>';
    $('#idiomasAdmin').innerHTML = idiomas.length
      ? idiomas.map(i => '<span class="language-chip">' + esc(i.Nome) + '</span>').join('')
      : '<span class="language-empty">Nenhum idioma cadastrado.</span>';
  }

  bindTabs(async tab => {
    const f={metricas:async()=>Promise.all([metricas(),carregarUsuarios()]),empresas:carregarEmpresas,denuncias,catalogo,contatos,notificacoes,mensagens};
    await f[tab]?.();
  });

  $('#buscaUsuarios').addEventListener('input',filtrarUsuarios);
  $('#buscaEmpresas').addEventListener('input',filtrarEmpresas);

  $('#usuariosAdmin').addEventListener('click',run(async e=>{
    const edit=e.target.dataset.uEdit, stat=e.target.dataset.uStatus, del=e.target.dataset.uDel;
    if(edit){const u=usuarios.find(x=>x.ID_Usuarios===edit); if(!u)return; $('#usuarioId').value=u.ID_Usuarios;$('#usuarioNome').value=u.Nome||'';$('#usuarioEmail').value=u.Email||'';$('#usuarioTelefone').value=u.Telefone||'';$('#modalUsuario').showModal();}
    if(stat){const ativo=e.target.dataset.ativo==='1';await api('/admin/usuarios/'+stat+'/status',{method:'PATCH',body:JSON.stringify({ativo})});await Promise.all([carregarUsuarios(),metricas()]);toast(ativo?'Usuário ativado.':'Usuário desativado.');}
    if(del){if(!confirm('Excluir permanentemente este usuário? Dados vinculados podem ser removidos em cascata.'))return;await api('/admin/usuarios/'+del+'?confirmar=true',{method:'DELETE'});await Promise.all([carregarUsuarios(),metricas()]);toast('Usuário excluído permanentemente.');}
  }));

  $('#formUsuarioAdmin').addEventListener('submit',run(async e=>{e.preventDefault();await api('/admin/usuarios/'+$('#usuarioId').value,{method:'PUT',body:JSON.stringify({nome:$('#usuarioNome').value.trim(),email:$('#usuarioEmail').value.trim(),telefone:$('#usuarioTelefone').value.trim()||null})});$('#modalUsuario').close();await carregarUsuarios();toast('Usuário atualizado.');}));

  $('#empresasAdmin').addEventListener('click',run(async e=>{
    const edit=e.target.dataset.eEdit, check=e.target.dataset.eCheck, stat=e.target.dataset.eStatus, del=e.target.dataset.eDel;
    if(edit){const x=empresas.find(v=>v.ID_Empresas===edit);if(!x)return;$('#empresaId').value=x.ID_Empresas;$('#empresaRazao').value=x.RazaoSocial||'';$('#empresaFantasia').value=x.NomeFantasia||'';$('#empresaCnpj').value=x.Cnpj||'';$('#empresaSetor').value=x.Setor||'';$('#empresaPorte').value=x.Porte||'';$('#empresaSite').value=x.SiteUrl||'';$('#empresaEndereco').value=x.Endereco||'';$('#empresaDescricao').value=x.Descricao||'';$('#empresaVerificada').checked=Boolean(x.Verificada);$('#modalEmpresa').showModal();}
    if(check){await api('/empresas/'+check+'/verificar',{method:'PATCH'});await carregarEmpresas();toast('Empresa verificada.');}
    if(stat){const ativo=e.target.dataset.ativo==='1';await api('/admin/empresas/'+stat+'/status',{method:'PATCH',body:JSON.stringify({ativo})});await Promise.all([carregarEmpresas(),metricas()]);toast(ativo?'Empresa ativada.':'Empresa desativada.');}
    if(del){if(!confirm('Excluir permanentemente esta empresa? Vagas e vínculos relacionados podem ser removidos.'))return;await api('/admin/empresas/'+del+'?confirmar=true',{method:'DELETE'});await Promise.all([carregarEmpresas(),metricas()]);toast('Empresa excluída permanentemente.');}
  }));

  $('#formEmpresaAdmin').addEventListener('submit',run(async e=>{e.preventDefault();await api('/admin/empresas/'+$('#empresaId').value,{method:'PUT',body:JSON.stringify({razao_social:$('#empresaRazao').value.trim(),nome_fantasia:$('#empresaFantasia').value.trim()||null,cnpj:$('#empresaCnpj').value.trim(),descricao:$('#empresaDescricao').value.trim()||null,setor:$('#empresaSetor').value.trim()||null,porte:$('#empresaPorte').value.trim()||null,site_url:$('#empresaSite').value.trim()||null,endereco:$('#empresaEndereco').value.trim()||null,verificada:$('#empresaVerificada').checked})});$('#modalEmpresa').close();await carregarEmpresas();toast('Empresa atualizada.');}));

  $('#denunciasAdmin').addEventListener('click',run(async e=>{if(!e.target.dataset.denuncia)return;await api('/denuncias/'+e.target.dataset.denuncia+'/resolver',{method:'PATCH',body:JSON.stringify({id_status_denuncia:Number(e.target.dataset.status)})});await Promise.all([denuncias(),metricas(),notificacoes()]);toast('Denúncia atualizada.');}));
  $('#contatosAdmin').addEventListener('click',run(async e=>{if(!e.target.dataset.contato)return;await api('/contato/'+e.target.dataset.contato+'/marcar-lido',{method:'PATCH'});await contatos();toast('Contato marcado como lido.');}));
  document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>document.getElementById(b.dataset.close)?.close()));

  $('#limparCurso').addEventListener('click',()=>{$('#formCursoAdmin').reset();$('#cursoId').value='';});
  $('#formCursoAdmin').addEventListener('submit',run(async e=>{e.preventDefault();const d={titulo:$('#cursoTitulo').value.trim(),descricao:$('#cursoDescricao').value||null,plataforma:$('#cursoPlataforma').value||null,categoria:$('#cursoCategoria').value||null,url:$('#cursoUrl').value||null},id=$('#cursoId').value;await api(id?'/cursos/'+id:'/cursos',{method:id?'PUT':'POST',body:JSON.stringify(d)});$('#formCursoAdmin').reset();$('#cursoId').value='';await catalogo();toast('Curso salvo.');}));
  $('#cursosAdmin').addEventListener('click',run(async e=>{if(e.target.dataset.editarCurso){const c=cursos.find(x=>x.ID_Cursos===e.target.dataset.editarCurso);if(!c)return;$('#cursoId').value=c.ID_Cursos;[['cursoTitulo','Titulo'],['cursoDescricao','Descricao'],['cursoPlataforma','Plataforma'],['cursoCategoria','Categoria'],['cursoUrl','Url']].forEach(([i,k])=>$('#'+i).value=c[k]||'');$('#cursoTitulo').focus();}if(e.target.dataset.excluirCurso){await api('/cursos/'+e.target.dataset.excluirCurso,{method:'DELETE'});await catalogo();}}));
  $('#formIdiomaAdmin').addEventListener('submit',run(async e=>{e.preventDefault();await api('/idiomas',{method:'POST',body:JSON.stringify({nome:$('#idiomaNome').value.trim()})});$('#formIdiomaAdmin').reset();await catalogo();toast('Idioma adicionado.');}));

  try{
    const user=await api('/auth/me');
    if(user.tipo_usuario!=='administrador' || user.tipo_principal!=='administrador'){location.assign('login.html');return;}
    $('#userName').textContent=user.Nome;$('#userAvatar').textContent=user.Nome.charAt(0).toUpperCase();
    const modos = {recrutador:'Acessar painel do recrutador', empresa:'Acessar painel da empresa', candidato:'Acessar painel do candidato', usuario:'Acessar minha conta'};
    $('#btnModoUsuario').textContent = modos[user.tipo_alternativo] || 'Acessar outro perfil';
    $('#btnModoUsuario').disabled = false;
    await Promise.all([metricas(),carregarUsuarios()]);
  }catch(error){toast(error.message,true);}
});
