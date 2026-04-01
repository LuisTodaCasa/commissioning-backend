"""Rotas de relatórios de campo."""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.models import Relatorio, LinhaTubulacao, PastaTeste, ModeloRelatorio
from app.schemas.schemas import RelatorioCreate, RelatorioUpdate, RelatorioResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


def _auto_fill_dados_linha(db: Session, linha_id: int) -> dict:
    """Auto-preencher dados da linha de tubulação no relatório."""
    linha = db.query(LinhaTubulacao).filter(LinhaTubulacao.id == linha_id).first()
    if not linha:
        return {}
    return {
        "numero_linha": linha.numero_linha,
        "tag": linha.tag,
        "malha": linha.malha,
        "sistema": linha.sistema,
        "sop": linha.sop,
        "sub_sop": linha.sub_sop,
        "sth": linha.sth,
        "pressao_teste": linha.pressao_teste,
        "descricao_sistema": linha.descricao_sistema,
    }


@router.get("/", response_model=List[RelatorioResponse])
def list_relatorios(
    skip: int = 0,
    limit: int = 100,
    pasta_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Listar relatórios com filtros."""
    query = db.query(Relatorio)
    if pasta_id:
        query = query.filter(Relatorio.pasta_id == pasta_id)
    if status:
        query = query.filter(Relatorio.status == status)
    if search:
        query = query.filter(
            Relatorio.resultado.ilike(f"%{search}%") |
            Relatorio.observacoes.ilike(f"%{search}%")
        )

    return query.order_by(Relatorio.criado_em.desc()).offset(skip).limit(limit).all()


@router.get("/{relatorio_id}", response_model=RelatorioResponse)
def get_relatorio(
    relatorio_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rel = db.query(Relatorio).filter(Relatorio.id == relatorio_id).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")
    return rel


@router.post("/", response_model=RelatorioResponse, status_code=201)
def create_relatorio(
    data: RelatorioCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Criar novo relatório (pode ser rascunho para uso offline)."""
    # Validar pasta
    pasta = db.query(PastaTeste).filter(PastaTeste.id == data.pasta_id).first()
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    # Validar modelo
    modelo = db.query(ModeloRelatorio).filter(ModeloRelatorio.id == data.modelo_id).first()
    if not modelo:
        raise HTTPException(status_code=404, detail="Modelo não encontrado.")

    # Auto-fill dados da linha
    dados_linha = {}
    if data.linha_id:
        dados_linha = _auto_fill_dados_linha(db, data.linha_id)

    rel = Relatorio(
        pasta_id=data.pasta_id,
        modelo_id=data.modelo_id,
        linha_id=data.linha_id,
        usuario_id=current_user.id,
        dados_linha=dados_linha,
        dados_execucao=data.dados_execucao,
        pressao_inicial=data.pressao_inicial,
        pressao_final=data.pressao_final,
        tempo_teste=data.tempo_teste,
        resultado=data.resultado,
        observacoes=data.observacoes,
        status=data.status,
        offline_id=data.offline_id,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    logger.info(f"Relatório criado para pasta {data.pasta_id} por {current_user.email}")
    return rel


@router.put("/{relatorio_id}", response_model=RelatorioResponse)
def update_relatorio(
    relatorio_id: int,
    data: RelatorioUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Atualizar relatório (preenchimento de dados de campo)."""
    rel = db.query(Relatorio).filter(Relatorio.id == relatorio_id).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rel, field, value)
    db.commit()
    db.refresh(rel)
    return rel


@router.post("/{relatorio_id}/aprovar")
def aprovar_relatorio(
    relatorio_id: int,
    current_user=Depends(require_roles(["Administrador", "CQ"])),
    db: Session = Depends(get_db)
):
    """Aprovar relatório de teste (CQ)."""
    rel = db.query(Relatorio).filter(Relatorio.id == relatorio_id).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")

    if rel.status not in ("preenchido", "sincronizado"):
        raise HTTPException(status_code=400, detail="Relatório deve estar preenchido para ser aprovado.")

    rel.status = "aprovado"
    db.commit()
    logger.info(f"Relatório {relatorio_id} aprovado por {current_user.email}")
    return {"message": "Relatório aprovado com sucesso."}


@router.post("/{relatorio_id}/rejeitar")
def rejeitar_relatorio(
    relatorio_id: int,
    observacao: Optional[str] = None,
    current_user=Depends(require_roles(["Administrador", "CQ"])),
    db: Session = Depends(get_db)
):
    """Rejeitar relatório de teste."""
    rel = db.query(Relatorio).filter(Relatorio.id == relatorio_id).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")

    rel.status = "rejeitado"
    if observacao:
        existing_obs = rel.observacoes or ""
        rel.observacoes = f"{existing_obs}\n[CQ - Rejeitado]: {observacao}".strip()
    db.commit()
    return {"message": "Relatório rejeitado."}


@router.delete("/{relatorio_id}")
def delete_relatorio(
    relatorio_id: int,
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db)
):
    rel = db.query(Relatorio).filter(Relatorio.id == relatorio_id).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")
    db.delete(rel)
    db.commit()
    return {"message": "Relatório removido com sucesso."}
