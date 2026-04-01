"""Rotas de gestão de usuários e permissões de disciplinas."""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.security import require_roles, get_current_user, hash_password
from app.models.models import Usuario, Disciplina, UsuarioDisciplina
from app.schemas.schemas import (
    UsuarioResponse, UsuarioUpdate, UsuarioCreate,
    AssignDisciplinasRequest, DisciplinaResponse, DisciplinaSimples
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/usuarios", tags=["Usuários"])


@router.get("/", response_model=List[UsuarioResponse])
def list_users(
    skip: int = 0, limit: int = 100,
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db)
):
    """Listar todos os usuários (apenas Administrador)."""
    users = db.query(Usuario).options(
        joinedload(Usuario.disciplinas).joinedload(UsuarioDisciplina.disciplina)
    ).offset(skip).limit(limit).all()

    result = []
    for u in users:
        discs = [DisciplinaSimples(id=ud.disciplina.id, nome=ud.disciplina.nome)
                 for ud in u.disciplinas if ud.disciplina]
        result.append(UsuarioResponse(
            id=u.id, nome=u.nome, email=u.email,
            role=u.role.value if hasattr(u.role, 'value') else str(u.role),
            ativo=u.ativo, criado_em=u.criado_em, disciplinas=discs
        ))
    return result


@router.get("/{user_id}", response_model=UsuarioResponse)
def get_user(
    user_id: int,
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db)
):
    user = db.query(Usuario).options(
        joinedload(Usuario.disciplinas).joinedload(UsuarioDisciplina.disciplina)
    ).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    discs = [DisciplinaSimples(id=ud.disciplina.id, nome=ud.disciplina.nome)
             for ud in user.disciplinas if ud.disciplina]
    return UsuarioResponse(
        id=user.id, nome=user.nome, email=user.email,
        role=user.role.value if hasattr(user.role, 'value') else str(user.role),
        ativo=user.ativo, criado_em=user.criado_em, disciplinas=discs
    )


@router.put("/{user_id}", response_model=UsuarioResponse)
def update_user(
    user_id: int, data: UsuarioUpdate,
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db)
):
    """Atualizar dados do usuário."""
    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    logger.info(f"Usuário {user_id} atualizado por {current_user.email}")
    return get_user(user_id, current_user, db)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db)
):
    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    user.ativo = False
    db.commit()
    return {"message": f"Usuário {user.nome} desativado com sucesso."}


@router.post("/{user_id}/disciplinas")
def assign_disciplinas(
    user_id: int, data: AssignDisciplinasRequest,
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db)
):
    """Atribuir disciplinas a um usuário."""
    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    # Remover permissões existentes
    db.query(UsuarioDisciplina).filter(UsuarioDisciplina.usuario_id == user_id).delete()

    # Adicionar novas
    for disc_id in data.disciplina_ids:
        disc = db.query(Disciplina).filter(Disciplina.id == disc_id).first()
        if not disc:
            raise HTTPException(status_code=404, detail=f"Disciplina {disc_id} não encontrada.")
        db.add(UsuarioDisciplina(usuario_id=user_id, disciplina_id=disc_id))

    db.commit()
    logger.info(f"Disciplinas atualizadas para usuário {user_id}: {data.disciplina_ids}")
    return {"message": "Disciplinas atribuídas com sucesso.", "disciplina_ids": data.disciplina_ids}


@router.get("/{user_id}/disciplinas", response_model=List[DisciplinaResponse])
def get_user_disciplinas(
    user_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retorna disciplinas do usuário."""
    uds = db.query(UsuarioDisciplina).filter(
        UsuarioDisciplina.usuario_id == user_id
    ).all()
    result = []
    for ud in uds:
        disc = db.query(Disciplina).filter(Disciplina.id == ud.disciplina_id).first()
        if disc:
            result.append(DisciplinaResponse(
                id=disc.id, nome=disc.nome, descricao=disc.descricao, ativo=disc.ativo
            ))
    return result
