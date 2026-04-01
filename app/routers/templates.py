"""
Rotas do módulo de Modelos de Relatórios (Templates).

Endpoints sob /api/v1/templates para upload, listagem, download,
configuração de campos e gestão de templates PDF de relatórios.
"""
import os
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user, require_roles
from app.models.models import ModeloRelatorio, PastaTeste_Teste, TipoModelo
from app.schemas.schemas import (
    ModeloCreate, ModeloUpdate, ModeloResponse, ModeloDetail,
    CampoTemplate, CamposTemplateRequest,
    TIPOS_MODELO_VALIDOS, AUTO_FILL_FIELDS,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/templates", tags=["Modelos de Relatório (Templates)"])

MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB

# ── Helpers ────────────────────────────────────────────────────────────

def _validate_tipo(tipo: str) -> str:
    """Valida se o tipo informado é um dos suportados."""
    if tipo not in TIPOS_MODELO_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo inválido: '{tipo}'. Valores aceitos: {', '.join(TIPOS_MODELO_VALIDOS)}",
        )
    return tipo


def _get_modelo_or_404(db: Session, modelo_id: int) -> ModeloRelatorio:
    modelo = db.query(ModeloRelatorio).filter(ModeloRelatorio.id == modelo_id).first()
    if not modelo:
        raise HTTPException(status_code=404, detail="Template não encontrado.")
    return modelo


def _build_download_url(modelo: ModeloRelatorio) -> Optional[str]:
    """Gera URL de download se houver PDF."""
    pdf_path = modelo.arquivo_pdf or modelo.caminho_template
    if pdf_path:
        return f"/api/v1/templates/{modelo.id}/download"
    return None


def _count_pastas_usando(db: Session, modelo_id: int) -> int:
    """Conta quantas pastas estão usando este template."""
    return db.query(func.count(PastaTeste_Teste.id)).filter(
        PastaTeste_Teste.modelo_id == modelo_id
    ).scalar() or 0


def _modelo_to_response(db: Session, modelo: ModeloRelatorio) -> dict:
    """Converte modelo ORM para dicionário com campos extras."""
    data = {
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
        "total_pastas_usando": _count_pastas_usando(db, modelo.id),
    }
    return data


def _modelo_to_detail(db: Session, modelo: ModeloRelatorio) -> dict:
    """Converte modelo ORM para dicionário detalhado (com campos_template)."""
    data = _modelo_to_response(db, modelo)
    # Parse campos_template de JSON para lista de CampoTemplate
    raw = modelo.campos_template
    if raw and isinstance(raw, list):
        data["campos_template"] = raw
    else:
        data["campos_template"] = None
    return data


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

    # Campos padrão se não detectar automaticamente
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
            "resultado": {
                "tipo": "select", "auto_fill": False, "label": "Resultado",
                "opcoes": ["Aprovado", "Reprovado", "Pendente"],
            },
            "observacoes": {"tipo": "textarea", "auto_fill": False, "label": "Observações"},
        },
    }


def _get_default_campos_template() -> list:
    """Retorna a configuração padrão de campos para um novo template."""
    return [
        {"nome_campo": "tag", "tipo_campo": "text", "label": "TAG", "obrigatorio": True, "auto_fill": True},
        {"nome_campo": "malha", "tipo_campo": "text", "label": "Malha", "obrigatorio": False, "auto_fill": True},
        {"nome_campo": "numero_linha", "tipo_campo": "text", "label": "Número da Linha", "obrigatorio": True, "auto_fill": True},
        {"nome_campo": "sop", "tipo_campo": "text", "label": "SOP", "obrigatorio": False, "auto_fill": True},
        {"nome_campo": "sub_sop", "tipo_campo": "text", "label": "Sub SOP", "obrigatorio": False, "auto_fill": True},
        {"nome_campo": "sth", "tipo_campo": "text", "label": "STH", "obrigatorio": False, "auto_fill": True},
        {"nome_campo": "pressao_teste", "tipo_campo": "number", "label": "Pressão de Teste (kgf/cm²)", "obrigatorio": True, "auto_fill": True},
        {"nome_campo": "descricao_sistema", "tipo_campo": "text", "label": "Descrição do Sistema", "obrigatorio": False, "auto_fill": True},
        {"nome_campo": "pressao_inicial", "tipo_campo": "number", "label": "Pressão Inicial", "obrigatorio": False, "auto_fill": False},
        {"nome_campo": "pressao_final", "tipo_campo": "number", "label": "Pressão Final", "obrigatorio": False, "auto_fill": False},
        {"nome_campo": "tempo_teste", "tipo_campo": "number", "label": "Tempo de Teste (min)", "obrigatorio": False, "auto_fill": False},
        {"nome_campo": "resultado", "tipo_campo": "select", "label": "Resultado", "obrigatorio": False, "auto_fill": False, "opcoes": ["Aprovado", "Reprovado", "Pendente"]},
        {"nome_campo": "observacoes", "tipo_campo": "textarea", "label": "Observações", "obrigatorio": False, "auto_fill": False},
    ]


def _validate_pdf(content: bytes, filename: str):
    """Valida que o conteúdo é um PDF válido e dentro do limite de tamanho."""
    if len(content) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo excede o tamanho máximo de {MAX_PDF_SIZE // (1024*1024)} MB.",
        )
    if not filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são permitidos.")
    # Check PDF magic bytes
    if not content[:5] == b'%PDF-':
        raise HTTPException(status_code=400, detail="O arquivo não é um PDF válido.")


def _check_nome_unique_per_tipo(db: Session, nome: str, tipo: str, exclude_id: Optional[int] = None):
    """Verifica unicidade do nome por tipo."""
    q = db.query(ModeloRelatorio).filter(
        ModeloRelatorio.nome == nome,
        ModeloRelatorio.tipo == tipo,
    )
    if exclude_id:
        q = q.filter(ModeloRelatorio.id != exclude_id)
    if q.first():
        raise HTTPException(
            status_code=409,
            detail=f"Já existe um template com o nome '{nome}' para o tipo '{tipo}'.",
        )


# ── Endpoints CRUD ─────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=ModeloResponse,
    status_code=201,
    summary="Upload de template PDF com metadados",
    description=(
        "Faz upload de um arquivo PDF de template com metadados (nome, tipo, descrição). "
        "O PDF é armazenado em uploads/templates/{tipo}/ e os metadados são salvos no banco. "
        "Apenas usuários com role Administrador podem criar templates."
    ),
)
async def create_template(
    nome: str = Form(..., description="Nome do template"),
    tipo: str = Form(..., description="Tipo: teste_hidrostatico, descarga_linha, flush_line, teste_estanqueidade, certificado_teste"),
    descricao: Optional[str] = Form(None, description="Descrição do template"),
    file: UploadFile = File(..., description="Arquivo PDF do template (máx. 50 MB)"),
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db),
):
    _validate_tipo(tipo)
    _check_nome_unique_per_tipo(db, nome, tipo)

    # Ler e validar PDF
    content = await file.read()
    _validate_pdf(content, file.filename)

    # Salvar arquivo
    upload_dir = os.path.join(settings.UPLOAD_DIR, "templates", tipo)
    os.makedirs(upload_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_name = file.filename.replace(" ", "_")
    filename = f"{timestamp}_{safe_name}"
    filepath = os.path.join(upload_dir, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    # Extrair campos do PDF
    campos = _extract_pdf_fields(filepath)
    campos_template_default = _get_default_campos_template()

    modelo = ModeloRelatorio(
        nome=nome,
        descricao=descricao,
        tipo=tipo,
        arquivo_pdf=filepath,
        caminho_template=filepath,  # compatibilidade
        campos=campos,
        campos_template=campos_template_default,
    )
    db.add(modelo)
    db.commit()
    db.refresh(modelo)
    logger.info(f"Template '{nome}' ({tipo}) criado por {current_user.email}")
    return _modelo_to_response(db, modelo)


@router.get(
    "/",
    response_model=List[ModeloResponse],
    summary="Listar todos os templates",
    description="Retorna todos os templates ativos. Opcionalmente filtra por tipo.",
)
def list_templates(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo de template"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(ModeloRelatorio).filter(ModeloRelatorio.ativo == True)
    if tipo:
        _validate_tipo(tipo)
        query = query.filter(ModeloRelatorio.tipo == tipo)
    modelos = query.order_by(ModeloRelatorio.criado_em.desc()).all()
    return [_modelo_to_response(db, m) for m in modelos]


@router.get(
    "/{template_id}",
    response_model=ModeloDetail,
    summary="Obter detalhes de um template",
    description="Retorna informações detalhadas do template incluindo configuração de campos.",
)
def get_template(
    template_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    modelo = _get_modelo_or_404(db, template_id)
    return _modelo_to_detail(db, modelo)


@router.put(
    "/{template_id}",
    response_model=ModeloResponse,
    summary="Atualizar metadados do template",
    description="Atualiza metadados (nome, descrição, tipo) do template. Não altera o PDF.",
)
def update_template(
    template_id: int,
    data: ModeloUpdate,
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db),
):
    modelo = _get_modelo_or_404(db, template_id)

    update_data = data.model_dump(exclude_unset=True)

    # Validar tipo se estiver sendo atualizado
    if "tipo" in update_data and update_data["tipo"]:
        _validate_tipo(update_data["tipo"])

    # Verificar unicidade do nome por tipo
    new_nome = update_data.get("nome", modelo.nome)
    new_tipo = update_data.get("tipo", modelo.tipo.value if hasattr(modelo.tipo, 'value') else str(modelo.tipo))
    if "nome" in update_data or "tipo" in update_data:
        _check_nome_unique_per_tipo(db, new_nome, new_tipo, exclude_id=template_id)

    # Tratar campos_template (converter CampoTemplate para dict)
    if "campos_template" in update_data and update_data["campos_template"] is not None:
        update_data["campos_template"] = [
            c.model_dump() if hasattr(c, 'model_dump') else c
            for c in update_data["campos_template"]
        ]

    for field, value in update_data.items():
        setattr(modelo, field, value)

    db.commit()
    db.refresh(modelo)
    logger.info(f"Template {template_id} atualizado por {current_user.email}")
    return _modelo_to_response(db, modelo)


@router.delete(
    "/{template_id}",
    summary="Excluir template",
    description=(
        "Exclui o template e remove o arquivo PDF. "
        "Não permite exclusão se o template estiver atribuído a alguma pasta de teste."
    ),
)
def delete_template(
    template_id: int,
    force: bool = Query(False, description="Forçar exclusão mesmo com pastas usando o template"),
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db),
):
    modelo = _get_modelo_or_404(db, template_id)

    # Verificar se está sendo usado por pastas
    pastas_count = _count_pastas_usando(db, template_id)
    if pastas_count > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Não é possível excluir: o template está atribuído a {pastas_count} pasta(s) de teste. "
                "Use force=true para forçar a exclusão (irá desassociar das pastas)."
            ),
        )

    # Se force, remover associações
    if pastas_count > 0 and force:
        db.query(PastaTeste_Teste).filter(PastaTeste_Teste.modelo_id == template_id).delete()

    # Remover arquivo PDF
    for path_attr in [modelo.arquivo_pdf, modelo.caminho_template]:
        if path_attr and os.path.exists(path_attr):
            try:
                os.remove(path_attr)
                logger.info(f"Arquivo removido: {path_attr}")
            except Exception as e:
                logger.warning(f"Erro ao remover arquivo {path_attr}: {e}")

    db.delete(modelo)
    db.commit()
    logger.info(f"Template {template_id} excluído por {current_user.email}")
    return {"message": "Template excluído com sucesso.", "id": template_id}


@router.get(
    "/{template_id}/download",
    summary="Download do template PDF",
    description="Faz download do arquivo PDF do template.",
)
def download_template(
    template_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    modelo = _get_modelo_or_404(db, template_id)
    pdf_path = modelo.arquivo_pdf or modelo.caminho_template
    if not pdf_path:
        raise HTTPException(status_code=404, detail="Este template não possui arquivo PDF.")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Arquivo do template não encontrado no servidor.")

    tipo_str = modelo.tipo.value if hasattr(modelo.tipo, 'value') else str(modelo.tipo)
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"{tipo_str}_{modelo.nome}.pdf",
    )


# ── Endpoints de configuração de campos ────────────────────────────────

@router.post(
    "/{template_id}/campos",
    response_model=ModeloDetail,
    summary="Configurar campos do template",
    description=(
        "Define a configuração de campos do template. "
        "Campos com auto_fill=true serão preenchidos automaticamente a partir dos dados da linha: "
        "tag, malha, numero_linha, sop, sub_sop, sth, pressao_teste, descricao_sistema."
    ),
)
def configure_campos(
    template_id: int,
    data: CamposTemplateRequest,
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db),
):
    modelo = _get_modelo_or_404(db, template_id)

    # Validar campos
    for campo in data.campos:
        if campo.tipo_campo not in ("text", "number", "date", "select", "textarea"):
            raise HTTPException(
                status_code=400,
                detail=f"tipo_campo inválido para '{campo.nome_campo}': '{campo.tipo_campo}'. "
                       f"Valores aceitos: text, number, date, select, textarea",
            )
        # Auto-fill validation
        if campo.auto_fill and campo.nome_campo not in AUTO_FILL_FIELDS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"O campo '{campo.nome_campo}' não pode ter auto_fill=true. "
                    f"Campos auto_fill suportados: {', '.join(AUTO_FILL_FIELDS)}"
                ),
            )

    modelo.campos_template = [c.model_dump() for c in data.campos]
    db.commit()
    db.refresh(modelo)
    logger.info(f"Campos do template {template_id} configurados por {current_user.email}")
    return _modelo_to_detail(db, modelo)


@router.get(
    "/{template_id}/campos",
    response_model=List[CampoTemplate],
    summary="Obter configuração de campos do template",
    description="Retorna a lista de campos configurados para o template.",
)
def get_campos(
    template_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    modelo = _get_modelo_or_404(db, template_id)
    raw = modelo.campos_template
    if not raw or not isinstance(raw, list):
        return []
    return [CampoTemplate(**c) for c in raw]
