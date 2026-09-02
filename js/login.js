/* ============================================================
                        Observação!!!!
        Sobre RH/Recrutador:
     A API atual não expõe um cadastro público de recrutador.
     Um recrutador é adicionado por uma empresa já autenticada,
     via POST /empresas/{id_empresa}/recrutadores, informando o
     ID de um usuário já existente. Por isso, ao escolher "RH /
     Recrutador" aqui, criamos apenas a conta de usuário base
     (via /auth/cadastro/candidato, que cria a linha em Usuarios)
     e orientamos a pessoa a pedir para a empresa vinculá-la.
     Ajuste este trecho se/quando existir um endpoint dedicado.

                    Observação!!!!! 
        Sobre recuperação de senha:
     A API atual não possui endpoint de "esqueci minha senha".
     O formulário abaixo já está pronto e chama
     POST /auth/recuperar-senha — implemente essa rota no backend
     (gerar token, enviar e-mail via notificar.py, e um endpoint
     de redefinição) para o fluxo funcionar de ponta a ponta.
     Até lá, o front trata a ausência do endpoint (404) sem
     quebrar a experiência do usuário.
   ============================================================ */

   

document.addEventListener('DOMContentLoaded', () => {

  const $ = (seletor) => document.querySelector(seletor);
  const $all = (seletor) => document.querySelectorAll(seletor);

  const regexEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  function mostrarErro(inputEl, erroEl, mostrar) {
    if (!inputEl || !erroEl) return;
    inputEl.classList.toggle('input-error', mostrar);
    erroEl.classList.toggle('show', mostrar);
  }

  function limparErro(inputEl, erroEl) {
    mostrarErro(inputEl, erroEl, false);
  }

  function extrairMensagemErro(corpo, padrao) {
    if (!corpo) return padrao;
    if (Array.isArray(corpo.detail)) {
      return corpo.detail.map((d) => d.msg).join(' ');
    }
    return corpo.detail || padrao;
  }

  /* ============================================================
     1. Alternância Entrar <-> Criar conta
     ============================================================ */

  const modeLogin = $('#modeLogin');
  const modeCadastro = $('#modeCadastro');
  const painelLogin = $('#painelLogin');
  const painelCadastro = $('#painelCadastro');

  function irParaLogin() {
    modeLogin.checked = true;
    painelLogin.classList.add('active');
    painelCadastro.classList.remove('active');
  }

  function irParaCadastroPanel() {
    modeCadastro.checked = true;
    painelLogin.classList.remove('active');
    painelCadastro.classList.add('active');
  }

  modeLogin.addEventListener('change', () => { if (modeLogin.checked) irParaLogin(); });
  modeCadastro.addEventListener('change', () => { if (modeCadastro.checked) irParaCadastroPanel(); });

  $('#irParaCadastro')?.addEventListener('click', (e) => {
    e.preventDefault();
    irParaCadastroPanel();
  });
  $('#irParaLogin')?.addEventListener('click', (e) => {
    e.preventDefault();
    irParaLogin();
  });

  /* ============================================================
     2. Painel editorial (headline muda conforme o perfil)
     ============================================================ */

  const introHeadline = $('#introHeadline');
  const introSub = $('#introSub');

  const copyPorPerfil = {
    candidato: {
      titulo: 'Encontre a vaga certa, sem enviar currículo no escuro.',
      sub: 'A Talentix cruza seu perfil com vagas reais e mostra exatamente onde você se encaixa — e onde ainda precisa evoluir.',
    },
    empresa: {
      titulo: 'Contrate com base em dados, não só em currículo.',
      sub: 'Publique vagas, acompanhe candidaturas e deixe a triagem inicial mais rápida com apoio de IA.',
    },
    recrutador: {
      titulo: 'Centralize os processos seletivos da sua empresa.',
      sub: 'Acompanhe candidaturas, agende entrevistas e converse com candidatos em um só lugar.',
    },
  };

  function aplicarCopyIntro(perfil) {
    const copy = copyPorPerfil[perfil] || copyPorPerfil.candidato;
    introHeadline.textContent = copy.titulo;
    introSub.textContent = copy.sub;
  }

  /* ============================================================
     3. Seletor de perfil — Cadastro
        Alterna: label do nome, campo de CNPJ, aviso de recrutador
        e texto do botão.
     ============================================================ */

  const cadRoleCandidato = $('#cadRoleCandidato');
  const cadRoleEmpresa = $('#cadRoleEmpresa');
  const cadRoleRecrutador = $('#cadRoleRecrutador');
  const labelCadNome = $('#labelCadNome');
  const cadNomeInput = $('#cadNome');
  const grupoCnpj = $('#grupoCnpj');
  const cadCnpjInput = $('#cadCnpj');
  const labelCadastroSubmit = $('#labelCadastroSubmit');
  const recrutadorAvisoAlert = $('#recrutadorAvisoAlert');

  function perfilCadastroSelecionado() {
    if (cadRoleEmpresa.checked) return 'empresa';
    if (cadRoleRecrutador.checked) return 'recrutador';
    return 'candidato';
  }

  function aplicarPerfilCadastro(perfil) {
    grupoCnpj.style.display = 'none';
    cadCnpjInput.removeAttribute('required');
    recrutadorAvisoAlert.classList.remove('show');

    if (perfil === 'empresa') {
      labelCadNome.textContent = 'Razão social';
      cadNomeInput.placeholder = 'Nome oficial da empresa';
      grupoCnpj.style.display = '';
      cadCnpjInput.setAttribute('required', 'required');
      labelCadastroSubmit.textContent = 'Criar conta de empresa';
    } else if (perfil === 'recrutador') {
      labelCadNome.textContent = 'Nome completo';
      cadNomeInput.placeholder = 'Como você quer ser chamado(a)';
      labelCadastroSubmit.textContent = 'Criar minha conta';
      recrutadorAvisoAlert.classList.add('show');
    } else {
      labelCadNome.textContent = 'Nome completo';
      cadNomeInput.placeholder = 'Como você quer ser chamado(a)';
      labelCadastroSubmit.textContent = 'Criar conta de candidato';
    }

    aplicarCopyIntro(perfil);
  }

  cadRoleCandidato.addEventListener('change', () => { if (cadRoleCandidato.checked) aplicarPerfilCadastro('candidato'); });
  cadRoleEmpresa.addEventListener('change', () => { if (cadRoleEmpresa.checked) aplicarPerfilCadastro('empresa'); });
  cadRoleRecrutador.addEventListener('change', () => { if (cadRoleRecrutador.checked) aplicarPerfilCadastro('recrutador'); });

  aplicarPerfilCadastro('candidato');

  /* ============================================================
     4. Mostrar / ocultar senha
     ============================================================ */

  $all('.input-toggle').forEach((botao) => {
    botao.addEventListener('click', () => {
      const alvoId = botao.getAttribute('data-toggle-for');
      const input = document.getElementById(alvoId);
      if (!input) return;

      const visivel = input.type === 'text';
      input.type = visivel ? 'password' : 'text';
      botao.textContent = visivel ? '👁' : '🙈';
      botao.setAttribute('aria-label', visivel ? 'Mostrar senha' : 'Ocultar senha');
    });
  });

  /* ============================================================
     5. Máscaras (telefone e CNPJ)
     ============================================================ */

  function maskTelefone(valor) {
    return valor
      .replace(/\D/g, '')
      .slice(0, 11)
      .replace(/^(\d{2})(\d)/, '($1) $2')
      .replace(/(\d{5})(\d)/, '$1-$2');
  }

  function maskCnpj(valor) {
    return valor
      .replace(/\D/g, '')
      .slice(0, 14)
      .replace(/^(\d{2})(\d)/, '$1.$2')
      .replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3')
      .replace(/\.(\d{3})(\d)/, '.$1/$2')
      .replace(/(\d{4})(\d)/, '$1-$2');
  }

  $('#cadTelefone')?.addEventListener('input', (e) => {
    e.target.value = maskTelefone(e.target.value);
  });

  cadCnpjInput?.addEventListener('input', (e) => {
    e.target.value = maskCnpj(e.target.value);
  });

  /* ============================================================
     6. Força da senha (cadastro)
     ============================================================ */

  const cadSenhaInput = $('#cadSenha');
  const pwBars = $all('#pwStrength .pw-strength__bar');
  const pwHint = $('#pwHint');

  const coresForca = ['#E4581B', '#E6A417', '#3D9E5F', '#2E7D6B'];
  const textosForca = ['Muito fraca', 'Fraca', 'Boa', 'Forte'];

  function calcularForcaSenha(senha) {
    let pontos = 0;
    if (senha.length >= 8) pontos++;
    if (/[A-Z]/.test(senha)) pontos++;
    if (/[0-9]/.test(senha)) pontos++;
    if (/[^A-Za-z0-9]/.test(senha)) pontos++;
    return pontos;
  }

  cadSenhaInput?.addEventListener('input', () => {
    const senha = cadSenhaInput.value;
    const forca = senha.length === 0 ? 0 : Math.max(1, calcularForcaSenha(senha));

    pwBars.forEach((barra, indice) => {
      barra.style.background = indice < forca ? coresForca[forca - 1] : '#E3E0D8';
    });

    pwHint.textContent = senha.length === 0
      ? 'Mínimo de 6 caracteres.'
      : `Força da senha: ${textosForca[forca - 1] || 'Muito fraca'}`;
  });

  /* ============================================================
     7. LOGIN
     ============================================================ */

  const formLogin = $('#formLogin');
  const loginEmail = $('#loginEmail');
  const loginSenha = $('#loginSenha');
  const loginAlert = $('#loginAlert');
  const btnLoginSubmit = $('#btnLoginSubmit');

  [loginEmail, loginSenha].forEach((input) => {
    input?.addEventListener('input', () => {
      const erroEl = document.getElementById(`erro${input.id.charAt(0).toUpperCase()}${input.id.slice(1)}`);
      limparErro(input, erroEl);
      loginAlert.classList.remove('show');
    });
  });

  formLogin?.addEventListener('submit', (e) => {
    e.preventDefault();
    loginAlert.classList.remove('show');

    let valido = true;

    if (!regexEmail.test(loginEmail.value.trim())) {
      mostrarErro(loginEmail, $('#erroLoginEmail'), true);
      valido = false;
    } else {
      limparErro(loginEmail, $('#erroLoginEmail'));
    }

    if (loginSenha.value.trim().length === 0) {
      mostrarErro(loginSenha, $('#erroLoginSenha'), true);
      valido = false;
    } else {
      limparErro(loginSenha, $('#erroLoginSenha'));
    }

    if (!valido) return;

    realizarLogin({
      email: loginEmail.value.trim(),
      senha: loginSenha.value,
    });
  });

  function destinoPorTipo(tipoUsuario) {
    switch (tipoUsuario) {
      case 'empresa': return 'dashboard-empresa.html';
      case 'administrador': return 'dashboard-admin.html';
      case 'candidato': return 'dashboard-candidato.html';
      default: return 'dashboard.html'; // recrutador e demais tipos genéricos
    }
  }

  async function realizarLogin(dados) {
    btnLoginSubmit.setAttribute('data-loading', 'true');

    try {
      const resposta = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email: dados.email, senha: dados.senha }),
      });

      const corpo = await resposta.json().catch(() => ({}));

      if (!resposta.ok) {
        $('#loginAlertText').textContent = extrairMensagemErro(
          corpo,
          'E-mail ou senha incorretos. Verifique seus dados e tente novamente.'
        );
        loginAlert.classList.add('show');
        return;
      }

      window.location.href = destinoPorTipo(corpo.tipo_usuario);
    } catch (erro) {
      console.error('Falha ao conectar com a API:', erro);
      $('#loginAlertText').textContent = 'Não foi possível conectar ao servidor. Verifique se a API está no ar e tente novamente.';
      loginAlert.classList.add('show');
    } finally {
      btnLoginSubmit.removeAttribute('data-loading');
    }
  }

  /* ============================================================
     8. CADASTRO
     ============================================================ */

  const formCadastro = $('#formCadastro');
  const cadastroAlert = $('#cadastroAlert');
  const btnCadastroSubmit = $('#btnCadastroSubmit');

  const cadEmailInput = $('#cadEmail');
  const cadConfirmarSenhaInput = $('#cadConfirmarSenha');
  const aceitarTermosInput = $('#aceitarTermos');

  function validarCampoNome() {
    const ok = cadNomeInput.value.trim().length >= 3;
    mostrarErro(cadNomeInput, $('#erroCadNome'), !ok);
    return ok;
  }

  function validarCampoEmail() {
    const ok = regexEmail.test(cadEmailInput.value.trim());
    mostrarErro(cadEmailInput, $('#erroCadEmail'), !ok);
    return ok;
  }

  function validarCampoCnpj() {
    if (!cadRoleEmpresa.checked) return true;
    const digitos = cadCnpjInput.value.replace(/\D/g, '');
    const ok = digitos.length === 14;
    mostrarErro(cadCnpjInput, $('#erroCadCnpj'), !ok);
    return ok;
  }

  function validarCampoSenha() {
    const ok = cadSenhaInput.value.length >= 6;
    mostrarErro(cadSenhaInput, $('#erroCadSenha'), !ok);
    return ok;
  }

  function validarConfirmarSenha() {
    const ok = cadConfirmarSenhaInput.value === cadSenhaInput.value && cadConfirmarSenhaInput.value.length > 0;
    mostrarErro(cadConfirmarSenhaInput, $('#erroCadConfirmarSenha'), !ok);
    return ok;
  }

  function validarTermos() {
    const ok = aceitarTermosInput.checked;
    $('#erroTermos').classList.toggle('show', !ok);
    return ok;
  }

  cadNomeInput.addEventListener('input', validarCampoNome);
  cadEmailInput.addEventListener('input', validarCampoEmail);
  cadCnpjInput.addEventListener('input', validarCampoCnpj);
  cadSenhaInput.addEventListener('input', validarCampoSenha);
  cadConfirmarSenhaInput.addEventListener('input', validarConfirmarSenha);
  aceitarTermosInput.addEventListener('change', validarTermos);

  formCadastro?.addEventListener('submit', (e) => {
    e.preventDefault();
    cadastroAlert.classList.remove('show');

    const validacoes = [
      validarCampoNome(),
      validarCampoEmail(),
      validarCampoCnpj(),
      validarCampoSenha(),
      validarConfirmarSenha(),
      validarTermos(),
    ];

    const tudoValido = validacoes.every(Boolean);

    if (!tudoValido) {
      $('#cadastroAlertText').textContent = 'Verifique os campos destacados abaixo.';
      cadastroAlert.classList.add('show');
      return;
    }

    const perfil = perfilCadastroSelecionado();
    const telefone = $('#cadTelefone').value.trim();

    realizarCadastro({
      perfil,
      nome: cadNomeInput.value.trim(),
      cnpj: perfil === 'empresa' ? cadCnpjInput.value.trim() : null,
      email: cadEmailInput.value.trim(),
      telefone: telefone.length > 0 ? telefone : null,
      senha: cadSenhaInput.value,
    });
  });

  async function realizarCadastro(dados) {
    btnCadastroSubmit.setAttribute('data-loading', 'true');

    // RH/Recrutador não tem cadastro público próprio na API atual:
    // criamos a conta de usuário base pelo mesmo endpoint de candidato
    // (que popula Usuarios) e orientamos a vinculação pela empresa.
    const endpoint = dados.perfil === 'empresa'
      ? '/auth/cadastro/empresa'
      : '/auth/cadastro/candidato';

    const payload = dados.perfil === 'empresa'
      ? {
          nome: dados.nome,
          email: dados.email,
          senha: dados.senha,
          telefone: dados.telefone,
          razao_social: dados.nome,
          cnpj: dados.cnpj,
        }
      : {
          nome: dados.nome,
          email: dados.email,
          senha: dados.senha,
          telefone: dados.telefone,
        };

    try {
      const resposta = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      });

      const corpo = await resposta.json().catch(() => ({}));

      if (!resposta.ok) {
        $('#cadastroAlertText').textContent = extrairMensagemErro(
          corpo,
          'Não foi possível concluir o cadastro. Verifique os dados e tente novamente.'
        );
        cadastroAlert.classList.add('show');
        return;
      }

      // Loga automaticamente para já abrir com sessão ativa
      const loginResposta = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email: dados.email, senha: dados.senha }),
      });

      if (loginResposta.ok) {
        const sessao = await loginResposta.json();

        if (dados.perfil === 'recrutador') {
          // Sem vínculo com empresa ainda: manda para uma tela de
          // instrução, não para o dashboard de candidato.
          alert('Conta criada! Peça para a empresa te adicionar como recrutador no painel dela para liberar o acesso completo.');
        }

        window.location.href = destinoPorTipo(sessao.tipo_usuario);
        return;
      }

      irParaLogin();
      formCadastro.reset();
    } catch (erro) {
      console.error('Falha ao conectar com a API:', erro);
      $('#cadastroAlertText').textContent = 'Não foi possível conectar ao servidor. Verifique se a API está no ar e tente novamente.';
      cadastroAlert.classList.add('show');
    } finally {
      btnCadastroSubmit.removeAttribute('data-loading');
    }
  }

  /* ============================================================
     9. Modal — Recuperar senha
     ============================================================ */

  const modalRecuperar = $('#modalRecuperar');
  const formRecuperar = $('#formRecuperar');
  const modalSucesso = $('#modalSucesso');
  const recuperarEmailInput = $('#recuperarEmail');
  const btnRecuperarSubmit = $('#btnRecuperarSubmit');

  function abrirModal() {
    modalRecuperar.classList.add('show');
    formRecuperar.classList.remove('hide');
    formRecuperar.style.display = '';
    modalSucesso.classList.remove('show');
    recuperarEmailInput.value = '';
    limparErro(recuperarEmailInput, $('#erroRecuperarEmail'));
    setTimeout(() => recuperarEmailInput.focus(), 150);
  }

  function fecharModal() {
    modalRecuperar.classList.remove('show');
  }

  $('#abrirRecuperarSenha')?.addEventListener('click', (e) => {
    e.preventDefault();
    abrirModal();
  });

  $('#fecharModal')?.addEventListener('click', fecharModal);
  $('#cancelarRecuperar')?.addEventListener('click', fecharModal);
  $('#fecharModalSucesso')?.addEventListener('click', fecharModal);

  modalRecuperar?.addEventListener('click', (e) => {
    if (e.target === modalRecuperar) fecharModal();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modalRecuperar.classList.contains('show')) {
      fecharModal();
    }
  });

  formRecuperar?.addEventListener('submit', async (e) => {
    e.preventDefault();

    const ok = regexEmail.test(recuperarEmailInput.value.trim());
    mostrarErro(recuperarEmailInput, $('#erroRecuperarEmail'), !ok);
    if (!ok) return;

    btnRecuperarSubmit.setAttribute('data-loading', 'true');

    try {
      // TODO_API (backend): este endpoint ainda não existe em auth.py.
      // Sugestão de implementação:
      //   POST /auth/recuperar-senha { email }
      //     -> gera token (itsdangerous, mesma lib da sessão), grava
      //        ou embute o token assinado, envia link por e-mail via
      //        app/core/notificar.py (respeitando SMTP_ENABLED).
      //   POST /auth/redefinir-senha { token, nova_senha }
      //     -> valida o token e faz UPDATE Usuarios SET SenhaHash=...
      const resposta = await fetch(`${API_BASE_URL}/auth/recuperar-senha`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: recuperarEmailInput.value.trim() }),
      });

      // Por segurança, tratamos 404 (endpoint ainda não implementado)
      // e 2xx da mesma forma visível ao usuário: nunca revelamos se o
      // e-mail existe ou não na base.
      if (resposta.status === 404) {
        console.warn('Endpoint /auth/recuperar-senha ainda não implementado na API.');
      }
    } catch (erro) {
      console.error('Falha ao conectar com a API:', erro);
    } finally {
      btnRecuperarSubmit.removeAttribute('data-loading');
      formRecuperar.style.display = 'none';
      modalSucesso.classList.add('show');
    }
  });

  /* ============================================================
     10. Sessão já ativa? Pula direto pro dashboard.                              ( DESATIVADO )
     ============================================================ 

  (async function verificarSessaoExistente() {
    try {
      const resposta = await fetch(`${API_BASE_URL}/auth/me`, {
        credentials: 'include',
      });
      if (resposta.ok) {
        const sessao = await resposta.json();
        window.location.href = destinoPorTipo(sessao.tipo_usuario);
      }
    } catch {
      // API fora do ar ou sem sessão: permanece na tela de login normalmente.
    }
  })(); */


  /* ============================================================
     10. Redefinir senha via link do e-mail (?token=...)
     ============================================================ */

  const modalNovaSenha = $('#modalNovaSenha');
  const formNovaSenha = $('#formNovaSenha');
  const modalNovaSenhaSucesso = $('#modalNovaSenhaSucesso');
  const novaSenhaInput = $('#novaSenhaInput');
  const confirmarNovaSenhaInput = $('#confirmarNovaSenhaInput');
  const novaSenhaAlert = $('#novaSenhaAlert');
  const btnNovaSenhaSubmit = $('#btnNovaSenhaSubmit');
  const pwBarsNova = $all('#pwStrengthNova .pw-strength__bar');
  const pwHintNova = $('#pwHintNova');

  let tokenResetAtual = null;

  function abrirModalNovaSenha(token) {
    tokenResetAtual = token;
    modalNovaSenha.classList.add('show');
    formNovaSenha.style.display = '';
    modalNovaSenhaSucesso.classList.remove('show');
    novaSenhaInput.value = '';
    confirmarNovaSenhaInput.value = '';
    novaSenhaAlert.classList.remove('show');
    limparErro(novaSenhaInput, $('#erroNovaSenha'));
    limparErro(confirmarNovaSenhaInput, $('#erroConfirmarNovaSenha'));
    setTimeout(() => novaSenhaInput.focus(), 150);
  }

  function fecharModalNovaSenha() {
    modalNovaSenha.classList.remove('show');
    // Limpa o token da URL para evitar reuso acidental via refresh
    const url = new URL(window.location.href);
    url.searchParams.delete('token');
    window.history.replaceState({}, document.title, url.pathname + url.search);
  }

  $('#fecharModalNovaSenha')?.addEventListener('click', fecharModalNovaSenha);
  $('#fecharNovaSenhaSucesso')?.addEventListener('click', () => {
    fecharModalNovaSenha();
    irParaLogin();
  });

  novaSenhaInput?.addEventListener('input', () => {
    const senha = novaSenhaInput.value;
    const forca = senha.length === 0 ? 0 : Math.max(1, calcularForcaSenha(senha));
    pwBarsNova.forEach((barra, indice) => {
      barra.style.background = indice < forca ? coresForca[forca - 1] : '#E3E0D8';
    });
    pwHintNova.textContent = senha.length === 0
      ? 'Mínimo de 6 caracteres.'
      : `Força da senha: ${textosForca[forca - 1] || 'Muito fraca'}`;
    limparErro(novaSenhaInput, $('#erroNovaSenha'));
  });

  confirmarNovaSenhaInput?.addEventListener('input', () => {
    limparErro(confirmarNovaSenhaInput, $('#erroConfirmarNovaSenha'));
  });

  formNovaSenha?.addEventListener('submit', async (e) => {
    e.preventDefault();
    novaSenhaAlert.classList.remove('show');

    let valido = true;

    if (novaSenhaInput.value.length < 6) {
      mostrarErro(novaSenhaInput, $('#erroNovaSenha'), true);
      valido = false;
    } else {
      limparErro(novaSenhaInput, $('#erroNovaSenha'));
    }

    if (confirmarNovaSenhaInput.value !== novaSenhaInput.value || confirmarNovaSenhaInput.value.length === 0) {
      mostrarErro(confirmarNovaSenhaInput, $('#erroConfirmarNovaSenha'), true);
      valido = false;
    } else {
      limparErro(confirmarNovaSenhaInput, $('#erroConfirmarNovaSenha'));
    }

    if (!valido) return;

    btnNovaSenhaSubmit.setAttribute('data-loading', 'true');

    try {
      const resposta = await fetch(`${API_BASE_URL}/auth/redefinir-senha`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: tokenResetAtual,
          nova_senha: novaSenhaInput.value,
        }),
      });

      const corpo = await resposta.json().catch(() => ({}));

      if (!resposta.ok) {
        novaSenhaAlertText.textContent = extrairMensagemErro(
          corpo,
          'Este link não é mais válido. Solicite uma nova redefinição de senha.'
        );
        $('#novaSenhaAlertText').textContent = extrairMensagemErro(
          corpo,
          'Este link não é mais válido. Solicite uma nova redefinição de senha.'
        );
        novaSenhaAlert.classList.add('show');
        return;
      }

      formNovaSenha.style.display = 'none';
      modalNovaSenhaSucesso.classList.add('show');
    } catch (erro) {
      console.error('Falha ao conectar com a API:', erro);
      $('#novaSenhaAlertText').textContent = 'Não foi possível conectar ao servidor. Tente novamente em instantes.';
      novaSenhaAlert.classList.add('show');
    } finally {
      btnNovaSenhaSubmit.removeAttribute('data-loading');
    }
  });

  // Detecta ?token= na URL ao carregar a página e abre o modal automaticamente
  (function verificarTokenNaUrl() {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    if (token) {
      abrirModalNovaSenha(token);
    }
  })();

});