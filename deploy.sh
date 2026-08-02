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

# 3. Executar pós-deploy (migrações + seed)
echo "[3/4] Executando pós-deploy (migrações e seed)..."
bash scripts/post-deploy.sh

echo "==============================="
echo "  Deploy concluído com sucesso!"
echo "==============================="
