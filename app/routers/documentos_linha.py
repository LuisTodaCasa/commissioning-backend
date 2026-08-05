"""Rotas de documentos de linha (STH) com upload para Cloudflare R2 ou armazenamento local."""
import os
import uuid
import shutil
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
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

# ── Configuração de armazenamento ──────────────────────────────────────────────
# Se R2_ENDPOINT_URL estiver configurado, usa Cloudflare R2.
# Caso contrário, usa armazenamento local em UPLOAD_DIR.

_USE_R2 = bool(settings.R2_ENDPOINT_URL and settings.R2_ACCESS_KEY_ID)

if _USE_R2:
    import boto3
    from botocore.exceptions import ClientError
    s3_client = boto3.client(
        's3',
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name='auto',
    )
    BUCKET_NAME = settings.R2_BUCKET_NAME
    PUBLIC_URL = settings.R2_PUBLIC_URL.rstrip('/')
else:
    s3_client = None
    BUCKET_NAME = None
    PUBLIC_URL = ""

LOCAL_UPLOAD_DIR = os.path.join(settings.UPLOAD_DIR, "documentos_linha")
os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)


def _generate_unique_filename(original_filename: str) -> str:
    ext = original_filename.rsplit('.', 1)[-1] if '.' in original_filename else ''
    return f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex


def _upload_file(file: UploadFile, folder: str = "documentos") -> str:
    """Salva arquivo localmente ou no R2. Retorna a chave/path do arquivo."""
    filename = _generate_unique_filename(file.filename)
    if _USE_R2:
        key = f"{folder}/{filename}"
        file.file.seek(0)
        s3_client.upload_fileobj(file.file, BUCKET_NAME, key)
        return key
    else:
        dest_dir = os.path.join(LOCAL_UPLOAD_DIR, folder)
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, filename)
        file.file.seek(0)
        with open(dest_path, 'wb') as f:
            shutil.copyfileobj(file.file, f)
        return os.path.join(folder, filename)


def _delete_file(key: str) -> bool:
    """Remove arquivo local ou do R2."""
    try:
        if _USE_R2:
            s3_client.delete_object(Bucket=BUCKET_NAME, Key=key)
        else:
            full_path = os.path.join(LOCAL_UPLOAD_DIR, key)
            if os.path.exists(full_path):
                os.remove(full_path)
        return True
    except Exception:
        return False


def _get_download_url(key: str, doc_id: int) -> str:
    """Retorna URL de download do arquivo."""
    if _USE_R2 and PUBLIC_URL:
        return f"{PUBLIC_URL}/{key}"
    return f"/api/v1/documentos-linha/{doc_id}/download"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/sth/{sth_id}", response_model=List[DocumentoLinhaResponse])
def listar_documentos_sth(
    sth_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Listar documentos de um STH."""
    docs = db.query(DocumentoLinha).filter(DocumentoLinha.sth_id == sth_id).all()
    result = []
    for doc in docs:
        result.append(DocumentoLinhaResponse(
            id=doc.id,
            sth_id=doc.sth_id,
            linha_id=doc.linha_id,
            tipo_documento=doc.tipo_documento.value if hasattr(doc.tipo_documento, 'value') else str(doc.tipo_documento),
            numero_documento=doc.numero_documento,
            arquivo_key=doc.arquivo_key,
            arquivo_nome=doc.arquivo_nome,
            ativo=doc.ativo,
            enviado_por_id=doc.enviado_por_id,
            criado_em=doc.criado_em,
            download_url=_get_download_url(doc.arquivo_key, doc.id) if doc.arquivo_key else None,
        ))
    return result


@router.post("/sth/{sth_id}/upload", response_model=DocumentoLinhaResponse)
async def upload_documento_linha(
    sth_id: int,
    file: UploadFile = File(...),
    tipo_documento: str = Form(...),
    numero_documento: str = Form(...),
    linha_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(["Administrador", "Engenharia", "Comissionamento"])),
):
    """Upload de documento para um STH."""
    sth = db.query(STH).filter(STH.id == sth_id).first()
    if not sth:
        raise HTTPException(404, "STH não encontrado")

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(400, "Apenas arquivos PDF são aceitos")

    try:
        tipo_enum = TipoDocumento(tipo_documento)
    except ValueError:
        raise HTTPException(400, f"Tipo de documento inválido: {tipo_documento}")

    key = _upload_file(file, folder="documentos_linha")

    doc = DocumentoLinha(
        sth_id=sth_id,
        linha_id=linha_id,
        tipo_documento=tipo_enum,
        numero_documento=numero_documento,
        arquivo_key=key,
        arquivo_nome=file.filename,
        ativo=True,
        enviado_por_id=current_user.id,
        criado_em=datetime.utcnow(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return DocumentoLinhaResponse(
        id=doc.id,
        sth_id=doc.sth_id,
        linha_id=doc.linha_id,
        tipo_documento=doc.tipo_documento.value,
        numero_documento=doc.numero_documento,
        arquivo_key=doc.arquivo_key,
        arquivo_nome=doc.arquivo_nome,
        ativo=doc.ativo,
        enviado_por_id=doc.enviado_por_id,
        criado_em=doc.criado_em,
        download_url=_get_download_url(doc.arquivo_key, doc.id),
    )


@router.get("/{doc_id}/download")
def download_documento_linha(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Download de documento (armazenamento local)."""
    doc = db.query(DocumentoLinha).filter(DocumentoLinha.id == doc_id).first()
    if not doc or not doc.arquivo_key:
        raise HTTPException(404, "Documento não encontrado")

    if _USE_R2:
        url = _get_download_url(doc.arquivo_key, doc_id)
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=url)

    full_path = os.path.join(LOCAL_UPLOAD_DIR, doc.arquivo_key)
    if not os.path.exists(full_path):
        raise HTTPException(404, "Arquivo não encontrado no servidor")
    return FileResponse(full_path, filename=doc.arquivo_nome or "documento.pdf")


@router.delete("/{doc_id}")
def deletar_documento_linha(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(["Administrador", "Engenharia"])),
):
    """Remover documento."""
    doc = db.query(DocumentoLinha).filter(DocumentoLinha.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Documento não encontrado")

    if doc.arquivo_key:
        _delete_file(doc.arquivo_key)

    db.delete(doc)
    db.commit()
    return {"mensagem": "Documento removido com sucesso"}


@router.get("/status/sth/{sth_id}", response_model=DocumentoLinhaStatusResponse)
def status_documentos_sth(
    sth_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Status de documentos esperados vs enviados para um STH."""
    sth = db.query(STH).filter(STH.id == sth_id).first()
    if not sth:
        raise HTTPException(404, "STH não encontrado")

    esperados = db.query(DocumentoLinha).filter(
        DocumentoLinha.sth_id == sth_id,
        DocumentoLinha.ativo == True
    ).all()

    itens = []
    pendentes = 0
    for doc in esperados:
        tem_arquivo = bool(doc.arquivo_key)
        if not tem_arquivo:
            pendentes += 1
        itens.append(DocumentoLinhaStatusItem(
            id=doc.id,
            tipo_documento=doc.tipo_documento.value if hasattr(doc.tipo_documento, 'value') else str(doc.tipo_documento),
            numero_documento=doc.numero_documento,
            tem_arquivo=tem_arquivo,
            download_url=_get_download_url(doc.arquivo_key, doc.id) if tem_arquivo else None,
        ))

    return DocumentoLinhaStatusResponse(
        sth_id=sth_id,
        codigo_sth=sth.codigo,
        total_esperados=len(itens),
        total_enviados=len(itens) - pendentes,
        total_pendentes=pendentes,
        documentos=itens,
    )
