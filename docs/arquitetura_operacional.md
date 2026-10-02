# Arquitetura operacional — Talentix

## Ambientes

A API reconhece três ambientes: `development`, `test` e `production`, definidos
por `APP_ENV`. Segredos continuam fora do repositório. Em produção,
`SESSION_COOKIE_SECURE=false` é recusado na inicialização.

## Rastreabilidade

Toda requisição recebe um identificador em `X-Request-ID`. Um valor fornecido
pelo cliente só é reutilizado quando possui formato seguro; caso contrário a API
gera um UUID. O mesmo identificador aparece nos logs JSON e nos erros HTTP.

Os logs registram método, caminho, status e duração. Senhas, cookies, corpos de
requisição e tokens não são escritos automaticamente.

## Banco e migrations

`sql/talentix_db.sql` instala um banco novo. Instalações existentes usam
`python/migrate.py` e `Schema_Migrations`. Cada alteração incremental nova deve
receber um identificador versionado e ser idempotente. Reimportar o SQL completo
sobre um banco de produção não é uma estratégia de atualização.

## Desenvolvimento reproduzível

`docker-compose.yml` disponibiliza MySQL, FastAPI e o frontend estático. Antes de
subir os containers, gere `python/.env` com `python configure_dev.py`.
