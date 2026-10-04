/* TALENTIX — configuração compartilhada de acesso à API. */
const API_BASE_URL = (() => {
  const definida = String(window.TALENTIX_API_BASE_URL || '').trim().replace(/\/$/, '');
  if (definida) return definida;
  const host = window.location.hostname;
  if (host === 'localhost' || host === '127.0.0.1') return 'http://' + host + ':8000';
  if (window.location.protocol === 'file:' || !host) return 'http://127.0.0.1:8000';
  return window.location.origin;
})();

(function configurarFetchSeguro() {
  const fetchOriginal = window.fetch.bind(window);
  const metodosMutaveis = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

  function lerCookie(nome) {
    const prefixo = encodeURIComponent(nome) + '=';
    const parte = document.cookie.split('; ').find((item) => item.startsWith(prefixo));
    return parte ? decodeURIComponent(parte.slice(prefixo.length)) : '';
  }

  function mesmaApi(input) {
    try {
      const valor = typeof input === 'string' ? input : input.url;
      return new URL(valor, window.location.href).origin === new URL(API_BASE_URL).origin;
    } catch {
      return false;
    }
  }

  window.fetch = function talentixFetch(input, init = {}) {
    const opcoes = { ...init };
    const metodo = String(opcoes.method || 'GET').toUpperCase();
    if (mesmaApi(input)) {
      opcoes.credentials = 'include';
      if (metodosMutaveis.has(metodo)) {
        const csrf = lerCookie('talentix_csrf');
        if (csrf) {
          const headers = new Headers(opcoes.headers || {});
          headers.set('X-CSRF-Token', csrf);
          opcoes.headers = headers;
        }
      }
    }
    return fetchOriginal(input, opcoes);
  };
})();
