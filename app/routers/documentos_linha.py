"""Rotas de upload/download de documentos PDF por linha de tubulação (STH)."""
import os
import re
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user, require_roles
from app.models.models import (
    DocumentoLinha, STH, LinhaTubulacaoCatalogo, STHLinha,
    TipoDocumento, PastaTeste,
)
from app.schemas.schemas import (
    DocumentoLinhaResponse, DocumentoLinhaStatusResponse,
    DocumentoLinhaStatusItem,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documentos-linha", tags=["Documentos de Linha"])

ALLOWED_TYPES = [t.value for t in TipoDocumento]
MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


def _doc_to_response(doc: DocumentoLinha) -> DocumentoLinhaResponse:
    tipo_val = doc.tipo_documento.value if hasattr(doc.tipo_documento, 'value') else str(doc.tipo_documento)
    return DocumentoLinhaResponse(
        id=doc.id,
        sth_id=doc.sth_id,
        linha_id=doc.linha_id,
        tipo_documento=tipo_val,
        nome_arquivo=doc.nome_arquivo,
        tamanho_bytes=doc.tamanho_bytes,
        numero_documento=doc.numero_documento,
        uploaded_by_id=doc.uploaded_by_id,
        ativo=doc.ativo,
        download_url=f"/api/v1/documentos-linha/{doc.id}/download" if doc.caminho_arquivo else None,
        data_upload=doc.data_upload,
        criado_em=doc.criado_em,
    )


# ── Upload de documento para uma linha de STH ──────────────────────────

@router.post(
    "/upload",
    response_model=DocumentoLinhaResponse,
    status_code=201,
    summary="Upload de documento PDF para linha de STH",
)
async def upload_documento_linha(
    sth_id: int = Form(..., description="ID do STH"),
    linha_id: int = Form(..., description="ID da linha do catálogo"),
    tipo: str = Form(..., description="Tipo: isometrico, fluxograma, lista_suportes, mapa_juntas, fluxoteste"),
    file: UploadFile = File(..., description="Arquivo PDF"),
    numero_documento: Optional[str] = Form(None, description="Número/referência do documento"),
    current_user=Depends(require_roles(["Administrador", "Engenharia", "Comissionamento"])),
    db: Session = Depends(get_db),
):
    """Upload de PDF para uma linha específica de um STH."""
    # Validar STH
    sth = db.query(STH).filter(STH.id == sth_id).first()
    if not sth:
        raise HTTPException(404, "STH não encontrado.")

    # Validar linha
    linha = db.query(LinhaTubulacaoCatalogo).filter(LinhaTubulacaoCatalogo.id == linha_id).first()
    if not linha:
        raise HTTPException(404, "Linha não encontrada.")

    # Validar vínculo STH-Linha
    link = db.query(STHLinha).filter(
        STHLinha.sth_id == sth_id, STHLinha.linha_id == linha_id
    ).first()
    if not link:
        raise HTTPException(400, "Linha não pertence a este STH.")

    # Validar tipo
    if tipo not in ALLOWED_TYPES:
        raise HTTPException(400, f"Tipo inválido '{tipo}'. Permitidos: {', '.join(ALLOWED_TYPES)}")

    # Validar PDF
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(400, "Apenas arquivos PDF são permitidos.")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Arquivo vazio.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"Arquivo excede {settings.MAX_UPLOAD_SIZE_MB}MB.")

    # Desativar documento anterior do mesmo tipo/linha (versionamento)
    existing = db.query(DocumentoLinha).filter(
        DocumentoLinha.sth_id == sth_id,
        DocumentoLinha.linha_id == linha_id,
        DocumentoLinha.tipo_documento == tipo,
        DocumentoLinha.ativo == True,
    ).first()
    if existing:
        existing.ativo = False
        db.flush()

    # Salvar arquivo
    upload_dir = os.path.join(settings.UPLOAD_DIR, "documentos_linha", str(sth_id), str(linha_id))
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    filename = f"{tipo}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(upload_dir, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    doc = DocumentoLinha(
        sth_id=sth_id,
        linha_id=linha_id,
        tipo_documento=tipo,
        nome_arquivo=file.filename,
        caminho_arquivo=filepath,
        tamanho_bytes=len(content),
        numero_documento=numero_documento,
        uploaded_by_id=current_user.id,
        ativo=True,
        data_upload=datetime.utcnow(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    logger.info(f"Documento {tipo} uploaded para STH {sth_id} / Linha {linha_id} por {current_user.email}")
    return _doc_to_response(doc)


# ── Upload em lote ─────────────────────────────────────────────────────

@router.post(
    "/upload-lote",
    response_model=List[DocumentoLinhaResponse],
    status_code=201,
    summary="Upload em lote de documentos PDF",
)
async def upload_lote(
    sth_id: int = Form(...),
    linha_id: int = Form(...),
    tipos: str = Form(..., description="Tipos separados por vírgula, na ordem dos arquivos"),
    files: List[UploadFile] = File(...),
    current_user=Depends(require_roles(["Administrador", "Engenharia", "Comissionamento"])),
    db: Session = Depends(get_db),
):
    """Upload de múltiplos PDFs para uma linha de STH."""
    tipo_list = [t.strip() for t in tipos.split(",")]
    if len(tipo_list) != len(files):
        raise HTTPException(400, "Número de tipos deve ser igual ao número de arquivos.")

    # Validar STH + Linha
    sth = db.query(STH).filter(STH.id == sth_id).first()
    if not sth:
        raise HTTPException(404, "STH não encontrado.")
    link = db.query(STHLinha).filter(STHLinha.sth_id == sth_id, STHLinha.linha_id == linha_id).first()
    if not link:
        raise HTTPException(400, "Linha não pertence a este STH.")

    results = []
    for f, tipo in zip(files, tipo_list):
        if tipo not in ALLOWED_TYPES:
            raise HTTPException(400, f"Tipo inválido '{tipo}'.")
        if not f.filename or not f.filename.lower().endswith('.pdf'):
            raise HTTPException(400, f"Arquivo '{f.filename}' não é PDF.")

        content = await f.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(400, f"Arquivo '{f.filename}' excede {settings.MAX_UPLOAD_SIZE_MB}MB.")

        # Desativar anterior
        existing = db.query(DocumentoLinha).filter(
            DocumentoLinha.sth_id == sth_id,
            DocumentoLinha.linha_id == linha_id,
            DocumentoLinha.tipo_documento == tipo,
            DocumentoLinha.ativo == True,
        ).first()
        if existing:
            existing.ativo = False
            db.flush()

        upload_dir = os.path.join(settings.UPLOAD_DIR, "documentos_linha", str(sth_id), str(linha_id))
        os.makedirs(upload_dir, exist_ok=True)
        ext = os.path.splitext(f.filename)[1]
        filename = f"{tipo}_{uuid.uuid4().hex[:8]}{ext}"
        filepath = os.path.join(upload_dir, filename)
        with open(filepath, "wb") as fh:
            fh.write(content)

        doc = DocumentoLinha(
            sth_id=sth_id, linha_id=linha_id, tipo_documento=tipo,
            nome_arquivo=f.filename, caminho_arquivo=filepath,
            tamanho_bytes=len(content), uploaded_by_id=current_user.id,
            ativo=True, data_upload=datetime.utcnow(),
        )
        db.add(doc)
        db.flush()
        results.append(doc)

    db.commit()
    for doc in results:
        db.refresh(doc)
    return [_doc_to_response(d) for d in results]


# ── Helpers de matching ──────────────────────────────────────────────────

def _extrair_numero_documento(nome_arquivo: str) -> str:
    """Extrai número do documento do nome do arquivo PDF."""
    base = nome_arquivo.rsplit('.', 1)[0] if '.' in nome_arquivo else nome_arquivo
    # Remover sufixos de versão comuns: _v2, -v2, (1), _rev1, -REV02, etc
    base = re.sub(r'[\s_-]+(v|rev|r)\d+$', '', base, flags=re.IGNORECASE)
    base = re.sub(r'\s*\(\d+\)$', '', base)
    base = re.sub(r'\s*_\d+$', '', base)  # _1, _2 trailing
    return base.strip()


def _normalizar_numero(numero: str) -> str:
    """Normaliza número removendo prefixos IS-xxxx.xx- e espaços."""
    n = numero.strip().upper()
    # Remove prefixo tipo "IS-5290.00-" se existir
    n = re.sub(r'^IS-\d+\.\d+-', '', n)
    return n


def _match_numero(numero_arquivo: str, numero_esperado: str) -> bool:
    """Verifica se o número do arquivo corresponde ao número esperado.
    Suporta match exato e parcial (contém).
    """
    na = numero_arquivo.strip().upper()
    ne = numero_esperado.strip().upper()
    if not na or not ne:
        return False
    # Match exato
    if na == ne:
        return True
    # Um contém o outro
    if ne in na or na in ne:
        return True
    # Normalizar e comparar
    na_norm = _normalizar_numero(na)
    ne_norm = _normalizar_numero(ne)
    if na_norm == ne_norm:
        return True
    if ne_norm in na_norm or na_norm in ne_norm:
        return True
    return False


# ── Upload em lote inteligente ─────────────────────────────────────────

@router.post(
    "/upload-lote-inteligente",
    summary="Upload em lote com matching automático por número do documento",
)
async def upload_lote_inteligente(
    sth_id: int = Form(..., description="ID do STH"),
    arquivos: List[UploadFile] = File(..., description="Arquivos PDF"),
    current_user=Depends(require_roles(["Administrador", "Engenharia", "Comissionamento"])),
    db: Session = Depends(get_db),
):
    """
    Upload de múltiplos PDFs com matching automático.
    O sistema extrai o número do documento do nome do arquivo e busca
    correspondência nos documentos esperados do STH.
    """
    sth = db.query(STH).filter(STH.id == sth_id).first()
    if not sth:
        raise HTTPException(404, "STH não encontrado.")

    # Buscar todos os documentos esperados (sem arquivo) e já enviados
    todos_docs = db.query(DocumentoLinha).filter(
        DocumentoLinha.sth_id == sth_id,
        DocumentoLinha.ativo == True,
    ).all()

    # Indexar documentos esperados (sem arquivo enviado) por numero_documento
    pendentes_iso: dict[str, DocumentoLinha] = {}  # numero -> doc
    pendentes_fluxo: dict[str, list[DocumentoLinha]] = {}  # numero -> [docs]

    for doc in todos_docs:
        if doc.caminho_arquivo:
            continue  # Já tem arquivo, pular
        if not doc.numero_documento:
            continue
        tipo_val = doc.tipo_documento.value if hasattr(doc.tipo_documento, 'value') else str(doc.tipo_documento)

        if tipo_val.upper() == 'ISOMETRICO':
            pendentes_iso[doc.numero_documento.strip().upper()] = doc
        elif tipo_val.upper() == 'FLUXOGRAMA':
            key = doc.numero_documento.strip().upper()
            if key not in pendentes_fluxo:
                pendentes_fluxo[key] = []
            pendentes_fluxo[key].append(doc)

    # Buscar linhas do STH para mapeamento
    linhas_map: dict[int, str] = {}
    for sl in sth.sth_linhas:
        if sl.linha_cat:
            linhas_map[sl.linha_cat.id] = sl.linha_cat.numero_linha

    resultados = []
    erros = []
    sucessos = 0

    for arq in arquivos:
        try:
            # Validar PDF
            if not arq.filename or not arq.filename.lower().endswith('.pdf'):
                raise ValueError(f"Arquivo '{arq.filename}' não é PDF")

            content = await arq.read()
            if len(content) == 0:
                raise ValueError("Arquivo vazio")
            if len(content) > MAX_UPLOAD_BYTES:
                raise ValueError(f"Excede {settings.MAX_UPLOAD_SIZE_MB}MB")

            # Extrair número do documento do nome do arquivo
            numero_extraido = _extrair_numero_documento(arq.filename)
            numero_upper = numero_extraido.strip().upper()

            doc_encontrado: Optional[DocumentoLinha] = None
            tipo_match = ""
            destino_info = ""

            # 1. Tentar como isométrico (match exato primeiro, depois parcial)
            # Match exato
            if numero_upper in pendentes_iso:
                doc_encontrado = pendentes_iso[numero_upper]
                tipo_match = "isometrico"
                destino_info = f"Isométrico → Linha {linhas_map.get(doc_encontrado.linha_id, '?')}"
                del pendentes_iso[numero_upper]
            else:
                # Match parcial/aproximado nos isométricos
                matched_key = None
                for num_esp, doc_esp in pendentes_iso.items():
                    if _match_numero(numero_upper, num_esp):
                        doc_encontrado = doc_esp
                        tipo_match = "isometrico"
                        destino_info = f"Isométrico → Linha {linhas_map.get(doc_esp.linha_id, '?')} [match aproximado]"
                        matched_key = num_esp
                        break
                if matched_key:
                    del pendentes_iso[matched_key]

            # 2. Se não encontrou como isométrico, tentar como fluxograma
            if not doc_encontrado:
                # Match exato
                if numero_upper in pendentes_fluxo and pendentes_fluxo[numero_upper]:
                    doc_encontrado = pendentes_fluxo[numero_upper].pop(0)
                    tipo_match = "fluxograma"
                    destino_info = f"Fluxograma → Linha {linhas_map.get(doc_encontrado.linha_id, '?')}"
                    if not pendentes_fluxo[numero_upper]:
                        del pendentes_fluxo[numero_upper]
                else:
                    # Match parcial nos fluxogramas
                    matched_key = None
                    for num_esp, docs_esp in pendentes_fluxo.items():
                        if docs_esp and _match_numero(numero_upper, num_esp):
                            doc_encontrado = docs_esp.pop(0)
                            tipo_match = "fluxograma"
                            destino_info = f"Fluxograma → Linha {linhas_map.get(doc_encontrado.linha_id, '?')} [match aproximado]"
                            matched_key = num_esp
                            break
                    if matched_key and not pendentes_fluxo.get(matched_key):
                        del pendentes_fluxo[matched_key]

            # Se não encontrou correspondência, criar documento genérico
            if not doc_encontrado:
                # Criar novo DocumentoLinha genérico (aceitando qualquer PDF)
                doc_encontrado = DocumentoLinha(
                    sth_id=sth_id,
                    linha_id=None,  # Sem linha específica
                    tipo_documento='outro',  # Tipo genérico
                    numero_documento=numero_extraido,
                    ativo=True,
                )
                db.add(doc_encontrado)
                db.flush()
                tipo_match = "outro"
                destino_info = f"Documento Genérico ({numero_extraido})"

            # Salvar arquivo
            upload_dir = os.path.join(
                settings.UPLOAD_DIR, "documentos_linha",
                str(sth_id), str(doc_encontrado.linha_id or 0)
            )
            os.makedirs(upload_dir, exist_ok=True)
            ext = os.path.splitext(arq.filename)[1]
            filename = f"{tipo_match}_{uuid.uuid4().hex[:8]}{ext}"
            filepath = os.path.join(upload_dir, filename)

            with open(filepath, "wb") as f:
                f.write(content)

            # Atualizar registro do documento
            doc_encontrado.nome_arquivo = arq.filename
            doc_encontrado.caminho_arquivo = filepath
            doc_encontrado.tamanho_bytes = len(content)
            doc_encontrado.uploaded_by_id = current_user.id
            doc_encontrado.data_upload = datetime.utcnow()
            db.flush()

            sucessos += 1
            resultados.append({
                "arquivo": arq.filename,
                "sucesso": True,
                "tipo": tipo_match,
                "destino": destino_info,
                "numero_extraido": numero_extraido,
                "documento_id": doc_encontrado.id,
            })

        except Exception as e:
            erros.append({
                "arquivo": arq.filename or "desconhecido",
                "erro": str(e),
            })

    db.commit()

    logger.info(
        f"Upload lote inteligente STH {sth_id}: {sucessos}/{len(arquivos)} por {current_user.email}"
    )

    return {
        "total": len(arquivos),
        "sucessos": sucessos,
        "erros": erros,
        "resultados": resultados,
    }


# ── Listar documentos de um STH ────────────────────────────────────────

@router.get(
    "/sth/{sth_id}",
    response_model=List[DocumentoLinhaResponse],
    summary="Listar documentos de um STH",
)
def listar_documentos_sth(
    sth_id: int,
    linha_id: Optional[int] = Query(None),
    tipo: Optional[str] = Query(None),
    apenas_ativos: bool = Query(True),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Listar documentos de linha de um STH."""
    q = db.query(DocumentoLinha).filter(DocumentoLinha.sth_id == sth_id)
    if linha_id:
        q = q.filter(DocumentoLinha.linha_id == linha_id)
    if tipo:
        q = q.filter(DocumentoLinha.tipo_documento == tipo)
    if apenas_ativos:
        q = q.filter(DocumentoLinha.ativo == True)
    docs = q.order_by(DocumentoLinha.linha_id, DocumentoLinha.tipo_documento).all()
    return [_doc_to_response(d) for d in docs]


# ── Status de documentos de um STH ─────────────────────────────────────

@router.get(
    "/sth/{sth_id}/status",
    response_model=DocumentoLinhaStatusResponse,
    summary="Status de documentos do STH",
)
def status_documentos_sth(
    sth_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna status de completude dos documentos por linha."""
    sth = db.query(STH).filter(STH.id == sth_id).first()
    if not sth:
        raise HTTPException(404, "STH não encontrado.")

    # Tipos esperados por padrão: isometrico e fluxograma
    tipos_esperados_padrao = ["isometrico", "fluxograma"]

    linhas_status = []
    total_esperados = 0
    total_enviados = 0

    for sl in sth.sth_linhas:
        lc = sl.linha_cat
        # Verificar quais tipos são esperados para esta linha
        # Baseado nos registros de DocumentoLinha (incluindo pendentes sem arquivo)
        esperados_db = db.query(DocumentoLinha.tipo_documento).filter(
            DocumentoLinha.sth_id == sth_id,
            DocumentoLinha.linha_id == lc.id,
        ).distinct().all()
        esperados_set = set(t[0].value if hasattr(t[0], 'value') else str(t[0]) for t in esperados_db)
        # Merge com padrão
        esperados_set.update(tipos_esperados_padrao)
        esperados = sorted(esperados_set)

        # Documentos enviados (com arquivo e ativos)
        enviados = db.query(DocumentoLinha).filter(
            DocumentoLinha.sth_id == sth_id,
            DocumentoLinha.linha_id == lc.id,
            DocumentoLinha.ativo == True,
            DocumentoLinha.caminho_arquivo.isnot(None),
        ).all()
        enviados_tipos = set(
            d.tipo_documento.value if hasattr(d.tipo_documento, 'value') else str(d.tipo_documento)
            for d in enviados
        )

        pendentes = [t for t in esperados if t not in enviados_tipos]
        pct = (len(enviados_tipos) / len(esperados) * 100) if esperados else 100.0

        total_esperados += len(esperados)
        total_enviados += len(enviados_tipos)

        linhas_status.append(DocumentoLinhaStatusItem(
            linha_id=lc.id,
            numero_linha=lc.numero_linha,
            documentos_esperados=esperados,
            documentos_enviados=sorted(enviados_tipos),
            documentos_pendentes=pendentes,
            percentual=round(pct, 1),
        ))

    pct_geral = (total_enviados / total_esperados * 100) if total_esperados else 100.0

    return DocumentoLinhaStatusResponse(
        sth_id=sth.id,
        codigo_sth=sth.codigo,
        total_esperados=total_esperados,
        total_enviados=total_enviados,
        percentual_geral=round(pct_geral, 1),
        linhas=linhas_status,
    )


# ── Download de documento de linha ─────────────────────────────────────

@router.get(
    "/{doc_id}/download",
    summary="Download de documento de linha",
)
def download_documento_linha(
    doc_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(DocumentoLinha).filter(DocumentoLinha.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Documento não encontrado.")
    if not doc.caminho_arquivo or not os.path.exists(doc.caminho_arquivo):
        raise HTTPException(404, "Arquivo não encontrado no servidor.")
    return FileResponse(
        path=doc.caminho_arquivo,
        media_type="application/pdf",
        filename=doc.nome_arquivo or "documento.pdf",
    )


# ── Excluir documento de linha ─────────────────────────────────────────

@router.delete(
    "/{doc_id}",
    summary="Excluir documento de linha",
)
def delete_documento_linha(
    doc_id: int,
    current_user=Depends(require_roles(["Administrador", "Engenharia"])),
    db: Session = Depends(get_db),
):
    doc = db.query(DocumentoLinha).filter(DocumentoLinha.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Documento não encontrado.")

    if doc.caminho_arquivo and os.path.exists(doc.caminho_arquivo):
        try:
            os.remove(doc.caminho_arquivo)
        except OSError as e:
            logger.warning(f"Erro ao remover arquivo: {e}")

    db.delete(doc)
    db.commit()
    logger.info(f"Documento de linha {doc_id} removido por {current_user.email}")
    return {"message": "Documento removido com sucesso."}
