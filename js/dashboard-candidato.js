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
    const resposta = await fetch(`${API_BASE_URL}${path}`, {
      credentials: 'include',
      headers: options.body instanceof FormData
        ? undefined
        : { 'Content-Type': 'application/json' },
      ...options,
    });

    if (resposta.status === 401) {
      window.location.href = 'login.html';
      throw new Error('Não autenticado');
    }

    const corpo = await resposta.json().catch(() => null);

    if (!resposta.ok) {
      const msg = Array.isArray(corpo?.detail)
        ? corpo.detail.map((d) => d.msg).join(' ')
        : (corpo?.detail || 'Ocorreu um erro inesperado.');
      throw new Error(msg);
    }

    return corpo;
  }

  function formatarData(iso) {
    if (!iso) return '';
    const [ano, mes, dia] = String(iso).slice(0, 10).split('-');
    return `${dia}/${mes}/${ano}`;
  }

  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  /* ============================================================
     Navegação entre abas
     ============================================================ */

  $all('.nav-item').forEach((botao) => {
    botao.addEventListener('click', () => {
      $all('.nav-item').forEach((b) => b.classList.remove('active'));
      $all('.tab-panel').forEach((p) => p.classList.remove('active'));
      botao.classList.add('active');
      $(`#tab-${botao.dataset.tab}`).classList.add('active');

      if (botao.dataset.tab === 'vagas' && !listaVagasCarregada) carregarVagas();
      if (botao.dataset.tab === 'candidaturas') carregarCandidaturas();
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

    await carregarStatusCandidatura();
    await carregarCandidato();
  }

    async function carregarCandidato() {
    try {
      const meu = await api('/candidatos/me');
      idCandidato = meu.ID_Candidatos;
      preencherFormPerfil(meu);
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

  async function carregarCandidaturas() {
    const container = $('#listaCandidaturas');
    container.innerHTML = '<p class="empty-state">Carregando suas candidaturas…</p>';

    // A API não tem "GET /candidatos/me"; localizamos pelo ID do
    // usuário logado, listando e filtrando no client não é ideal —
    // por isso usamos diretamente os dados básicos de /auth/me e
    // buscamos o registro de Candidatos pela listagem filtrável.
    // Para manter simples e correto, guardamos o ID assim que a
    // primeira ação de escrita (perfil) precisar dele: ele já vem
    // implícito nas respostas de currículo/experiência/formação
    // que exigem id_candidato na URL. Buscamos aqui via candidatos
    // (rota pública) filtrando não é suportado por usuário, então
    // resolvemos com um endpoint auxiliar: tentamos obter pela
    // listagem geral não é viável em produção — usamos o próprio
    // ID de usuário como chave de busca não suportada pela API.
    //
    // Solução real usada: o backend cria Candidatos com
    // ID_Usuarios = sessao.id_usuario no cadastro. Como não há
    // endpoint de busca por ID_Usuarios exposto publicamente,
    // pedimos ao backend via /candidatos e filtramos no cliente.
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
              <p class="list-item__sub">${escapeHtml(c.NomeEmpresa || '')} ${c.LocalizacaoVaga ? '· ' + escapeHtml(c.LocalizacaoVaga) : ''}</p>
              <p class="list-item__meta">Candidatura enviada em ${formatarData(c.CriadaEm)}</p>
            </div>
            <div class="list-item__actions">
              <span class="badge ${classeBadge}">${escapeHtml(statusTexto)}</span>
            </div>
          </div>
        `;
      }).join('');
    } catch (erro) {
      container.innerHTML = `<p class="empty-state">${escapeHtml(erro.message)}</p>`;
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
          body: JSON.stringify({ nome, categoria: null }),
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

    async function carregarCurriculos() {
    const container = $('#listaCurriculos');
    try {
      const curriculos = await api(`/candidatos/${idCandidato}/curriculos`);
      if (curriculos.length === 0) {
        container.innerHTML = '<p class="empty-state">Nenhum currículo enviado ainda.</p>';
        return;
      }
      container.innerHTML = curriculos.map((c) => {
        const tamanhoKb = c.ArquivoTamanhoBytes ? (Number(c.ArquivoTamanhoBytes) / 1024).toFixed(0) : '—';
        return `
          <div class="list-item">
            <div class="list-item__main">
              <p class="list-item__title">${escapeHtml(c.Titulo)} ${c.Principal ? '<span class="badge">Principal</span>' : ''}</p>
              <p class="list-item__sub">${tamanhoKb} KB · ${escapeHtml(c.ArquivoTipoMime || '')}</p>
            </div>
            <div class="list-item__actions">
              <a class="btn btn-secondary" style="text-decoration:none;padding:7px 12px;font-size:12.5px;" href="${API_BASE_URL}${c.ArquivoUrl}" target="_blank" rel="noopener">Abrir</a>
              <button type="button" class="btn-danger-ghost" data-remover-curriculo="${c.ID_Curriculos}">Remover</button>
            </div>
          </div>
        `;
      }).join('');
    } catch (erro) {
      container.innerHTML = `<p class="empty-state">${escapeHtml(erro.message)}</p>`;
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
    formData.append('arquivo', arquivo);

    try {
      await api(`/candidatos/${idCandidato}/curriculos`, { method: 'POST', body: formData });
      mostrarToast('Currículo enviado com sucesso.');
      $('#formCurriculo').reset();
      carregarCurriculos();
    } catch (erro) {
      mostrarToast(erro.message, 'error');
    } finally {
      botao.removeAttribute('data-loading');
    }
  });

  $('#listaCurriculos')?.addEventListener('click', async (e) => {
    const id = e.target.getAttribute('data-remover-curriculo');
    if (!id) return;
    if (!confirm('Remover este currículo?')) return;
    try {
      await api(`/curriculos/${id}`, { method: 'DELETE' });
      mostrarToast('Currículo removido.');
      carregarCurriculos();
    } catch (erro) {
      mostrarToast(erro.message, 'error');
    }
  });

  async function carregarExperiencias() {
    const container = $('#listaExperiencias');
    try {
      const experiencias = await api(`/candidatos/${idCandidato}/experiencias`);
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
      await api(`/candidatos/${idCandidato}/experiencias`, { method: 'POST', body: JSON.stringify(payload) });
      mostrarToast('Experiência adicionada.');
      $('#formExperiencia').reset();
      carregarExperiencias();
    } catch (erro) {
      mostrarToast(erro.message, 'error');
    }
  });

  $('#listaExperiencias')?.addEventListener('click', async (e) => {
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
    $('#grupoNivelFormacao').style.display = ehCertificado ? 'none' : '';
    $('#grupoStatusFormacao').style.display = ehCertificado ? 'none' : '';
    $('#fInstituicao').placeholder = ehCertificado ? 'Ex: Alura, AWS, Google...' : 'Ex: UFMG, Alura, Coursera...';
    $('#fCurso').placeholder = ehCertificado ? 'Ex: AWS Cloud Practitioner' : 'Ex: Ciência da Computação';
  }
  fTipo?.addEventListener('change', atualizarCamposFormacao);
  atualizarCamposFormacao();

  async function carregarFormacoes() {
    const containerFormacoes = $('#listaFormacoes');
    const containerCertificados = $('#listaCertificados');
    try {
      const formacoes = await api(`/candidatos/${idCandidato}/formacoes`);

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
          <button type="button" class="btn-danger-ghost" data-remover-formacao="${f.ID_Formacoes}">Remover</button>
        </div>
      </div>
    `;
  }

  $('#formFormacao')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const ehCertificado = fTipo.value === 'certificado';

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
      await api(`/candidatos/${idCandidato}/formacoes`, { method: 'POST', body: JSON.stringify(payload) });
      mostrarToast(ehCertificado ? 'Certificado adicionado.' : 'Formação adicionada.');
      $('#formFormacao').reset();
      atualizarCamposFormacao();
      carregarFormacoes();
    } catch (erro) {
      mostrarToast(erro.message, 'error');
    }
  });

  $all('#listaFormacoes, #listaCertificados').forEach((lista) => {
    lista.addEventListener('click', async (e) => {
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

  async function carregarVagas(filtros = {}) {
    const container = $('#listaVagas');
    container.innerHTML = '<p class="empty-state">Buscando vagas…</p>';

    const params = new URLSearchParams({ apenas_publicadas: 'true' });
    if (filtros.titulo) params.set('titulo', filtros.titulo);
    if (filtros.localizacao) params.set('localizacao', filtros.localizacao);
    if (filtros.modalidade) params.set('modalidade', filtros.modalidade);
    if (filtros.nivel) params.set('nivel', filtros.nivel);

    try {
      const [vagas, minhasCandidaturas] = await Promise.all([
        api(`/vagas?${params.toString()}`),
        api(`/candidaturas?id_candidato=${idCandidato}`).catch(() => []),
      ]);

      vagasEmCache = vagas;
      idsVagasCandidatadas = new Set(minhasCandidaturas.map((c) => c.ID_Vagas));
      listaVagasCarregada = true;

      renderizarVagas(vagas);
    } catch (erro) {
      container.innerHTML = `<p class="empty-state">${escapeHtml(erro.message)}</p>`;
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
            <p class="list-item__sub">${[v.Modalidade, v.Nivel, v.Localizacao].filter(Boolean).map(escapeHtml).join(' · ')}</p>
            ${faixaSalarial ? `<p class="list-item__meta">${escapeHtml(faixaSalarial)}</p>` : ''}
          </div>
          <div class="list-item__actions">
            <button type="button" class="btn btn-secondary" data-ver-vaga="${v.ID_Vagas}">Ver detalhes</button>
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
    carregarVagas({
      titulo: $('#fvTitulo').value.trim(),
      localizacao: $('#fvLocalizacao').value.trim(),
      modalidade: $('#fvModalidade').value,
      nivel: $('#fvNivel').value,
    });
  });

  $('#listaVagas')?.addEventListener('click', async (e) => {
    const idVer = e.target.getAttribute('data-ver-vaga');
    const idCandidatar = e.target.getAttribute('data-candidatar');

    if (idVer) {
      abrirDetalheVaga(idVer);
    }

    if (idCandidatar) {
      await candidatarSe(idCandidatar, e.target);
    }
  });

  async function candidatarSe(idVaga, botao) {
    botao.setAttribute('data-loading', 'true');
    botao.disabled = true;
    try {
      await api('/candidaturas', { method: 'POST', body: JSON.stringify({ id_vaga: idVaga }) });
      mostrarToast('Candidatura enviada com sucesso!');
      idsVagasCandidatadas.add(idVaga);
      renderizarVagas(vagasEmCache);
      fecharModalVaga();
    } catch (erro) {
      mostrarToast(erro.message, 'error');
      botao.disabled = false;
      botao.removeAttribute('data-loading');
    }
  }

  /* ---------- Modal de detalhe da vaga ---------- */

  const modalVaga = $('#modalVaga');
  function abrirDetalheVaga(idVaga) {
    const vaga = vagasEmCache.find((v) => v.ID_Vagas === idVaga);
    if (!vaga) return;

    const jaCandidatado = idsVagasCandidatadas.has(idVaga);

    $('#modalVagaConteudo').innerHTML = `
      <h3>${escapeHtml(vaga.Titulo)}</h3>
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
    modalVaga.classList.add('show');
  }

  function fecharModalVaga() {
    modalVaga.classList.remove('show');
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

      // Busca o título da vaga para cada candidatura (a listagem não traz join).
      const vagasIds = [...new Set(candidaturas.map((c) => c.ID_Vagas))];
      const vagasDetalhe = await Promise.all(
        vagasIds.map((id) => api(`/vagas/${id}`).catch(() => null))
      );
      const vagaPorId = Object.fromEntries(
        vagasDetalhe.filter(Boolean).map((v) => [v.ID_Vagas, v])
      );

      container.innerHTML = candidaturas.map((c) => {
        const vaga = vagaPorId[c.ID_Vagas];
        const statusTexto = statusCandidaturaMap[c.ID_Status_Candidatura] || `Status ${c.ID_Status_Candidatura}`;
        const classeBadge = classeBadgeStatus(statusTexto);

        return `
          <div class="list-item">
            <div class="list-item__main">
              <p class="list-item__title">${escapeHtml(vaga ? vaga.Titulo : 'Vaga não encontrada')}</p>
              <p class="list-item__meta">Candidatura enviada em ${formatarData(c.CriadaEm)}</p>
            </div>
            <div class="list-item__actions">
              <span class="badge ${classeBadge}">${escapeHtml(statusTexto)}</span>
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

  inicializar();
});