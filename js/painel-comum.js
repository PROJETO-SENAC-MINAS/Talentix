/* Utilitários compartilhados dos painéis; todas as operações usam a sessão da API. */
window.Talentix = (() => {
  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeUrl = (value) => {
    try { const url = new URL(value, API_BASE_URL); return ['http:', 'https:'].includes(url.protocol) ? url.href : '#'; }
    catch { return '#'; }
  };
  async function api(path, options = {}) {
    let response;
    try {
      response = await fetch(`${API_BASE_URL}${path}`, {
        credentials: 'include', ...options,
        headers: options.body instanceof FormData ? options.headers : {'Content-Type':'application/json', ...options.headers},
      });
    } catch {
      throw new Error(`Não foi possível conectar à API em ${API_BASE_URL}. Verifique se o FastAPI está em execução e recarregue a página.`);
    }
    const body = await response.json().catch(() => null);
    if (response.status === 401) { window.location.assign('login.html'); throw new Error('Sessão encerrada.'); }
    if (!response.ok) throw new Error(Array.isArray(body?.detail) ? body.detail.map(d => d.msg).join(' ') : body?.detail || 'Não foi possível concluir a operação.');
    return body;
  }
  function toast(message, error = false) {
    const target = $('#toast');
    if (!target) return;
    target.textContent = message; target.classList.toggle('error', error); target.classList.add('show');
    clearTimeout(target._timer); target._timer = setTimeout(() => target.classList.remove('show'), 5000);
  }
  function bindTabs(onChange = () => {}) {
    document.querySelectorAll('.nav-item[data-tab]').forEach(button => button.addEventListener('click', () => {
      document.querySelectorAll('.nav-item, .tab-panel').forEach(el => el.classList.remove('active'));
      button.classList.add('active'); $(`#tab-${button.dataset.tab}`)?.classList.add('active');
      Promise.resolve(onChange(button.dataset.tab)).catch(error => toast(error.message, true));
    }));
  }
  function bindLogout() { $('#btnLogout')?.addEventListener('click', async () => { try { await api('/auth/logout', {method:'POST'}); window.location.assign('login.html'); } catch(error) { toast(error.message, true); } }); }
  async function notifications() {
    const target = $('#listaNotificacoes'); if (!target) return;
    const records = await api('/notificacoes');
    target.innerHTML = records.length ? records.map(n => `<article class="list-item"><div class="list-item__main"><h2 class="list-item__heading">${esc(n.Titulo)}</h2><p>${esc(n.Mensagem)}</p></div>${n.Lida ? '<span class="badge">Lida</span>' : `<button class="btn btn-secondary" data-notificacao="${esc(n.ID_Notificacoes)}">Marcar como lida</button>`}</article>`).join('') : '<p class="empty-state">Nenhuma notificação.</p>';
  }
  async function messages() {
    const target = $('#listaMensagens'); if (!target) return;
    const records = await api('/mensagens');
    target.innerHTML = records.length ? records.map(m => `<article class="list-item"><div class="list-item__main"><h2 class="list-item__heading">${esc(m.NomeRemetente || 'Mensagem recebida')}</h2><p>${esc(m.Conteudo)}</p><p>${esc(m.EnviadaEm)}</p></div><button class="btn btn-secondary" data-responder="${esc(m.ID_Remetente)}" data-contexto="${esc(m.ID_Candidaturas || '')}" data-msg="${esc(m.ID_Mensagens)}">Responder</button></article>`).join('') : '<p class="empty-state">Nenhuma mensagem recebida.</p>';
  }
  async function conversation(user, context) {
    $('#msgDestinatario').value = user; $('#msgContexto').value = context || '';
    const records = await api(`/mensagens/conversas/${encodeURIComponent(user)}`);
    $('#conversa').innerHTML = records.map(m => `<p><strong>${esc(m.NomeRemetente || 'Usuário')}:</strong> ${esc(m.Conteudo)}</p>`).join('') || '<p>Inicie a conversa.</p>';
    $('#modalMensagem').showModal(); $('#msgConteudo').focus();
  }
  function bindCommunication() {
    $('#listaNotificacoes')?.addEventListener('click', async event => {
      const id = event.target.dataset.notificacao; if (!id) return;
      try { await api(`/notificacoes/${id}/marcar-lida`, {method:'PATCH'}); await notifications(); } catch(error) { toast(error.message, true); }
    });
    $('#listaMensagens')?.addEventListener('click', async event => {
      const button = event.target.closest('[data-responder]'); if (!button) return;
      try { await api(`/mensagens/${button.dataset.msg}/marcar-lida`, {method:'PATCH'}); await conversation(button.dataset.responder, button.dataset.contexto); } catch(error) { toast(error.message, true); }
    });
    $('#fecharMensagem')?.addEventListener('click', () => $('#modalMensagem').close());
    $('#formMensagem')?.addEventListener('submit', async event => {
      event.preventDefault(); const button = event.submitter; button.disabled = true;
      try {
        await api('/mensagens', {method:'POST', body:JSON.stringify({id_destinatario:$('#msgDestinatario').value, id_candidatura:$('#msgContexto').value || null, conteudo:$('#msgConteudo').value.trim()})});
        $('#msgConteudo').value = ''; await conversation($('#msgDestinatario').value, $('#msgContexto').value); toast('Mensagem enviada.');
      } catch(error) { toast(error.message, true); } finally { button.disabled = false; }
    });
  }
  return {$, esc, safeUrl, api, toast, bindTabs, bindLogout, notifications, messages, conversation, bindCommunication};
})();
