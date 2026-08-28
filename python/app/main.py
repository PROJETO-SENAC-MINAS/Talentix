"""
Talentix API — ponto de entrada da aplicação FastAPI.
Registra todos os routers, o middleware de CORS, e o ciclo de vida do pool MySQL.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.db.database import init_pool, close_pool

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
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title="Talentix API",
    description="API REST completa da plataforma de recrutamento Talentix.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,  # necessário para cookies de sessão
    allow_methods=["*"],
    allow_headers=["*"],
)

# Arquivos enviados (fotos, logos, currículos) servidos estaticamente
app.mount(f"/{settings.UPLOAD_DIR}", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

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


@app.get("/", tags=["Status"])
async def raiz():
    return {"servico": "Talentix API", "status": "online", "docs": "/docs"}


@app.get("/saude", tags=["Status"])
async def verificar_saude():
    return {"status": "ok"}