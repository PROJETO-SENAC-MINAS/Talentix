/* ============================================================
   TALENTIX — config.js
   Configuração compartilhada de acesso à API.
   Ajuste API_BASE_URL se a API rodar em outra porta/host.
   ============================================================ */

const API_BASE_URL = 'http://127.0.0.1:8000';

/* Segurança compartilhada do cliente: anexa CSRF automaticamente às mutações. */
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
