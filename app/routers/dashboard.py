"""Rotas do dashboard com estatísticas gerais."""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import PastaTeste, LinhaTubulacao, Relatorio, Usuario, StatusPasta
from app.schemas.schemas import DashboardResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/", response_model=DashboardResponse)
def get_dashboard(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna estatísticas gerais do sistema para o dashboard."""
    total_pastas = db.query(PastaTeste).count()
    pastas_abertas = db.query(PastaTeste).filter(
        PastaTeste.status.in_([StatusPasta.CRIADA, StatusPasta.EM_ANDAMENTO])
    ).count()
    pastas_concluidas = db.query(PastaTeste).filter(PastaTeste.status == StatusPasta.CONCLUIDA).count()
    total_linhas = db.query(LinhaTubulacao).count()
    total_relatorios = db.query(Relatorio).count()
    relatorios_rascunho = db.query(Relatorio).filter(Relatorio.status == "rascunho").count()
    relatorios_preenchidos = db.query(Relatorio).filter(Relatorio.status == "preenchido").count()
    relatorios_aprovados = db.query(Relatorio).filter(Relatorio.status == "aprovado").count()
    relatorios_pendentes_sync = db.query(Relatorio).filter(Relatorio.sincronizado == False).count()
    total_usuarios = db.query(Usuario).filter(Usuario.ativo == True).count()

    return DashboardResponse(
        total_pastas=total_pastas,
        pastas_abertas=pastas_abertas,
        pastas_concluidas=pastas_concluidas,
        total_linhas=total_linhas,
        total_relatorios=total_relatorios,
        relatorios_rascunho=relatorios_rascunho,
        relatorios_preenchidos=relatorios_preenchidos,
        relatorios_aprovados=relatorios_aprovados,
        relatorios_pendentes_sync=relatorios_pendentes_sync,
        total_usuarios=total_usuarios,
    )
