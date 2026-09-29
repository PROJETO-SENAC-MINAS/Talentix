# Talentix

Plataforma full stack de recrutamento com HTML, CSS, JavaScript, FastAPI e MySQL 8.
A API inclui cadastro, autenticação, perfis, currículos, vagas, candidaturas,
entrevistas, mensagens e endpoints para integrações externas de IA e pagamentos.

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
pip install -r requirements.txt
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

Os endpoints de IA armazenam solicitações/resultados; o worker que realiza a
análise e o gateway de pagamentos são serviços externos, não incluídos aqui.
Ao integrar um gateway real, valide também sua assinatura específica, os dados
da transação e eventos repetidos antes de chamar a rota interna de confirmação.

## Testes

```bash
cd python
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Os testes fazem requisições HTTP à aplicação, usam cookies assinados reais e
executam as consultas afetadas em um banco SQLite isolado. Não enviam e-mails e
não dependem de um MySQL disponível. Cobrem acessos de empresas e candidatos
distintos, arquivos privados, tokens de serviço e tentativas de alteração de
dados de terceiros. Não substituem testes completos de integração com MySQL,
SMTP, worker de IA e gateway de pagamentos.

O workflow `.github/workflows/security-checks.yml` executa esses testes e impede
que configurações secretas, caches Python ou uploads sejam versionados novamente.

## Funcionalidades ainda em desenvolvimento

O painel de candidato está incluído. Os painéis de empresa e administrador ainda
não estão no repositório. O formulário de contato ainda é uma demonstração de
interface. Esses recursos, o worker de IA e o checkout real precisam ser
concluídos antes de uma disponibilização geral para usuários.
