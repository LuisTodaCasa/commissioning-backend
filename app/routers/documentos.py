"""Rotas de upload e download de documentos PDF por pasta."""
import os
import logging
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user, require_roles
from app.models.models import DocumentoPasta, PastaTeste, TipoDocumento
from app.schemas.schemas import DocumentoResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documentos", tags=["Documentos"])

ALLOWED_TYPES = [t.value for t in TipoDocumento]
MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


def _doc_to_response(doc: DocumentoPasta) -> DocumentoResponse:
    """Converter modelo de documento para resposta com URL de download."""
    return DocumentoResponse(
        id=doc.id,
        pasta_id=doc.pasta_id,
        tipo=doc.tipo.value if hasattr(doc.tipo, 'value') else str(doc.tipo),
        nome_arquivo=doc.nome_arquivo,
        tamanho_bytes=doc.tamanho_bytes,
        download_url=f"/api/v1/documentos/{doc.id}/download",
        criado_em=doc.criado_em,
    )


@router.post(
    "/pasta/{pasta_id}",
    response_model=DocumentoResponse,
    status_code=201,
    summary="Upload de documento PDF",
    description=(
        "Faz upload de um documento PDF para a pasta de teste. "
        "Tipos permitidos: fluxograma, fluxoteste, isometrico, lista_suportes, mapa_juntas. "
        "Permite múltiplos documentos do mesmo tipo (versionamento)."
    )
)
async def upload_documento(
    pasta_id: int,
    tipo: str = Form(..., description="Tipo do documento: fluxograma, fluxoteste, isometrico, lista_suportes, mapa_juntas"),
    file: UploadFile = File(..., description="Arquivo PDF a ser enviado"),
    current_user=Depends(require_roles(["Administrador", "Comissionamento", "Engenharia"])),
    db: Session = Depends(get_db)
):
    """Upload de documento PDF para uma pasta de teste."""
    # Validar pasta
    pasta = db.query(PastaTeste).filter(PastaTeste.id == pasta_id).first()
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    # Validar tipo
    if tipo not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo inválido '{tipo}'. Tipos permitidos: {', '.join(ALLOWED_TYPES)}"
        )

    # Validar extensão PDF
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são permitidos.")

    # Ler conteúdo
    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Erro ao ler arquivo: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar o arquivo enviado.")

    # Validar tamanho
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo excede o tamanho máximo permitido de {settings.MAX_UPLOAD_SIZE_MB}MB."
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio não é permitido.")

    # Criar diretório
    upload_dir = os.path.join(settings.UPLOAD_DIR, "documentos", str(pasta_id))
    os.makedirs(upload_dir, exist_ok=True)

    # Gerar nome único
    ext = os.path.splitext(file.filename)[1]
    filename = f"{tipo}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(upload_dir, filename)

    # Salvar arquivo
    try:
        with open(filepath, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Erro ao salvar arquivo: {e}")
        raise HTTPException(status_code=500, detail="Erro ao salvar o arquivo no servidor.")

    # Salvar metadados no banco
    doc = DocumentoPasta(
        pasta_id=pasta_id,
        tipo=tipo,
        nome_arquivo=file.filename,
        caminho_arquivo=filepath,
        tamanho_bytes=len(content),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    logger.info(f"Documento {tipo} uploaded para pasta {pasta_id} por {current_user.email}")
    return _doc_to_response(doc)


@router.get(
    "/pasta/{pasta_id}",
    response_model=List[DocumentoResponse],
    summary="Listar documentos da pasta",
    description="Retorna todos os documentos PDF associados à pasta de teste."
)
def list_documentos_pasta(
    pasta_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Listar documentos de uma pasta."""
    pasta = db.query(PastaTeste).filter(PastaTeste.id == pasta_id).first()
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    docs = db.query(DocumentoPasta).filter(DocumentoPasta.pasta_id == pasta_id).all()
    return [_doc_to_response(doc) for doc in docs]


@router.get(
    "/{doc_id}/download",
    summary="Download de documento PDF",
    description="Faz o download de um documento PDF pelo seu ID."
)
def download_documento(
    doc_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download de um documento PDF."""
    doc = db.query(DocumentoPasta).filter(DocumentoPasta.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    if not os.path.exists(doc.caminho_arquivo):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado no servidor.")

    return FileResponse(
        path=doc.caminho_arquivo,
        media_type="application/pdf",
        filename=doc.nome_arquivo,
    )


@router.delete(
    "/{doc_id}",
    summary="Excluir documento",
    description="Remove o documento do banco e do sistema de arquivos."
)
def delete_documento(
    doc_id: int,
    current_user=Depends(require_roles(["Administrador", "Comissionamento"])),
    db: Session = Depends(get_db)
):
    """Excluir um documento PDF."""
    doc = db.query(DocumentoPasta).filter(DocumentoPasta.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")

    # Remover arquivo físico
    if os.path.exists(doc.caminho_arquivo):
        try:
            os.remove(doc.caminho_arquivo)
        except OSError as e:
            logger.warning(f"Não foi possível remover arquivo {doc.caminho_arquivo}: {e}")

    db.delete(doc)
    db.commit()
    logger.info(f"Documento {doc_id} removido por {current_user.email}")
    return {"message": "Documento removido com sucesso."}
