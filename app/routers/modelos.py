"""
Rotas legadas de modelos/templates de relatório.

Mantidas para compatibilidade com endpoints existentes (/api/v1/modelos).
A implementação principal está em app.routers.templates (/api/v1/templates).
"""
import os
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user, require_roles
from app.models.models import ModeloRelatorio, PastaTeste_Teste
from app.schemas.schemas import ModeloCreate, ModeloUpdate, ModeloResponse, TIPOS_MODELO_VALIDOS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/modelos", tags=["Modelos de Relatório (Legacy)"])


def _build_download_url(modelo: ModeloRelatorio) -> Optional[str]:
    pdf_path = modelo.arquivo_pdf or modelo.caminho_template
    if pdf_path:
        return f"/api/v1/modelos/{modelo.id}/template-download"
    return None


def _count_pastas(db: Session, modelo_id: int) -> int:
    return db.query(func.count(PastaTeste_Teste.id)).filter(
        PastaTeste_Teste.modelo_id == modelo_id
    ).scalar() or 0


def _modelo_to_response(db: Session, modelo: ModeloRelatorio) -> dict:
    return {
        "id": modelo.id,
        "nome": modelo.nome,
        "descricao": modelo.descricao,
        "tipo": modelo.tipo.value if hasattr(modelo.tipo, 'value') else str(modelo.tipo),
        "arquivo_pdf": modelo.arquivo_pdf,
        "caminho_template": modelo.caminho_template,
        "campos": modelo.campos,
        "ativo": modelo.ativo,
        "data_criacao": modelo.data_criacao,
        "criado_em": modelo.criado_em,
        "atualizado_em": modelo.atualizado_em,
        "download_url": _build_download_url(modelo),
        "total_pastas_usando": _count_pastas(db, modelo.id),
    }


def _extract_pdf_fields(filepath: str) -> dict:
    """Tenta extrair campos editáveis de um PDF template."""
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(filepath)
        fields = {}
        if reader.get_fields():
            for name, field in reader.get_fields().items():
                fields[name] = {
                    "tipo": str(field.get("/FT", "/Tx")),
                    "valor_padrao": str(field.get("/V", "")),
                    "obrigatorio": bool(field.get("/Ff", 0) & 2),
                }
            return {"auto_detected": True, "fields": fields}
    except Exception as e:
        logger.warning(f"Não foi possível extrair campos do PDF: {e}")

    return {
        "auto_detected": False,
        "fields": {
            "numero_linha": {"tipo": "text", "auto_fill": True, "label": "Número da Linha"},
            "tag": {"tipo": "text", "auto_fill": True, "label": "TAG"},
            "malha": {"tipo": "text", "auto_fill": True, "label": "Malha"},
            "sop": {"tipo": "text", "auto_fill": True, "label": "SOP"},
            "sub_sop": {"tipo": "text", "auto_fill": True, "label": "Sub SOP"},
            "sth": {"tipo": "text", "auto_fill": True, "label": "STH"},
            "pressao_teste": {"tipo": "number", "auto_fill": True, "label": "Pressão de Teste"},
            "descricao_sistema": {"tipo": "text", "auto_fill": True, "label": "Descrição do Sistema"},
            "pressao_inicial": {"tipo": "number", "auto_fill": False, "label": "Pressão Inicial"},
            "pressao_final": {"tipo": "number", "auto_fill": False, "label": "Pressão Final"},
            "tempo_teste": {"tipo": "number", "auto_fill": False, "label": "Tempo de Teste (min)"},
            "resultado": {"tipo": "select", "auto_fill": False, "label": "Resultado",
                         "opcoes": ["Aprovado", "Reprovado", "Pendente"]},
            "observacoes": {"tipo": "textarea", "auto_fill": False, "label": "Observações"},
        },
    }


@router.get("/", response_model=List[ModeloResponse],
            summary="Listar modelos de relatório")
def list_modelos(
    tipo: Optional[str] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Listar modelos de relatório ativos."""
    query = db.query(ModeloRelatorio).filter(ModeloRelatorio.ativo == True)
    if tipo:
        query = query.filter(ModeloRelatorio.tipo == tipo)
    modelos = query.all()
    return [_modelo_to_response(db, m) for m in modelos]


@router.get("/{modelo_id}", response_model=ModeloResponse,
            summary="Obter detalhes de um modelo")
def get_modelo(
    modelo_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    modelo = db.query(ModeloRelatorio).filter(ModeloRelatorio.id == modelo_id).first()
    if not modelo:
        raise HTTPException(status_code=404, detail="Modelo não encontrado.")
    return _modelo_to_response(db, modelo)


@router.post("/", response_model=ModeloResponse, status_code=201,
             summary="Criar modelo de relatório (sem PDF)")
def create_modelo(
    data: ModeloCreate,
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db),
):
    """Criar modelo de relatório (sem PDF template)."""
    if data.tipo:
        if data.tipo not in TIPOS_MODELO_VALIDOS:
            raise HTTPException(status_code=400, detail=f"Tipo inválido: '{data.tipo}'.")

    modelo = ModeloRelatorio(
        nome=data.nome,
        descricao=data.descricao,
        tipo=data.tipo,
        campos=data.campos or _extract_pdf_fields("")["fields"],
    )
    db.add(modelo)
    db.commit()
    db.refresh(modelo)
    return _modelo_to_response(db, modelo)


@router.post("/upload-template", response_model=ModeloResponse, status_code=201,
             summary="Upload de template PDF")
async def upload_template(
    nome: str = Form(...),
    tipo: str = Form(...),
    descricao: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db),
):
    """Upload de template PDF para modelo de relatório."""
    if tipo not in TIPOS_MODELO_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Tipo inválido: '{tipo}'.")

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Apenas PDFs são permitidos.")

    upload_dir = os.path.join(settings.UPLOAD_DIR, "templates", tipo)
    os.makedirs(upload_dir, exist_ok=True)

    filename = f"{tipo}_{uuid.uuid4().hex[:8]}.pdf"
    filepath = os.path.join(upload_dir, filename)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    campos = _extract_pdf_fields(filepath)

    modelo = ModeloRelatorio(
        nome=nome,
        descricao=descricao,
        tipo=tipo,
        arquivo_pdf=filepath,
        caminho_template=filepath,
        campos=campos,
    )
    db.add(modelo)
    db.commit()
    db.refresh(modelo)
    logger.info(f"Template '{nome}' ({tipo}) criado por {current_user.email}")
    return _modelo_to_response(db, modelo)


@router.put("/{modelo_id}", response_model=ModeloResponse,
            summary="Atualizar modelo de relatório")
def update_modelo(
    modelo_id: int,
    data: ModeloUpdate,
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db),
):
    modelo = db.query(ModeloRelatorio).filter(ModeloRelatorio.id == modelo_id).first()
    if not modelo:
        raise HTTPException(status_code=404, detail="Modelo não encontrado.")

    update_data = data.model_dump(exclude_unset=True)

    if "tipo" in update_data and update_data["tipo"]:
        if update_data["tipo"] not in TIPOS_MODELO_VALIDOS:
            raise HTTPException(status_code=400, detail=f"Tipo inválido: '{update_data['tipo']}'.")

    # Handle campos_template serialization
    if "campos_template" in update_data and update_data["campos_template"] is not None:
        update_data["campos_template"] = [
            c.model_dump() if hasattr(c, 'model_dump') else c
            for c in update_data["campos_template"]
        ]

    for field, value in update_data.items():
        setattr(modelo, field, value)
    db.commit()
    db.refresh(modelo)
    return _modelo_to_response(db, modelo)


@router.get("/{modelo_id}/template-download",
            summary="Download do template PDF")
def download_template(
    modelo_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download do template PDF."""
    modelo = db.query(ModeloRelatorio).filter(ModeloRelatorio.id == modelo_id).first()
    if not modelo:
        raise HTTPException(status_code=404, detail="Template não encontrado.")

    pdf_path = modelo.arquivo_pdf or modelo.caminho_template
    if not pdf_path:
        raise HTTPException(status_code=404, detail="Template não possui arquivo PDF.")

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Arquivo do template não encontrado.")

    tipo_str = modelo.tipo.value if hasattr(modelo.tipo, 'value') else str(modelo.tipo)
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"{tipo_str}_template.pdf",
    )


@router.delete("/{modelo_id}", summary="Desativar/excluir modelo")
def delete_modelo(
    modelo_id: int,
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db),
):
    modelo = db.query(ModeloRelatorio).filter(ModeloRelatorio.id == modelo_id).first()
    if not modelo:
        raise HTTPException(status_code=404, detail="Modelo não encontrado.")

    pastas_count = _count_pastas(db, modelo_id)
    if pastas_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Não é possível desativar: template atribuído a {pastas_count} pasta(s).",
        )

    modelo.ativo = False
    db.commit()
    return {"message": "Modelo desativado com sucesso."}
