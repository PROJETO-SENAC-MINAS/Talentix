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
| 4 — Nov/26, perfil | PARCIAL | PARCIAL: experiências/formações/projetos/certificações, privacidade e revisão manual preservados | Aceite humano; detalhes em updates_novembro.md |
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

Próxima ação de produto: homologar o roteiro de `plataforma_integrada.md`, registrar aceite por update
e priorizar as lacunas técnicas indicadas. Não mover releases futuras para a data desta execução.
