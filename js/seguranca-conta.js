
document.addEventListener('DOMContentLoaded', () => {
  if (!window.Talentix) return;

  const {api, esc, toast} = Talentix;
  const nav = document.querySelector('.sidebar__nav');
  const main = document.querySelector('main.content');
  if (!nav || !main || document.querySelector('[data-tab="seguranca"]')) return;

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'nav-item';
  btn.dataset.tab = 'seguranca';
  btn.textContent = 'Segurança';
  nav.appendChild(btn);

  const section = document.createElement('section');
  section.className = 'tab-panel';
  section.id = 'tab-seguranca';
  section.innerHTML = `
    <header class="content__header">
      <div>
        <h1>Segurança e configurações</h1>
        <p class="content__sub">Gerencie sua conta, sessões e preferências visuais do Talentix.</p>
      </div>
    </header>

    <div class="card settings-card">
      <h2>Preferências do site</h2>
      <p class="content__sub">As preferências ficam salvas somente neste navegador.</p>
      <div class="settings-grid">
        <label class="setting-toggle">
          <span><strong>Tema escuro</strong><small>Reduz o brilho da interface.</small></span>
          <input id="settingDarkMode" type="checkbox">
        </label>
        <label class="setting-toggle">
          <span><strong>Controles de acessibilidade</strong><small>Exibe os atalhos flutuantes de contraste e texto.</small></span>
          <input id="settingA11yEnabled" type="checkbox">
        </label>
        <label class="setting-toggle">
          <span><strong>Alto contraste</strong><small>Aumenta o contraste visual da interface.</small></span>
          <input id="settingHighContrast" type="checkbox">
        </label>
        <label class="setting-toggle">
          <span><strong>Texto ampliado</strong><small>Aumenta o tamanho-base dos textos.</small></span>
          <input id="settingLargeText" type="checkbox">
        </label>
        <label class="setting-toggle">
          <span><strong>Reduzir animações</strong><small>Minimiza transições e movimentos na interface.</small></span>
          <input id="settingReducedMotion" type="checkbox">
        </label>
      </div>
    </div>

    <div class="card">
      <h2>Status da conta</h2>
      <div id="securityStatus" aria-live="polite">Carregando…</div>
    </div>

    <div class="card">
      <h2>Alterar senha</h2>
      <form id="securityPassword">
        <div class="field">
          <label for="secCurrentPassword">Senha atual</label>
          <input id="secCurrentPassword" type="password" autocomplete="current-password" required>
        </div>
        <div class="field">
          <label for="secNewPassword">Nova senha</label>
          <input id="secNewPassword" type="password" autocomplete="new-password" required minlength="10">
        </div>
        <button class="btn btn-primary" type="submit">Alterar senha</button>
      </form>
    </div>

    <div class="card">
      <h2>Autenticação em dois fatores</h2>
      <p id="security2faText"></p>
      <button class="btn btn-secondary" id="security2faStart" type="button">Configurar 2FA</button>
      <div id="security2faSetup" hidden>
        <p>Adicione a chave ao seu aplicativo autenticador:</p>
        <code id="security2faSecret" class="account-id"></code>
        <div class="field">
          <label for="security2faCode">Código de 6 dígitos</label>
          <input id="security2faCode" inputmode="numeric" pattern="[0-9]{6}" maxlength="6">
        </div>
        <button class="btn btn-primary" id="security2faConfirm" type="button">Confirmar 2FA</button>
      </div>
      <div id="security2faDisable" hidden>
        <div class="grid-2">
          <div class="field">
            <label for="security2faDisablePassword">Senha atual</label>
            <input id="security2faDisablePassword" type="password" autocomplete="current-password">
          </div>
          <div class="field">
            <label for="security2faDisableCode">Código atual</label>
            <input id="security2faDisableCode" inputmode="numeric" pattern="[0-9]{6}" maxlength="6">
          </div>
        </div>
        <button class="btn-danger-ghost" id="security2faDisableButton" type="button">Desativar 2FA</button>
      </div>
    </div>

    <div class="card">
      <div class="content__header">
        <div>
          <h2>Sessões ativas</h2>
          <p class="content__sub">Encerre acessos que você não reconhece.</p>
        </div>
        <button class="btn btn-secondary" id="securityCloseAll" type="button">Encerrar todas</button>
      </div>
      <div class="list" id="securitySessions"></div>
    </div>
  `;
  main.insertBefore(section, main.querySelector('.page-footer'));

  let me = null;
  const fmt = value => value ? new Date(value).toLocaleString('pt-BR') : '—';

  function ativarAbaSeguranca() {
    document.querySelectorAll('.nav-item, .tab-panel').forEach(el => el.classList.remove('active'));
    btn.classList.add('active');
    section.classList.add('active');
  }

  function aplicarPreferencias() {
    const root = document.documentElement;
    const dark = localStorage.getItem('talentix-theme') === 'dark';
    const enabled = localStorage.getItem('talentix-a11y-enabled') !== 'false';
    const contrast = enabled && localStorage.getItem('talentix-a11y-contrast') === 'high';
    const large = enabled && localStorage.getItem('talentix-a11y-text') === 'large';
    const reduced = localStorage.getItem('talentix-reduced-motion') === 'true';

    root.dataset.theme = dark ? 'dark' : '';
    root.dataset.a11yContrast = contrast ? 'high' : '';
    root.dataset.a11yText = large ? 'large' : '';
    root.dataset.reducedMotion = reduced ? 'true' : '';

    document.querySelectorAll('.a11y-toolbar').forEach(el => {
      el.hidden = !enabled;
    });

    document.querySelector('#settingDarkMode').checked = dark;
    document.querySelector('#settingA11yEnabled').checked = enabled;
    document.querySelector('#settingHighContrast').checked = contrast;
    document.querySelector('#settingLargeText').checked = large;
    document.querySelector('#settingReducedMotion').checked = reduced;
    document.querySelector('#settingHighContrast').disabled = !enabled;
    document.querySelector('#settingLargeText').disabled = !enabled;
  }

  function salvarToggle(id, chave, valorAtivo, valorInativo = '') {
    document.querySelector(id)?.addEventListener('change', event => {
      localStorage.setItem(chave, event.target.checked ? valorAtivo : valorInativo);
      aplicarPreferencias();
      window.dispatchEvent(new CustomEvent('talentix:preferences-changed'));
    });
  }

  salvarToggle('#settingDarkMode', 'talentix-theme', 'dark');
  salvarToggle('#settingA11yEnabled', 'talentix-a11y-enabled', 'true', 'false');
  salvarToggle('#settingHighContrast', 'talentix-a11y-contrast', 'high');
  salvarToggle('#settingLargeText', 'talentix-a11y-text', 'large');
  salvarToggle('#settingReducedMotion', 'talentix-reduced-motion', 'true', 'false');

  async function load() {
    me = await api('/auth/me');
    document.querySelector('#securityStatus').innerHTML =
      '<p><strong>E-mail:</strong> ' + esc(me.Email) + ' · ' +
      (me.email_confirmado ? 'confirmado' : 'pendente') + '</p>' +
      '<p><strong>Último login:</strong> ' + esc(fmt(me.UltimoLoginEm)) + '</p>';

    document.querySelector('#security2faText').textContent =
      me.two_factor_ativo ? '2FA está ativo nesta conta.' : '2FA ainda não está ativo.';
    document.querySelector('#security2faStart').hidden = Boolean(me.two_factor_ativo);
    document.querySelector('#security2faDisable').hidden = !me.two_factor_ativo;

    const sessions = await api('/auth/sessoes');
    document.querySelector('#securitySessions').innerHTML = sessions.length
      ? sessions.map(s =>
          '<article class="list-item"><div><h3>' +
          (s.Atual ? 'Este dispositivo' : 'Sessão') +
          '</h3><p>' + esc(s.UserAgent || 'Dispositivo não identificado') +
          '</p><p>Última atividade: ' + esc(fmt(s.UltimaAtividadeEm)) +
          '</p></div>' +
          (s.RevogadaEm
            ? '<span class="badge badge-muted">Encerrada</span>'
            : '<button class="btn btn-secondary" data-session="' + esc(s.ID_Sessoes) + '" type="button">Encerrar</button>') +
          '</article>'
        ).join('')
      : '<p class="empty-state">Nenhuma sessão registrada.</p>';
  }

  btn.addEventListener('click', () => {
    ativarAbaSeguranca();
    aplicarPreferencias();
    load().catch(error => toast(error.message, true));
  });

  document.querySelector('#securityPassword').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      await api('/auth/alterar-senha', {
        method: 'POST',
        body: JSON.stringify({
          senha_atual: document.querySelector('#secCurrentPassword').value,
          nova_senha: document.querySelector('#secNewPassword').value,
        }),
      });
      window.location.assign('login.html');
    } catch (error) {
      toast(error.message, true);
    }
  });

  document.querySelector('#security2faStart').addEventListener('click', async () => {
    try {
      const data = await api('/auth/2fa/iniciar', {method: 'POST'});
      document.querySelector('#security2faSecret').textContent = data.secret;
      document.querySelector('#security2faSetup').hidden = false;
      document.querySelector('#security2faCode').focus();
    } catch (error) {
      toast(error.message, true);
    }
  });

  document.querySelector('#security2faConfirm').addEventListener('click', async () => {
    try {
      await api('/auth/2fa/confirmar', {
        method: 'POST',
        body: JSON.stringify({codigo: document.querySelector('#security2faCode').value}),
      });
      toast('2FA ativado.');
      document.querySelector('#security2faSetup').hidden = true;
      await load();
    } catch (error) {
      toast(error.message, true);
    }
  });

  document.querySelector('#security2faDisableButton').addEventListener('click', async () => {
    try {
      await api('/auth/2fa', {
        method: 'DELETE',
        body: JSON.stringify({
          senha: document.querySelector('#security2faDisablePassword').value,
          codigo: document.querySelector('#security2faDisableCode').value,
        }),
      });
      toast('2FA desativado.');
      await load();
    } catch (error) {
      toast(error.message, true);
    }
  });

  document.querySelector('#securitySessions').addEventListener('click', async event => {
    const id = event.target.dataset.session;
    if (!id) return;
    try {
      await api('/auth/sessoes/' + id, {method: 'DELETE'});
      if (me && id === me.id_sessao) window.location.assign('login.html');
      else await load();
    } catch (error) {
      toast(error.message, true);
    }
  });

  document.querySelector('#securityCloseAll').addEventListener('click', async () => {
    if (!window.confirm('Encerrar todas as sessões, inclusive esta?')) return;
    try {
      await api('/auth/sessoes/encerrar-todas', {method: 'POST'});
      window.location.assign('login.html');
    } catch (error) {
      toast(error.message, true);
    }
  });

  aplicarPreferencias();
});
