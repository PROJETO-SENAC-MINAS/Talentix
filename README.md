# Talentix

Plataforma full stack de recrutamento com HTML, CSS, JavaScript, FastAPI e MySQL 8.
A API inclui cadastro, autenticação, perfis, currículos, vagas, candidaturas,
entrevistas, mensagens, painéis por papel, contatos persistidos, compatibilidade local
e endpoints protegidos para serviços de IA e pagamentos.

## Segurança e credenciais anteriormente expostas

O `.env` e os currículos de demonstração foram removidos da versão atual desta
branch. Uma remoção em um commit **não apaga versões anteriores nem outras
branches**. Os valores antigos devem ser considerados comprometidos.

Antes de executar uma instalação que usava esse `.env`:

1. Revogue a senha de aplicativo SMTP na conta do provedor de e-mail e gere outra.
2. Execute `python configure_dev.py --rotate-keys`, dentro de `python/`, para
   substituir `SECRET_KEY`, `IA_WORKER_TOKEN` e `PAYMENT_WEBHOOK_TOKEN` no `.env`
   local. Isso invalida cookies e links de recuperação assinados com a chave antiga.
3. Configure a senha SMTP nova no `.env` local; não reutilize a senha publicada.
4. Para remover os arquivos do histórico de todo o repositório, coordene com os
   mantenedores uma limpeza de histórico e dos demais branches. Esta correção
   preserva o histórico compartilhado e trabalha somente na branch solicitada.

Nunca versione `.env`, credenciais, currículos de pessoas reais ou arquivos de
upload. O único arquivo de configuração distribuído é `python/.env.example`,
com os campos secretos vazios. `configure_dev.py` gera chaves aleatórias distintas,
sem exibi-las no terminal. A API recusa uma chave de sessão com menos de 64
caracteres; a chave antiga publicada não atende a esse requisito.

## Executar localmente

Requisitos: Python 3.12, MySQL 8 e um servidor HTTP para o frontend.

Na raiz do repositório, importe o banco:

```bash
mysql -u root -p < sql/talentix_db.sql
```

O script cria e usa o banco `talentix`. Crie no MySQL um usuário exclusivo para a
aplicação, com permissões `SELECT`, `INSERT`, `UPDATE` e `DELETE` nesse banco;
informe seu usuário e sua senha no `.env` em vez de usar a conta root.

Prepare a API:

```bash
cd python
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-ia.txt
python configure_dev.py
```

No Windows/PowerShell, a ativação é `.venv\Scripts\Activate.ps1`.
Edite `python/.env` para preencher `DB_USER` e `DB_PASSWORD`. O configurador não
sobrescreve um arquivo existente sem `--rotate-keys`.

Ainda dentro de `python/`, inicie a API:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Em outro terminal, na raiz do repositório:

```bash
python -m http.server 5500 --bind 127.0.0.1
```

Abra `http://127.0.0.1:5500/html/index.html`. A documentação interativa da API fica
em `http://127.0.0.1:8000/docs`. Use o mesmo host definido em `FRONTEND_ORIGIN`;
`localhost` e `127.0.0.1` são origens diferentes.

## Sessões, arquivos e integrações

- Cookies usam `HttpOnly` e `SameSite=Lax`. `SESSION_COOKIE_SECURE` é `true` por
  padrão. Em produção, use HTTPS e mantenha esse valor. O configurador de
  desenvolvimento define `false` somente para o ambiente HTTP local.
  Em configurações locais antigas que não possuem esse campo, acrescente
  `SESSION_COOKIE_SECURE=false` se estiver usando HTTP, depois de rotacionar as chaves.
- Candidaturas, análises e entrevistas são limitadas ao candidato responsável,
  à empresa dona da vaga ou ao administrador, conforme a operação.
- Fotos e logos possuem rotas públicas. Currículos não possuem rota estática:
  `/uploads/curriculos/{arquivo}` exige sessão e só permite o dono, um
  administrador ou a empresa à qual o arquivo foi anexado em uma candidatura.
  Uma empresa não tem acesso a todo o acervo de currículos de um candidato.
- A criação de uma candidatura valida que o currículo anexado pertence ao candidato.
- Todas as rotas de processamento/falha de IA exigem o cabeçalho
  `X-IA-Worker-Token`, correspondente a `IA_WORKER_TOKEN`.
- A confirmação de pagamentos exige `X-Payment-Webhook-Token`, correspondente a
  `PAYMENT_WEBHOOK_TOKEN`. Os tokens de IA, pagamento e sessão devem ser distintos
  e enviados somente por serviços confiáveis, através de HTTPS.
- Uma integração com token vazio permanece desativada (`503`). Um token ausente
  ou incorreto em uma integração configurada retorna `401`. Cookies de usuários
  não substituem esses tokens.
- A criação e a renovação manual de assinaturas são exclusivas do administrador;
  uma empresa não pode atribuir a si própria uma assinatura ativa.

## Atualizar um banco existente

Faça um backup e, dentro de `python/`, execute `python migrate.py` com uma conta
MySQL autorizada a executar DDL. O script consulta a configuração local e aplica
somente as alterações incrementais. Depois, volte a executar a API com o usuário
restrito a `SELECT`, `INSERT`, `UPDATE` e `DELETE`.

A migração pode ser repetida e não apaga registros de negócio. Ela verifica
transações de pagamento duplicadas, avaliações repetidas e múltiplas assinaturas
ativas antes de executar DDL. Se encontrar um conflito, interrompe a atualização
para revisão dos dados. O SQL de instalação deve ser usado somente em banco novo;
reimportá-lo sobre uma instalação existente não substitui uma migração.

## Administrador e worker de compatibilidade

Crie o primeiro administrador local, informando a senha de forma interativa:

```bash
cd python
python create_admin.py --nome "Administrador" --email "seu-email@exemplo.com"
```

Com `requirements-ia.txt` instalado e `IA_WORKER_TOKEN` configurado, execute em
outro terminal dentro de `python/`:

```bash
python -m app.worker_ia
```

Para processar a fila existente e sair, use `python -m app.worker_ia --once`.
O worker usa o mesmo banco, não envia dados a serviços externos e não precisa de
chave de provedor de IA. O modelo TF-IDF e as habilidades fornecem um índice
explicável; não são uma previsão de contratação. A metodologia e o roteiro estão
em [docs/andamento_inicial.md](docs/andamento_inicial.md).

As empresas e os candidatos fazem cadastro na interface. Recrutadores têm uma
conta própria e aguardam o vínculo concedido no painel da empresa. Os painéis
validam o papel na API; a autorização nunca depende apenas do redirecionamento.
Mudança de senha invalida sessões anteriores. Vagas em rascunho são privadas,
e o salário confidencial não aparece na resposta pública da API.

## Testes

```bash
cd python
pip install -r requirements-dev.txt
python -m pytest tests -q
```

A suíte rápida verifica segurança HTTP em SQLite isolado e propriedades do índice
de compatibilidade. Os testes completos usam MySQL 8 com isolamento padrão e
Chromium, incluindo falha no segundo INSERT do cadastro, rollback, concorrência,
revogação, migração de esquema anterior e worker real.

O workflow `.github/workflows/security-checks.yml` executa essas suítes, o roteiro
no navegador, a validação Mermaid/HTML, `pip-audit` e `npm audit`. Também impede que
configurações privadas, caches ou uploads sejam versionados. Os dados e as senhas
do CI são fictícios e exclusivos de serviços descartáveis.

Para verificar os arquivos e o diagrama localmente (Node 24):

```bash
npm ci --prefix web-tests --ignore-scripts
npm run check --prefix web-tests
```

Os scripts `python/tests/mysql/run_scenarios.py`, `run_regressions.py` e
`web-tests/flow.cjs` são destinados **somente a banco descartável de testes**.
Exigem `TALENTIX_ISOLATED_TESTS=1`, variáveis de conexão e uma API de teste em
execução. A preparação reproduzível completa está no workflow; não execute esses
scripts no banco pessoal ou compartilhado. `run_scenarios.py` exige banco vazio e
não o apaga. Os resultados ficam em `test-results/`, fora do controle de versão.

## Serviços externos

O contato é gravado no banco e aparece para o administrador. As notificações são
persistidas junto à operação; SMTP ocorre após o commit. Para entrega de e-mail,
habilite e configure SMTP com credenciais atuais no seu `.env`.

Os pagamentos continuam sendo registros internos: não há checkout nem estorno
financeiro real. Uma integração com um provedor deve validar assinatura de webhook,
valor, identidade da transação e executar a movimentação financeira. Os testes de
callback usam tokens isolados e não movimentam dinheiro.


## Execução com Docker Compose

Updates 4–6 (perfil profissional, currículo inteligente e busca profissional):
consulte [o contrato das APIs e a atualização segura](docs/updates_novembro.md).
O Compose inicia também o `worker-profissional` e aplica a migration 005 sem
apagar os dados existentes.

O ambiente local usa Docker Compose v2 com MySQL 8.4, bootstrap, FastAPI e frontend.
Na raiz, faça a configuração inicial uma única vez:

```bash
python python/configure_dev.py
cp .env.example .env
```

No PowerShell, use `Copy-Item .env.example .env`. Se `python/.env` já existe,
preserve-o e pule `configure_dev.py`. Preencha no `.env` **da raiz**
`MYSQL_ROOT_PASSWORD` e `MYSQL_APP_PASSWORD` com senhas diferentes e novas.
Para criar as três contas de apresentação, defina também `SEED_DEMO=true` e
`DEMO_PASSWORD` com pelo menos 12 caracteres. Não versione nenhum `.env`.
Depois execute:

```bash
docker compose up --build --wait
```

A sequência automática é: banco saudável → migrations → conta de runtime com
somente SELECT/INSERT/UPDATE/DELETE → seed opcional → API saudável → frontend.
Qualquer falha do bootstrap impede o início da API. A conta administrativa do
banco só entra no serviço de bootstrap; não é repassada à API.
O MySQL não publica porta no host. API e frontend escutam somente em localhost.
O frontend serve apenas html/css/js/docs, sem expor `.env`, código Python ou Git.
Abra `http://127.0.0.1:5500/html/index.html`; API em `http://127.0.0.1:8000`.

Contas fictícias (senha definida em `DEMO_PASSWORD`):

- `candidato@demo.talentix.com`
- `empresa@demo.talentix.com`
- `admin@demo.talentix.com`

O seed não redefine senhas nem duplica usuários ao repetir. Ele recusa colisões
com contas não pertencentes ao demo e é bloqueado em produção. Sem seed, deixe
`SEED_DEMO=false`. Para atualizar uma instalação Compose existente, preserve o
volume e a senha root original, pare os serviços com `docker compose down`
(**sem `--volumes`**) e execute novamente `docker compose up --build --wait`.
Não use este Compose de desenvolvimento como configuração de produção.

### Contrato das migrations

`migrate.py` descobre `sql/migrations/NNN_nome.sql`, ordena pela versão, registra
checksum SHA-256 e só grava sucesso após concluir o arquivo. As versões 001/002
mantêm os adaptadores legados para compatibilidade com bancos existentes; 003/004
e futuras versões entram automaticamente. Alterações em arquivos já registrados
são rejeitadas: crie uma nova versão. O runner usa lock MySQL para serializar DDL.
Arquivos SQL devem ser idempotentes para retomada após falha; DDL no MySQL faz
commit implícito e não pode ser desfeito por rollback. Não use comandos do cliente
`DELIMITER`/`SOURCE` nem `USE` para trocar de banco nas migrations.

A 003 agora mantém as responsabilidades de DBA fora da fila automática e remove
a promoção implícita por e-mail. O bootstrap aplica privilégios reais à conta
runtime; instalações manuais usam `sql/operations/runtime_privileges.sql` com DBA.
Administradores são criados explicitamente via `create_admin.py` ou seed demo.
Faça backup do seu banco WAMP antes de aplicar migrations como DBA; o Compose
usa volume próprio e não altera esse banco local.

### Evidências de acessibilidade

`npm run check --prefix web-tests` executa verificações estáticas e Axe/Playwright
nas páginas públicas em desktop, mobile e viewport equivalente ao reflow em 200%.
`npm test --prefix web-tests` acrescenta painéis autenticados, abas e diálogos com
dados reais do ambiente isolado. Violações A/AA até WCAG 2.2 e boas práticas falham
o CI. Os artefatos incluem regras aprovadas, violações e itens `incomplete` para
revisão humana. Regras de contraste e áreas clicáveis não são desativadas.
Auditoria automática não certifica conformidade integral: leitura com NVDA/VoiceOver,
qualidade dos textos alternativos e zoom real do navegador requerem revisão manual.

## Ambientes, logs e rastreabilidade

`APP_ENV` aceita `development`, `test` ou `production`. Em produção a API
exige cookie seguro. Cada requisição recebe um `X-Request-ID`, também incluído
nos logs JSON da API e nas respostas de erro, permitindo correlacionar falhas sem
expor dados sensíveis.
