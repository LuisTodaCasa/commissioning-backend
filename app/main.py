"""Ponto de entrada principal da aplicação FastAPI."""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import engine, Base
from app.core.logging_config import setup_logging

# Configurar logging
setup_logging()
logger = logging.getLogger(__name__)

# Criar aplicação
app = FastAPI(
    title="Sistema de Comissionamento - API",
    description=(
        "API Backend para o Sistema de Pastas de Teste de Comissionamento Industrial. "
        "Gerenciamento de linhas de tubulação, pastas de teste, documentos, "
        "relatórios de campo e sincronização offline."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Criar tabelas automaticamente (para desenvolvimento)
Base.metadata.create_all(bind=engine)

# Criar diretório de uploads
os.makedirs(os.path.join(settings.UPLOAD_DIR, "documentos"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "templates"), exist_ok=True)

# Registrar routers
from app.routers import auth, usuarios, disciplinas, linhas, pastas, documentos, modelos, templates, testes, relatorios, execucao, sync, dashboard, tubulacao, documentos_linha

API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(usuarios.router, prefix=API_PREFIX)
app.include_router(disciplinas.router, prefix=API_PREFIX)
app.include_router(linhas.router, prefix=API_PREFIX)
app.include_router(pastas.router, prefix=API_PREFIX)
app.include_router(documentos.router, prefix=API_PREFIX)
app.include_router(modelos.router, prefix=API_PREFIX)
app.include_router(templates.router, prefix=API_PREFIX)
app.include_router(testes.router, prefix=API_PREFIX)
app.include_router(relatorios.router, prefix=API_PREFIX)
app.include_router(execucao.router, prefix=API_PREFIX)
app.include_router(sync.router, prefix=API_PREFIX)
app.include_router(dashboard.router, prefix=API_PREFIX)
app.include_router(tubulacao.router, prefix=API_PREFIX)
app.include_router(documentos_linha.router, prefix=API_PREFIX)


@app.get("/")
def root():
    return {
        "nome": "Sistema de Comissionamento - API",
        "versao": "1.0.0",
        "documentacao": "/docs",
        "status": "online",
    }


@app.get("/health")
def health_check():
    return {"status": "ok", "database": "connected"}


@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("Sistema de Comissionamento - API Iniciada")
    logger.info(f"Ambiente: {settings.APP_ENV}")
    logger.info(f"Docs: http://localhost:8000/docs")
    logger.info("=" * 60)
