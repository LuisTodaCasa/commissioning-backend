#!/bin/bash
set -e

echo "==============================="
echo "  Deploy - Sistema Comissionamento"
echo "==============================="

# 1. Instalar dependências
echo "[1/4] Instalando dependências..."
pip install -r requirements.txt --quiet

# 2. Criar diretórios de upload
echo "[2/4] Criando diretórios de upload..."
mkdir -p ${UPLOAD_DIR:-./uploads}/documentos
mkdir -p ${UPLOAD_DIR:-./uploads}/documentos_linha
mkdir -p ${UPLOAD_DIR:-./uploads}/templates

# 3. Executar migrações
echo "[3/4] Executando migrações do banco..."
alembic upgrade head

# 4. Popular dados iniciais (apenas se admin não existir)
echo "[4/4] Verificando dados iniciais..."
python seed.py

echo "==============================="
echo "  Deploy concluído com sucesso!"
echo "==============================="
