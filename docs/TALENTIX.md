# Talentix — instruções únicas para agentes


## Índice do documento único

- [Instruções operacionais para agentes](#decisões-confirmadas-em-14102026)
- [Estado oficial dos 23 updates e evidências](#estado-roadmap)
- [Plataforma integrada: operação e contratos](#plataforma-integrada)
- [Revisão de segurança](#revisao-seguranca)
- [Fluxo inicial e regras da apresentação](#fluxo-inicial)
- [Histórico técnico de novembro](#historico-novembro)
- [Histórico técnico de dezembro](#historico-dezembro)
- [Requisitos originais de segurança](#requisitos-originais-seguranca)
- [Agenda original completa até maio de 2027](#agenda-original)

## Regra de autoridade e manutenção

As decisões confirmadas e o estado oficial dos updates representam a situação vigente. A agenda original e os históricos preservam intenção e rastreabilidade; quando houver divergência, não substituem uma decisão posterior registrada no estado oficial. Toda mudança futura deve atualizar este arquivo no mesmo commit da implementação. Não criar novamente `ROADMAP_STATUS.md`, `plataforma_integrada.md`, `revisao_seguranca.md`, `andamento_inicial.md` ou documentos mensais separados.

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
- Este é o único documento operacional, de produto, segurança, roadmap e histórico destinado aos agentes. Não criar documentos paralelos para estes assuntos: atualizar a seção correspondente deste arquivo. `docs/` mantém apenas imagens, diagrama e material auxiliar que não substitui este documento.

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

Consultar a seção [Estado oficial dos 23 updates](#estado-roadmap) deste arquivo em cada sessão; registrar critérios atendidos, evidências, pendências, riscos, data real, branch e próxima ação. Não confundir arquivo/rota existente com entrega concluída. Até três releases relevantes por mês planejado, duas em maio; antecipação de desenvolvimento não altera datas nem declara RC antecipadamente. Corrigir divergências nos checks após cada push autorizado. Não desativar segurança/testes para obter CI verde.

Checkpoints devem informar branch, mês/update, resultado, validação, bloqueios e próxima ação. Commits por unidade lógica. Não expandir para folha, ponto, RH de empregados, apps nativos, cursos/videoconferência próprios ou cobrança real sem novo escopo.

---

<a id="estado-roadmap"></a>

# Estado oficial dos 23 updates e evidências

> Conteúdo consolidado de `docs/ROADMAP_STATUS.md` em 14/10/2026. O arquivo separado foi removido para manter uma única fonte de verdade.

# Agenda oficial e evidências — Talentix

Atualizado em 14/10/2026, branch `arthur`; base de trabalho `3fbc14c`.
Desenvolvimento dos meses futuros foi antecipado com autorização; o calendário de releases permanece outubro/2026–maio/2027.
Não é RC antecipada. Commits/push autorizados; sem PR/merge ou alteração de `main`.

CONCLUÍDO exige implementação, validação e aceite; PARCIAL explicita pendências; BLOQUEADO
identifica dependência externa; FORA DO ESCOPO registra adiamento confirmado.
Não se atribui percentual a funcionalidades sem critérios de aceite/denominador aprovado.
O estado inicial está preservado na coluna anterior; arquivos existentes não são prova de conclusão.

| Update / mês | Antes | Agora e evidência de implementação | Pendência para aceite completo |
|---|---|---|---|
| 1 — Out/26, arquitetura | PARCIAL | PARCIAL: FastAPI/MySQL, migrations 001–007, bootstrap de privilégio mínimo, servidor frontend restrito, execução sem Docker | Restore/recuperação e operação no computador do SENAC |
| 2 — Out/26, contas | PARCIAL | PARCIAL: sessões persistidas, CSRF, bcrypt, confirmação, revogação e regressões | Homologação de entrega SMTP e rotação histórica pelos responsáveis |
| 3 — Out/26, acessibilidade | PARCIAL | PARCIAL: Axe WCAG 2.2 A/AA, teclado, mobile e reflow nos painéis/ATS/Central | Leitor de tela, zoom real, textos e revisão humana |
| 4 — Nov/26, perfil | PARCIAL | PARCIAL: experiências/formações/projetos/certificações, privacidade e revisão manual preservados | Aceite humano; detalhes no [histórico técnico de novembro](#historico-novembro) |
| 5 — Nov/26, currículo | PARCIAL | PARCIAL: versões, importação com seleção e confirmação, PDF privado e worker | Corpus real autorizado e avaliação de extração |
| 6 — Nov/26, busca | PARCIAL | PARCIAL: filtros, busca salva/alertas, testes HTTP/MySQL/navegador | Homologação de relevância e entrega dos alertas |
| 7 — Dez/26, pipeline | PARCIAL | PARCIAL: Kanban por vaga, histórico, concorrência, navegação e movimentação por teclado | Aceite de operação/UX |
| 8 — Dez/26, scorecards | PARCIAL | PARCIAL: avaliações cegas e permissões; entrevistador limitado à atribuição na API | Homologar experiência de formulário do entrevistador na Central/ATS |
| 9 — Dez/26, CRM | PARCIAL | PARCIAL: consentimento por empresa, pools, convites/revogação e testes reais | Política de retenção final e aceite |
| 10 — Jan/27, agenda | PARCIAL | PARCIAL: UTC/fuso IANA, duração, conflito concorrente, repetição segura, versões, reagendar/cancelar/realizar, lembretes | Homologar fusos e operação manual; autoagendamento adiado |
| 11 — Jan/27, comunicação | PARCIAL | PARCIAL: timeline por processo, leitura, modelos, lote limitado/consentido, PDF privado, outbox com retentativas | SMTP externo real e revisão dos textos/modelos |
| 12 — Jan/27, automações | NÃO INICIADO | PARCIAL: regras determinísticas, tarefas, notificações/e-mail, histórico e execução única comprovada | Homologar regras na rotina; nenhuma decisão seletiva automática |
| 13 — Fev/27, matching | PARCIAL | PARCIAL: V2 local, TF-IDF, aliases, habilidades ponderadas e atributos estruturados sensíveis excluídos | Embeddings semânticos e avaliação de qualidade não implementados; experiência/formação/logística sem pontuação estruturada |
| 14 — Fev/27, explicação | PARCIAL | PARCIAL: fatores/pesos, lacunas, obrigatórios, limites, versão e histórico persistidos | Calibração, avaliação de viés e aceite das explicações |
| 15 — Fev/27, assistente | NÃO INICIADO | PARCIAL: orientações de perfil, resumo de vaga e perguntas sugeridas integradas à Central | É assistência determinística, sem modelo generativo ou avaliação com usuários |
| 16 — Mar/27, empresas públicas | NÃO INICIADO | PARCIAL: publicação explícita, cultura/benefícios/tecnologias, vagas e avaliações moderadas | Capa/redes sociais e revisão editorial completa |
| 17 — Mar/27, SEO | NÃO INICIADO | PARCIAL: HTML SSR, canonical/OG/JSON-LD, sitemap/robots, país, expiração e salário confidencial protegido | Domínio HTTPS, validação externa e indexação pelo buscador |
| 18 — Mar/27, PWA | NÃO INICIADO | PARCIAL: manifest/ícones, instalação, offline sem cache privado, push consentido com allowlist e fila | Push externo e instalação em dispositivos reais |
| 19 — Abr/27, analytics | PARCIAL | PARCIAL: coorte, filtros, conversão/desistência, histórico de tempo por etapa, CSV/PDF privado | Origem/departamento não coletados; carga sustentada e aceite das definições |
| 20 — Abr/27, RBAC | PARCIAL | PARCIAL: multiempresa, cinco papéis, convites, revogação, publicação privilegiada e último Owner protegido | Homologação completa de todos os papéis na interface |
| 21 — Abr/27, governança | PARCIAL | PARCIAL: auditoria/IP, exportação própria, consentimento, exclusão cancelável/anonimização e retenção conservadora | Política definitiva de candidaturas/backups/auditoria e revisão dos responsáveis |
| 22 — Mai/27, hardening | NÃO INICIADO | PARCIAL: regressões, MySQL concorrente, revisão de fonte/Bandit, auditoria de dependências e CI ampliado | Pentest independente, carga, restore e infraestrutura HTTPS |
| 23 — Mai/27, RC/apresentação | NÃO INICIADO | PARCIAL: roteiro integrado fictício e instruções de operação disponíveis | Congelamento, aceite, apresentação e RC na data oficial |

## Evidências reproduzíveis

- Suíte rápida: 138 testes aprovados (base tinha 120), com cinco avisos de depreciação legados.
- MySQL real 8.0.46: preparação limpa/upgrade legado e migrations repetidas; cenários anteriores
  e cenário integrado com conflito concorrente, repetição, revogação, worker, exportações e privacidade.
- Navegador real: perfil/importação, 15 casos de painéis, ATS em quatro larguras, fluxo de 33 casos
  e ATS real. A Central e páginas públicas acrescentam cenários próprios de Axe, isolamento e cache.
- `python/check_sast.py`: 30 alertas B608 médios revisados individualmente, sem alertas altos;
  novo achado/arquivo alterado exige revisão e falha no CI. Não foram suprimidas regras.
- `pip-audit` e `npm audit`: nenhuma vulnerabilidade conhecida encontrada na execução local.
- Ambiente local não tinha Docker; o bootstrap Compose é validado no job próprio do GitHub Actions.
- Playwright 1.63 local usou Chromium 141 por indisponibilidade do download padrão nesse ambiente;
  o CI instala o Chromium padrão da versão fixada. Isso limita a equivalência local/CI.

Resultados detalhados de API, Axe, screenshots e logs são gerados em `test-results/` e nos artefatos do CI.
A auditoria automática não certifica WCAG, privacidade ou segurança integral.

## Decisões e bloqueios

Entrevista/confirmação no chat: completar o produto, fluxo completo primeiro, IA informativa,
mais controle sensível, comunicação autorizada, preservar entregas/dados/APIs/identidade,
SENAC sem Docker/npm, instruções únicas `TALENTIX.md`, somente `arthur`.

Autoagendamento e integrações funcionais Calendar/Outlook/Meet/Teams: FORA DO ESCOPO desta
entrega inicial. A agenda preserva horários/fuso/link/versão para adaptadores futuros.
SMTP e push reais: BLOQUEADOS para homologação externa sem configuração/credenciais atuais.
Rotação de credenciais históricas, domínio/HTTPS e aceite humano dependem dos responsáveis.
Esses pontos não foram apresentados como concluídos nem impedem testar a implementação local.

Próxima ação de produto: homologar o roteiro da seção [Plataforma integrada](#plataforma-integrada), registrar aceite por update
e priorizar as lacunas técnicas indicadas. Não mover releases futuras para a data desta execução.


---

<a id="plataforma-integrada"></a>

# Plataforma integrada: operação e contratos

> Conteúdo consolidado de `docs/plataforma_integrada.md` em 14/10/2026. O arquivo separado foi removido para manter uma única fonte de verdade.

# Plataforma integrada — operação e contratos

Implementação antecipada em 14/10/2026, exclusivamente na branch `arthur`.
A Central é uma entrada adicional para os módulos; os painéis e o ATS existentes continuam disponíveis.

## Instalação e atualização

Use Python 3.12 e MySQL 8. Para uma instalação nova, importe `sql/talentix_db.sql`.
Para banco existente, faça backup de banco, `.env` e uploads; aplique `python migrate.py`
dentro de `python/` com a conta de migração. Volte à conta runtime, com somente
SELECT/INSERT/UPDATE/DELETE, para API e workers. Nunca reimporte o SQL completo em um banco de trabalho.
A versão 007 é aditiva e idempotente. O runner mantém checksum e lock; versões 001–006 não mudaram.
DDL MySQL faz commit implícito: para retornar uma instalação inteira, restaure o backup em banco separado,
valide-o e altere a conexão. Não há promessa de rollback de DDL por transação.

No Windows, use `.venv\Scripts\python.exe` diretamente, sem alterar a política de execução do PowerShell.
API: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` dentro de `python/`.
Frontend: `python serve_frontend.py` na raiz. Abra `http://127.0.0.1:5500/html/index.html`.
Não é necessário Node/npm ou Docker para executar o produto.

Os workers profissional, IA e plataforma são processos separados:

```bash
python -m app.worker_profissional
python -m app.worker_ia
python -m app.worker_platform
```

Cada comando deve usar o interpretador virtual e o mesmo `.env` da API. O worker plataforma
executa a cada 30 segundos; `--once` permite uma execução única monitorável.
Não envie segredos em URLs nem publique a porta MySQL. O servidor estático não publica
Python, SQL, `.env`, arquivos Git, diretórios ou documentos internos, inclusive via symlink.
Produção exige proxy/servidor HTTPS e configuração dos domínios reais; o servidor incluído é de desenvolvimento.

## Equipes e isolamento

`GET /organizacoes` lista vínculos autorizados. `X-Organization-ID` seleciona o contexto,
sem conceder permissão. Ausência do cabeçalho preserva o contexto das APIs legadas.
A sessão resolve o vínculo no banco a cada requisição; o frontend não é autoridade.
Um vínculo revogado não pode reaparecer pela compatibilidade com o recrutador legado.

| Papel | Permissões |
|---|---|
| Owner | Gestão completa da própria organização, inclusive equipe, publicação e financeiro interno |
| RH Admin | Operação, equipe, publicação, automações e analytics; sem financeiro |
| Recrutador | Rascunhos de vagas, processos, entrevistas, comunicação e avaliação |
| Hiring Manager | Leitura, avaliação e analytics |
| Entrevistador | Leitura das entrevistas atribuídas e avaliação vinculada à entrevista |

Publicar/encerrar vagas exige Owner ou RH Admin. Convites têm token aleatório, hash no banco,
prazo de sete dias, e-mail confirmado correspondente e consumo único. A API impede remover o último Owner.
O administrador precisa de contexto explícito nas operações empresariais novas; seu modo usuário não mantém privilégios administrativos.
A tela da Central prioriza Owner/Recrutador/Candidato; o formulário completo de scorecard permanece no ATS.
A avaliação de entrevistador por API está limitada à atribuição, mas sua experiência de formulário na Central ainda precisa de homologação específica.

## Agenda e comunicação

`POST /agenda` recebe candidatura, recrutador, horário, fuso IANA, duração, local/link e chave de repetição.
Novos horários são armazenados em UTC. A projeção legada preserva horário local com offset e acrescenta
`DataHoraUtc`, `Fuso`, `DuracaoMin` e `Versao`. Horários locais ambíguos/inexistentes no horário de verão são rejeitados.
A criação serializa locks de empresa/candidato/recrutador e verifica sobreposição com leitura atual.
O mesmo pedido/chave retorna a entrevista existente; chave reutilizada com outro conteúdo retorna conflito.
Reagendar, cancelar e realizar exigem versão atual. Observações internas não são retornadas ao candidato.
Lembretes de 24h/1h são deduplicados por entrevista/versão e respeitam estado e preferências.

`/comunicacao` reúne processos autorizados, timeline, modelos, preferências, lotes e anexos.
Mensagens usam as rotas existentes de `/mensagens`; iniciar conversa sem contexto exige vínculo comprovado.
Lotes têm até 100 candidaturas, até dez envios por empresa/dia, chave de repetição,
validação de todos os destinatários antes de gravar e deduplicação de usuário.
O destinatário precisa aceitar comunicação em massa; essa preferência nasce desativada.
PDFs usam upload privado e autorização no download; não entram em rota estática ou cache público.
A timeline não inclui notas internas ou scorecards cegos.

SMTP usa outbox transacional. A entrega ocorre fora da transação, após reivindicação com lease,
com até cinco tentativas e espera progressiva. É necessário endereço confirmado e preferência de e-mail.
Desativar a preferência antes da entrega impede novos envios da fila. Uma interrupção depois de o provedor
aceitar e antes de gravar o resultado pode repetir a entrega: a semântica externa é ao menos uma vez.
IDs de negócio evitam repetir mensagens, tarefas e execuções internas; não existe promessa de exactly-once SMTP.

## Automações e integrações

Regras de mudança de etapa ou tempo parado executam somente notificação, tarefa ou e-mail.
Cada regra/evento possui execução única persistida; reativar regra não repete um evento consumido.
Status de candidatura, publicação e perfil nunca são alterados pelo motor ou pela IA.
A Central apresenta regras, versões, tarefas e histórico de execuções.

A fronteira para Calendar/Outlook/Meet/Teams é o registro manual de horário UTC/fuso, duração,
responsável, link/local e versão da entrevista. Um futuro adaptador deve consumir evento confirmado,
mapear ID externo por empresa/versão, usar outbox própria e OAuth com escopo mínimo e revogação.
Nenhum token OAuth ou reunião externa é criado nesta entrega. Agendamento manual é a decisão vigente.

## Orientação informativa e publicação

`/inteligencia` V2 combina habilidades declaradas (80%) e similaridade TF-IDF (20%);
sem requisitos de habilidade, o texto vale 100%. Aliases locais normalizam termos comuns.
A resposta registra fatores, requisitos obrigatórios pendentes, limites, versão e revisão humana.
Experiência, formação e logística são contexto visível, sem inventar pontuação estruturada.
Não é modelo generativo, embedding treinado, probabilidade de contratação ou recomendação decisória.
Campos estruturados sensíveis não são usados como fatores; texto livre pode conter informações
pessoais e exige revisão antes de ser usado no produto. Não há garantia estatística de ausência de viés.

A publicação de empresa/vaga é explícita e auditada. Páginas `/p/empresa/{slug}` e `/p/vaga/{slug}`
são HTML renderizado pela API, com canonical, Open Graph, JSON-LD, CSS local e conteúdo escapado.
Vaga expirada/encerrada retorna 410/noindex e sai do sitemap. Salário confidencial não entra no HTML/JSON-LD.
O botão de candidatura passa o ID da vaga ao login e ao painel do candidato.
Avaliação pública exige relação com o processo e só aparece após moderação administrativa.
Indexação por buscadores não é garantida; configurar `PUBLIC_SITE_URL` HTTPS e revisar os dados de localização.
Referência: [JobPosting do Google Search](https://developers.google.com/search/docs/appearance/structured-data/job-posting).

## Métricas, privacidade e notificações

`/analytics` filtra coorte por período de criação, vaga e responsável atual. A resposta explica os denominadores,
conta pessoas distintas por etapa e calcula duração apenas de passagens finalizadas com histórico.
Aprovação é status do processo, sem inferir admissão externa. Sem amostra, tempo é nulo.
Origem/departamento não são coletados e não são estimados. CSV neutraliza fórmulas; PDF escapa texto.
Ambos exigem permissão empresarial e são privados.

`/privacidade/meus-dados` exporta somente dados do próprio usuário; exclui hashes, sessões,
segredos, notas e avaliações internas. Consentimentos têm histórico de finalidade/versão.
Exclusão exige senha e confirmação textual, com cancelamento até `PRIVACY_DELETE_GRACE_DAYS` (padrão 7).
O worker anonimiza perfil, encerra sessões, revoga vínculos, desativa inscrições push e remove arquivos
quando não compartilhados. Último Owner deve transferir a organização primeiro.
Registros relacionais/auditoria de processos continuam existindo; não é apagamento integral de todo histórico.
CVs arquivados sem candidatura são limpos após `DATA_RETENTION_DAYS` (padrão 365).
Retenção de candidaturas, backups e auditoria precisa de política e aceite dos responsáveis antes de produção.

PWA guarda somente CSS/JS/ícones e uma tela offline genérica. Navegações autenticadas são network-only;
respostas da API, cookies e documentos não são cacheados pelo service worker.
Push é opcional, exige configuração VAPID, ação explícita e permissão do navegador.
O backend aceita somente provedores de navegador allowlisted, bloqueia destinos internos e redirects,
com lease, até três tentativas e desativação para 404/410. O payload é genérico, sem PII.
A chave privada fica no `.env`; `configure_push.py` não mostra nem substitui chaves existentes.

## Ensaio integrado para apresentação

1. Em banco fictício, cadastre empresa/candidato/recrutador e confirme os e-mails.
2. Empresa cria vaga e requisitos, publica, candidato completa perfil/CV e se candidata.
3. Empresa abre ATS, move etapa e faz avaliação humana; Central mostra o processo.
4. Cadastre entrevista manual; tente um horário sobreposto e confira a rejeição.
5. Candidato habilita preferências; empresa envia mensagem/PDF e lote; candidato consulta e marca leitura.
6. Crie regra de tarefa, mova etapa e execute o worker duas vezes; histórico deve manter uma execução.
7. Confira a orientação V2 e suas limitações, sem mudança automática de status.
8. Owner publica página da empresa/vaga; confira a página sem login, salário protegido e retorno da candidatura.
9. Veja analytics/exportações; tente o mesmo ID com outra empresa e confira a recusa.
10. Exporte dados próprios, registre consentimento e solicite/cancele exclusão.

Dados de apresentação devem ser fictícios. `seed_demo.py` é idempotente e recusa produção;
as senhas são definidas localmente, nunca distribuídas no repositório.


---

<a id="revisao-seguranca"></a>

# Revisão de segurança

> Conteúdo consolidado de `docs/revisao_seguranca.md` em 14/10/2026. O arquivo separado foi removido para manter uma única fonte de verdade.

# Revisão de segurança — 14/10/2026

Escopo: diferença da branch `arthur` a partir de `3fbc14c`, módulos legados afetados,
frontend, migração 007, worker e operação local. Revisão manual de fonte e testes,
com Bandit e auditorias de dependências. Não constitui pentest independente ou certificação.
O workflow completo do plugin Codex Security não foi executado: suas referências complementares
não estavam disponíveis no ambiente. Não há relatório fictício desse serviço.

## Controles verificados

| Risco | Controle/evidência |
|---|---|
| IDOR/BOLA entre pessoas e empresas | ACL compartilhada, sessão revalidada, contexto empresarial não confiável, testes A/B/MySQL |
| Escalada e revogação | Roles no banco, revogação prevalece sobre legado, último Owner protegido, convites vinculados a e-mail confirmado |
| CSRF/sessões | Cookie HttpOnly/SameSite, Secure em produção, token CSRF/origem nas mutações, revogação persistida |
| SQLi/mass assignment | Valores parametrizados, modelos com limites, mapas literais para nomes de coluna; revisão de cada alerta B608 |
| XSS/injeção em exportação | HTML/texto escapados, JSON-LD neutraliza delimitadores, CSV neutraliza fórmulas, PDF escapa texto |
| SSRF | Push restrito a provedores de navegador, HTTPS, DNS público e redirects desativados; sem URL arbitrária de callback |
| Upload/leitura privada | PDF validado, armazenamento separado e autorização por processo, sem publicação estática |
| Concorrência/repetição | Transações, locks atuais, versões e chaves de repetição; cenário concorrente no MySQL padrão |
| Abuso | Buckets sensíveis, tamanho de request/upload, até 100 destinatários e dez lotes/dia, preferência explícita |
| Vazamento por cache/log | API privada no-store, SW só público, logs SMTP genéricos, frontend não registra queries com tokens |
| Efeito externo antes do commit | SMTP por outbox; claim/lease fora da transação de negócio, retentativa limitada |
| IA decisória | Somente cálculo local/orientação; nenhuma publicação, contratação, reprovação ou edição autônoma |

## SAST e dependências

`python python/check_sast.py` executa Bandit 1.9.4 em `python/app` e grava relatório completo
em `test-results/bandit.json`. A revisão inicial contém 30 alertas B608 de severidade média,
com confiança baixa/média, por SQL construído com mapas/tuplas literais ou placeholders.
Cada aceitação em `security/bandit-reviewed.json` contém justificativa, linha, tipo, severidade,
confiança e SHA-256 do arquivo inteiro. Qualquer mudança no arquivo exige nova análise;
alerta novo ou alto falha no CI. Nenhuma regra foi desativada e o relatório mantém os alertas.
A revisão reduz falsos positivos conhecidos, não prova ausência de vulnerabilidade.

`pip-audit` cobre requirements-dev (inclui runtime e IA); `npm audit` cobre o lock de testes.
Auditorias verificam vulnerabilidades publicadas, sem avaliar integralmente a cadeia de suprimentos.
Versões/ferramentas devem ser atualizadas com revalidação. Relatórios e dados fictícios de teste
permanecem em artefatos do CI, sem currículos ou segredos reais.

## Limites e pendências de produção

- README mantém a exposição histórica de credenciais: rotação no provedor e limpeza coordenada
  do histórico dependem dos responsáveis. Não houve reescrita de histórico nem uso de segredo antigo.
- Rate limit é por processo; múltiplas réplicas precisam de limite compartilhado no proxy/Redis.
- Entrega SMTP/push é ao menos uma vez. Interrupção após aceite do provedor pode repetir aviso.
- Homologar SMTP/push reais, backups/restore, disponibilidade, carga sustentada, HTTPS e domínios reais.
- Fazer revisão humana de acessibilidade, privacidade e retenção, e testes específicos de perfil Entrevistador.
- Texto livre pode conter PII; o índice local não tem certificação de viés ou qualidade semântica.
- Permissões administrativas existentes continuam sensíveis e auditadas; não ampliá-las para integrações genéricas.

Esses limites constam também da agenda; não se declara RC/produção ou conformidade integral por testes automáticos.


---

<a id="fluxo-inicial"></a>

# Fluxo inicial e regras da apresentação

> Conteúdo consolidado de `docs/andamento_inicial.md` em 14/10/2026. O arquivo separado foi removido para manter uma única fonte de verdade.

# Fluxo inicial e regras da apresentação

O diagrama é conceitual: os métodos indicam responsabilidades de negócio. A API implementa essas responsabilidades em funções FastAPI com schemas Pydantic e SQL, sem ORM. Dashboard é um serviço de métricas, não uma tabela. A estrutura tem 37 tabelas de aplicação (29 de negócio e oito domínios); `Schema_Migrations` registra as atualizações de uma instalação existente.

A empresa possui histórico de assinaturas, com **no máximo uma ativa**. O banco impõe essa unicidade, a unicidade da transação de pagamento e uma avaliação por avaliador/candidatura. Uma candidatura e sua primeira etapa são confirmadas na mesma transação. Leituras isoladas usam autocommit, sem alterar o isolamento padrão do MySQL.

| Papel | Acesso inicial | Limites |
|---|---|---|
| Candidato | Perfil, documentos, vagas, candidaturas, entrevistas, comunicação e desenvolvimento | Dados próprios; só se candidata a vagas publicadas de empresas ativas |
| Empresa | Perfil da empresa, vagas, candidatos inscritos, etapas, entrevistas e equipe | Acesso apenas à empresa responsável e ao currículo anexado à candidatura |
| Recrutador | Vagas e processos da empresa de seu vínculo ativo | Não verifica empresas, administra equipe ou financeiro; revogação do vínculo remove o acesso imediatamente |
| Administrador | Métricas, verificação, denúncias, cursos, idiomas e contatos | Operações administrativas exigem perfil ativo |
| Recrutador sem vínculo | Painel de espera com seu ID | O responsável da empresa deve conceder o vínculo |

## Ensaio no navegador

1. Prepare MySQL e a configuração local. Para banco existente, execute a migração; não reimporte o SQL de instalação.
2. Crie o administrador pelo comando documentado no README e cadastre cursos de preparação no painel administrativo.
3. Cadastre uma empresa e um recrutador pela tela de login. No painel da empresa, adicione o ID mostrado no painel de espera do recrutador; ele verifica o vínculo e entra no seu painel.
4. Crie e publique uma vaga. Informe as habilidades obrigatórias no formulário da vaga.
5. Cadastre um candidato, preencha o perfil e envie um currículo fictício. Busque a vaga, escolha o documento no formulário da candidatura e envie.
6. Na empresa, abra a candidatura e o documento anexado, adicione etapas e agende a entrevista com um recrutador da própria empresa.
7. No candidato, acompanhe o status, a entrevista e as notificações. Troque mensagens pelo contexto da candidatura.
8. Solicite a compatibilidade no acompanhamento. Com o worker em execução, veja pontuação, pontos fortes, lacunas e cursos pertinentes na aba Desenvolvimento.
9. Envie um contato e consulte-o no painel administrativo. Demonstre a verificação de empresa, o catálogo e a resolução de uma denúncia fictícia.

## Compatibilidade e integrações

O worker incluído calcula um índice local com TF-IDF e habilidades declaradas; não é um modelo generativo nem uma previsão de contratação. Havendo habilidades exigidas, o peso é 80% para habilidades (respeitando nível, peso e obrigatoriedade) e 20% para similaridade textual. Sem habilidades exigidas, utiliza apenas a similaridade dos textos. Nome, e-mail, cidade, salário e outros dados pessoais não entram no cálculo. O texto vem do perfil, experiências e formações; o conteúdo de PDF/DOC não é extraído. O modelo e a justificativa ficam registrados junto ao resultado.

A fila segue NA_FILA → PROCESSANDO → CONCLUIDO/FALHOU, com recuperação de trabalhos interrompidos após dez minutos e bloqueio para evitar que dois workers assumam o mesmo registro. Cursos ativos são sugeridos quando sua descrição/categoria/título contêm uma habilidade ausente. Isso auxilia a preparação; a decisão do processo continua com a empresa. Referência do algoritmo: [documentação do scikit-learn](https://scikit-learn.org/stable/modules/feature_extraction.html#text-feature-extraction).

SMTP exige as credenciais reais do provedor, configuradas localmente. Com SMTP desativado, as notificações continuam funcionando no site; recuperação de senha não entrega e-mail. Os testes não enviam mensagens externas.

Os endpoints financeiros registram assinaturas, pagamentos e resultados autenticados. O callback é idempotente e não altera um pagamento terminal para outro resultado. **Não há checkout nem devolução de dinheiro real**: o gateway contratado deve validar sua assinatura de webhook e executar cobrança/devolução antes de registrar o resultado interno. Essa integração depende do provedor e será uma etapa separada.


---

<a id="historico-novembro"></a>

# Histórico técnico de novembro

> Conteúdo consolidado de `docs/updates_novembro.md` em 14/10/2026. O arquivo separado foi removido para manter uma única fonte de verdade.

# Novembro — Updates 4, 5 e 6

Implementação na branch `arthur`, sem merge na `main`. API 1.2.0.

## Atualização de uma instalação

Faça backup do MySQL e do volume de uploads antes de atualizar. Não reimporte
`sql/talentix_db.sql` sobre um banco existente e não use `docker compose down -v`:
essa opção remove os volumes. Atualize a branch e execute:

```powershell
git switch arthur
git pull --ff-only
docker compose up --build --wait
```

O bootstrap aplica automaticamente a migration **005**, mantendo os registros
existentes. Ela adiciona campos profissionais, cursos/projetos, versões,
texto extraído, dados confirmados, buscas salvas, histórico e deduplicação dos
alertas. Currículos antigos recebem números de versão em ordem cronológica.
O usuário de execução continua sem CREATE/ALTER/GRANT. Nenhuma migration antiga
foi reescrita e o runner continua descobrindo migrations futuras.

O novo serviço `worker-profissional` compartilha o volume de arquivos com a API
e usa a conta restrita do banco. Não há novos segredos obrigatórios no `.env`.
Não usa serviços externos de IA. Sem Docker, execute `python migrate.py` com a
conta de migração e, em outro terminal, `python -m app.worker_profissional` com a
conta operacional. A API verifica o schema na inicialização, sem executar DDL.

## Update 4: perfil profissional

Na aba **Perfil**, todos os formulários profissionais ficam na mesma tela.
Experiências e formações também permanecem disponíveis pelas abas antigas.
Headline, apresentação, localização, disponibilidade, salário, modalidades,
contratos, links, preferências e habilidades comportamentais usam
`PUT /candidatos/{id}`. Experiências, formações, certificados, habilidades técnicas
e idiomas mantêm as APIs anteriores. Cursos e projetos usam:

| Método | Endpoint | Finalidade |
|---|---|---|
| GET | `/candidatos/{id}/profissional` | Perfil, coleções, completude e faltantes |
| POST | `/candidatos/{id}/itens` | Criar curso ou projeto |
| PUT / DELETE | `/itens-profissionais/{id}` | Editar/remover item próprio |
| PUT | `/candidatos/{id}/idiomas/{id_associacao}` | Editar idioma do próprio perfil |
| POST | `/uploads/foto-perfil` | Atualizar foto da conta autenticada |

Exemplo dos novos campos:

```json
{"modalidades":["remoto","hibrido"],"tipos_contrato":["CLT","PJ"],
 "habilidades_comportamentais":["Comunicação","Colaboração"],
 "preferencias":"Tecnologia, horário comercial"}
```

Contratos aceitos: `CLT`, `PJ`, `estagio`, `temporario`, `aprendiz`, `freelancer`.
As coleções têm limites; links aceitam apenas HTTP(S) sem credenciais. O backend
valida UF, datas, salário e comprimentos, além da validação HTML/JavaScript.

Completude é calculada dos dados oficiais, nunca enviada pelo cliente. Os pesos
somam 100: foto 5; headline 10; apresentação 10; cidade/UF 5; disponibilidade 2;
modalidades 5; salário 5; contratos 5; experiências 10; formação 10; certificados
3; cursos 3; projetos 5; habilidades técnicas 5; comportamentais 3; idiomas 3;
GitHub 5; LinkedIn 2; portfólio 2; preferências 2. Campos vazios não pontuam;
disponibilidade falsa e salário zero são respostas válidas. A interface consulta
o cálculo novamente depois de salvar, adicionar, editar ou remover dados.

**Visualizar perfil salvo** abre a prévia privada dos dados persistidos, com
experiências, preferências, formação, certificados, cursos, projetos, habilidades
e idiomas. Campos ainda não salvos não entram na prévia. Cursos ficam no card
**Formação acadêmica e cursos**, com inclusão/edição pelo formulário de estudos;
o card **Projetos** recebe somente projetos. Cursos anteriormente cadastrados
continuam disponíveis com seus mesmos IDs, descrições, links e datas, sem migração
nem exclusão. A prévia e o PDF seguem essa organização. As folhas de estilo são mantidas.

Foto: JPG/PNG/WebP, até o menor limite entre 5 MB e `MAX_UPLOAD_SIZE_MB`, até
16 megapixels. O servidor confere formato real, decodifica os pixels, remove
EXIF/ICC/metadados e grava PNG de até 1200×1200. SVG é recusado. Fotos não são
mais estáticas/públicas: exigem sessão e permissão sobre o perfil, com
`private, no-store`. Perfil do candidato só pode ser lido pelo proprietário,
admin ou empresa/recrutador com candidatura autorizada; não existe diretório
público de candidatos. Isso não é RLS nativo do MySQL: é autorização contextual
na API, com testes de IDOR.

## Update 5: currículo inteligente

Cada novo documento original cria uma versão imutável; upload idêntico reutiliza
o documento da mesma pessoa, sem sobrescrever o arquivo. A escrita física é
atômica e o nome deriva de SHA-256, nunca do nome fornecido pelo usuário.
O proprietário pode escolher o principal, mudar o título ou remover logicamente
uma versão. A exclusão não apaga os bytes compartilhados; versões não excluídas
continuam disponíveis e trocar o principal não altera candidaturas anteriores.

O botão **Histórico de versões** usa `GET /candidatos/{id}/curriculos/historico`
e inclui versões arquivadas, origem, número de versão e quantidade de candidaturas
com aquele documento. Somente proprietário/admin podem listar esse histórico.
**Editar nome** altera o título sem modificar os bytes nem o currículo principal.
Arquivar remove a versão do seletor de novas candidaturas; o proprietário pode
consultá-la no histórico e a empresa só pode acessar o documento anexado à sua
própria candidatura ativa. A primeira versão disponível torna-se principal; ao
arquivar a principal, a versão disponível mais recente assume essa preferência.
Prévia inline está disponível para PDF; DOC/DOCX são baixados.

| Método | Endpoint | Finalidade |
|---|---|---|
| POST / GET | `/candidatos/{id}/curriculos` | Upload e histórico de versões |
| PUT / DELETE | `/curriculos/{id}` | Título/principal ou remoção lógica |
| POST | `/curriculos/{id}/analisar` | Enfileirar análise ou retornar análise existente |
| GET | `/curriculos/{id}/importacao` | Consultar estado, texto e prévia privada |
| POST | `/curriculos/{id}/importacao/aplicar` | Aplicar somente dados aprovados |
| POST | `/candidatos/{id}/curriculo-talentix` | Gerar nova versão PDF a partir do perfil oficial |
| GET | `/uploads/curriculos/{hash}.pdf` | Download autorizado |
| GET | `/uploads/curriculos/{hash}.pdf?preview=true` | Prévia inline autorizada |

Estados persistidos: **1 aguardando**, **2 processando**, **3 concluída**, **4
falhou**. O worker reivindica itens com lock e retoma processamento abandonado
após dez minutos. Extração ocorre em subprocesso descartável, com timeout de
45 segundos e limites de CPU/memória no Linux; o subprocesso não recebe os
segredos/credenciais do banco da API. Texto tem limite de 100 mil
caracteres e PDF de 30 páginas. O processamento não ocupa a requisição de upload.
PDF digital e DOCX são analisados; DOC permanece apenas como arquivo legado.
PDF escaneado sem texto/OCR, criptografado ou ilegível resulta em erro orientativo,
sem expor caminhos ou mensagens internas. Não há promessa de extração perfeita.

`TextoExtraido`, `DadosExtraidos` e `DadosConfirmados` ficam separados do perfil.
Nome, e-mail e telefone são sugestões de contato; o e-mail autenticador não é
trocado pela importação, pois exige o fluxo de verificação da conta. Experiências,
formação/certificados, skills e idiomas também aparecem na prévia. Na interface,
as opções individuais começam **desmarcadas**. Confirmação explícita envia:

```json
{"selecionados":{"perfil":["resumo"],"experiencias":[0],"formacoes":[],
 "habilidades":[1],"idiomas":[]},"sobrescrever_perfil":false}
```

Índices referem-se à prévia armazenada no servidor. O cliente não pode injetar
dados oficiais substitutos. `sobrescrever_perfil=false` preserva campos já
preenchidos; sugestões inválidas são recusadas com orientação para desmarcar e
corrigir manualmente. Clientes anteriores ainda podem aprovar categorias inteiras
explicitamente omitindo `selecionados`; o worker nunca chama a confirmação.

A candidatura mantém a URL da versão selecionada. A empresa/recrutador só pode
baixar o currículo anexado à candidatura da própria empresa — não o acervo, o
texto extraído ou a prévia do candidato. Downloads/preview têm autorização,
`nosniff`, cache privado e sandbox. Não há montagem estática do diretório de CVs.
O PDF Talentix usa texto escapado; não incorpora imagens/URLs externas.

A revisão separa **Formação acadêmica**, **Certificados** e **Projetos**, cada
grupo com seleção independente. A extração v2 reconhece cabeçalhos de projetos
e não deixa suas descrições entrarem no grupo anterior. Formações e certificados
vão para `Formacoes` (certificados com `Nivel='Certificado'`); projetos vão para
`Candidato_Itens` com `Tipo='projeto'`. Repetir a confirmação não duplica os itens.
O cliente envia `versao_revisao: 2`, as seleções `certificados`/`projetos` e os
respectivos indicadores `importar_certificados`/`importar_projetos`. Seleções
continuam referenciando a prévia do servidor, nunca conteúdo enviado pelo cliente.
Análises v1 com texto armazenado recebem a nova separação ao abrir a revisão,
sem reenvio do arquivo e sem alterar o texto/original ou o perfil automaticamente.
Quando o texto antigo não está disponível, os certificados são separados pelo
nível já identificado; projetos antes não extraídos podem ser adicionados na seção Projetos.
Essa compatibilidade não reclassifica registros já confirmados no perfil.

A extração v3 também reconhece cabeçalhos compostos, como **EXPERIÊNCIA PRÁTICA ·
PRINCIPAIS PROJETOS PESSOAIS** e **CURSOS E CERTIFICAÇÕES COMPLEMENTARES**. Versões
anteriores (inclusive sem versão) com texto armazenado recebem a nova separação
ao reabrir a revisão. Anos em nomes de produtos, como Office 2016, não viram datas
de estudo. A interface verifica a versão recebida e orienta a atualizar/reiniciar
API e worker quando recebe uma revisão antiga, evitando enviar índices incompatíveis.
Erros de seleção distinguem categoria desconhecida, limite de 50 itens por grupo
e referências inválidas/desatualizadas; nenhum desses casos confirma dados parciais.

## Update 6: busca profissional

`GET /vagas/busca` é paginado, público e preserva `/vagas` como API legada da
listagem e gestão empresarial. Parâmetros: `cargo`, `palavra_chave`,
`localizacao`, `modalidade`, `salario_min`, `salario_max`, `nivel`,
`tipo_contrato`, `empresa`, `dias`, `habilidades` (até dez, separadas por vírgula),
`area`, `ordenar`, `pagina`, `por_pagina`. Limite: 50 resultados por página;
`ordenar` aceita apenas `relevancia`, `data` ou `salario`.

```text
/vagas/busca?cargo=python&localizacao=contagem&modalidade=remoto&pagina=1&por_pagina=20
/html/dashboard-candidato.html?cargo=python&localizacao=contagem&modalidade=Remoto
```

Resposta: `resultados`, `total`, `pagina`, `por_pagina`, `compatibilidade_base`.
Resultados incluem empresa pública, habilidades exigidas, compatibilidade e se
o candidato já se inscreveu. Compatibilidade mede correspondência entre skills e
níveis cadastrados, não probabilidade de contratação. Sem palavras de busca, a
relevância prioriza habilidades do perfil autenticado; com termos, prioriza
correspondência do título. Empates têm ordenação estável por data/ID.
Salários confidenciais são nulos, não são inferíveis pelo filtro ou ordenação.
Vagas rascunho/pausadas/encerradas e empresas inativas não são oportunidades.
Dados empresariais privados não são projetados nos resultados nem no catálogo
público de empresas. Consultas são parametrizadas; curingas LIKE do usuário são
escapados e cláusulas ORDER BY vêm de lista fixa.

`GET /vagas/autocomplete?q=py&limite=8` exige dois caracteres e limita a dez
sugestões. A interface usa debounce e lista nativa acessível. Filtros ficam na
URL ao recarregar; buscas/histórico são vinculados à sessão, não a IDs do cliente.
O número da página também é restaurado e ajustado se o total de vagas diminuir.
Também há detalhe, favoritar, compartilhar e seleção de CV na candidatura.

| Método | Endpoint | Finalidade |
|---|---|---|
| GET / POST | `/buscas` | Listar/criar busca própria (até 30) |
| PUT / DELETE | `/buscas/{id}` | Editar/pausar/excluir busca própria |
| GET / POST | `/buscas-historico` | Histórico limitado às últimas 20 pesquisas |

Busca salva recebe `nome`, `filtros` e `ativa`. O worker gera alertas somente para
buscas ativas e vagas publicadas depois da criação da busca. A chave única
`(ID_Busca,ID_Vagas)` impede repetição. Revalida publicação e estado da busca
dentro da transação. Notificação aparece no painel; e-mail é opcional, requer
SMTP configurado e conta com e-mail confirmado. Falha de SMTP não desfaz a
notificação; não existe garantia de entrega ou reenvio automático de e-mail.

## Segurança e verificações

Mantidos: hash bcrypt, sessão HttpOnly, CSRF para escritas, rate limit, validação,
CORS restrito, transações e autorização por proprietário/papel/contexto.
Não se adicionam credenciais ao Git nem permissões DDL à conta da API/worker.

Execute `python -m pytest tests -q` em `python`. No CI, `Security checks` também
executa bootstrap Compose, migrations repetidas, MySQL real, worker real,
`tests/mysql/run_november.py`, Playwright, Axe WCAG 2.2 A/AA, teclado/reflow e
auditoria de dependências. Relatórios são anexados à execução do Actions.
Axe não certifica conformidade WCAG completa: revisão humana de texto alternativo,
leitor de tela, foco e contrastes não textuais continua necessária.


---

<a id="historico-dezembro"></a>

# Histórico técnico de dezembro

> Conteúdo consolidado de `docs/updates-dezembro.md` em 14/10/2026. O arquivo separado foi removido para manter uma única fonte de verdade.

# Dezembro — ATS para empresas

## Instalação e acesso

Na raiz do Talentix, atualize a branch `arthur`. Com o ambiente virtual ativo,
execute `python migrate.py` dentro de `python/` e reinicie a API. A migration
`006_ats.sql` acrescenta nove tabelas, índices e chaves estrangeiras. O runner
registra checksum, usa lock de migration e não reaplica versões já instaladas.
O SQL de instalação limpa também inclui essas tabelas. Não execute o SQL completo
em um banco existente: use o runner incremental.

Empresa e recrutador: abra o painel habitual e clique em **ATS / Banco de talentos**.
A nova tela é `html/ats.html`. A empresa é resolvida pela sessão; um recrutador
precisa ter vínculo ativo com ela. Não é possível escolher outra empresa pela URL.

Administrador autorizado: o mesmo link existe no painel administrativo. Informe
explicitamente o ID da empresa no campo **ID da empresa para administração
autorizada** e clique em **Abrir empresa**. Também pode usar
`html/ats.html?empresa=ID_DA_EMPRESA`. Um administrador em modo usuário continua
limitado ao papel e vínculo desse modo.

As folhas de estilo anteriormente aprovadas foram preservadas. A nova tela usa
os mesmos cards, campos, botões, diálogos e sidebar, com CSS adicional exclusivo
para o grid do Kanban.

## Update 1 — Pipeline Visual / Kanban ATS

1. Abra **Pipeline** e selecione uma vaga. O sistema cria seis etapas iniciais
   somente quando ainda não existe configuração ativa: Novos, Triagem,
   Entrevista RH, Entrevista técnica, Proposta e Contratado.
2. A lista incorpora candidaturas existentes sem duplicar cards nem apagar o
   histórico anterior do processo. **Atualizar pipeline** incorpora novas entradas.
3. Arraste um card para outra coluna ou abra **Movimentar / detalhes**. Por teclado,
   use Tab para chegar ao botão, Enter para abrir, selecione o destino e salve.
4. No diálogo, configure responsável, prazo, posição (inicia em zero), status,
   observações internas e motivo. Reprovação e retirada exigem motivo. Aprovação
   é uma escolha explícita do RH; mover para uma coluna chamada Contratado não
   aprova automaticamente.
5. **Personalizar etapas** permite criar, renomear, reordenar e arquivar colunas.
   Uma coluna com candidatos ativos precisa ser esvaziada antes do arquivamento.
6. Os filtros de responsável/status atuam na vaga selecionada. Cada coluna mostra
   a quantidade encontrada. O diálogo conserva autor, ordem temporal, estado
   anterior/novo e anotações das movimentações.

Atualizações concorrentes usam versão do card. Uma versão desatualizada recebe
409 e pede recarregamento, sem sobrescrever a mudança de outro recrutador.
A posição inserida reorganiza a coluna de forma determinística. A mudança de
status pela tela antiga e a desistência do candidato também registram evento
no ATS. Candidaturas canceladas não podem ser reativadas pelo RH nessa tela.

## Update 2 — Scorecards e entrevistas estruturadas

1. Selecione a vaga em **Pipeline**, depois abra **Scorecards**.
2. Escolha uma etapa, dê nome à avaliação e adicione critérios. Cada critério tem
   peso positivo, nota de 0 a 5 e indicação de obrigatório/opcional.
3. Deixe marcado **Ocultar avaliações dos outros até enviar a minha** para
   avaliação cega. Essa proteção é aplicada pela API, inclusive no histórico do
   banco de talentos; esconder elementos no navegador não é a proteção.
4. Selecione um candidato e clique em **Avaliar candidato**, ou use **Ver
   scorecards** nos detalhes do card. Escolha o scorecard, preencha as notas,
   comentários, parecer final e recomendação **Aprovar / Avaliar / Reprovar**.
5. Cada integrante autorizado da empresa entra com sua própria conta e envia
   sua avaliação. Após enviar, pode consultar as avaliações liberadas, a média
   individual ponderada e a média dos entrevistadores.

Cada envio é imutável e identificado pelo entrevistador/data. Não é possível
substituir uma avaliação enviada; crie outro scorecard para uma nova rodada.
Critérios opcionais sem nota não entram no denominador. Ao menos uma nota é
necessária. A recomendação e as médias não mudam a candidatura: o RH toma a
 decisão no Pipeline.

## Update 3 — Talent CRM / Banco de talentos

**Autorização do candidato:** no painel do candidato, em Perfil, a seção
**Banco de talentos das empresas** lista empresas para as quais ele se candidatou.
Ele pode escolher **Autorizar banco de talentos** ou **Revogar autorização**.
A autorização começa desativada e não afeta a candidatura atual.

1. No ATS, abra **Banco de talentos** e **Gerenciar pools**. Crie pools como Backend,
   Frontend, Full Stack, Dados, QA, Jovem Aprendiz, Estágio ou Administrativo.
   Os nomes são configuráveis; também é possível renomear ou arquivar pools.
2. Pesquise por nome, habilidade, formação/curso, experiência/cargo e tag. Combine
   pool, favoritos e **Previamente avaliados**; a lista tem páginas de 20 resultados.
3. Abra **Histórico / pools / convite** de um talento. O histórico mostra somente
   os processos desta empresa, vagas anteriores, status, motivos de reprovação
   e scorecards liberados para a conta atual.
4. Escolha um pool, adicione tags, favorito e notas internas e salve. Use
   **Editar tags / notas** ou **Remover do pool** para ajustar os vínculos.
5. Escolha uma vaga publicada e **Enviar convite**. O candidato recebe uma
   notificação no painel e decide se quer se candidatar. O convite não cria
   candidatura automaticamente e não envia e-mail externo.

O banco requer simultaneamente relacionamento prévio com a empresa e
consentimento específico para ela. Autorizar a empresa A não autoriza B. Revogar
retira o candidato das buscas, impede novos convites e limpa tags/favoritos/notas
 dos pools dessa empresa. O histórico de candidaturas e avaliações fica preservado
para o processo anterior; não é exposto a outras empresas nem ao candidato como
notas internas.

## Update 4 — Consolidação e integração

- As rotas ATS exigem papel e autorização sobre empresa/vaga/candidatura/pool.
- Candidatos acessam somente suas próprias autorizações e dados públicos do
  processo. Notas de entrevistas internas também foram retiradas das respostas
  de candidatura/entrevistas destinadas ao candidato.
- As mutações usam CSRF e transações. Queries recebem parâmetros; IDs enviados
  para outro tenant não ampliam o escopo.
- O rate limit transversal inclui ATS e agrupa URLs por domínio de API, impedindo
  contornar o limite alternando IDs. Respostas ATS usam `Cache-Control: no-store`.
- Movimentações, avaliações, pools, convites e consentimentos têm auditoria.
- MySQL tem índices por vaga/etapa/empresa/candidato e unicidade de avaliação,
  convite e sequência do histórico.
- Testes HTTP cobrem IDOR, vínculos desativados, admin, CSRF, rate limit,
  notas obrigatórias, avaliação cega, isolamento do CRM, revogação, ordenação,
  conflitos e desistência. CI executa também MySQL real e Playwright E2E.
- Playwright verifica quatro larguras na interface ATS, drag-and-drop, alternativa
  por teclado, avaliações, pools e auditoria axe. Outro cenário usa API/MySQL reais
  para candidatura, consentimento, pipeline, avaliação, convite e revogação.

## Verificação

Com dependências instaladas, na raiz:

```text
python -m pytest python/tests -q
npm run test:ats --prefix web-tests
```

`npm test --prefix web-tests` inclui os fluxos reais e exige o ambiente descartável
`TALENTIX_ISOLATED_TESTS=1`. O GitHub Actions prepara MySQL 8, roda migrations duas
vezes, testes de API e ATS, navegador, acessibilidade e auditoria de dependências.
Não execute os scripts de integração num banco de uso cotidiano.


---

<a id="requisitos-originais-seguranca"></a>

# Requisitos originais de segurança

> Pedido original preservado como fonte histórica. A seção [Segurança obrigatória](#segurança-obrigatória) registra a interpretação técnica vigente: senhas usam hash bcrypt/Argon2, e o MySQL aplica isolamento equivalente a RLS por autorização central, escopo de queries e privilégio mínimo.

segurança do talentix, verifique o repositório TALENTIX.  Sistema de RLS diretamente no banco de dados, para evitar que pessoas com más pretensões roube os dados (somente administradores, arthurhpb7@gmail.com/administrador e outros futuros adms do talentix) tenha acesso a eles. Segundo, mude todos as variáveis que exigem senha de "password" para "bcript" para também gerar uma camada a mais de segurança nas senhas dos usuários e mantê-las criptografadas. Terceiro, exija que todas as rotas do site tenham um rate limit, para evitar que pessoas dropem os dados da aplicação. Quarto, não deixe o front-end e nem do back-end sem validação. Quinto, bloqueie todos os campos de entrada de dados para evitar invasores a inserirem comandos na minha aplicação (SQLi). Sexto, faça com que essa aplicação tenha uma camada de segurança boa contra ataques de IDOR. Sétimo, proteja o site de ataques CSRF, onde evita usuários mal-intencionados executem ações não planejadas no nosso site (bloqueando cookies de sessão ativos do navegador). Oitavo, deixe os tokens do site sempre otimizados. Nono, evite deixar que usuários pratiquem SSRF na aplicação, evitando-os a enviarem requisições HTTP para destinos inesperados e internos. Décimo, deixe os cookies do site seguros, procure sempre utilizar as diretrizes corretas aos usuários. E para encerrar, implemente o CORS (Cross-Origin Resource Sharing) na aplicação como um mecanismo de segurança, restringindo requisições HTTP feitas para domínios diferentes


---

<a id="agenda-original"></a>

# Agenda original completa até maio de 2027

> Planejamento original preservado integralmente. O estado real e as decisões posteriores ficam na seção [Estado oficial dos 23 updates](#estado-roadmap).

# Visão do Talentix para maio de 2027

O produto final deveria funcionar como quatro sistemas integrados:

| Área | Resultado esperado |
|---|---|
| Candidato | Perfil profissional, currículo, busca, matching, candidatura, acompanhamento, entrevistas e recomendações |
| Empresa/RH | ATS completo, banco de talentos, pipeline, entrevistas, avaliações, comunicação e analytics |
| IA | Matching explicável, busca semântica, resumo de perfil, análise de lacunas e assistência ao recrutador |
| Plataforma | Segurança, acessibilidade, observabilidade, SEO, administração, integrações e deploy real |

A regra será **até 3 releases relevantes por mês**, evitando commits gigantes e permitindo testar cada módulo antes do próximo.

---

# Outubro de 2026 — Fundação profissional

## Update 1 — Estabilização e arquitetura

Primeiro eu fecharia completamente a base que já existe.

Entregas:

- deixar GitHub Actions 100% verde;
- eliminar inconsistências entre `talentix_db.sql`, migrations e banco existente;
- migrations versionadas `001`, `002`, `003` etc.;
- padronizar erros da API;
- revisar todos os endpoints;
- documentação OpenAPI organizada;
- logging estruturado;
- IDs de requisição;
- separar configurações `development`, `test` e `production`;
- Docker Compose com FastAPI + MySQL;
- script único de instalação;
- seed de demonstração.

Critério de conclusão:

```text
clone
→ configurar .env
→ docker compose up
→ migrations
→ seed
→ aplicação funcionando
```

sem intervenções manuais.

---

## Update 2 — Segurança e contas 2.0

O login já existe, mas precisa evoluir para padrão de produto real.

Implementaria:

- confirmação de e-mail;
- alteração de e-mail;
- alteração de senha;
- sessões ativas;
- botão “encerrar todas as sessões”;
- rate limiting;
- proteção contra brute force;
- bloqueio temporário após tentativas repetidas;
- autenticação em dois fatores opcional;
- registro de último login;
- histórico de acessos;
- auditoria de alterações administrativas;
- permissões mais granulares.

Novo conceito:

```text
Usuário
 ├── Candidato
 ├── Empresa
 ├── Recrutador
 └── Administrador
```

mas permitindo múltiplos papéis quando necessário.

---

## Update 3 — Acessibilidade completa

Esse deveria ser um diferencial forte do Talentix.

Meta:

**WCAG 2.2 AA.**

O W3C recomenda WCAG 2.2 para maximizar a acessibilidade futura, cobrindo necessidades relacionadas a visão, audição, movimento e aspectos cognitivos, em desktop e dispositivos móveis. [W3C](https://www.w3.org/TR/wcag/?utm_source=chatgpt.com)

Implementaria:

- navegação completa por teclado;
- foco visível;
- contraste adequado;
- `aria-label`;
- landmarks semânticos;
- formulários acessíveis;
- mensagens de erro acessíveis;
- suporte a leitores de tela;
- `prefers-reduced-motion`;
- zoom 200% sem quebrar interface;
- tamanho mínimo de áreas clicáveis;
- modo alto contraste;
- testes automatizados de acessibilidade.

Isso combina muito bem com o próprio conceito do nome **Talentix: ampliar acesso às oportunidades**.

---

# Novembro de 2026 — Experiência do candidato

## Update 4 — Perfil profissional 2.0

O candidato passaria a ter um perfil comparável a plataformas profissionais.

Adicionar:

- foto;
- headline;
- apresentação;
- cidade/estado;
- disponibilidade;
- modalidade desejada;
- pretensão salarial;
- tipos de contrato;
- experiências;
- formações;
- certificados;
- cursos;
- projetos;
- habilidades;
- idiomas;
- links GitHub/LinkedIn/portfólio;
- preferências profissionais.

Criaria ainda um:

```text
Completude do perfil: 82%
```

com orientações:

```text
+10% adicionar experiência
+5% adicionar GitHub
+3% adicionar idioma
```

---

## Update 5 — Currículo inteligente

Hoje vocês têm currículos, mas podem transformar isso em um sistema muito mais interessante.

Implementaria:

```text
Upload PDF
      ↓
Extração de texto
      ↓
Experiências
Formação
Skills
Idiomas
Contato
      ↓
Sugestão para preencher perfil
```

Nunca alteraria automaticamente os dados; o candidato confirma.

Também:

- múltiplas versões de currículo;
- currículo principal;
- preview no navegador;
- geração de currículo Talentix;
- exportação PDF;
- histórico de versões;
- currículo específico por candidatura.

---

## Update 6 — Busca de vagas profissional

Criaria um verdadeiro mecanismo de busca:

```text
Cargo
Localização
Remoto/Híbrido/Presencial
Faixa salarial
Senioridade
Contrato
Empresa
Data de publicação
Skills
```

Com:

- paginação;
- ordenação;
- autocomplete;
- histórico de pesquisas;
- buscas salvas;
- filtros persistentes;
- alerta de novas vagas.

Isso transforma o sistema de “lista de vagas” em marketplace de empregos.

---

# Dezembro de 2026 — ATS para empresas

## Update 7 — Pipeline visual

Esse é um dos recursos mais importantes.

Criaria Kanban:

```text
Novos
  ↓
Triagem
  ↓
Entrevista RH
  ↓
Entrevista técnica
  ↓
Proposta
  ↓
Contratado
```

Com drag-and-drop.

Cada vaga poderá ter seu próprio pipeline.

Também:

- motivos de reprovação;
- histórico de movimentação;
- responsável por etapa;
- prazo da etapa;
- observações internas.

---

## Update 8 — Scorecards e entrevistas estruturadas

Greenhouse coloca contratação estruturada e scorecards no centro do produto, justamente para que candidatos sejam avaliados com os mesmos critérios. [Greenhouse](https://www.greenhouse.com/blog/structured-hiring-explained?utm_source=chatgpt.com)

Talentix deveria adicionar:

```text
Entrevista Backend Developer

Python ................ 4/5
SQL ................... 5/5
APIs .................. 4/5
Comunicação ........... 3/5
Resolução de problemas  5/5
```

Com:

- critérios configuráveis;
- pesos;
- comentários;
- avaliadores diferentes;
- média automática;
- decisão final;
- histórico.

Isso deixa o sistema muito mais sério para RH.

---

## Update 9 — Talent CRM

Hoje um candidato normalmente existe associado ao processo.

Criaria um banco de talentos independente:

```text
Talent Pool
├── Backend
├── Front-end
├── Dados
├── Jovem Aprendiz
└── Estágio
```

Recursos:

- tags;
- notas;
- favoritos;
- pesquisa por skills;
- pesquisa por experiência;
- histórico;
- candidato já avaliado;
- convite para vaga;
- segmentação.

Workable também trata um Talent CRM pesquisável como parte central de seu ATS. [Workable](https://www.workable.com/features/?key=job-descriptions\&utm_source=chatgpt.com)

---

# Janeiro de 2027 — Comunicação e automação

## Update 10 — Agenda de entrevistas

Criaria calendário Talentix:

```text
Janeiro 2027
SEG TER QUA QUI SEX
        14:00 João
             Backend
```

Recursos:

- disponibilidade do recrutador;
- disponibilidade do candidato;
- autoagendamento;
- reagendamento;
- cancelamento;
- timezone;
- lembretes.

Greenhouse e Workable oferecem autoagendamento e integração com calendário justamente para reduzir o trabalho manual de coordenação. [Greenhouse](https://www.greenhouse.com/candidate-experience?utm_source=chatgpt.com)

Arquitetura preparada para:

- Google Calendar;
- Outlook;
- Google Meet;
- Microsoft Teams.

---

## Update 11 — Central de comunicação

Unificaria:

```text
Mensagens
E-mail
Notificações
Eventos
```

dentro de uma timeline:

```text
10:30 Candidato enviou candidatura
11:15 RH abriu currículo
14:20 Mensagem enviada
17:00 Entrevista marcada
```

Também:

- templates de mensagem;
- mensagens em massa;
- lembretes;
- confirmação de leitura;
- anexos;
- resposta diretamente pelo processo seletivo.

---

## Update 12 — Motor de automação

Esse seria um recurso excelente para apresentação.

Exemplo:

```text
QUANDO
candidatura entrar em "Entrevista"

ENTÃO
enviar notificação
+
enviar e-mail
+
criar tarefa para recrutador
```

Outro:

```text
SE
candidato permanecer 7 dias em Triagem

ENTÃO
avisar recrutador
```

Ou:

```text
SE
score >= 85

ENTÃO
marcar como candidato prioritário
```

Isso aproxima bastante o Talentix de ATS comerciais modernos, nos quais workflows e automações são um recurso central. [Workable](https://www.workable.com/features/?key=job-descriptions\&utm_source=chatgpt.com)

---

# Fevereiro de 2027 — Talentix IA 2.0

Esse deveria ser o mês de maior diferencial técnico.

## Update 13 — Matching semântico

Hoje vocês já têm TF-IDF e skills.

Eu manteria isso como camada explicável, mas adicionaria embeddings.

Arquitetura:

```text
Vaga
 ↓
Skills + texto + experiência
 ↓
Embedding

Candidato
 ↓
Currículo + skills + experiência
 ↓
Embedding

        ↓

similaridade semântica
+
requisitos obrigatórios
+
pesos do recrutador
+
regras estruturadas
        ↓
Score Talentix
```

Resultado:

```text
Compatibilidade: 87%

Skills obrigatórias     92%
Experiência             80%
Formação                90%
Localização            100%
Skills desejáveis       75%
```

Não apenas:

```text
87%
```

---

## Update 14 — IA explicável

A IA nunca deveria apenas dizer “esse candidato é melhor”.

Mostrar:

```text
Pontos fortes
• Python: 2 anos
• FastAPI
• MySQL
• APIs REST

Lacunas
• Docker solicitado
• AWS desejável
• inglês intermediário solicitado
```

Para candidatos:

```text
Você tem 7 de 9 requisitos.
```

Para RH:

```text
Por que o candidato recebeu 84%?
```

Isso segue uma direção sensata em produtos atuais: usar IA dentro de critérios definidos e manter humanos responsáveis pela decisão. [Greenhouse](https://www.greenhouse.com/blog/structured-hiring-explained?utm_source=chatgpt.com)

---

## Update 15 — Assistente Talentix

Criaria um assistente de IA restrito ao domínio da plataforma.

Para empresa:

```text
"Crie uma descrição para uma vaga
de desenvolvedor Python Júnior."
```

Ele produz rascunho, nunca publica automaticamente.

Para candidato:

```text
"Como posso melhorar meu perfil para esta vaga?"
```

Resultado:

```text
1. Adicionar experiência com APIs
2. Informar seu conhecimento em SQL
3. Adicionar projeto FastAPI ao portfólio
```

Também:

- resumo automático de candidato;
- resumo de vaga;
- sugestão de skills;
- sugestão de perguntas de entrevista.

LinkedIn hoje destaca assistência de IA para busca, insights e mensagens de recrutamento, enquanto Gupy usa IA para ordenar candidatos conforme critérios definidos. [LinkedIn Business Solutions](https://business.linkedin.com/hire/product-update/wave2-2025?utm_source=chatgpt.com)

---

# Março de 2027 — Marketplace e alcance

## Update 16 — Página pública de empresas

Cada empresa ganha algo como:

```text
talentix.com.br/empresa/nubank
```

Com:

- logo;
- capa;
- descrição;
- setor;
- tamanho;
- localização;
- cultura;
- benefícios;
- tecnologias;
- redes;
- vagas abertas;
- avaliações.

Isso transforma Talentix também em plataforma de employer branding.

---

## Update 17 — Página pública de vagas + SEO

Cada vaga:

```text
talentix.com.br/vagas/desenvolvedor-python-1234
```

Adicionar:

```html
<script type="application/ld+json">
{
  "@type": "JobPosting"
}
</script>
```

O Google documenta que `JobPosting` pode tornar vagas elegíveis à experiência especializada de busca de empregos, inclusive com informações como cargo, local e empresa. [Google for Developers](https://developers.google.com/search/docs/appearance/structured-data/job-posting?hl=pt-br\&utm_source=chatgpt.com)

Também:

- sitemap;
- canonical URL;
- Open Graph;
- compartilhamento LinkedIn;
- compartilhamento WhatsApp;
- metadata dinâmica.

Isso pode trazer candidatos sem eles conhecerem Talentix previamente.

---

## Update 18 — PWA e experiência mobile

Transformaria em Progressive Web App.

Adicionar:

```text
manifest.json
service-worker.js
icons/
```

Permitir:

```text
Instalar Talentix
```

no celular.

Também:

- layout mobile completo;
- notificações push;
- navegação mobile;
- candidatura simplificada;
- upload de currículo pelo celular.

Não faria app Android/iOS separado nesse estágio. PWA entrega muito mais resultado pelo tempo disponível.

---

# Abril de 2027 — Plataforma empresarial

## Update 19 — Analytics avançado

Dashboard de RH deveria mostrar:

```text
Vagas abertas
Candidaturas
Conversão
Tempo médio por etapa
Tempo até contratação
Taxa de desistência
Origem dos candidatos
Entrevistas realizadas
Taxa de aprovação
```

Funil:

```text
1.250 candidaturas
      ↓ 38%
475 triagens
      ↓ 40%
190 entrevistas
      ↓ 20%
38 propostas
      ↓ 84%
32 contratações
```

Também:

- filtro por período;
- vaga;
- recrutador;
- departamento;
- exportação CSV/PDF.

Analytics já faz parte do núcleo de ATS como Greenhouse e Workable. [Greenhouse](https://www.greenhouse.com/pricing?utm_source=chatgpt.com)

---

## Update 20 — Empresa multiusuário e RBAC

Hoje existe empresa/recrutador.

Eu expandiria para:

```text
Empresa
├── Owner
├── Administrador RH
├── Recrutador
├── Hiring Manager
└── Entrevistador
```

Permissões:

| Função | Vagas | Candidatos | Entrevistas | Financeiro |
|---|---:|---:|---:|---:|
| Owner | ✓ | ✓ | ✓ | ✓ |
| RH Admin | ✓ | ✓ | ✓ | — |
| Recrutador | ✓ | ✓ | ✓ | — |
| Hiring Manager | leitura | ✓ | ✓ | — |
| Entrevistador | — | limitado | ✓ | — |

Isso é muito mais próximo de sistemas empresariais reais.

---

## Update 21 — Auditoria, LGPD e governança

Criaria:

```text
AuditLogs
```

registrando:

```text
Quem
Quando
IP
Ação
Recurso
Valor anterior
Valor novo
```

Também:

- consentimentos;
- exportar meus dados;
- excluir conta;
- anonimização;
- retenção de currículos;
- política de dados;
- histórico de consentimento;
- exclusão automática após período configurado.

Admin poderia consultar:

```text
Arthur alterou vaga #382
01/04/2027 14:32
```

---

# Maio de 2027 — Fechamento do produto

Eu faria apenas **duas grandes releases** nesse mês.

## Update 22 — Hardening e performance

Nenhuma funcionalidade nova grande.

Somente qualidade:

```text
segurança
performance
acessibilidade
responsividade
testes
bugs
UX
```

Executaria:

- testes unitários;
- testes de API;
- MySQL real;
- testes E2E;
- Playwright;
- testes de acessibilidade;
- testes de carga;
- concorrência;
- uploads;
- segurança;
- recuperação de senha;
- permissões;
- migrations;
- backup/restore.

Meta:

```text
CI: 100% verde
```

e nenhuma vulnerabilidade crítica conhecida nas dependências.

---

# Update 23 — Release Candidate e apresentação final

Entre aproximadamente **10 e 20 de maio de 2027**, congelaria funcionalidades.

Versão:

```text
Talentix 1.0 RC
```

Depois só:

```text
bugfix
documentação
polimento
```

Entrega final:

```text
Talentix 1.0
```

com ambiente de demonstração real.

Prepararia três usuários:

```text
candidato@demo.talentix.com
empresa@demo.talentix.com
admin@demo.talentix.com
```

e dados fictícios cuidadosamente construídos.

A demonstração deveria conseguir mostrar em sequência:

```text
CANDIDATO
cria perfil
→ adiciona currículo
→ recebe recomendação
→ visualiza explicação da IA
→ candidata

EMPRESA
publica vaga
→ recebe candidato
→ vê matching
→ movimenta pipeline
→ avalia scorecard
→ agenda entrevista

CANDIDATO
recebe notificação
→ escolhe horário
→ acompanha processo

EMPRESA
finaliza contratação

ADMIN
visualiza métricas
→ usuários
→ empresas
→ denúncias
→ auditoria
```

Essa história vale muito mais em uma apresentação do que mostrar 100 endpoints isolados.

---

# Cronograma resumido

| Mês | Update 1 | Update 2 | Update 3 |
|---|---|---|---|
| **Out/26** | Arquitetura/CI | Segurança 2.0 | Acessibilidade |
| **Nov/26** | Perfil 2.0 | Currículo inteligente | Busca de vagas |
| **Dez/26** | Pipeline Kanban | Scorecards | Talent CRM |
| **Jan/27** | Agenda | Comunicação | Automações |
| **Fev/27** | Matching semântico | IA explicável | Assistente IA |
| **Mar/27** | Empresa pública | SEO/JobPosting | PWA/mobile |
| **Abr/27** | Analytics | RBAC empresarial | LGPD/auditoria |
| **Mai/27** | Hardening | Talentix 1.0 | — |

São **23 releases relevantes em oito meses**, nunca ultrapassando três em um mês.

# O que eu deixaria fora da versão 1.0

Mesmo plataformas como Workable hoje agrupam recursos como SMS, videoentrevistas, assessments, referrals, e-signatures e diversos sistemas de RH. [Workable](https://www.workable.com/pricing?utm_source=chatgpt.com) Tentar implementar todos de forma completa diminuiria a qualidade do Talentix.

Eu deixaria para uma eventual **Talentix 2.0**:

- folha de pagamento;
- controle de ponto;
- onboarding de funcionário completo;
- avaliação de desempenho de funcionários;
- benefícios;
- app Android/iOS nativo;
- marketplace de cursos próprio;
- background check real;
- assinatura eletrônica própria;
- videoconferência própria.

Em 1.0, é melhor **integrar** esses serviços do que tentar recriá-los.

# Os cinco diferenciais que eu priorizaria

Se chegarmos em maio com apenas cinco coisas realmente excepcionais, eu escolheria:

1. **Matching explicável**, não uma porcentagem misteriosa.
2. **Pipeline + contratação estruturada + scorecards**.
3. **Experiência excelente de candidato**, especialmente mobile.
4. **Acessibilidade WCAG 2.2 AA**.
5. **Arquitetura, segurança e testes de nível profissional**.

O Talentix então deixaria de parecer apenas “um site para procurar emprego” e passaria a se apresentar como um **ATS + marketplace de vagas + Talent CRM + mecanismo de matching**, que é uma posição muito mais convincente diante dos professores e também muito melhor para seu portfólio.

A partir de agora, eu trataria esse cronograma como o **roadmap oficial do projeto**: cada uma dessas 23 entregas vira um milestone no GitHub, com issues menores, critérios de aceite e testes associados.
