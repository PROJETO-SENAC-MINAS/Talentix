# Talentix — instruções únicas para agentes

## Decisões confirmadas em 14/10/2026

- Repositório: `PROJETO-SENAC-MINAS/Talentix`. Trabalhar exclusivamente em `arthur`.
- Commits, push e migrations estão autorizados. Não criar branch, PR, merge, force push ou apagar branches sem solicitação explícita.
- Objetivo: Talentix 1.0; priorizar um fluxo integrado entre candidato, empresa, recrutador e administrador, usando a agenda de outubro/2026 a maio/2027.
- IA é apenas informativa. Nunca publicar, contratar, reprovar ou alterar perfil automaticamente.
- Entrevistas são agendadas manualmente. Autoagendamento é adiado por decisão do produto.
- Comunicação em massa exige permissão, contexto autorizado, limites, preferências e auditoria.
- Preservar dados, fluxos gratuitos, APIs, identidade visual e entregas existentes.
- SMTP é a integração atual; calendários e videoconferência devem ter pontos de extensão. Não declarar entrega externa validada sem credenciais e evidência real.
- Manter execução no SENAC sem Docker/npm. Docker e Node podem ser usados no desenvolvimento/CI.
- Este é o único documento operacional para agentes. Documentação de produto, arquitetura e histórico em `docs/` deve ser preservada.

## Estrutura e stack verificadas

Frontend em `html/`, `css/`, `js/`; HTML/CSS/JavaScript separados. Scripts externos antes de `</body>`. Backend FastAPI em `python/app/main.py`, routers em `python/app/routers/`, controles reutilizáveis em `python/app/core/`. Banco MySQL 8, SQL parametrizado com aiomysql/PyMySQL, sem ORM. Versões exatas em `python/requirements*.txt` e `web-tests/package-lock.json`; Python 3.12 e Node 24 são usados no CI.

`sql/talentix_db.sql` instala banco novo. `python/migrate.py` descobre `sql/migrations/NNN_nome.sql`, controla checksum e serializa DDL com lock. Nunca modificar migrations já aplicadas. Criar versão nova, aditiva e idempotente: DDL MySQL não tem rollback transacional. Testar instalação limpa e upgrade de banco anterior. A API/worker usa somente SELECT/INSERT/UPDATE/DELETE; DDL usa credencial de migração separada.

`AtomicRouter` agrupa escritas, auditoria e notificações em transação. Efeitos externos ocorrem depois do commit ou pela outbox. A autenticação usa cookie assinado e sessões persistidas, revogação e bcrypt. `usuario_atual` resolve os papéis no banco, sem confiar no cliente. Administradores em modo usuário perdem poderes administrativos nesse modo.

## Execução real sem Docker

Na raiz: `python -m venv .venv`; instalar com `.venv/bin/python -m pip install -r python/requirements-dev.txt` (desenvolvimento/testes). No Windows, substituir `.venv/bin/python` por `.venv\Scripts\python.exe`, dispensando Activate.ps1.

Para a aplicação: instalar `python/requirements-ia.txt`, executar `python python/configure_dev.py`, preencher `python/.env` localmente, importar SQL somente em banco novo e executar `python migrate.py` dentro de `python/` em banco existente. Não imprimir nem versionar `.env`. Fazer backup antes do upgrade. Iniciar dentro de `python/`: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`. Em outro terminal na raiz: `python serve_frontend.py`; abrir `/html/index.html`. Em Windows usar o caminho absoluto do interpretador virtual se necessário.

Workers: `python -m app.worker_ia`, `python -m app.worker_profissional` e `python -m app.worker_platform`, dentro de `python/`. `--once` processa uma passagem/fila e termina, conforme o worker. SMTP pode permanecer desativado; registrar claramente que entrega de e-mail fica indisponível.

## Perfis e módulos

| Perfil | Escopo obrigatório |
|---|---|
| Candidato | Próprio perfil, versões de CV, candidatura, consentimentos e comunicação autorizada |
| Empresa | Vagas e processos próprios; responsável administra vínculos e publicação |
| Recrutador | Empresa e permissões do vínculo ativo; revogação deve ter efeito imediato |
| Administrador | Gestão explícita, auditada, com seleção de empresa quando exigida |

Módulos existentes: autenticação/contas, perfis profissionais, currículos e revisão manual, busca/alertas, vagas, candidaturas/entrevistas, mensagens/notificações, ATS pipeline/scorecards/CRM, cursos, denúncias, contatos, financeiro interno e compatibilidade TF-IDF. Financeiro não representa checkout nem transferência real.

Invariantes: currículo anexado pertence ao candidato; empresa acessa somente a versão de sua candidatura; salário confidencial nunca aparece em projeções públicas/filtros; vaga em rascunho é privada; scorecards cegos são protegidos na API; consentimento de CRM é por empresa; IA auxilia e nunca decide.

## Segurança obrigatória

- Hash bcrypt/Argon2 adequado, nunca senha reversível/texto puro. Não renomear campos de entrada para bcrypt. Segredos somente em ambiente/cofre; não exibir tokens, cookies, senhas, currículos ou PII em logs.
- MySQL não tem RLS nativo: aplicar autorização central, queries escopadas e privilégios mínimos. Testar usuário A/B, empresa A/B, IDOR/BOLA e ações administrativas.
- Validação no frontend e backend, schemas com limites, SQL parametrizado, saída escapada; evitar mass assignment, SQLi, XSS, command injection e path traversal.
- Upload: tipo real, extensão, tamanho, conteúdo e autorização; sem execução/nomes arbitrários. Dados privados sem cache público.
- Rate limit transversal e limites mais rígidos para autenticação, uploads, IA e comunicação; proxies não confiáveis não definem identidade.
- CSRF nas mutações com cookie, origem validada, CORS allowlist sem wildcard com credenciais. Cookies HttpOnly/Secure em produção/SameSite; sessões curtas, revogáveis, invalidadas após eventos sensíveis.
- URLs e requisições externas devem impedir SSRF, loopback, redes privadas, metadata e redirects perigosos. CSP, nosniff, política de referrer, frames e HSTS de produção.
- Não introduzir segredos no Git. O README documenta exposição histórica: rotação e limpeza do histórico dependem dos responsáveis, sem reescrever histórico compartilhado automaticamente.
- Privacidade por finalidade, retenção e acesso mínimo; consentimentos e acesso administrativo auditados. Seeds/testes somente fictícios.

## Validação e Definition of Done

Na raiz: `.venv/bin/python -m pytest python/tests -q`; `.venv/bin/python python/check_sast.py`; `.venv/bin/python -m pip_audit -r python/requirements-dev.txt`; `npm ci --prefix web-tests --ignore-scripts`; `npm run check --prefix web-tests`; `npm test --prefix web-tests`. Os testes MySQL/navegador reais exigem banco descartável, `TALENTIX_ISOLATED_TESTS=1` e as variáveis do workflow `.github/workflows/security-checks.yml`. Nunca executar os scripts de integração no banco pessoal/produção.

Cada incremento precisa de fluxo integrado, autorização e isolamento, validações, erro e rate limit, migration segura quando aplicável, testes positivos/negativos/regressão, acessibilidade e responsividade. Estados loading/vazio/erro/permissão/sucesso; teclado, foco visível, semântica, contraste, reduced-motion e reflow. Axe não certifica WCAG: revisão humana deve permanecer explícita.

Consultar `docs/ROADMAP_STATUS.md` em cada sessão; registrar critérios atendidos, evidências, pendências, riscos, data real, branch e próxima ação. Não confundir arquivo/rota existente com entrega concluída. Até três releases relevantes por mês planejado, duas em maio; antecipação de desenvolvimento não altera datas nem declara RC antecipadamente. Corrigir divergências nos checks após cada push autorizado. Não desativar segurança/testes para obter CI verde.

Checkpoints devem informar branch, mês/update, resultado, validação, bloqueios e próxima ação. Commits por unidade lógica. Não expandir para folha, ponto, RH de empregados, apps nativos, cursos/videoconferência próprios ou cobrança real sem novo escopo.
