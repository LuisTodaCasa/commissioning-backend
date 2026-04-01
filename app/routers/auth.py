"""Rotas de autenticação: login, registro, redefinição de senha."""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password, create_access_token,
    create_reset_token, decode_token, get_current_user
)
from app.models.models import Usuario, UsuarioDisciplina, Disciplina
from app.schemas.schemas import (
    LoginRequest, TokenResponse, UsuarioCreate, UsuarioResponse,
    PasswordResetRequest, PasswordResetConfirm, DisciplinaSimples
)
from app.utils.email import send_reset_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Autenticação"])


def _build_user_response(user: Usuario) -> UsuarioResponse:
    discs = []
    for ud in user.disciplinas:
        if ud.disciplina:
            discs.append(DisciplinaSimples(id=ud.disciplina.id, nome=ud.disciplina.nome))
    return UsuarioResponse(
        id=user.id, nome=user.nome, email=user.email,
        role=user.role.value if hasattr(user.role, 'value') else str(user.role),
        ativo=user.ativo, criado_em=user.criado_em, disciplinas=discs
    )


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """Autenticação por e-mail e senha."""
    user = db.query(Usuario).options(
        joinedload(Usuario.disciplinas).joinedload(UsuarioDisciplina.disciplina)
    ).filter(Usuario.email == data.email).first()

    if not user or not verify_password(data.senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos.")

    if not user.ativo:
        raise HTTPException(status_code=403, detail="Usuário desativado. Contate o administrador.")

    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    return TokenResponse(
        access_token=token,
        usuario=_build_user_response(user)
    )


@router.post("/register", response_model=UsuarioResponse, status_code=201)
def register(data: UsuarioCreate, db: Session = Depends(get_db)):
    """Registrar novo usuário."""
    existing = db.query(Usuario).filter(Usuario.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")

    user = Usuario(
        nome=data.nome,
        email=data.email,
        senha_hash=hash_password(data.senha),
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"Novo usuário registrado: {user.email} (role: {user.role})")
    return _build_user_response(user)


@router.post("/password-reset-request")
async def request_password_reset(data: PasswordResetRequest, db: Session = Depends(get_db)):
    """Solicitar redefinição de senha via e-mail."""
    user = db.query(Usuario).filter(Usuario.email == data.email).first()
    if not user:
        # Não revelar se o e-mail existe
        return {"message": "Se o e-mail estiver cadastrado, você receberá um link de redefinição."}

    token = create_reset_token(data.email)
    user.reset_token = token
    user.reset_token_expira = datetime.utcnow() + timedelta(minutes=30)
    db.commit()

    await send_reset_email(data.email, token)
    return {"message": "Se o e-mail estiver cadastrado, você receberá um link de redefinição."}


@router.post("/password-reset-confirm")
def confirm_password_reset(data: PasswordResetConfirm, db: Session = Depends(get_db)):
    """Confirmar redefinição de senha com token."""
    payload = decode_token(data.token)
    if payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="Token inválido.")

    email = payload.get("sub")
    user = db.query(Usuario).filter(Usuario.email == email).first()
    if not user or user.reset_token != data.token:
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")

    if user.reset_token_expira and user.reset_token_expira < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token expirado.")

    user.senha_hash = hash_password(data.nova_senha)
    user.reset_token = None
    user.reset_token_expira = None
    db.commit()
    logger.info(f"Senha redefinida para: {email}")
    return {"message": "Senha redefinida com sucesso."}


@router.get("/me", response_model=UsuarioResponse)
def get_me(current_user: Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retorna dados do usuário autenticado."""
    user = db.query(Usuario).options(
        joinedload(Usuario.disciplinas).joinedload(UsuarioDisciplina.disciplina)
    ).filter(Usuario.id == current_user.id).first()
    return _build_user_response(user)
