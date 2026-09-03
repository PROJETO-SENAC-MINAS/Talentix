document.addEventListener('DOMContentLoaded', () => {

    /* ---------- Menu mobile (igual index) ---------- */
    const navToggle = document.getElementById('navToggle');
    const nav = document.querySelector('.nav');
  
    navToggle?.addEventListener('click', () => {
      const aberto = nav.classList.toggle('nav--open');
      navToggle.setAttribute('aria-expanded', String(aberto));
    });
  
    document.querySelectorAll('.nav__links a').forEach((link) => {
      link.addEventListener('click', () => {
        nav?.classList.remove('nav--open');
        navToggle?.setAttribute('aria-expanded', 'false');
      });
    });
  
    /* ---------- Realce do item ativo no sumário (Termos / Privacidade) ---------- */
    const secoes = document.querySelectorAll('.legal__body section[id]');
    const linksToc = document.querySelectorAll('.legal__toc a');
  
    if (secoes.length && linksToc.length && 'IntersectionObserver' in window) {
      const observer = new IntersectionObserver(
        (entradas) => {
          entradas.forEach((entrada) => {
            if (entrada.isIntersecting) {
              const id = entrada.target.getAttribute('id');
              linksToc.forEach((link) => {
                const ativo = link.getAttribute('href') === `#${id}`;
                link.style.color = ativo ? 'var(--accent-dark)' : '';
                link.style.fontWeight = ativo ? '600' : '';
              });
            }
          });
        },
        { rootMargin: '-40% 0px -50% 0px' }
      );
      secoes.forEach((s) => observer.observe(s));
    }
  
    /* ---------- Validação do formulário de contato ---------- */
    const formContato = document.getElementById('formContato');
    if (!formContato) return;
  
    const regexEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const sucesso = document.getElementById('contatoSucesso');
    const btnSubmit = document.getElementById('btnContatoSubmit');
  
    const nome = document.getElementById('contatoNome');
    const email = document.getElementById('contatoEmail');
    const assunto = document.getElementById('contatoAssunto');
    const mensagem = document.getElementById('contatoMensagem');
  
    function mostrarErro(input, erroId, mostrar) {
      const erroEl = document.getElementById(erroId);
      input.classList.toggle('input-error', mostrar);
      erroEl?.classList.toggle('show', mostrar);
    }
  
    function validarNome() {
      const ok = nome.value.trim().length >= 3;
      mostrarErro(nome, 'erroContatoNome', !ok);
      return ok;
    }
    function validarEmail() {
      const ok = regexEmail.test(email.value.trim());
      mostrarErro(email, 'erroContatoEmail', !ok);
      return ok;
    }
    function validarAssunto() {
      const ok = assunto.value !== '';
      mostrarErro(assunto, 'erroContatoAssunto', !ok);
      return ok;
    }
    function validarMensagem() {
      const ok = mensagem.value.trim().length >= 10;
      mostrarErro(mensagem, 'erroContatoMensagem', !ok);
      return ok;
    }
  
    nome.addEventListener('input', validarNome);
    email.addEventListener('input', validarEmail);
    assunto.addEventListener('change', validarAssunto);
    mensagem.addEventListener('input', validarMensagem);
  
    formContato.addEventListener('submit', (e) => {
      e.preventDefault();
      sucesso.classList.remove('show');
  
      const valido = [validarNome(), validarEmail(), validarAssunto(), validarMensagem()].every(Boolean);
      if (!valido) return;
  
      btnSubmit.setAttribute('disabled', 'true');
      btnSubmit.textContent = 'Enviando...';
  
      // TODO_API: substituir pelo fetch real, ex.: POST /api/contato
      setTimeout(() => {
        btnSubmit.removeAttribute('disabled');
        btnSubmit.textContent = 'Enviar mensagem';
        sucesso.classList.add('show');
        formContato.reset();
      }, 800);
    });
  });