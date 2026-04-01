"""Rotas de atribuição de testes a pastas.

Quando templates são atribuídos a uma pasta, o sistema gera automaticamente
relatórios de execução para cada combinação (linha, template).
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.models import (
    PastaTeste_Teste, PastaTeste, ModeloRelatorio,
    RelatorioExecucao, StatusExecucao
)
from app.schemas.schemas import AssignTestesRequest, PastaTesteResponse, ModeloResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/testes", tags=["Testes de Pasta"])


@router.post("/pasta/{pasta_id}")
def assign_testes(
    pasta_id: int,
    data: AssignTestesRequest,
    current_user=Depends(require_roles(["Administrador", "Comissionamento", "Engenharia"])),
    db: Session = Depends(get_db)
):
    """
    Atribuir testes (modelos) a uma pasta de teste.

    Ao atribuir templates, o sistema gera automaticamente relatórios de execução
    para cada combinação (linha, template) na pasta. Templates removidos que possuem
    relatórios pendentes terão seus relatórios marcados como removidos (soft delete).
    """
    pasta = db.query(PastaTeste).filter(PastaTeste.id == pasta_id).first()
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    # Identificar templates que estão sendo removidos
    existing_assignments = db.query(PastaTeste_Teste).filter(
        PastaTeste_Teste.pasta_id == pasta_id
    ).all()
    old_modelo_ids = {a.modelo_id for a in existing_assignments}
    new_modelo_ids = set(data.modelo_ids)
    removed_modelo_ids = old_modelo_ids - new_modelo_ids

    # Soft-delete relatórios de execução de templates removidos
    # (só remove pendentes; em_execucao, concluido e reprovado são preservados)
    if removed_modelo_ids:
        deleted_count = db.query(RelatorioExecucao).filter(
            RelatorioExecucao.pasta_id == pasta_id,
            RelatorioExecucao.template_id.in_(removed_modelo_ids),
            RelatorioExecucao.status == StatusExecucao.PENDENTE,
        ).delete(synchronize_session="fetch")
        if deleted_count > 0:
            logger.info(
                f"Removidos {deleted_count} relatórios de execução pendentes "
                f"de templates removidos da pasta {pasta_id}"
            )

    # Remover atribuições existentes
    db.query(PastaTeste_Teste).filter(PastaTeste_Teste.pasta_id == pasta_id).delete()

    for idx, modelo_id in enumerate(data.modelo_ids):
        modelo = db.query(ModeloRelatorio).filter(ModeloRelatorio.id == modelo_id).first()
        if not modelo:
            raise HTTPException(status_code=404, detail=f"Modelo {modelo_id} não encontrado.")
        db.add(PastaTeste_Teste(
            pasta_id=pasta_id,
            modelo_id=modelo_id,
            ordem=idx,
        ))

    db.commit()

    # Gerar relatórios de execução automaticamente
    from app.routers.execucao import generate_reports_for_pasta
    gen_result = generate_reports_for_pasta(db, pasta_id)

    logger.info(f"Testes atribuídos à pasta {pasta_id}: {data.modelo_ids}")
    return {
        "message": "Testes atribuídos com sucesso.",
        "modelo_ids": data.modelo_ids,
        "relatorios_gerados": gen_result.total_gerados,
        "relatorios_existentes": gen_result.relatorios_existentes,
    }


@router.get("/pasta/{pasta_id}", response_model=List[PastaTesteResponse])
def list_testes_pasta(
    pasta_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Listar testes atribuídos a uma pasta."""
    pts = db.query(PastaTeste_Teste).filter(
        PastaTeste_Teste.pasta_id == pasta_id
    ).order_by(PastaTeste_Teste.ordem).all()

    result = []
    for pt in pts:
        modelo = db.query(ModeloRelatorio).filter(ModeloRelatorio.id == pt.modelo_id).first()
        result.append(PastaTesteResponse(
            id=pt.id,
            pasta_id=pt.pasta_id,
            modelo_id=pt.modelo_id,
            ordem=pt.ordem,
            obrigatorio=pt.obrigatorio,
            modelo=ModeloResponse.model_validate(modelo) if modelo else None,
            criado_em=pt.criado_em,
        ))
    return result


@router.delete("/pasta/{pasta_id}/{modelo_id}")
def remove_teste(
    pasta_id: int,
    modelo_id: int,
    current_user=Depends(require_roles(["Administrador", "Comissionamento"])),
    db: Session = Depends(get_db)
):
    """
    Remover um teste (template) de uma pasta.
    Relatórios de execução pendentes associados são removidos.
    Relatórios em outros status são preservados.
    """
    pt = db.query(PastaTeste_Teste).filter(
        PastaTeste_Teste.pasta_id == pasta_id,
        PastaTeste_Teste.modelo_id == modelo_id,
    ).first()
    if not pt:
        raise HTTPException(status_code=404, detail="Teste não encontrado nesta pasta.")

    # Remover relatórios de execução pendentes deste template
    deleted_reports = db.query(RelatorioExecucao).filter(
        RelatorioExecucao.pasta_id == pasta_id,
        RelatorioExecucao.template_id == modelo_id,
        RelatorioExecucao.status == StatusExecucao.PENDENTE,
    ).delete(synchronize_session="fetch")

    db.delete(pt)
    db.commit()

    logger.info(
        f"Template {modelo_id} removido da pasta {pasta_id}. "
        f"{deleted_reports} relatórios pendentes removidos."
    )
    return {
        "message": "Teste removido da pasta.",
        "relatorios_pendentes_removidos": deleted_reports,
    }
