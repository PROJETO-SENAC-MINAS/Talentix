/* ============================================================
   TALENTIX — dashboard.js (Candidato)
   Perfil, currículo, experiências, formações/certificados,
   busca de vagas e candidaturas — tudo via API real.
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {

  const $ = (s) => document.querySelector(s);
  const $all = (s) => document.querySelectorAll(s);

  let sessao = null;      // { id_usuario, tipo_usuario }
  let idCandidato = null; // ID_Candidatos do usuário logado
  let statusCandidaturaMap = {}; // { ID_Status_Candidatura: Descricao }

  /* ============================================================
     Utilitários
     ============================================================ */

  function mostrarToast(mensagem, tipo = 'ok') {
    const toast = $('#toast');
    toast.textContent = mensagem;
    toast.classList.remove('error');
    if (tipo === 'error') toast.classList.add('error');
    toast.classList.add('show');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('show'), 3200);
  }

  async function api(path, options = {}) {
    let resposta;
    try {
      resposta = await fetch(`${API_BASE_URL}${path}`, {
        credentials: 'include',
        headers: options.body instanceof FormData
          ? undefined
          : { 'Content-Type': 'application/json' },
        ...options,
      });
    } catch {
      throw new Error(`Não foi possível conectar à API em ${API_BASE_URL}. Verifique se o FastAPI está em execução e recarregue a página.`);
    }

    if (resposta.status === 401) {
      window.location.href = 'login.html';
      throw new Error('Não autenticado');
    }

    const corpo = await resposta.json().catch(() => null);

    if (!resposta.ok) {
      const msg = Array.isArray(corpo?.detail)
        ? corpo.detail.map((d) => d.msg).join(' ')
        : (corpo?.detail || 'Ocorreu um erro inesperado.');
      if (path.endsWith('/importacao/aplicar') && msg.includes('Seleção de dados inválida')) {
        throw new Error('A API recusou a seleção da revisão. Atualize o projeto, reinicie a API e reabra esta página com Ctrl+F5.');
      }
      throw new Error(msg);
    }

    if (options.method && /candidatos|experiencias|formacoes|curriculos|foto-perfil|itens-profissionais/.test(path)) document.dispatchEvent(new Event('perfil:alterado'));
    return corpo;
  }

  function formatarData(iso) {
    if (!iso) return '';
    const [ano, mes, dia] = String(iso).slice(0, 10).split('-');
    return `${dia}/${mes}/${ano}`;
  }

  const escapeHtml = Talentix.esc;
  Talentix.bindCommunication();

  /* ============================================================
     Navegação entre abas
     ============================================================ */

  $all('.nav-item').forEach((botao) => {
    botao.addEventListener('click', () => {
      $all('.nav-item').forEach((b) => b.classList.remove('active'));
      $all('.tab-panel').forEach((p) => p.classList.remove('active'));
      botao.classList.add('active');
      $(`#tab-${botao.dataset.tab}`).classList.add('active');

      if (botao.dataset.tab === 'vagas' && !listaVagasCarregada) carregarVagas(null, paginaBusca);
      if (botao.dataset.tab === 'candidaturas') carregarCandidaturas();
      if (botao.dataset.tab === 'notificacoes') Talentix.notifications().catch(e => mostrarToast(e.message, 'error'));
      if (botao.dataset.tab === 'mensagens') Talentix.messages().catch(e => mostrarToast(e.message, 'error'));
      if (botao.dataset.tab === 'recomendacoes') carregarDesenvolvimento().catch(e => mostrarToast(e.message, 'error'));
    });
  });

  /* ============================================================
     Logout
     ============================================================ */

  $('#btnLogout')?.addEventListener('click', async () => {
    try {
      await api('/auth/logout', { method: 'POST' });
    } catch { /* ignora falha de rede no logout */ }
    window.location.href = 'login.html';
  });

  async function voltarAdministracao() {
    await api('/auth/alternar-modo', {
      method: 'POST',
      body: JSON.stringify({modo_usuario: false}),
    });
    window.location.href = 'dashboard-admin.html';
  }

  /* ============================================================
     Inicialização: sessão -> candidato -> dados do perfil
     ============================================================ */

  async function inicializar() {
    try {
      sessao = await api('/auth/me');
    } catch {
      window.location.href = 'login.html';
      return;
    }

    if (sessao.tipo_usuario !== 'candidato') {
      // Este dashboard é específico para candidatos.
      mostrarToast('Esta área é exclusiva para candidatos.', 'error');
      return;
    }

    $('#userName').textContent = sessao.Nome || 'Meu perfil';
    $('#userAvatar').textContent = (sessao.Nome || '?').trim().charAt(0).toUpperCase();

    const btnModoAdmin = $('#btnModoAdmin');
    const adminEmModoUsuario = sessao.tipo_principal === 'administrador' && sessao.modo_usuario;
    if (btnModoAdmin) {
      btnModoAdmin.hidden = !adminEmModoUsuario;
      btnModoAdmin.onclick = adminEmModoUsuario
        ? () => voltarAdministracao().catch((erro) => mostrarToast(erro.message, 'error'))
        : null;
    }

    await carregarStatusCandidatura();
    await carregarCandidato();
  }

    async function carregarCandidato() {
    try {
      const meu = await api('/candidatos/me');
      idCandidato = meu.ID_Candidatos;
      preencherFormPerfil(meu);
      document.dispatchEvent(new CustomEvent('perfil:pronto', {detail: meu.ID_Candidatos}));
    } catch (erro) {
      mostrarToast(erro.message, 'error');
      return;
    }

    carregarHabilidades();
    carregarCurriculos();
    carregarExperiencias();
    carregarFormacoes();
  }

  async function carregarStatusCandidatura() {
    try {
      const lista = await api('/dominios/status-candidatura');
      lista.forEach((s) => { statusCandidaturaMap[s.ID_Status_Candidatura] = s.Descricao; });
    } catch {
      // Segue sem os rótulos amigáveis — usa fallback numérico.
    }
  }

  /* ============================================================
     PERFIL
     ============================================================ */

  function preencherFormPerfil(c) {
    $('#pTituloProfissional').value = c.TituloProfissional || '';
    $('#pResumo').value = c.Resumo || '';
    $('#pCidade').value = c.Cidade || '';
    $('#pEstado').value = c.Estado || '';
    $('#pExperienciaAnos').value = c.ExperienciaAnos ?? '';
    $('#pPretensaoSalarial').value = c.PretensaoSalarial ?? '';
    $('#pLinkedin').value = c.LinkedinUrl || '';
    $('#pGithub').value = c.GithubUrl || '';
    $('#pPortfolio').value = c.PortfolioUrl || '';
    $('#pDisponivel').checked = !!c.Disponivel;
    const lista = v => typeof v === 'string' ? JSON.parse(v) : (v || []);
    $all('[name="pModalidade"]').forEach(el => {el.checked = lista(c.Modalidades).includes(el.value);});
    $all('[name="pContrato"]').forEach(el => {el.checked = lista(c.TiposContrato).includes(el.value);});
    $('#pSoftSkills').value = lista(c.HabilidadesComportamentais).join(', ');
    $('#pPreferencias').value = c.Preferencias || '';
  }

  $('#formPerfil')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const botao = $('#btnSalvarPerfil');
    botao.setAttribute('data-loading', 'true');

    const payload = {
      titulo_profissional: $('#pTituloProfissional').value.trim() || null,
      resumo: $('#pResumo').value.trim() || null,
      cidade: $('#pCidade').value.trim() || null,
      estado: $('#pEstado').value.trim().toUpperCase() || null,
      experiencia_anos: $('#pExperienciaAnos').value ? Number($('#pExperienciaAnos').value) : null,
      pretensao_salarial: $('#pPretensaoSalarial').value ? Number($('#pPretensaoSalarial').value) : null,
      linkedin_url: $('#pLinkedin').value.trim() || null,
      github_url: $('#pGithub').value.trim() || null,
      portfolio_url: $('#pPortfolio').value.trim() || null,
      disponivel: $('#pDisponivel').checked,
      modalidades: [...$all('[name="pModalidade"]:checked')].map(el => el.value),
      tipos_contrato: [...$all('[name="pContrato"]:checked')].map(el => el.value),
      habilidades_comportamentais: $('#pSoftSkills').value.split(',').map(s => s.trim()).filter(Boolean),
      preferencias: $('#pPreferencias').value.trim() || null,
    };

    try {
      await api(`/candidatos/${idCandidato}`, { method: 'PUT', body: JSON.stringify(payload) });
      mostrarToast('Perfil atualizado com sucesso.');
    } catch (erro) {
      mostrarToast(erro.message, 'error');
    } finally {
      botao.removeAttribute('data-loading');
    }
  });

  /* ---------- Habilidades ---------- */

  async function carregarHabilidades() {
    const container = $('#listaHabilidades');
    try {
      const habilidades = await api(`/candidatos/${idCandidato}/habilidades`);
      if (habilidades.length === 0) {
        container.innerHTML = '<li class="empty-state" style="list-style:none;">Nenhuma habilidade adicionada ainda.</li>';
        return;
      }
      container.innerHTML = habilidades.map((h) => `
        <li class="chip">
          ${escapeHtml(h.NomeHabilidade)}
          <button type="button" data-remover-habilidade="${h.ID_Candidato_Habilidades}" aria-label="Remover">✕</button>
        </li>
      `).join('');
    } catch (erro) {
      container.innerHTML = `<li class="empty-state" style="list-style:none;">${escapeHtml(erro.message)}</li>`;
    }
  }

  $('#formHabilidade')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const nome = $('#hNome').value.trim();
    if (!nome) return;

    try {
      // Garante que a habilidade existe no catálogo (idempotente:
      // o backend retorna a existente se já houver mesmo nome).
      let habilidadeCatalogo;
      try {
        habilidadeCatalogo = await api('/habilidades', {
          method: 'POST',
          body: JSON.stringify({ nome, categoria: 'Técnica' }),
        });
      } catch {
        // Provavelmente exige admin para criar no catálogo; tenta localizar existente.
        const encontradas = await api(`/habilidades?busca=${encodeURIComponent(nome)}`);
        habilidadeCatalogo = encontradas.find((h) => h.Nome.toLowerCase() === nome.toLowerCase());
        if (!habilidadeCatalogo) throw new Error('Não foi possível adicionar esta habilidade agora.');
      }

      await api(`/candidatos/${idCandidato}/habilidades`, {
        method: 'POST',
        body: JSON.stringify({
          id_habilidade: habilidadeCatalogo.ID_Habilidades,
          nivel: $('#hNivel').value ? Number($('#hNivel').value) : null,
        }),
      });

      $('#hNome').value = '';
      $('#hNivel').value = '';
      mostrarToast('Habilidade adicionada.');
      carregarHabilidades();
    } catch (erro) {
      mostrarToast(erro.message, 'error');
    }
  });

  $('#listaHabilidades')?.addEventListener('click', async (e) => {
    const id = e.target.getAttribute('data-remover-habilidade');
    if (!id) return;
    try {
      await api(`/candidatos/${idCandidato}/habilidades/${id}`, { method: 'DELETE' });
      carregarHabilidades();
    } catch (erro) {
      mostrarToast(erro.message, 'error');
    }
  });

  /* ============================================================
     CURRÍCULO (arquivo) + EXPERIÊNCIAS
     ============================================================ */

  let curriculosEmCache = [];
  let timerCurriculos;
  let curriculoAguardandoRevisao = null;
  document.addEventListener('curriculos:atualizar', carregarCurriculos);

  function rotuloStatusImportacao(status) {
    return {
      1: 'Na fila',
      2: 'Analisando',
      3: 'Pronto para revisar',
      4: 'Falha na análise',
    }[Number(status)] || 'Não analisado';
  }

  function atualizarEstadoImportacao(curriculos) {
    const container = $('#curriculoImportacaoEstado');
    if (!container) return;
    const analisados = curriculos.filter((c) => Number(c.ImportacaoStatus) === 3);
    const falhos = curriculos.filter((c) => Number(c.ImportacaoStatus) === 4);

    if (analisados.length) {
      const atual = analisados[0];
      container.innerHTML = `
        <div class="list-item">
          <div class="list-item__main">
            <p class="list-item__title">Dados identificados em ${escapeHtml(atual.Titulo)}</p>
            <p class="list-item__sub">Revise as sugestões antes de atualizar seu perfil.</p>
          </div>
          <div class="list-item__actions">
            <button type="button" class="btn btn-primary" data-revisar-importacao="${escapeHtml(atual.ID_Curriculos)}">Revisar e importar</button>
          </div>
        </div>
      `;
      return;
    }

    if (falhos.length) {
      container.innerHTML = `<p class="empty-state">${escapeHtml(falhos[0].ImportacaoErro || 'Não foi possível analisar o currículo.')}</p>`;
      return;
    }

    container.innerHTML = '<p class="empty-state">Envie um PDF ou DOCX. O Talentix tentará identificar as informações automaticamente.</p>';
  }

  async function carregarCurriculos() {
    const container = $('#listaCurriculos');
    try {
      const curriculos = await api(`/candidatos/${idCandidato}/curriculos`);
      curriculosEmCache = curriculos;
      clearTimeout(timerCurriculos);
      if (curriculos.some(c => [1, 2].includes(Number(c.ImportacaoStatus)))) timerCurriculos = setTimeout(carregarCurriculos, 4000);
      atualizarEstadoImportacao(curriculos);

      if (curriculos.length === 0) {
        container.innerHTML = '<p class="empty-state">Nenhum currículo enviado ainda.</p>';
        return;
      }

      container.innerHTML = curriculos.map((c) => {
        const tamanhoKb = c.ArquivoTamanhoBytes ? (Number(c.ArquivoTamanhoBytes) / 1024).toFixed(0) : '—';
        const extensao = String(c.ArquivoUrl || '').split('.').pop().toLowerCase();
        const statusImportacao = Number(c.ImportacaoStatus || 0);
        const podeAnalisar = ['pdf', 'docx'].includes(extensao);
        let acaoImportacao = '';

        if (statusImportacao === 3) {
          acaoImportacao = `<button type="button" class="btn btn-primary" data-revisar-importacao="${escapeHtml(c.ID_Curriculos)}">Revisar dados</button>`;
        } else if (statusImportacao === 2 || statusImportacao === 1) {
          acaoImportacao = '<span class="badge badge--muted">Analisando…</span>';
        } else if (podeAnalisar) {
          acaoImportacao = `<button type="button" class="btn btn-secondary" data-analisar-curriculo="${escapeHtml(c.ID_Curriculos)}">Analisar currículo</button>`;
        } else {
          acaoImportacao = '<span class="badge badge--muted">Importação: somente PDF/DOCX</span>';
        }

        return `
          <div class="list-item">
            <div class="list-item__main">
              <p class="list-item__title">${escapeHtml(c.Titulo)} ${c.Principal ? '<span class="badge">Principal</span>' : ''}</p>
              <p class="list-item__sub">Versão ${Number(c.Versao || 1)} · ${tamanhoKb} KB · ${escapeHtml(c.ArquivoTipoMime || '')}</p>
              <p class="list-item__meta">Origem: ${c.Origem === 'talentix' ? 'PDF do perfil Talentix' : 'Arquivo enviado'}</p>
              <p class="list-item__meta">Preenchimento inteligente: ${escapeHtml(rotuloStatusImportacao(c.ImportacaoStatus))}</p>
              ${c.ImportacaoErro ? `<p class="list-item__meta">${escapeHtml(c.ImportacaoErro)}</p>` : ''}
            </div>
            <div class="list-item__actions">
              <a class="btn btn-secondary" style="text-decoration:none;padding:7px 12px;font-size:12.5px;" href="${API_BASE_URL}${c.ArquivoUrl}?preview=true" target="_blank" rel="noopener">Prévia</a>
              <a class="btn btn-secondary" href="${API_BASE_URL}${c.ArquivoUrl}" target="_blank" rel="noopener">Baixar</a>
              ${acaoImportacao}
              ${!c.Principal ? `<button type="button" class="btn btn-secondary" data-principal-curriculo="${escapeHtml(c.ID_Curriculos)}">Tornar principal</button>` : ''}
              <button type="button" class="btn btn-secondary" data-nome-curriculo="${escapeHtml(c.ID_Curriculos)}" data-principal="${c.Principal ? '1' : '0'}" data-titulo="${escapeHtml(c.Titulo)}">Editar nome</button>
              <button type="button" class="btn-danger-ghost" data-remover-curriculo="${escapeHtml(c.ID_Curriculos)}">Arquivar</button>
            </div>
          </div>
        `;
      }).join('');

      if (curriculoAguardandoRevisao) {
        const pendente = curriculos.find(c => c.ID_Curriculos === curriculoAguardandoRevisao);
        const statusPendente = Number(pendente?.ImportacaoStatus);
        if (statusPendente === 3) {
          const idPronto = curriculoAguardandoRevisao;
          curriculoAguardandoRevisao = null;
          await abrirImportacaoCurriculo(idPronto);
          mostrarToast('Análise concluída. Revise as sugestões; seu perfil só muda quando você confirmar a importação.');
        } else if (statusPendente === 4) {
          curriculoAguardandoRevisao = null;
          mostrarToast(pendente.ImportacaoErro || 'Não foi possível analisar este currículo.', 'error');
        }
      }
    } catch (erro) {
      container.innerHTML = `<p class="empty-state">${escapeHtml(erro.message)}</p>`;
    }
  }

  const gruposImportacao = {
    perfil: {id: 'impPerfil', nome: 'dados do perfil'},
    experiencias: {id: 'impExperiencias', nome: 'experiências'},
    formacoes: {id: 'impFormacoes', nome: 'formação acadêmica'},
    certificados: {id: 'impCertificados', nome: 'certificados'},
    projetos: {id: 'impProjetos', nome: 'projetos'},
    habilidades: {id: 'impHabilidades', nome: 'habilidades'},
    idiomas: {id: 'impIdiomas', nome: 'idiomas'},
  };

  function cabecalhoSecaoImportacao(titulo, secao) {
    const grupo = gruposImportacao[secao];
    return `<div class="import-section-header"><h3>${escapeHtml(titulo)}</h3><label class="checkbox-line"><input type="checkbox" id="${grupo.id}" data-importar-secao="${secao}" aria-label="Selecionar todos: ${escapeHtml(grupo.nome)}"> Selecionar todos</label></div>`;
  }

  function sincronizarSelecaoImportacao() {
    const itens = [...$all('#curriculoImportacaoResumo input[data-secao]')];
    const selecionados = itens.filter(item => item.checked).length;
    for (const [secao, grupo] of Object.entries(gruposImportacao)) {
      const controle = $('#' + grupo.id);
      const itensGrupo = itens.filter(item => item.dataset.secao === secao);
      const marcados = itensGrupo.filter(item => item.checked).length;
      controle.disabled = !itensGrupo.length;
      controle.checked = itensGrupo.length > 0 && marcados === itensGrupo.length;
      controle.indeterminate = marcados > 0 && marcados < itensGrupo.length;
    }
    $('#curriculoSelecaoResumo').textContent = `${selecionados} de ${itens.length} informações selecionadas.`;
    $('#btnAplicarCurriculo').disabled = selecionados === 0;
  }

  $('#curriculoImportacaoResumo')?.addEventListener('change', (e) => {
    const secao = e.target.dataset.importarSecao;
    if (secao) {
      $all(`#curriculoImportacaoResumo input[data-secao="${secao}"]`).forEach(item => {
        item.checked = e.target.checked;
      });
    }
    sincronizarSelecaoImportacao();
    $('#curriculoImportacaoErro').hidden = true;
  });

  function listaPreview(titulo, itens, renderItem, secao) {
    if (!itens?.length) {
      return `<section>${cabecalhoSecaoImportacao(titulo, secao)}<p class="curriculum-import-empty">Nada identificado.</p></section>`;
    }
    return `
      <section>
        ${cabecalhoSecaoImportacao(titulo, secao)}
        <ul class="import-item-list">${itens.map((item, i) => `<li><label class="import-item"><input type="checkbox" checked data-secao="${secao}" data-indice="${i}"><span>${renderItem(item)}</span></label></li>`).join('')}</ul>
      </section>
    `;
  }

  function renderizarPreviewImportacao(dados) {
    $('#impSobrescrever').checked = false;
    $('#curriculoImportacaoErro').hidden = true;
    $('#curriculoImportacaoErro').textContent = '';
    if (dados?.versao !== 3) {
      $('#curriculoImportacaoResumo').innerHTML = '<p>A revisão retornada está desatualizada. Atualize o projeto, reinicie a API e o worker e recarregue a página com Ctrl+F5. Depois abra “Revisar dados” novamente.</p>';
      $('#curriculoSelecaoResumo').textContent = 'Aguardando a revisão atualizada.';
      $('#btnAplicarCurriculo').disabled = true;
      return;
    }
    const perfil = dados?.perfil || {};
    const camposPerfil = [
      ['Título', perfil.titulo_profissional, 'titulo_profissional'],
      ['Resumo', perfil.resumo, 'resumo'],
      ['Cidade', perfil.cidade, 'cidade'], ['Estado', perfil.estado, 'estado'],
      ['LinkedIn', perfil.linkedin_url, 'linkedin_url'],
      ['GitHub', perfil.github_url, 'github_url'],
      ['Portfólio', perfil.portfolio_url, 'portfolio_url'],
      ['Experiência estimada', Number.isFinite(perfil.experiencia_anos) ? `${perfil.experiencia_anos} ano(s)` : null, 'experiencia_anos'],
    ].filter(([, valor]) => valor);

    $('#curriculoImportacaoResumo').innerHTML = `
      <div class="curriculum-import-preview">
        <section>
          ${cabecalhoSecaoImportacao('Perfil', 'perfil')}
          ${camposPerfil.length
            ? `<ul class="import-item-list">${camposPerfil.map(([nome, valor, chave]) => `<li><label class="import-item"><input type="checkbox" checked data-secao="perfil" data-campo="${chave}"><span><strong>${escapeHtml(nome)}:</strong> ${escapeHtml(String(valor))}</span></label></li>`).join('')}</ul>`
            : '<p class="curriculum-import-empty">Nenhum dado de perfil identificado.</p>'}
        </section>
        <section><h3>Contato identificado</h3><p>${escapeHtml(dados?.contato?.nome || '')} · ${escapeHtml(dados?.contato?.email || '')} · ${escapeHtml(dados?.contato?.telefone || '')}</p><p>Revise seu contato nas configurações da conta. O e-mail de acesso não é alterado por importação.</p></section>
        ${listaPreview('Experiências', dados?.experiencias, (item) =>
          `${escapeHtml(item.cargo || '')} · ${escapeHtml(item.empresa || '')} ${item.data_inicio ? `(${escapeHtml(item.data_inicio.slice(0, 4))}${item.atual ? ' — atual' : item.data_fim ? ` — ${escapeHtml(item.data_fim.slice(0, 4))}` : ''})` : ''}`
        , 'experiencias')}
        ${listaPreview('Formação acadêmica', dados?.formacoes, (item) =>
          `${escapeHtml(item.curso || '')} · ${escapeHtml(item.instituicao || '')}${item.nivel ? ` — ${escapeHtml(item.nivel)}` : ''}${item.data_inicio ? ` (${escapeHtml(item.data_inicio.slice(0, 4))}${item.data_conclusao ? ` — ${escapeHtml(item.data_conclusao.slice(0, 4))}` : ''})` : ''}`
        , 'formacoes')}
        ${listaPreview('Certificados', dados?.certificados, (item) =>
          `${escapeHtml(item.curso || '')} · ${escapeHtml(item.instituicao || '')}${item.data_conclusao ? ` — ${escapeHtml(item.data_conclusao.slice(0, 4))}` : ''}`
        , 'certificados')}
        ${listaPreview('Projetos', dados?.projetos, (item) =>
          `${escapeHtml(item.titulo || '')}${item.descricao ? ` — ${escapeHtml(item.descricao)}` : ''}${item.url ? ` · ${escapeHtml(item.url)}` : ''}`
        , 'projetos')}
        ${listaPreview('Habilidades', dados?.habilidades, (item) => escapeHtml(item.nome || ''), 'habilidades')}
        ${listaPreview('Idiomas', dados?.idiomas, (item) =>
          `${escapeHtml(item.idioma || '')}${item.nivel ? ` — ${escapeHtml(item.nivel)}` : ''}`
        , 'idiomas')}
      </div>
    `;
    sincronizarSelecaoImportacao();
  }

  async function abrirImportacaoCurriculo(idCurriculo) {
    if ($('#modalImportarCurriculo')?.open && $('#curriculoImportacaoId').value === idCurriculo) {
      curriculoAguardandoRevisao = null;
      return;
    }
    const importacao = await api(`/curriculos/${idCurriculo}/importacao`);
    if (Number(importacao.ID_Status_Processamento_IA) !== 3 || !importacao.DadosExtraidos) {
      throw new Error(importacao.ErroProcessamento || 'A análise ainda não está pronta.');
    }
    $('#curriculoImportacaoId').value = idCurriculo;
    renderizarPreviewImportacao(importacao.DadosExtraidos);
    $('#modalImportarCurriculo').showModal();
  }

  async function analisarCurriculoSelecionado(idCurriculo, botao) {
    botao?.setAttribute('data-loading', 'true');
    if (botao) botao.disabled = true;
    try {
      const importacao = await api(`/curriculos/${idCurriculo}/analisar`, { method: 'POST' });
      if (Number(importacao.ID_Status_Processamento_IA) !== 3) {
        curriculoAguardandoRevisao = idCurriculo;
        mostrarToast('Currículo na fila de análise. O resultado será atualizado automaticamente.'); await carregarCurriculos(); return;
      }
      mostrarToast('Currículo analisado. Revise os dados antes de importar.');
      await carregarCurriculos();
      renderizarPreviewImportacao(importacao.DadosExtraidos);
      $('#curriculoImportacaoId').value = idCurriculo;
      $('#modalImportarCurriculo').showModal();
    } finally {
      botao?.removeAttribute('data-loading');
      if (botao) botao.disabled = false;
    }
  }

  $('#formCurriculo')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const botao = $('#btnEnviarCurriculo');
    const arquivo = $('#cvArquivo').files[0];
    if (!arquivo) return;

    botao.setAttribute('data-loading', 'true');

    const formData = new FormData();
    formData.append('titulo', $('#cvTitulo').value.trim());
    formData.append('principal', $('#cvPrincipal').checked);
    formData.append('analisar', true);
    formData.append('arquivo', arquivo);

    try {
      const curriculo = await api(`/candidatos/${idCandidato}/curriculos`, { method: 'POST', body: formData });
      $('#formCurriculo').reset();
      if ([1, 2].includes(Number(curriculo.importacao?.ID_Status_Processamento_IA))) {
        curriculoAguardandoRevisao = curriculo.ID_Curriculos;
      }
      await carregarCurriculos();

      if (Number(curriculo.importacao?.ID_Status_Processamento_IA) === 3 && curriculo.importacao?.DadosExtraidos) {
        mostrarToast('Currículo enviado e analisado. Revise as sugestões.');
        $('#curriculoImportacaoId').value = curriculo.ID_Curriculos;
        renderizarPreviewImportacao(curriculo.importacao.DadosExtraidos);
        $('#modalImportarCurriculo').showModal();
      } else if (curriculo.importacao?.ErroProcessamento) {
        mostrarToast(`Currículo salvo. ${curriculo.importacao.ErroProcessamento}`, 'error');
      } else if ([1, 2].includes(Number(curriculo.importacao?.ID_Status_Processamento_IA)) && curriculoAguardandoRevisao === curriculo.ID_Curriculos) {
        mostrarToast('Currículo enviado e em análise. A prévia abrirá quando o processamento terminar.');
      } else {
        mostrarToast('Currículo enviado com sucesso.');
      }
    } catch (erro) {
      mostrarToast(erro.message, 'error');
    } finally {
      botao.removeAttribute('data-loading');
    }
  });

  $('#listaCurriculos')?.addEventListener('click', async (e) => {
    const botao = e.target.closest('button');
    if (!botao) return;

    const idRemover = botao.getAttribute('data-remover-curriculo');
    const idAnalisar = botao.getAttribute('data-analisar-curriculo');
    const idRevisar = botao.getAttribute('data-revisar-importacao');

    try {
      if (botao.dataset.principalCurriculo) {
        const cv = curriculosEmCache.find(c => c.ID_Curriculos === botao.dataset.principalCurriculo);
        await api(`/curriculos/${cv.ID_Curriculos}`, {method:'PUT', body:JSON.stringify({titulo:cv.Titulo, principal:true})});
        await carregarCurriculos(); return;
      }
      if (idAnalisar) {
        await analisarCurriculoSelecionado(idAnalisar, botao);
        return;
      }
      if (idRevisar) {
        await abrirImportacaoCurriculo(idRevisar);
        return;
      }
      if (!idRemover) return;
      if (!confirm('Arquivar esta versão? Candidaturas já enviadas mantêm o documento original.')) return;

      await api(`/curriculos/${idRemover}`, { method: 'DELETE' });
      mostrarToast('Versão arquivada. O histórico e as candidaturas foram preservados.');
      await carregarCurriculos();
    } catch (erro) {
      mostrarToast(erro.message, 'error');
    }
  });

  $('#curriculoImportacaoEstado')?.addEventListener('click', async (e) => {
    const botao = e.target.closest('[data-revisar-importacao]');
    if (!botao) return;
    try {
      await abrirImportacaoCurriculo(botao.dataset.revisarImportacao);
    } catch (erro) {
      mostrarToast(erro.message, 'error');
    }
  });

  function fecharImportacaoCurriculo() {
    $('#modalImportarCurriculo')?.close();
  }

  $('#fecharImportacaoCurriculo')?.addEventListener('click', fecharImportacaoCurriculo);
  $('#cancelarImportacaoCurriculo')?.addEventListener('click', fecharImportacaoCurriculo);

  $('#formAplicarCurriculo')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const botao = $('#btnAplicarCurriculo');
    if (botao.disabled) return;
    botao.disabled = true;
    botao.setAttribute('data-loading', 'true');

    const payload = {
      versao_revisao: 2,
      selecionados: {perfil:[], experiencias:[], formacoes:[], certificados:[], projetos:[], habilidades:[], idiomas:[]},
      sobrescrever_perfil: $('#impSobrescrever').checked,
    };
    $all('#curriculoImportacaoResumo input[data-secao]:checked').forEach(el => payload.selecionados[el.dataset.secao].push(el.dataset.campo || Number(el.dataset.indice)));
    for (const secao of Object.keys(gruposImportacao)) {
      payload['importar_' + secao] = payload.selecionados[secao].length > 0;
    }
    $('#curriculoImportacaoErro').hidden = true;

    try {
      const idCurriculo = $('#curriculoImportacaoId').value;
      const resultado = await api(`/curriculos/${idCurriculo}/importacao/aplicar`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      fecharImportacaoCurriculo();

      const meu = await api('/candidatos/me');
      preencherFormPerfil(meu);
      await Promise.all([
        carregarCurriculos(),
        carregarHabilidades(),
        carregarExperiencias(),
        carregarFormacoes(),
      ]);

      const total = Object.values(resultado.importados || {}).reduce((soma, valor) => soma + Number(valor || 0), 0);
      mostrarToast(total
        ? `Currículo importado: ${total} informação(ões) adicionada(s).`
        : 'Importação concluída. Os dados identificados já estavam no seu perfil.');
    } catch (erro) {
      $('#curriculoImportacaoErro').textContent = erro.message;
      $('#curriculoImportacaoErro').hidden = false;
      $('#curriculoImportacaoErro').scrollIntoView({block: 'nearest'});
      mostrarToast(erro.message, 'error');
    } finally {
      botao.removeAttribute('data-loading');
      sincronizarSelecaoImportacao();
    }
  });

  let experienciasEmCache = [], formacoesEmCache = [];
  async function carregarExperiencias() {
    const container = $('#listaExperiencias');
    try {
      const experiencias = await api(`/candidatos/${idCandidato}/experiencias`);
      experienciasEmCache = experiencias;
      if (experiencias.length === 0) {
        container.innerHTML = '<p class="empty-state">Nenhuma experiência cadastrada ainda.</p>';
        return;
      }
      container.innerHTML = experiencias.map((exp) => `
        <div class="list-item">
          <div class="list-item__main">
            <p class="list-item__title">${escapeHtml(exp.Cargo)} · ${escapeHtml(exp.Empresa)}</p>
            <p class="list-item__sub">${escapeHtml(exp.Descricao || '')}</p>
            <p class="list-item__meta">${formatarData(exp.DataInicio)} — ${exp.Atual ? 'atual' : formatarData(exp.DataFim) || '—'}</p>
          </div>
          <div class="list-item__actions">
            <button type="button" class="btn btn-secondary" data-editar-experiencia="${exp.ID_Experiencias}">Editar experiência</button>
            <button type="button" class="btn-danger-ghost" data-remover-experiencia="${exp.ID_Experiencias}">Remover</button>
          </div>
        </div>
      `).join('');
    } catch (erro) {
      container.innerHTML = `<p class="empty-state">${escapeHtml(erro.message)}</p>`;
    }
  }

  $('#expAtual')?.addEventListener('change', (e) => {
    $('#expFim').disabled = e.target.checked;
    if (e.target.checked) $('#expFim').value = '';
  });

  $('#formExperiencia')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      empresa: $('#expEmpresa').value.trim(),
      cargo: $('#expCargo').value.trim(),
      descricao: $('#expDescricao').value.trim() || null,
      data_inicio: $('#expInicio').value,
      data_fim: $('#expAtual').checked ? null : ($('#expFim').value || null),
      atual: $('#expAtual').checked,
    };
    try {
      if(payload.data_fim && payload.data_inicio>payload.data_fim) throw new Error('O término não pode anteceder o início.');
      const editando = $('#formExperiencia').dataset.editando;
      await api(editando ? `/experiencias/${editando}` : `/candidatos/${idCandidato}/experiencias`, { method: editando ? 'PUT':'POST', body: JSON.stringify(payload) });
      mostrarToast('Experiência adicionada.');
      $('#formExperiencia').reset();
      delete $('#formExperiencia').dataset.editando; $('#expFim').disabled=false;
      carregarExperiencias();
    } catch (erro) {
      mostrarToast(erro.message, 'error');
    }
  });

  $('#listaExperiencias')?.addEventListener('click', async (e) => {
    if(e.target.dataset.editarExperiencia) {
      const exp=experienciasEmCache.find(v=>v.ID_Experiencias===e.target.dataset.editarExperiencia);
      $('#formExperiencia').dataset.editando=exp.ID_Experiencias;
      for(const [id,key] of Object.entries({expEmpresa:'Empresa',expCargo:'Cargo',expDescricao:'Descricao',expInicio:'DataInicio',expFim:'DataFim'})) $('#'+id).value=exp[key] || '';
      $('#expAtual').checked=!!exp.Atual; $('#expFim').disabled=!!exp.Atual; $('#expEmpresa').focus(); return;
    }
    const id = e.target.getAttribute('data-remover-experiencia');
    if (!id) return;
    try {
      await api(`/experiencias/${id}`, { method: 'DELETE' });
      carregarExperiencias();
    } catch (erro) {
      mostrarToast(erro.message, 'error');
    }
  });

  /* ============================================================
     FORMAÇÃO E CERTIFICADOS (tabela Formacoes; certificado =
     Formação com Nivel = "Certificado")
     ============================================================ */

  const fTipo = $('#fTipo');
  function atualizarCamposFormacao() {
    const ehCertificado = fTipo.value === 'certificado';
    const ehCurso = fTipo.value === 'curso';
    $('#grupoNivelFormacao').style.display = ehCertificado || ehCurso ? 'none' : '';
    $('#grupoStatusFormacao').style.display = ehCertificado || ehCurso ? 'none' : '';
    $('#grupoDetalhesCurso').hidden = !ehCurso;
    $('#fDescricao').disabled = $('#fUrl').disabled = !ehCurso;
    $('#fInstituicao').required = !ehCurso;
    $('#fInstituicao').placeholder = ehCertificado ? 'Ex: Alura, AWS, Google...' : 'Ex: UFMG, Alura, Coursera...';
    $('#fCurso').placeholder = ehCertificado ? 'Ex: AWS Cloud Practitioner' : 'Ex: Ciência da Computação';
  }
  fTipo?.addEventListener('change', () => {delete $('#formFormacao').dataset.editando; $('#fItemId').value = ''; atualizarCamposFormacao();});
  $('#cancelarFormacao').addEventListener('click', () => {$('#formFormacao').reset(); delete $('#formFormacao').dataset.editando; $('#fItemId').value = ''; atualizarCamposFormacao();});
  document.addEventListener('curso:editar', e => {
    const curso = e.detail;
    $('#formFormacao').reset(); delete $('#formFormacao').dataset.editando;
    fTipo.value = 'curso'; atualizarCamposFormacao(); $('#fItemId').value = curso.ID_Item;
    for (const [id,key] of Object.entries({fCurso:'Titulo',fInstituicao:'Instituicao',fDescricao:'Descricao',fUrl:'Url',fInicio:'DataInicio',fConclusao:'DataFim'})) $('#'+id).value = curso[key] || '';
    $('#fCurso').focus();
  });
  atualizarCamposFormacao();

  async function carregarFormacoes() {
    const containerFormacoes = $('#listaFormacoes');
    const containerCertificados = $('#listaCertificados');
    try {
      const formacoes = await api(`/candidatos/${idCandidato}/formacoes`);
      formacoesEmCache = formacoes;

      const academicas = formacoes.filter((f) => f.Nivel !== 'Certificado');
      const certificados = formacoes.filter((f) => f.Nivel === 'Certificado');

      containerFormacoes.innerHTML = academicas.length === 0
        ? '<p class="empty-state">Nenhuma formação cadastrada ainda.</p>'
        : academicas.map((f) => itemFormacaoHtml(f, false)).join('');

      containerCertificados.innerHTML = certificados.length === 0
        ? '<p class="empty-state">Nenhum certificado cadastrado ainda.</p>'
        : certificados.map((f) => itemFormacaoHtml(f, true)).join('');
    } catch (erro) {
      containerFormacoes.innerHTML = `<p class="empty-state">${escapeHtml(erro.message)}</p>`;
      containerCertificados.innerHTML = '';
    }
  }

  function itemFormacaoHtml(f, ehCertificado) {
    const periodo = ehCertificado
      ? (f.DataConclusao ? `Concluído em ${formatarData(f.DataConclusao)}` : '')
      : `${formatarData(f.DataInicio) || '—'} — ${formatarData(f.DataConclusao) || (f.Status || '—')}`;

    return `
      <div class="list-item">
        <div class="list-item__main">
          <p class="list-item__title">${escapeHtml(f.Curso)}</p>
          <p class="list-item__sub">${escapeHtml(f.Instituicao)}${!ehCertificado && f.Nivel ? ' · ' + escapeHtml(f.Nivel) : ''}</p>
          <p class="list-item__meta">${escapeHtml(periodo)}</p>
        </div>
        <div class="list-item__actions">
          <button type="button" class="btn btn-secondary" data-editar-formacao="${f.ID_Formacoes}">Editar ${ehCertificado ? 'certificado':'formação'}</button>
          <button type="button" class="btn-danger-ghost" data-remover-formacao="${f.ID_Formacoes}">Remover</button>
        </div>
      </div>
    `;
  }

  $('#formFormacao')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const ehCertificado = fTipo.value === 'certificado';
    if (fTipo.value === 'curso') {
      try {
        const curso = {tipo:'curso',titulo:$('#fCurso').value.trim(),instituicao:$('#fInstituicao').value.trim() || null,descricao:$('#fDescricao').value.trim() || null,url:$('#fUrl').value.trim() || null,data_inicio:$('#fInicio').value || null,data_fim:$('#fConclusao').value || null};
        if (curso.data_inicio && curso.data_fim && curso.data_inicio > curso.data_fim) throw new Error('A conclusão não pode anteceder o início.');
        const id = $('#fItemId').value;
        await api(id ? `/itens-profissionais/${id}` : `/candidatos/${idCandidato}/itens`, {method:id ? 'PUT':'POST',body:JSON.stringify(curso)});
        $('#cancelarFormacao').click(); mostrarToast('Curso salvo.');
      } catch (erro) {mostrarToast(erro.message, 'error');}
      return;
    }

    const payload = {
      instituicao: $('#fInstituicao').value.trim(),
      curso: $('#fCurso').value.trim(),
      nivel: ehCertificado ? 'Certificado' : ($('#fNivel').value || null),
      data_inicio: $('#fInicio').value || null,
      data_conclusao: $('#fConclusao').value || null,
      status_formacao: ehCertificado ? 'Concluído' : ($('#fStatus').value || null),
    };

    if (!ehCertificado && !payload.nivel) {
      mostrarToast('Selecione o nível da formação.', 'error');
      return;
    }

    try {
      if(payload.data_inicio && payload.data_conclusao && payload.data_inicio>payload.data_conclusao) throw new Error('A conclusão não pode anteceder o início.');
      const editando = $('#formFormacao').dataset.editando;
      await api(editando ? `/formacoes/${editando}` : `/candidatos/${idCandidato}/formacoes`, { method: editando ? 'PUT':'POST', body: JSON.stringify(payload) });
      mostrarToast(ehCertificado ? 'Certificado adicionado.' : 'Formação adicionada.');
      $('#formFormacao').reset();
      delete $('#formFormacao').dataset.editando;
      $('#fItemId').value = '';
      atualizarCamposFormacao();
      carregarFormacoes();
    } catch (erro) {
      mostrarToast(erro.message, 'error');
    }
  });

  $all('#listaFormacoes, #listaCertificados').forEach((lista) => {
    lista.addEventListener('click', async (e) => {
      if(e.target.dataset.editarFormacao) {
        const f=formacoesEmCache.find(v=>v.ID_Formacoes===e.target.dataset.editarFormacao);
        $('#fItemId').value = '';
        $('#formFormacao').dataset.editando=f.ID_Formacoes; $('#fTipo').value=f.Nivel==='Certificado' ? 'certificado':'formacao'; atualizarCamposFormacao();
        for(const [id,key] of Object.entries({fInstituicao:'Instituicao',fCurso:'Curso',fNivel:'Nivel',fInicio:'DataInicio',fConclusao:'DataConclusao',fStatus:'Status'})) $('#'+id).value=f[key] || '';
        $('#fInstituicao').focus(); return;
      }
      const id = e.target.getAttribute('data-remover-formacao');
      if (!id) return;
      try {
        await api(`/formacoes/${id}`, { method: 'DELETE' });
        carregarFormacoes();
      } catch (erro) {
        mostrarToast(erro.message, 'error');
      }
    });
  });

  /* ============================================================
     VAGAS — listagem, filtro e candidatura
     ============================================================ */

  let listaVagasCarregada = false;
  let vagasEmCache = [];
  let idsVagasCandidatadas = new Set();
  let paginaBusca = 1;
  let geracaoBusca = 0;
  const camposBusca = {palavra_chave:'fvTitulo',cargo:'fvCargo',localizacao:'fvLocalizacao',modalidade:'fvModalidade',nivel:'fvNivel',salario_min:'fvSalarioMin',salario_max:'fvSalarioMax',tipo_contrato:'fvContrato',empresa:'fvEmpresa',dias:'fvDias',habilidades:'fvHabilidades',area:'fvArea',ordenar:'fvOrdenar'};
  const queryInicial = new URLSearchParams(location.search);
  const paginaInicial = Math.max(1, Math.min(10000, Math.trunc(Number(queryInicial.get('pagina'))) || 1));
  paginaBusca = paginaInicial;
  for (const [key,id] of Object.entries(camposBusca)) if(queryInicial.has(key)) $('#'+id).value = queryInicial.get(key);
  const botaoFiltros = $('#btnFiltrosVagas');
  function alternarOpcoesBusca(aberto) {
    $('#painelFiltrosVagas').hidden = !aberto;
    $('#opcoesBuscaSalva').hidden = !aberto;
    botaoFiltros.setAttribute('aria-expanded', String(aberto));
    botaoFiltros.setAttribute('aria-label', aberto ? 'Ocultar filtros e opções de busca' : 'Mostrar filtros e opções de busca');
  }
  botaoFiltros?.addEventListener('click', () => alternarOpcoesBusca(botaoFiltros.getAttribute('aria-expanded') !== 'true'));
  if (Object.keys(camposBusca).some(key => key !== 'palavra_chave' && queryInicial.has(key))) alternarOpcoesBusca(true);
  function filtrosAtuais() {
    const f = {};
    for (const [key,id] of Object.entries(camposBusca)) if ($('#'+id).value.trim()) f[key] = ['salario_min','salario_max','dias'].includes(key) ? Number($('#'+id).value) : $('#'+id).value.trim();
    return f;
  }

  async function carregarVagas(filtros = null, pagina = 1) {
    const geracao = ++geracaoBusca;
    const container = $('#listaVagas');
    container.innerHTML = '<p class="empty-state">Buscando vagas…</p>';

    filtros = filtros || filtrosAtuais();
    const params = new URLSearchParams({...filtros, pagina, por_pagina:20});
    const url = new URL(location.href); url.search = params.toString(); history.replaceState(null,'',url);
    paginaBusca = pagina;

    try {
      const [resultado, minhasCandidaturas] = await Promise.all([
        api(`/vagas/busca?${params.toString()}`),
        api(`/candidaturas?id_candidato=${idCandidato}`).catch(() => []),
      ]);
      if(geracao !== geracaoBusca) return;
      const ultimaPagina = Math.max(1, Math.ceil(resultado.total / resultado.por_pagina));
      if (pagina > ultimaPagina) return carregarVagas(filtros, ultimaPagina);
      const vagas = resultado.resultados;
      $('#resumoBusca').textContent = `${resultado.total} vaga(s) encontrada(s). Compatibilidade calculada pelas habilidades e níveis cadastrados.`;
      $('#paginaAtual').textContent = ` Página ${pagina} de ${Math.max(1,Math.ceil(resultado.total/resultado.por_pagina))} `;
      $('#paginaAnterior').disabled = pagina <= 1;
      $('#paginaProxima').disabled = pagina * resultado.por_pagina >= resultado.total;
      vagasEmCache = vagas;
      idsVagasCandidatadas = new Set(minhasCandidaturas.map((c) => c.ID_Vagas));
      listaVagasCarregada = true;

      renderizarVagas(vagas);
    } catch (erro) {
      if(geracao === geracaoBusca) container.innerHTML = `<p class="empty-state">${escapeHtml(erro.message)}</p>`;
    }
  }

  function renderizarVagas(vagas) {
    const container = $('#listaVagas');
    if (vagas.length === 0) {
      container.innerHTML = '<p class="empty-state">Nenhuma vaga encontrada com esses filtros.</p>';
      return;
    }

    container.innerHTML = vagas.map((v) => {
      const jaCandidatado = idsVagasCandidatadas.has(v.ID_Vagas);
      const faixaSalarial = v.SalarioConfidencial
        ? 'Salário confidencial'
        : (v.SalarioMin || v.SalarioMax)
          ? `R$ ${Number(v.SalarioMin || 0).toLocaleString('pt-BR')} — R$ ${Number(v.SalarioMax || 0).toLocaleString('pt-BR')}`
          : '';

      return `
        <div class="list-item">
          <div class="list-item__main">
            <p class="list-item__title">${escapeHtml(v.Titulo)}</p>
            <p class="list-item__sub">${[v.NomeEmpresa, v.Modalidade, v.Nivel, v.Localizacao].filter(Boolean).map(escapeHtml).join(' · ')}</p>
            <p class="list-item__meta">Habilidades: ${(v.habilidades || []).map(h => escapeHtml(h.Nome)).join(', ') || 'Não informadas'}</p>
            ${v.compatibilidade != null ? `<p>Compatibilidade de habilidades: ${v.compatibilidade}%</p>` : ''}
            ${faixaSalarial ? `<p class="list-item__meta">${escapeHtml(faixaSalarial)}</p>` : ''}
          </div>
          <div class="list-item__actions">
            <button type="button" class="btn btn-secondary" data-favoritar="${v.ID_Vagas}">Favoritar</button>
            <button type="button" class="btn btn-secondary" data-ver-vaga="${v.ID_Vagas}">Ver detalhes</button>
            <button type="button" class="btn btn-secondary" data-compartilhar="${v.ID_Vagas}">Compartilhar</button>
            ${jaCandidatado
              ? '<span class="badge">Já candidatado</span>'
              : `<button type="button" class="btn btn-primary" data-candidatar="${v.ID_Vagas}">Candidatar-se</button>`}
          </div>
        </div>
      `;
    }).join('');
  }

  $('#formFiltroVagas')?.addEventListener('submit', (e) => {
    e.preventDefault();
    if ($('#fvSalarioMin').value && $('#fvSalarioMax').value && Number($('#fvSalarioMin').value)>Number($('#fvSalarioMax').value)) {mostrarToast('Revise a faixa salarial.', 'error'); return;}
    const filtros = filtrosAtuais(); carregarVagas(filtros);
    api('/buscas-historico',{method:'POST',body:JSON.stringify(filtros)}).then(carregarBuscas).catch(e => mostrarToast(e.message,'error'));
  });
  $('#paginaAnterior').addEventListener('click', () => carregarVagas(null,paginaBusca-1));
  $('#paginaProxima').addEventListener('click', () => carregarVagas(null,paginaBusca+1));
  let autocompleteTimer;
  $('#fvTitulo').addEventListener('input', () => {
    clearTimeout(autocompleteTimer);
    const term = $('#fvTitulo').value.trim();
    if (term.length<2) {$('#cargosSugeridos').replaceChildren(); return;}
    autocompleteTimer=setTimeout(async () => {
      try {const rows=await api(`/vagas/autocomplete?q=${encodeURIComponent(term)}`); if($('#fvTitulo').value.trim()===term) $('#cargosSugeridos').innerHTML=rows.map(r=>`<option value="${escapeHtml(r.Titulo)}"></option>`).join('');} catch {$('#cargosSugeridos').replaceChildren();}
    },300);
  });
  let buscasSalvas = [], historicoBuscas = [];
  async function carregarBuscas() {
    [buscasSalvas,historicoBuscas] = await Promise.all([api('/buscas'),api('/buscas-historico')]);
    $('#buscasSalvas').innerHTML = buscasSalvas.map(b=>`<div class="list-item"><p>${escapeHtml(b.Nome)} · Alertas ${b.Ativa ? 'ativos':'desativados'}</p><button type="button" class="btn btn-secondary" data-usar-busca="${escapeHtml(b.ID_Busca)}">Usar busca</button><button type="button" class="btn btn-secondary" data-alerta-busca="${escapeHtml(b.ID_Busca)}">${b.Ativa ? 'Pausar':'Ativar'} alertas</button><button type="button" class="btn-danger-ghost" data-excluir-busca="${escapeHtml(b.ID_Busca)}">Excluir busca</button></div>`).join('') || '<p>Nenhuma busca salva.</p>';
    $('#historicoBuscas').innerHTML=historicoBuscas.map((b,i)=>`<button type="button" class="btn btn-secondary" data-historico="${i}">${escapeHtml(b.Filtros.cargo || b.Filtros.palavra_chave || 'Todas as vagas')} · ${escapeHtml(b.CriadoEm)}</button>`).join('') || '<p>Nenhuma pesquisa registrada.</p>';
  }
  function usarFiltros(f) {for (const [key,id] of Object.entries(camposBusca)) $('#'+id).value = f[key] ?? (key==='ordenar' ? 'relevancia':''); carregarVagas();}
  $('#formSalvarBusca').addEventListener('submit', async e=> {
    e.preventDefault(); try {await api('/buscas',{method:'POST',body:JSON.stringify({nome:$('#nomeBusca').value.trim(),filtros:filtrosAtuais(),ativa:$('#alertaBusca').checked})}); await carregarBuscas(); mostrarToast('Busca salva. Alertas ativos aparecem nas notificações.');} catch(error) {mostrarToast(error.message,'error');}
  });
  $('#buscasSalvas').addEventListener('click',async e=> {
    const id=e.target.dataset.usarBusca || e.target.dataset.alertaBusca || e.target.dataset.excluirBusca; if(!id)return;
    const b=buscasSalvas.find(b=>b.ID_Busca===id);
    try {if(e.target.dataset.usarBusca) usarFiltros(b.Filtros); else if(e.target.dataset.excluirBusca) await api(`/buscas/${id}`,{method:'DELETE'}); else await api(`/buscas/${id}`,{method:'PUT',body:JSON.stringify({nome:b.Nome,filtros:b.Filtros,ativa:!b.Ativa})}); await carregarBuscas();} catch(error) {mostrarToast(error.message,'error');}
  });
  $('#historicoBuscas').addEventListener('click',e=> {if(e.target.dataset.historico)usarFiltros(historicoBuscas[Number(e.target.dataset.historico)].Filtros);});
  document.addEventListener('perfil:pronto',()=> {
    carregarBuscas().catch(e=>mostrarToast(e.message,'error'));
    if(Object.keys(camposBusca).some(key=>queryInicial.has(key)) || queryInicial.has('vaga')) {
      document.querySelector('[data-tab="vagas"]').click();
      if(queryInicial.has('vaga')) api(`/vagas/${encodeURIComponent(queryInicial.get('vaga'))}`).then(v=>{vagasEmCache.push(v); abrirDetalheVaga(v.ID_Vagas);}).catch(e=>mostrarToast(e.message,'error'));
    }
  });

  $('#listaVagas')?.addEventListener('click', async (e) => {
    const idVer = e.target.getAttribute('data-ver-vaga');
    const idCandidatar = e.target.getAttribute('data-candidatar');
    const idFavoritar = e.target.getAttribute('data-favoritar');
    if (e.target.dataset.compartilhar) {
      const url = new URL(location.href); url.search = new URLSearchParams({vaga:e.target.dataset.compartilhar}).toString();
      try {if(navigator.share) await navigator.share({title:'Vaga no Talentix',url:url.href}); else {await navigator.clipboard.writeText(url.href); mostrarToast('Link da vaga copiado.');}} catch(error) {if(error.name!=='AbortError')mostrarToast('Não foi possível copiar. Use o endereço da página.','error');}
    }
    if (idFavoritar) { try { await api('/favoritos', {method:'POST',body:JSON.stringify({id_vaga:idFavoritar})}); mostrarToast('Vaga adicionada aos favoritos.'); } catch(error) { mostrarToast(error.message,'error'); } }

    if (idVer) {
      abrirDetalheVaga(idVer);
    }

    if (idCandidatar) {
      await candidatarSe(idCandidatar, e.target);
    }
  });

  async function candidatarSe(idVaga) {
    try {
      const curriculos = await api(`/candidatos/${idCandidato}/curriculos`);
      if (!curriculos.length) {
        mostrarToast('Envie um currículo na seção Currículo e experiências do seu Perfil antes de se candidatar.', 'error');
        document.querySelector('[data-tab="perfil"]').click();
        fecharModalVaga();
        $('#secaoCurriculos')?.scrollIntoView({behavior:'smooth',block:'start'});
        $('#cvTitulo')?.focus({preventScroll:true});
        return;
      }
      $('#candidaturaVaga').value = idVaga;
      $('#candidaturaCarta').value = '';
      $('#candidaturaCurriculo').innerHTML = curriculos.map(c => `<option value="${escapeHtml(c.ArquivoUrl)}" ${c.Principal ? 'selected' : ''}>${escapeHtml(c.Titulo)} · versão ${Number(c.Versao || 1)}${c.Principal ? ' (principal)' : ''}</option>`).join('');
      fecharModalVaga();
      $('#modalCandidatura').showModal();
    } catch (error) { mostrarToast(error.message, 'error'); }
  }

  $('#fecharCandidatura').addEventListener('click', () => $('#modalCandidatura').close());
  $('#formCandidatura').addEventListener('submit', async event => {
    event.preventDefault(); const button = event.submitter; button.disabled = true;
    try {
      const idVaga = $('#candidaturaVaga').value;
      await api('/candidaturas', {method:'POST', body:JSON.stringify({id_vaga:idVaga, curriculo_url:$('#candidaturaCurriculo').value, carta_apresentacao:$('#candidaturaCarta').value.trim() || null})});
      idsVagasCandidatadas.add(idVaga); renderizarVagas(vagasEmCache);
      $('#modalCandidatura').close(); mostrarToast('Candidatura enviada com o currículo selecionado.');
    } catch (error) { mostrarToast(error.message, 'error'); } finally { button.disabled = false; }
  });

  /* ---------- Modal de detalhe da vaga ---------- */

  const modalVaga = $('#modalVaga');
  function abrirDetalheVaga(idVaga) {
    const vaga = vagasEmCache.find((v) => v.ID_Vagas === idVaga);
    if (!vaga) return;

    const jaCandidatado = idsVagasCandidatadas.has(idVaga);

    $('#modalVagaConteudo').innerHTML = `
      <h2 id="modalVagaTitulo">${escapeHtml(vaga.Titulo)}</h2>
      <p class="list-item__sub" style="margin-bottom:16px;">
        ${[vaga.Modalidade, vaga.Nivel, vaga.TipoContrato, vaga.Localizacao].filter(Boolean).map(escapeHtml).join(' · ')}
      </p>
      <p style="white-space:pre-line;">${escapeHtml(vaga.Descricao)}</p>
      <div class="form-actions" style="margin-top:20px;">
        ${jaCandidatado
          ? '<span class="badge">Você já se candidatou a esta vaga</span>'
          : `<button type="button" class="btn btn-primary" data-candidatar="${vaga.ID_Vagas}">Candidatar-se a esta vaga</button>`}
      </div>
    `;
    modalVaga.showModal();
  }

  function fecharModalVaga() {
    modalVaga.close();
  }

  $('#fecharModalVaga')?.addEventListener('click', fecharModalVaga);
  modalVaga?.addEventListener('click', (e) => { if (e.target === modalVaga) fecharModalVaga(); });
  $('#modalVagaConteudo')?.addEventListener('click', async (e) => {
    const id = e.target.getAttribute('data-candidatar');
    if (id) await candidatarSe(id, e.target);
  });

  /* ============================================================
     MINHAS CANDIDATURAS
     ============================================================ */

  async function carregarCandidaturas() {
    const container = $('#listaCandidaturas');
    container.innerHTML = '<p class="empty-state">Carregando suas candidaturas…</p>';

    try {
      const candidaturas = await api(`/candidaturas?id_candidato=${idCandidato}`);
      if (candidaturas.length === 0) {
        container.innerHTML = '<p class="empty-state">Você ainda não se candidatou a nenhuma vaga.</p>';
        return;
      }

      container.innerHTML = candidaturas.map((c) => {
        const statusTexto = statusCandidaturaMap[c.ID_Status_Candidatura] || `Status ${c.ID_Status_Candidatura}`;
        const classeBadge = classeBadgeStatus(statusTexto);

        return `
          <div class="list-item">
            <div class="list-item__main">
              <p class="list-item__title">${escapeHtml(c.TituloVaga)}</p>
              <p class="list-item__meta">Candidatura enviada em ${formatarData(c.CriadaEm)}</p>
              ${c.CurriculoUrl ? `<p><a href="${escapeHtml(Talentix.safeUrl(c.CurriculoUrl))}" target="_blank" rel="noopener">Currículo anexado</a></p>` : '<p>Nenhum currículo anexado.</p>'}
            </div>
            <div class="list-item__actions">
              <span class="badge ${classeBadge}">${escapeHtml(statusTexto)}</span>
              <button class="btn btn-secondary" type="button" data-acompanhar="${escapeHtml(c.ID_Candidaturas)}">Etapas e entrevistas</button>
              <button class="btn btn-secondary" type="button" data-empresa-mensagem="${escapeHtml(c.ID_Usuario_Empresa)}" data-contexto="${escapeHtml(c.ID_Candidaturas)}">Mensagem à empresa</button>
            </div>
          </div>
        `;
      }).join('');
    } catch (erro) {
      container.innerHTML = `<p class="empty-state">${escapeHtml(erro.message)}</p>`;
    }
  }

  function classeBadgeStatus(texto) {
    const t = texto.toLowerCase();
    if (t.includes('aprovad')) return '';
    if (t.includes('recusad') || t.includes('cancelad')) return 'badge--danger';
    if (t.includes('entrevista') || t.includes('triagem') || t.includes('análise')) return 'badge--warn';
    return 'badge--muted';
  }

  /* ============================================================ */


  $('#fecharAcompanhamento').addEventListener('click', () => $('#modalAcompanhamento').close());
  $('#listaCandidaturas').addEventListener('click', async event => {
    const button = event.target.closest('button'); if (!button) return;
    try {
      if (button.dataset.empresaMensagem) { await Talentix.conversation(button.dataset.empresaMensagem, button.dataset.contexto); return; }
      if (!button.dataset.acompanhar) return;
      const c = await api(`/candidaturas/${button.dataset.acompanhar}`);
      const labels = {1:'Agendada',2:'Realizada',3:'Reagendada',4:'Cancelada',5:'Não compareceu'};
      $('#acompanhamentoConteudo').innerHTML = `<h3>Etapas do processo</h3>${c.etapas.map(e => `<p>${escapeHtml(e.Ordem)}. ${escapeHtml(e.Nome)} — ${e.ID_Status_Etapa === 3 ? 'Concluída' : 'Em andamento'}</p>`).join('')}<h3>Entrevistas</h3>${c.entrevistas.length ? c.entrevistas.map(e => `<p>${escapeHtml(e.DataHora)} — ${escapeHtml(labels[e.ID_Status_Entrevista])}</p><p>${escapeHtml(e.LocalOuLink)}</p>`).join('') : '<p>Nenhuma entrevista agendada.</p>'}<button class="btn btn-secondary" data-solicitar-analise="${escapeHtml(c.ID_Vagas)}" data-candidatura="${escapeHtml(c.ID_Candidaturas)}">Analisar compatibilidade</button>`;
      $('#modalAcompanhamento').showModal();
    } catch (error) { mostrarToast(error.message, 'error'); }
  });
  $('#acompanhamentoConteudo').addEventListener('click', async event => {
    if (!event.target.dataset.solicitarAnalise) return;
    event.target.disabled = true;
    try { await api('/analises-ia', {method:'POST',body:JSON.stringify({id_candidato:idCandidato,id_vaga:event.target.dataset.solicitarAnalise,id_candidatura:event.target.dataset.candidatura})}); mostrarToast('Análise solicitada. Acompanhe na aba Desenvolvimento.'); }
    catch(error) { mostrarToast(error.message, 'error'); } finally { event.target.disabled = false; }
  });
  let developmentTimer;
  async function carregarDesenvolvimento() {
    clearTimeout(developmentTimer);
    const [analyses,jobs,courses,favorites] = await Promise.all([api(`/analises-ia?id_candidato=${idCandidato}`),api(`/candidatos/${idCandidato}/recomendacoes-vaga`),api(`/candidatos/${idCandidato}/recomendacoes-curso`),api('/favoritos')]);
    const statuses = {1:'Na fila',2:'Processando',3:'Concluída',4:'Falhou'};
    $('#listaAnalises').innerHTML = analyses.length ? analyses.map(a => `<article class="list-item"><div><h3>${escapeHtml(statuses[a.ID_Status_Processamento_IA])}${a.ID_Status_Processamento_IA === 3 ? ` · ${escapeHtml(a.ScoreCompatibilidade)}% de compatibilidade` : ''}</h3><p>${escapeHtml(a.Justificativa)}</p>${a.PontosFortes ? `<p>Pontos fortes: ${escapeHtml(a.PontosFortes)}</p>` : ''}${a.Lacunas ? `<p>A desenvolver: ${escapeHtml(a.Lacunas)}</p>` : ''}</div></article>`).join('') : '<p class="empty-state">Solicite uma análise pelo acompanhamento de uma candidatura.</p>';
    $('#listaRecomendacoesVaga').innerHTML = jobs.length ? jobs.map(r => `<article class="list-item"><div><h3>${escapeHtml(r.Titulo)} · ${escapeHtml(r.Score)}%</h3><p>${escapeHtml(r.Motivo)}</p></div></article>`).join('') : '<p class="empty-state">Nenhuma vaga recomendada ainda.</p>';
    $('#listaRecomendacoesCurso').innerHTML = courses.length ? courses.map(r => `<article class="list-item"><div><h3>${escapeHtml(r.Titulo)}</h3><p>${escapeHtml(r.Motivo)}</p>${r.Url ? `<a href="${escapeHtml(Talentix.safeUrl(r.Url))}" target="_blank" rel="noopener">Acessar curso</a>` : ''}</div>${r.Concluida ? '<span class="badge">Concluído</span>' : `<button class="btn btn-secondary" data-concluir-curso="${escapeHtml(r.ID_Recomendacoes_Curso)}">Marcar concluído</button>`}</article>`).join('') : '<p class="empty-state">Nenhum curso recomendado ainda.</p>';
    $('#listaFavoritos').innerHTML = favorites.length ? favorites.map(f => `<article class="list-item"><h3>${escapeHtml(f.Titulo)}</h3><button class="btn-danger-ghost" data-remover-favorito="${escapeHtml(f.ID_Vagas)}">Remover</button></article>`).join('') : '<p class="empty-state">Nenhuma vaga favorita.</p>';
    if (analyses.some(a=>[1,2].includes(a.ID_Status_Processamento_IA))) developmentTimer = setTimeout(() => { if ($('#tab-recomendacoes').classList.contains('active')) carregarDesenvolvimento().catch(e=>mostrarToast(e.message,'error')); },5000);
  }
  $('#tab-recomendacoes').addEventListener('click', async event => {
    try {
      if (event.target.dataset.concluirCurso) await api(`/recomendacoes-curso/${event.target.dataset.concluirCurso}/concluir`,{method:'PATCH'});
      else if (event.target.dataset.removerFavorito) await api(`/favoritos/${event.target.dataset.removerFavorito}`,{method:'DELETE'});
      else return;
      await carregarDesenvolvimento();
    } catch(error) { mostrarToast(error.message,'error'); }
  });

  inicializar();
});
