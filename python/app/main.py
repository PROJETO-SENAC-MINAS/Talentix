"""
Talentix API — ponto de entrada da aplicação FastAPI.
Registra todos os routers, o middleware de CORS, e o ciclo de vida do pool MySQL.
"""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pymysql.err import IntegrityError, DataError

from app.core.config import settings
from app.db.database import init_pool, close_pool, fetch_one

from app.routers import (
    auth,
    dominios,
    perfis,
    vagas,
    curriculo,
    habilidades,
    candidaturas,
    favoritos,
    ia,
    cursos,
    notificacoes,
    mensagens,
    avaliacoes_denuncias,
    financeiro,
    uploads,
    dashboard,
    contato,
    admin,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    await contato.garantir_schema_contato()
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(
    title="Talentix API",
    description="API REST completa da plataforma de recrutamento Talentix.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Não devolver senhas ou outros valores privados no detalhe da validação.
    errors = [{key: error[key] for key in ("type", "loc", "msg") if key in error}
              for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    code = exc.args[0] if exc.args else None
    if code == 1062:
        return JSONResponse(status_code=409, content={"detail": "Este registro ou vínculo já existe."})
    return JSONResponse(status_code=422, content={"detail": "Relação inexistente ou dados incompatíveis."})


@app.exception_handler(DataError)
async def data_error(request, exc):
    return JSONResponse(status_code=422, content={"detail": "Dados fora dos limites permitidos."})

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,  # necessário para cookies de sessão
    allow_methods=["*"],
    allow_headers=["*"],
)

# Apenas fotos e logos são públicos. Currículos passam pelo router autenticado.
for categoria in ("fotos", "logos", "curriculos"):
    (Path(settings.UPLOAD_DIR) / categoria).mkdir(parents=True, exist_ok=True)
for categoria in ("fotos", "logos"):
    app.mount(
        f"/uploads/{categoria}",
        StaticFiles(directory=Path(settings.UPLOAD_DIR) / categoria),
        name=f"uploads-{categoria}",
    )

# Registro de routers
app.include_router(auth.router)
app.include_router(dominios.router)
app.include_router(perfis.router)
app.include_router(vagas.router)
app.include_router(curriculo.router)
app.include_router(habilidades.router)
app.include_router(candidaturas.router)
app.include_router(favoritos.router)
app.include_router(ia.router)
app.include_router(cursos.router)
app.include_router(notificacoes.router)
app.include_router(mensagens.router)
app.include_router(avaliacoes_denuncias.router)
app.include_router(financeiro.router)
app.include_router(uploads.router)
app.include_router(dashboard.router)
app.include_router(contato.router)
app.include_router(admin.router)


@app.get("/", tags=["Status"])
async def raiz():
    return {"servico": "Talentix API", "status": "online", "docs": "/docs"}


@app.get("/saude", tags=["Status"])
async def verificar_saude():
    await fetch_one("SELECT 1 AS ok")
    return {"status": "ok"}
