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
