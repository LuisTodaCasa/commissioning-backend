"""Rotas de documentos de linha (STH) com upload para Cloudflare R2."""
import os
import uuid
from typing import List, Optional
from datetime import datetime

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.core.config import settings
from app.models.models import (
    DocumentoLinha, STH, LinhaTubulacaoCatalogo, Usuario, TipoDocumento
)
from app.schemas.schemas import (
    DocumentoLinhaResponse, DocumentoLinhaStatusResponse, DocumentoLinhaStatusItem
)

router = APIRouter(prefix="/documentos-linha", tags=["Documentos de Linha"])

# Configuração do cliente S3 para Cloudflare R2
s3_client = boto3.client(
    's3',
    endpoint_url=settings.R2_ENDPOINT_URL,
    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
    region_name='auto'
)

BUCKET_NAME = settings.R2_BUCKET_NAME
PUBLIC_URL = settings.R2_PUBLIC_URL.rstrip('/')


def _generate_unique_filename(original_filename: str) -> str:
    """Gera um nome único para o arquivo no bucket."""
    ext = original_filename.split('.')[-1] if '.' in original_filename else ''
    unique_id = uuid.uuid4().hex
    return f"{unique_id}.{ext}" if ext else unique_id


def _upload_to_r2(file: UploadFile, folder: str = "documentos") -> str:
    """Faz upload do arquivo para o R2 e retorna a chave (key) do objeto."""
    filename = _generate_unique_filename(file.filename)
    key = f"{folder}/{filename}"
    try:
        s3_client.upload_fileobj(
            file.file,
            BUCKET_NAME,
            key,
            ExtraArgs={'ContentType': file.content_type or 'application/octet-stream'}
        )
        return key
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Erro ao enviar arquivo para storage: {str(e)}")


def _delete_from_r2(key: str) -> bool:
    """Remove um arquivo do R2."""
    try:
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=key)
        return True
    except ClientError:
        return False


def _generate_download_url(key: str, filename: str) -> str:
    """Gera URL pública para download (via R2 public bucket)."""
    return f"{PUBLIC_URL}/{key}"


# --- Endpoints ---

@router.post("/upload", response_model=DocumentoLinhaResponse)
async def upload_documento_linha(
    file: UploadFile = File(...),
    sth_id: int = Form(...),
    linha_id: Optional[int] = Form(None),
    tipo_documento: str = Form(...),
    numero_documento: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["Administrador", "Comissionamento", "Engenharia"]))
):
    """Upload de um documento de linha (isométrico, fluxograma, etc.)."""
    # Validações
    sth = db.query(STH).filter(STH.id == sth_id).first()
    if not sth:
        raise HTTPException(status_code=404, detail="STH não encontrado")

    if linha_id:
        linha = db.query(LinhaTubulacaoCatalogo).filter(
            and_(LinhaTubulacaoCatalogo.id == linha_id)
        ).first()
        if not linha:
            raise HTTPException(status_code=404, detail="Linha não encontrada")

    # Upload para R2
    key = _upload_to_r2(file, folder=f"sth_{sth_id}")

    # Criar registro no banco
    documento = DocumentoLinha(
        sth_id=sth_id,
        linha_id=linha_id,
        tipo_documento=tipo_documento,
        nome_arquivo=file.filename,
        caminho_arquivo=key,
        tamanho_bytes=file.size,
        numero_documento=numero_documento,
        uploaded_by_id=current_user.id,
        ativo=True,
        data_upload=datetime.now()
    )
    db.add(documento)
    db.commit()
    db.refresh(documento)

    download_url = _generate_download_url(key, file.filename)

    return DocumentoLinhaResponse(
        id=documento.id,
        sth_id=documento.sth_id,
        linha_id=documento.linha_id,
        tipo_documento=documento.tipo_documento,
        nome_arquivo=documento.nome_arquivo,
        tamanho_bytes=documento.tamanho_bytes,
        numero_documento=documento.numero_documento,
        uploaded_by_id=documento.uploaded_by_id,
        ativo=documento.ativo,
        download_url=download_url,
        data_upload=documento.data_upload,
        criado_em=documento.criado_em
    )


@router.post("/upload-lote-inteligente")
async def upload_lote_inteligente(
    files: List[UploadFile] = File(...),
    sth_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["Administrador", "Comissionamento", "Engenharia"]))
):
    """Upload em lote com identificação automática de tipo (isométrico/fluxograma)."""
    resultados = []
    for file in files:
        # Lógica de identificação simplificada: baseada no nome do arquivo
        filename_lower = file.filename.lower()
        if 'fluxograma' in filename_lower or 'fluxo' in filename_lower:
            tipo = 'FLUXOGRAMA'
            linha_id = None
        else:
            tipo = 'ISOMETRICO'
            # Tenta encontrar linha correspondente pelo número no nome
            linha_id = None
            # (implementação de matching pode ser refinada depois)

        # Upload para R2
        key = _upload_to_r2(file, folder=f"sth_{sth_id}")

        documento = DocumentoLinha(
            sth_id=sth_id,
            linha_id=linha_id,
            tipo_documento=tipo,
            nome_arquivo=file.filename,
            caminho_arquivo=key,
            tamanho_bytes=file.size,
            uploaded_by_id=current_user.id,
            ativo=True,
            data_upload=datetime.now()
        )
        db.add(documento)
        resultados.append({"filename": file.filename, "tipo": tipo})

    db.commit()
    return {"mensagem": f"{len(resultados)} documentos processados", "resultados": resultados}


@router.get("/{documento_id}/download")
async def download_documento_linha(
    documento_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Gera URL de download para um documento."""
    doc = db.query(DocumentoLinha).filter(DocumentoLinha.id == documento_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    download_url = _generate_download_url(doc.caminho_arquivo, doc.nome_arquivo)
    return {"download_url": download_url}


@router.delete("/{documento_id}")
async def delete_documento_linha(
    documento_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["Administrador"]))
):
    """Remove um documento (soft delete ou permanente)."""
    doc = db.query(DocumentoLinha).filter(DocumentoLinha.id == documento_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")

    # Remove do R2
    _delete_from_r2(doc.caminho_arquivo)

    db.delete(doc)
    db.commit()
    return {"mensagem": "Documento removido com sucesso"}


@router.get("/sth/{sth_id}", response_model=List[DocumentoLinhaResponse])
async def listar_documentos_sth(
    sth_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Lista todos os documentos associados a um STH."""
    docs = db.query(DocumentoLinha).filter(DocumentoLinha.sth_id == sth_id).all()
    result = []
    for doc in docs:
        download_url = _generate_download_url(doc.caminho_arquivo, doc.nome_arquivo)
        result.append(DocumentoLinhaResponse(
            id=doc.id,
            sth_id=doc.sth_id,
            linha_id=doc.linha_id,
            tipo_documento=doc.tipo_documento,
            nome_arquivo=doc.nome_arquivo,
            tamanho_bytes=doc.tamanho_bytes,
            numero_documento=doc.numero_documento,
            uploaded_by_id=doc.uploaded_by_id,
            ativo=doc.ativo,
            download_url=download_url,
            data_upload=doc.data_upload,
            criado_em=doc.criado_em
        ))
    return result


@router.get("/sth/{sth_id}/status", response_model=DocumentoLinhaStatusResponse)
async def status_documentos_sth(
    sth_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Retorna o status de documentos esperados vs. enviados para cada linha do STH."""
    sth = db.query(STH).filter(STH.id == sth_id).first()
    if not sth:
        raise HTTPException(status_code=404, detail="STH não encontrado")

    # Busca linhas associadas ao STH
    linhas = []
    for sl in sth.sth_linhas:
        linhas.append(sl.linha_cat)

    items = []
    for linha in linhas:
        # Documentos esperados: sempre isométrico para cada linha
        esperados = ["ISOMETRICO"]
        # Documentos enviados para esta linha
        enviados = db.query(DocumentoLinha).filter(
            and_(DocumentoLinha.sth_id == sth_id, DocumentoLinha.linha_id == linha.id)
        ).all()
        enviados_tipos = [d.tipo_documento for d in enviados if d.ativo]
        pendentes = [e for e in esperados if e not in enviados_tipos]
        percentual = (len(enviados_tipos) / len(esperados) * 100) if esperados else 100

        items.append(DocumentoLinhaStatusItem(
            linha_id=linha.id,
            numero_linha=linha.numero_linha,
            documentos_esperados=esperados,
            documentos_enviados=enviados_tipos,
            documentos_pendentes=pendentes,
            percentual=percentual
        ))

    # Documentos de fluxograma (gerais do STH)
    fluxogramas_enviados = db.query(DocumentoLinha).filter(
        and_(DocumentoLinha.sth_id == sth_id, DocumentoLinha.linha_id.is_(None))
    ).count()

    total_esperados = len(linhas) + (1 if fluxogramas_enviados == 0 else 0)  # Simplificação
    total_enviados = sum(len(item.documentos_enviados) for item in items) + fluxogramas_enviados
    percentual_geral = (total_enviados / total_esperados * 100) if total_esperados else 0

    return DocumentoLinhaStatusResponse(
        sth_id=sth_id,
        codigo_sth=sth.codigo,
        total_esperados=total_esperados,
        total_enviados=total_enviados,
        percentual_geral=percentual_geral,
        linhas=items
    )