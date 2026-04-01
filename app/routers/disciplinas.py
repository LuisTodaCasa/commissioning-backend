"""Rotas de gestão de disciplinas."""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.models import Disciplina
from app.schemas.schemas import DisciplinaResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/disciplinas", tags=["Disciplinas"])


@router.get("/", response_model=List[DisciplinaResponse])
def list_disciplinas(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Listar todas as disciplinas ativas."""
    return db.query(Disciplina).filter(Disciplina.ativo == True).all()


@router.get("/{disc_id}", response_model=DisciplinaResponse)
def get_disciplina(
    disc_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    disc = db.query(Disciplina).filter(Disciplina.id == disc_id).first()
    if not disc:
        raise HTTPException(status_code=404, detail="Disciplina não encontrada.")
    return disc
