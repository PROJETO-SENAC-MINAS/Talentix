"""
Talentix API — ponto de entrada da aplicação FastAPI.
Registra routers, middlewares, tratamento de erros e ciclo de vida do MySQL.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pymysql.err import DataError, IntegrityError, OperationalError

from app.core.config import settings
from app.core.logging_config import configurar_logging
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware, SecurityMiddleware
from app.db.database import close_pool, fetch_one, init_pool
from app.routers import (
    organizations, agenda, communication, automations, intelligence, public_pages, analytics, governance, push,
    ats,
    admin,
    auth,
    avaliacoes_denuncias,
    candidaturas,
    contato,
    curriculo,
    cursos,
    dashboard,
    dominios,
    favoritos,
    financeiro,
    habilidades,
    ia,
    mensagens,
    notificacoes,
    perfis,
    profissional,
    busca,
    uploads,
    vagas,
)

configurar_logging()

TAGS_METADATA = [
    {"name": "Status", "description": "Saúde e disponibilidade da API."},
    {"name": "Autenticação", "description": "Cadastro, sessão e segurança de contas."},
    {"name": "Perfis", "description": "Perfis profissionais e empresariais."},
    {"name": "Vagas", "description": "Publicação e consulta de oportunidades."},
    {"name": "Candidaturas", "description": "Processos seletivos, etapas e entrevistas."},
    {"name": "Administração", "description": "Operações protegidas de administração."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    try:
        await contato.garantir_schema_contato()
        await curriculo.garantir_schema_curriculo_importacoes()
        await profissional.garantir_schema()
        yield
    finally:
        await close_pool()


app = FastAPI(
    title="Talentix API",
    description="API REST da plataforma de recrutamento Talentix.",
    version="1.3.0",
    lifespan=lifespan,
    openapi_tags=TAGS_METADATA,
    docs_url="/docs" if settings.API_DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.API_DOCS_ENABLED else None,
)


def erro(request: Request, status_code: int, code: str, detail):
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "error": {
                "code": code,
                "message": detail if isinstance(detail, str) else "A requisição contém dados inválidos.",
                "request_id": request_id,
            },
        },
        headers={"X-Request-ID": request_id} if request_id else None,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc):
    errors = [
        {key: item[key] for key in ("type", "loc", "msg") if key in item}
        for item in exc.errors()
    ]
    return erro(request, 422, "validation_error", errors)


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc):
    code = exc.args[0] if exc.args else None
    if code == 1062:
        return erro(request, 409, "conflict", "Este registro ou vínculo já existe.")
    return erro(request, 422, "integrity_error", "Relação inexistente ou dados incompatíveis.")


@app.exception_handler(DataError)
async def data_error(request: Request, exc):
    return erro(request, 422, "data_error", "Dados fora dos limites permitidos.")


@app.exception_handler(OperationalError)
async def operational_error(request: Request, exc):
    if exc.args and exc.args[0] in {1205,1213}:
        return erro(request,409,'concurrent_update','Outra operação alterou os dados. Recarregue e tente novamente.')
    return erro(request,503,'database_unavailable','Serviço temporariamente indisponível. Tente novamente.')


app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
    expose_headers=["X-Request-ID"],
    max_age=600,
)
app.add_middleware(RequestContextMiddleware)

for categoria in ("fotos", "logos", "curriculos"):
    (Path(settings.UPLOAD_DIR) / categoria).mkdir(parents=True, exist_ok=True)
for categoria in ("logos",):
    app.mount(
        f"/uploads/{categoria}",
        StaticFiles(directory=Path(settings.UPLOAD_DIR) / categoria),
        name=f"uploads-{categoria}",
    )

for router in (
    organizations.router, agenda.router, communication.router, automations.router,
    intelligence.router, public_pages.router, analytics.router, governance.router, push.router,
    ats.router,
    auth.router,
    dominios.router,
    perfis.router,
    profissional.router,
    busca.router,
    vagas.router,
    curriculo.router,
    habilidades.router,
    candidaturas.router,
    favoritos.router,
    ia.router,
    cursos.router,
    notificacoes.router,
    mensagens.router,
    avaliacoes_denuncias.router,
    financeiro.router,
    uploads.router,
    dashboard.router,
    contato.router,
    admin.router,
):
    app.include_router(router)

app.mount('/publico-estatico', StaticFiles(directory=Path(__file__).resolve().parents[2] / 'css'), name='publico-estatico')


@app.get("/", tags=["Status"])
async def raiz():
    return {
        "servico": "Talentix API",
        "status": "online",
        "ambiente": settings.APP_ENV,
        "docs": "/docs" if settings.API_DOCS_ENABLED else None,
    }


@app.get("/saude", tags=["Status"])
async def verificar_saude():
    await fetch_one("SELECT 1 AS ok")
    return {"status": "ok", "ambiente": settings.APP_ENV}
