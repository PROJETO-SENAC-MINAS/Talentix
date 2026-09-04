document.addEventListener('DOMContentLoaded', () => {

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
  
    const observados = document.querySelectorAll('.persona-card, .flow-step, .testimonial');
  
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entradas) => {
        entradas.forEach((entrada) => {
          if (entrada.isIntersecting) {
            entrada.target.style.opacity = '1';
            entrada.target.style.transform = 'translateY(0)';
            observer.unobserve(entrada.target);
          }
        });
      }, { threshold: 0.15 });
  
      observados.forEach((el) => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(16px)';
        el.style.transition = 'opacity .5s ease, transform .5s ease';
        observer.observe(el);
      });
    }
  });

// ================= COOKIES =================

const cookieBanner = document.getElementById('cookieBanner');
const cookieAccept = document.getElementById('cookieAccept');
const cookieReject = document.getElementById('cookieReject');

// Sempre mostrar o banner ao carregar a página
if (cookieBanner) {
  setTimeout(() => {
    cookieBanner.classList.add('cookie-banner--visible');
  }, 500);
}

// Botão Aceitar
cookieAccept?.addEventListener('click', () => {
  cookieBanner?.classList.remove('cookie-banner--visible');
});

// Botão Recusar
cookieReject?.addEventListener('click', () => {
  cookieBanner?.classList.remove('cookie-banner--visible');
});