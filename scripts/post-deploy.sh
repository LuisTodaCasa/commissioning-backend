#!/bin/bash
# ============================================================
# post-deploy.sh — Pós-deploy do Sistema de Comissionamento
# Executado automaticamente pelo deploy.sh após cada deploy.
# ============================================================
set -e

echo "[post-deploy] Executando migrações do banco de dados..."
alembic upgrade head

echo "[post-deploy] Verificando dados iniciais (seed)..."
python seed.py

echo "[post-deploy] Pós-deploy concluído com sucesso."
