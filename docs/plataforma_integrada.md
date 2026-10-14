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
