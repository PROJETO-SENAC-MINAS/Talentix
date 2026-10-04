
(() => {
  const d = document;

  function preferencesEnabled() {
    return localStorage.getItem('talentix-a11y-enabled') !== 'false';
  }

  function applyPreferences() {
    const enabled = preferencesEnabled();
    const root = d.documentElement;
    root.dataset.a11yContrast =
      enabled && localStorage.getItem('talentix-a11y-contrast') === 'high' ? 'high' : '';
    root.dataset.a11yText =
      enabled && localStorage.getItem('talentix-a11y-text') === 'large' ? 'large' : '';
    root.dataset.theme = localStorage.getItem('talentix-theme') === 'dark' ? 'dark' : '';
    root.dataset.reducedMotion =
      localStorage.getItem('talentix-reduced-motion') === 'true' ? 'true' : '';

    d.querySelectorAll('.a11y-toolbar').forEach(toolbar => {
      toolbar.hidden = !enabled;
      toolbar.querySelector('[aria-label="Alternar alto contraste"]')?.setAttribute('aria-pressed', String(root.dataset.a11yContrast === 'high'));
      toolbar.querySelector('[aria-label="Alternar texto ampliado"]')?.setAttribute('aria-pressed', String(root.dataset.a11yText === 'large'));
    });
  }

  function tabs() {
    d.querySelectorAll('.sidebar__nav').forEach(nav => {
      const tabs = [...nav.querySelectorAll('.nav-item[data-tab]')];
      if (!tabs.length) return;
      nav.setAttribute('role', 'tablist');
      nav.setAttribute('aria-orientation', 'vertical');
      tabs.forEach((tab, index) => {
        const panel = d.getElementById('tab-' + tab.dataset.tab);
        tab.setAttribute('role', 'tab');
        tab.id = tab.id || 'tab-btn-' + tab.dataset.tab;
        tab.setAttribute('aria-controls', panel?.id || '');
        tab.setAttribute('aria-selected', tab.classList.contains('active') ? 'true' : 'false');
        tab.tabIndex = tab.classList.contains('active') ? 0 : -1;

        if (panel) {
          panel.setAttribute('role', 'tabpanel');
          panel.setAttribute('aria-labelledby', tab.id);
          panel.tabIndex = 0;
        }

        tab.addEventListener('click', () => queueMicrotask(() => {
          [...nav.querySelectorAll('.nav-item[data-tab]')].forEach(item => {
            const active = item.classList.contains('active');
            item.setAttribute('aria-selected', active ? 'true' : 'false');
            item.tabIndex = active ? 0 : -1;
          });
        }));

        tab.addEventListener('keydown', event => {
          if (!['ArrowDown','ArrowRight','ArrowUp','ArrowLeft','Home','End'].includes(event.key)) return;
          event.preventDefault();
          let target = index;
          if (event.key === 'Home') target = 0;
          else if (event.key === 'End') target = tabs.length - 1;
          else if (['ArrowDown','ArrowRight'].includes(event.key)) target = (index + 1) % tabs.length;
          else target = (index - 1 + tabs.length) % tabs.length;
          tabs.forEach((item, i) => { item.tabIndex = i === target ? 0 : -1; });
          tabs[target].focus();
        });
      });
    });
  }

  function toolbar() {
    if (d.querySelector('.a11y-toolbar')) return;
    const bar = d.createElement('div');
    bar.className = 'a11y-toolbar';
    bar.setAttribute('role', 'region');
    bar.setAttribute('aria-label', 'Opções de acessibilidade');

    const contrast = d.createElement('button');
    contrast.type = 'button';
    contrast.textContent = '◐';
    contrast.setAttribute('aria-label', 'Alternar alto contraste');

    const text = d.createElement('button');
    text.type = 'button';
    text.textContent = 'A+';
    text.setAttribute('aria-label', 'Alternar texto ampliado');

    bar.append(contrast, text);
    (d.querySelector('.candidate-dashboard .sidebar__footer') || d.body).appendChild(bar);

    contrast.onclick = () => {
      const on = d.documentElement.dataset.a11yContrast !== 'high';
      localStorage.setItem('talentix-a11y-contrast', on ? 'high' : '');
      applyPreferences();
    };
    text.onclick = () => {
      const on = d.documentElement.dataset.a11yText !== 'large';
      localStorage.setItem('talentix-a11y-text', on ? 'large' : '');
      applyPreferences();
    };
  }

  function dialogs() {
    d.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      const dialog = d.activeElement?.closest('dialog[open]');
      if (!dialog) return;
      const controls = [...dialog.querySelectorAll('a[href],button,input,select,textarea,[tabindex]')]
        .filter(el => !el.disabled && el.tabIndex >= 0 && el.getClientRects().length);
      if (!controls.length) { event.preventDefault(); dialog.focus(); return; }
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && d.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && d.activeElement === last) { event.preventDefault(); first.focus(); }
    });
  }

  function ready() {
    const main = d.querySelector('main');
    if (main && !main.id) main.id = 'conteudo-principal';
    if (main) main.tabIndex = -1;
    if (main && !d.querySelector('.skip-link')) {
      const skip = d.createElement('a');
      skip.className = 'skip-link';
      skip.href = '#' + main.id;
      skip.textContent = 'Pular para o conteúdo principal';
      d.body.prepend(skip);
    }

    d.querySelectorAll('.toast').forEach(element => {
      element.setAttribute('role', 'status');
      element.setAttribute('aria-live', 'polite');
      element.setAttribute('aria-atomic', 'true');
    });


    tabs();
    dialogs();
    toolbar();
    applyPreferences();
    window.addEventListener('talentix:preferences-changed', applyPreferences);
  }

  if (d.readyState === 'loading') d.addEventListener('DOMContentLoaded', ready);
  else ready();
})();
