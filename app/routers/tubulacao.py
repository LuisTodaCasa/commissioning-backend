"""Rotas de Tubulação – importação de Excel, listagem de STHs/Linhas/Spools."""
import io
import logging
import math
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.models import (
    STH, LinhaTubulacaoCatalogo, STHLinha, Spool, PastaTeste, StatusPasta,
    DocumentoLinha, TipoDocumento,
)
from app.schemas.schemas import (
    STHListResponse, STHDetailResponse, LinhaCatalogoResponse,
    SpoolResponse, ImportacaoExcelResponse, CriarPastaPorSTHRequest,
    PastaListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tubulacao", tags=["Tubulação"])


# ── Helpers ────────────────────────────────────────────────────────────

def _safe_str(val) -> Optional[str]:
    """Return stripped string or None."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    return str(val).strip() or None


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


# ── POST /tubulacao/importar-excel ─────────────────────────────────────

@router.post("/importar-excel", response_model=ImportacaoExcelResponse)
async def importar_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(["Administrador", "Engenharia"])),
):
    """Importar planilha Excel com dados de tubulação (aba BD)."""
    if not file.filename.endswith((".xlsx", ".xls", ".xlsm")):
        raise HTTPException(400, "Arquivo deve ser .xlsx, .xls ou .xlsm")

    contents = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(contents), sheet_name="BD")
    except Exception as exc:
        raise HTTPException(400, f"Erro ao ler planilha: {exc}")

    # Normalizar nomes de colunas (remove quebras de linha, \r, \n, tabs e espaços extras)
    import re
    df.columns = df.columns.str.replace('\n', ' ').str.replace('\r', ' ').str.replace('\t', ' ').str.strip()
    df.columns = [re.sub(r'\s+', ' ', str(c).strip()).upper() for c in df.columns]

    required = {"STH", "LINHA", "SPOOL"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(400, f"Colunas obrigatórias ausentes: {', '.join(missing)}")

    erros: List[str] = []
    stats = {"sths": 0, "linhas": 0, "spools": 0}

    # Cache para evitar queries repetidas
    sth_cache: dict[str, STH] = {}
    linha_cache: dict[str, LinhaTubulacaoCatalogo] = {}
    sth_linha_cache: set[tuple[int, int]] = set()  # (sth_id, linha_id) already linked
    doc_cache: set[tuple[int, int, str, str]] = set()  # (sth_id, linha_id, tipo, numero)

    for idx, row in df.iterrows():
        row_num = idx + 2  # header is row 1
        codigo_sth = _safe_str(row.get("STH"))
        numero_linha = _safe_str(row.get("LINHA"))
        codigo_spool = _safe_str(row.get("SPOOL"))

        if not codigo_sth:
            erros.append(f"Linha {row_num}: STH vazio, ignorada")
            continue
        if not numero_linha:
            erros.append(f"Linha {row_num}: LINHA vazia, ignorada")
            continue
        if not codigo_spool:
            erros.append(f"Linha {row_num}: SPOOL vazio, ignorada")
            continue

        # ── STH ──
        if codigo_sth not in sth_cache:
            sth_obj = db.query(STH).filter(STH.codigo == codigo_sth).first()
            if not sth_obj:
                sth_obj = STH(
                    codigo=codigo_sth,
                    sop=_safe_str(row.get("SOP")),
                    sub_sop=_safe_str(row.get("SSOP")),
                    descricao=_safe_str(row.get("DESCRIÇÃO")) or _safe_str(row.get("DESCRICAO")),
                )
                db.add(sth_obj)
                db.flush()
                stats["sths"] += 1
            sth_cache[codigo_sth] = sth_obj
        sth_obj = sth_cache[codigo_sth]

        # ── Linha catálogo ──
        if numero_linha not in linha_cache:
            linha_obj = db.query(LinhaTubulacaoCatalogo).filter(
                LinhaTubulacaoCatalogo.numero_linha == numero_linha
            ).first()
            if not linha_obj:
                linha_obj = LinhaTubulacaoCatalogo(
                    numero_linha=numero_linha,
                    fluido=_safe_str(row.get("FLUIDO")),
                    descricao_fluido=_safe_str(row.get("DESCRIÇÃO")) or _safe_str(row.get("DESCRICAO")),
                    pressao_teste=_safe_float(row.get("PRESSÃO DE TESTE")) or _safe_float(row.get("PRESSAO DE TESTE")),
                    pressao_operacao=_safe_float(row.get("PRESSÃO OPERAÇÃO")) or _safe_float(row.get("PRESSAO OPERACAO")),
                )
                db.add(linha_obj)
                db.flush()
                stats["linhas"] += 1
            linha_cache[numero_linha] = linha_obj
        linha_obj = linha_cache[numero_linha]

        # ── STH ↔ Linha (M2M) ──
        link_key = (sth_obj.id, linha_obj.id)
        if link_key not in sth_linha_cache:
            existing_link = db.query(STHLinha).filter(
                STHLinha.sth_id == sth_obj.id,
                STHLinha.linha_id == linha_obj.id,
            ).first()
            if not existing_link:
                db.add(STHLinha(sth_id=sth_obj.id, linha_id=linha_obj.id))
                db.flush()
            sth_linha_cache.add(link_key)

        # ── Spool ──
        existing_spool = db.query(Spool).filter(
            Spool.sth_id == sth_obj.id,
            Spool.codigo_spool == codigo_spool,
        ).first()
        if not existing_spool:
            spool = Spool(
                sth_id=sth_obj.id,
                linha_id=linha_obj.id,
                codigo_spool=codigo_spool,
                origem=_safe_str(row.get("DE")),
                destino=_safe_str(row.get("PARA")),
                isometrico_ref=_safe_str(row.get("ISOMÉTRICO")) or _safe_str(row.get("ISOMETRICO")),
                fluxograma=_safe_str(row.get("FLUXOGRAMA")),
            )
            db.add(spool)
            stats["spools"] += 1
        else:
            erros.append(f"Linha {row_num}: Spool '{codigo_spool}' duplicado no STH '{codigo_sth}', ignorado")

        # ── Registrar documentos esperados (isométrico e fluxograma) ──
        iso_ref = _safe_str(row.get("ISOMÉTRICO")) or _safe_str(row.get("ISOMETRICO"))
        fluxo_ref = _safe_str(row.get("FLUXOGRAMA"))

        for tipo_doc, num_doc in [
            (TipoDocumento.ISOMETRICO, iso_ref),
            (TipoDocumento.FLUXOGRAMA, fluxo_ref),
        ]:
            if num_doc:
                doc_key = (sth_obj.id, linha_obj.id, tipo_doc.value, num_doc)
                if doc_key not in doc_cache:
                    existing_doc = db.query(DocumentoLinha).filter(
                        DocumentoLinha.sth_id == sth_obj.id,
                        DocumentoLinha.linha_id == linha_obj.id,
                        DocumentoLinha.tipo_documento == tipo_doc,
                        DocumentoLinha.numero_documento == num_doc,
                    ).first()
                    if not existing_doc:
                        db.add(DocumentoLinha(
                            sth_id=sth_obj.id,
                            linha_id=linha_obj.id,
                            tipo_documento=tipo_doc,
                            numero_documento=num_doc,
                            ativo=True,
                        ))
                    doc_cache.add(doc_key)

    db.commit()
    return ImportacaoExcelResponse(
        mensagem="Importação concluída com sucesso",
        total_sths=stats["sths"],
        total_linhas=stats["linhas"],
        total_spools=stats["spools"],
        erros=erros,
    )


# ── GET /tubulacao/sths ────────────────────────────────────────────────

@router.get("/sths", response_model=List[STHListResponse])
def listar_sths(
    busca: Optional[str] = Query(None, description="Busca por código STH"),
    sop: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Listar STHs com filtros."""
    q = db.query(STH)
    if busca:
        q = q.filter(STH.codigo.ilike(f"%{busca}%"))
    if sop:
        q = q.filter(STH.sop == sop)
    q = q.order_by(STH.codigo)
    sths = q.offset(skip).limit(limit).all()

    result = []
    for s in sths:
        total_linhas = db.query(func.count(STHLinha.id)).filter(STHLinha.sth_id == s.id).scalar() or 0
        total_spools = db.query(func.count(Spool.id)).filter(Spool.sth_id == s.id).scalar() or 0
        pasta = db.query(PastaTeste).filter(PastaTeste.sth_id == s.id).first()
        result.append(STHListResponse(
            id=s.id,
            codigo_sth=s.codigo,
            sop=s.sop,
            ssop=s.sub_sop,
            descricao=s.descricao,
            total_linhas=total_linhas,
            total_spools=total_spools,
            pasta_id=pasta.id if pasta else None,
            criado_em=s.criado_em,
        ))
    return result


# ── GET /tubulacao/sths/{id} ───────────────────────────────────────────

@router.get("/sths/{sth_id}", response_model=STHDetailResponse)
def detalhe_sth(
    sth_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Detalhe de um STH com linhas e spools."""
    sth = db.query(STH).filter(STH.id == sth_id).first()
    if not sth:
        raise HTTPException(404, "STH não encontrado")

    # Linhas
    linhas_resp = []
    for sl in sth.sth_linhas:
        lc = sl.linha_cat
        total_sp = db.query(func.count(Spool.id)).filter(
            Spool.sth_id == sth.id, Spool.linha_id == lc.id
        ).scalar() or 0
        linhas_resp.append(LinhaCatalogoResponse(
            id=lc.id,
            numero_linha=lc.numero_linha,
            fluido=lc.fluido,
            descricao_fluido=lc.descricao_fluido,
            pressao_teste=lc.pressao_teste,
            pressao_operacao=lc.pressao_operacao,
            total_spools=total_sp,
        ))

    # Spools
    spools_resp = []
    for sp in sth.spools:
        spools_resp.append(SpoolResponse(
            id=sp.id,
            codigo_spool=sp.codigo_spool,
            origem=sp.origem,
            destino=sp.destino,
            isometrico_ref=sp.isometrico_ref,
            fluxograma=sp.fluxograma,
            linha_numero=sp.linha_cat.numero_linha if sp.linha_cat else None,
            criado_em=sp.criado_em,
        ))

    pasta = db.query(PastaTeste).filter(PastaTeste.sth_id == sth.id).first()

    return STHDetailResponse(
        id=sth.id,
        codigo_sth=sth.codigo,
        sop=sth.sop,
        ssop=sth.sub_sop,
        descricao=sth.descricao,
        pasta_id=pasta.id if pasta else None,
        pasta_numero=pasta.numero_pasta if pasta else None,
        linhas=linhas_resp,
        spools=spools_resp,
        criado_em=sth.criado_em,
    )


# ── POST /tubulacao/criar-pasta-por-sth ────────────────────────────────

@router.post("/criar-pasta-por-sth", response_model=PastaListResponse)
def criar_pasta_por_sth(
    payload: CriarPastaPorSTHRequest,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(["Administrador", "Engenharia"])),
):
    """Criar uma pasta de teste a partir de um STH."""
    # 1. Buscar pelo ID informado
    sth = db.query(STH).filter(STH.id == payload.sth_id).first()

    # 2. Se não encontrou por ID, buscar pelo código (caso o ID seja um ID local/IndexedDB)
    if not sth and payload.codigo_sth:
        sth = db.query(STH).filter(STH.codigo == payload.codigo_sth).first()
        if sth:
            logger.info(f"STH encontrado pelo código '{payload.codigo_sth}' (id real={sth.id}, id enviado={payload.sth_id})")

    # 3. Se realmente não existe nem por ID nem por código, criar novo
    if not sth:
        if not payload.codigo_sth:
            raise HTTPException(400, "STH não encontrado e nenhum código foi fornecido para criação")
        
        # Criar novo STH (sem forçar o ID, deixar o banco gerar)
        sth = STH(
            codigo=payload.codigo_sth,
            descricao=payload.descricao or "",
            sop=payload.sop,
            sub_sop=payload.ssop,
        )
        db.add(sth)
        try:
            db.flush()  # Flush to get the ID without committing
            logger.info(f"Novo STH criado: codigo={payload.codigo_sth}, id={sth.id}")
        except Exception as e:
            logger.error(f"Erro ao criar STH '{payload.codigo_sth}': {e}")
            raise HTTPException(500, f"Erro ao criar STH: {str(e)}")

    # Verifica se já existe pasta para este STH
    existing = db.query(PastaTeste).filter(PastaTeste.sth_id == sth.id).first()
    if existing:
        raise HTTPException(400, f"Já existe pasta '{existing.numero_pasta}' para este STH")

    # Verifica numero_pasta único
    dup = db.query(PastaTeste).filter(PastaTeste.numero_pasta == payload.numero_pasta).first()
    if dup:
        raise HTTPException(400, f"Já existe uma pasta com o número '{payload.numero_pasta}'")

    # Pega pressão de teste da primeira linha
    first_link = db.query(STHLinha).filter(STHLinha.sth_id == sth.id).first()
    pressao = None
    if first_link and first_link.linha_cat:
        pressao = first_link.linha_cat.pressao_teste

    pasta = PastaTeste(
        numero_pasta=payload.numero_pasta,
        sth=sth.codigo,
        sth_id=sth.id,
        descricao_sistema=sth.descricao,
        pressao_teste=pressao,
        status=StatusPasta.CRIADA,
        data_criacao=payload.data_criacao,
        criado_por_id=current_user.id,
    )
    db.add(pasta)
    db.commit()
    db.refresh(pasta)

    return PastaListResponse(
        id=pasta.id,
        numero_pasta=pasta.numero_pasta,
        sth=pasta.sth,
        descricao_sistema=pasta.descricao_sistema,
        pressao_teste=pasta.pressao_teste,
        status=pasta.status.value if hasattr(pasta.status, 'value') else str(pasta.status),
        data_criacao=pasta.data_criacao,
        criado_em=pasta.criado_em,
        atualizado_em=pasta.atualizado_em,
        total_linhas=0,
        total_documentos=0,
        total_testes=0,
    )
