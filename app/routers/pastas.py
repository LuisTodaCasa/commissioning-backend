"""Rotas de pastas de teste (CRUD, associação de linhas, documentos e testes)."""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.models import (
    PastaTeste, PastaLinha, LinhaTubulacao, DocumentoPasta,
    PastaTeste_Teste, Relatorio, StatusPasta, ModeloRelatorio, STH, Spool
)
from app.schemas.schemas import (
    PastaCreate, PastaUpdate, PastaResponse, PastaListResponse,
    PastaLinhaAssign, LinhaResponse, PastaTesteDetail,
    DocumentoResponse, PastaTesteResponse, ModeloResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pastas", tags=["Pastas de Teste"])


# ── Helpers ────────────────────────────────────────────────────────────

def _build_download_url(doc: DocumentoPasta) -> str:
    """Gerar URL de download para um documento."""
    return f"/api/v1/documentos/{doc.id}/download"


def _pasta_to_list_response(pasta: PastaTeste, db: Session) -> PastaListResponse:
    """Converter pasta para resposta de listagem com contagens."""
    return PastaListResponse(
        id=pasta.id,
        numero_pasta=pasta.numero_pasta,
        sth=pasta.sth,
        descricao_sistema=pasta.descricao_sistema,
        pressao_teste=pasta.pressao_teste,
        status=pasta.status.value if hasattr(pasta.status, 'value') else str(pasta.status),
        data_criacao=pasta.data_criacao,
        total_linhas=db.query(PastaLinha).filter(PastaLinha.pasta_id == pasta.id).count(),
        total_documentos=db.query(DocumentoPasta).filter(DocumentoPasta.pasta_id == pasta.id).count(),
        total_testes=db.query(PastaTeste_Teste).filter(PastaTeste_Teste.pasta_id == pasta.id).count(),
        total_relatorios=db.query(Relatorio).filter(Relatorio.pasta_id == pasta.id).count(),
        criado_em=pasta.criado_em,
    )


def _validate_status(status_value: str) -> str:
    """Validar que o status é um valor permitido."""
    valid = [s.value for s in StatusPasta]
    if status_value not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Status inválido: '{status_value}'. Valores permitidos: {', '.join(valid)}"
        )
    return status_value


def _get_pasta_or_404(pasta_id: int, db: Session) -> PastaTeste:
    """Buscar pasta por ID ou retornar 404."""
    pasta = db.query(PastaTeste).filter(PastaTeste.id == pasta_id).first()
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")
    return pasta


# ── CRUD de Pastas ─────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=List[PastaListResponse],
    summary="Listar pastas de teste",
    description="Retorna lista de pastas com filtros opcionais por status, STH e busca textual."
)
def list_pastas(
    skip: int = Query(0, ge=0, description="Registros a pular (paginação)"),
    limit: int = Query(100, ge=1, le=500, description="Limite de registros"),
    search: Optional[str] = Query(None, description="Busca por número, STH ou descrição"),
    status: Optional[str] = Query(None, description="Filtrar por status (CRIADA, EM_ANDAMENTO, CONCLUIDA, CANCELADA)"),
    sth: Optional[str] = Query(None, description="Filtrar por STH"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Listar pastas de teste com filtros."""
    query = db.query(PastaTeste)

    if search:
        query = query.filter(
            PastaTeste.numero_pasta.ilike(f"%{search}%") |
            PastaTeste.sth.ilike(f"%{search}%") |
            PastaTeste.descricao_sistema.ilike(f"%{search}%")
        )
    if status:
        _validate_status(status)
        query = query.filter(PastaTeste.status == status)
    if sth:
        query = query.filter(PastaTeste.sth.ilike(f"%{sth}%"))

    pastas = query.order_by(PastaTeste.numero_pasta).offset(skip).limit(limit).all()
    return [_pasta_to_list_response(p, db) for p in pastas]


@router.get(
    "/{pasta_id}",
    response_model=PastaTesteDetail,
    summary="Obter detalhes completos de uma pasta",
    description="Retorna a pasta com todas as linhas, documentos e testes associados."
)
def get_pasta(
    pasta_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Obter detalhes completos de uma pasta de teste (linhas, documentos, testes)."""
    pasta = _get_pasta_or_404(pasta_id, db)

    # Linhas associadas - retornar linhas do STH, não apenas as vinculadas à pasta
    linhas = []
    if pasta.sth_id:
        sth = db.query(STH).filter(STH.id == pasta.sth_id).first()
        if sth:
            linhas = [
                LinhaResponse.model_validate(sth_linha.linha_cat)
                for sth_linha in sth.sth_linhas if sth_linha.linha_cat
            ]
    else:
        # Fallback: retornar linhas explicitamente vinculadas
        linhas = [
            LinhaResponse.model_validate(pl.linha)
            for pl in pasta.linhas if pl.linha
        ]

    # Documentos com URL de download
    documentos = [
        DocumentoResponse(
            id=doc.id,
            pasta_id=doc.pasta_id,
            tipo=doc.tipo.value if hasattr(doc.tipo, 'value') else str(doc.tipo),
            nome_arquivo=doc.nome_arquivo,
            tamanho_bytes=doc.tamanho_bytes,
            download_url=_build_download_url(doc),
            criado_em=doc.criado_em,
        )
        for doc in pasta.documentos
    ]

    # Testes/templates associados
    testes = [
        PastaTesteResponse(
            id=pt.id,
            pasta_id=pt.pasta_id,
            modelo_id=pt.modelo_id,
            ordem=pt.ordem,
            obrigatorio=pt.obrigatorio,
            modelo=ModeloResponse.model_validate(pt.modelo) if pt.modelo else None,
            criado_em=pt.criado_em,
        )
        for pt in sorted(pasta.testes, key=lambda x: x.ordem)
    ]

    # Spools do STH associado
    spools = []
    if pasta.sth_id:
        sth = db.query(STH).filter(STH.id == pasta.sth_id).first()
        if sth:
            spools = [
                {
                    'id': s.id,
                    'codigo_spool': s.codigo_spool,
                    'origem': s.origem,
                    'destino': s.destino,
                    'isometrico_ref': s.isometrico_ref,
                    'linha_id': s.linha_id,
                    'numero_linha': s.linha_cat.numero_linha if s.linha_cat else None,
                }
                for s in sth.spools
            ]

    # Derivar disciplina a partir do SOP (Tubulação se tem SOP, senão vazio)
    disciplina = None
    if pasta.sth_id:
        sth = db.query(STH).filter(STH.id == pasta.sth_id).first()
        if sth and sth.sop:
            disciplina = "Tubulação"  # SOPs estão associados à Tubulação

    total_relatorios = db.query(Relatorio).filter(Relatorio.pasta_id == pasta_id).count()

    return PastaTesteDetail(
        id=pasta.id,
        numero_pasta=pasta.numero_pasta,
        sth=pasta.sth,
        sth_id=pasta.sth_id,
        descricao_sistema=pasta.descricao_sistema,
        pressao_teste=pasta.pressao_teste,
        disciplina=disciplina,
        status=pasta.status.value if hasattr(pasta.status, 'value') else str(pasta.status),
        data_criacao=pasta.data_criacao,
        criado_em=pasta.criado_em,
        atualizado_em=pasta.atualizado_em,
        linhas=linhas,
        documentos=documentos,
        testes=testes,
        spools=spools,
        total_relatorios=total_relatorios,
    )


@router.post(
    "/",
    response_model=PastaListResponse,
    status_code=201,
    summary="Criar pasta de teste",
    description="Cria nova pasta. Apenas Administrador, Comissionamento e Engenharia."
)
def create_pasta(
    data: PastaCreate,
    current_user=Depends(require_roles(["Administrador", "Comissionamento", "Engenharia"])),
    db: Session = Depends(get_db)
):
    """Criar nova pasta de teste."""
    # Validar unicidade do numero_pasta
    existing = db.query(PastaTeste).filter(PastaTeste.numero_pasta == data.numero_pasta).first()
    if existing:
        raise HTTPException(status_code=400, detail="Já existe uma pasta com este número.")

    pasta = PastaTeste(
        numero_pasta=data.numero_pasta,
        sth=data.sth,
        descricao_sistema=data.descricao_sistema,
        pressao_teste=data.pressao_teste,
        data_criacao=data.data_criacao,
        criado_por_id=current_user.id,
    )
    db.add(pasta)
    db.commit()
    db.refresh(pasta)
    logger.info(f"Pasta {pasta.numero_pasta} criada por {current_user.email}")
    return _pasta_to_list_response(pasta, db)


@router.put(
    "/{pasta_id}",
    response_model=PastaListResponse,
    summary="Atualizar pasta de teste",
    description="Atualiza dados da pasta. Apenas Administrador, Comissionamento e Engenharia."
)
def update_pasta(
    pasta_id: int,
    data: PastaUpdate,
    current_user=Depends(require_roles(["Administrador", "Comissionamento", "Engenharia"])),
    db: Session = Depends(get_db)
):
    """Atualizar uma pasta de teste existente."""
    pasta = _get_pasta_or_404(pasta_id, db)

    update_data = data.model_dump(exclude_unset=True)

    # Validar unicidade do numero_pasta se estiver sendo alterado
    if "numero_pasta" in update_data and update_data["numero_pasta"] != pasta.numero_pasta:
        existing = db.query(PastaTeste).filter(
            PastaTeste.numero_pasta == update_data["numero_pasta"],
            PastaTeste.id != pasta_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Já existe outra pasta com este número.")

    # Validar status se estiver sendo alterado
    if "status" in update_data:
        _validate_status(update_data["status"])

    for field, value in update_data.items():
        setattr(pasta, field, value)

    db.commit()
    db.refresh(pasta)
    logger.info(f"Pasta {pasta_id} atualizada por {current_user.email}")
    return _pasta_to_list_response(pasta, db)


@router.delete(
    "/{pasta_id}",
    summary="Excluir pasta de teste",
    description="Exclui a pasta e todas as associações. Apenas Administrador."
)
def delete_pasta(
    pasta_id: int,
    current_user=Depends(require_roles(["Administrador"])),
    db: Session = Depends(get_db)
):
    """Excluir uma pasta de teste (cascade: linhas, documentos, testes, relatórios)."""
    pasta = _get_pasta_or_404(pasta_id, db)
    numero = pasta.numero_pasta
    db.delete(pasta)
    db.commit()
    logger.info(f"Pasta {numero} removida por {current_user.email}")
    return {"message": f"Pasta {numero} removida com sucesso."}


# ── Linhas da Pasta ────────────────────────────────────────────────────

@router.post(
    "/{pasta_id}/linhas",
    summary="Atribuir linhas à pasta",
    description="Atribui múltiplas linhas de tubulação a uma pasta. Substitui atribuições anteriores."
)
def assign_linhas(
    pasta_id: int,
    data: PastaLinhaAssign,
    current_user=Depends(require_roles(["Administrador", "Comissionamento", "Engenharia"])),
    db: Session = Depends(get_db)
):
    """Atribuir linhas de tubulação a uma pasta de teste."""
    pasta = _get_pasta_or_404(pasta_id, db)

    # Validar que todas as linhas existem
    not_found = []
    for linha_id in data.linha_ids:
        exists = db.query(LinhaTubulacao).filter(LinhaTubulacao.id == linha_id).first()
        if not exists:
            not_found.append(linha_id)
    if not_found:
        raise HTTPException(
            status_code=404,
            detail=f"Linhas não encontradas: {not_found}"
        )

    # Remover duplicatas na lista de entrada
    unique_ids = list(dict.fromkeys(data.linha_ids))

    # Remover associações existentes
    db.query(PastaLinha).filter(PastaLinha.pasta_id == pasta_id).delete()

    # Criar novas associações
    for linha_id in unique_ids:
        db.add(PastaLinha(pasta_id=pasta_id, linha_id=linha_id))

    db.commit()

    # Gerar relatórios de execução para templates existentes na pasta
    relatorios_gerados = 0
    existing_templates = db.query(PastaTeste_Teste).filter(
        PastaTeste_Teste.pasta_id == pasta_id
    ).count()
    if existing_templates > 0:
        from app.routers.execucao import generate_reports_for_pasta
        gen_result = generate_reports_for_pasta(db, pasta_id)
        relatorios_gerados = gen_result.total_gerados

    logger.info(f"Linhas atribuídas à pasta {pasta_id}: {unique_ids}")
    return {
        "message": "Linhas atribuídas com sucesso.",
        "pasta_id": pasta_id,
        "linha_ids": unique_ids,
        "total": len(unique_ids),
        "relatorios_gerados": relatorios_gerados,
    }


@router.get(
    "/{pasta_id}/linhas",
    response_model=List[LinhaResponse],
    summary="Listar linhas da pasta",
    description="Retorna todas as linhas de tubulação associadas à pasta."
)
def get_pasta_linhas(
    pasta_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Listar linhas associadas a uma pasta."""
    _get_pasta_or_404(pasta_id, db)

    pasta_linhas = (
        db.query(PastaLinha)
        .filter(PastaLinha.pasta_id == pasta_id)
        .all()
    )
    return [pl.linha for pl in pasta_linhas if pl.linha]


@router.delete(
    "/{pasta_id}/linhas/{linha_id}",
    summary="Remover linha da pasta",
    description="Remove uma linha específica da pasta de teste."
)
def remove_linha_from_pasta(
    pasta_id: int,
    linha_id: int,
    current_user=Depends(require_roles(["Administrador", "Comissionamento", "Engenharia"])),
    db: Session = Depends(get_db)
):
    """Remover uma linha de uma pasta de teste."""
    _get_pasta_or_404(pasta_id, db)

    pasta_linha = db.query(PastaLinha).filter(
        PastaLinha.pasta_id == pasta_id,
        PastaLinha.linha_id == linha_id,
    ).first()

    if not pasta_linha:
        raise HTTPException(
            status_code=404,
            detail=f"Linha {linha_id} não está associada à pasta {pasta_id}."
        )

    db.delete(pasta_linha)
    db.commit()
    logger.info(f"Linha {linha_id} removida da pasta {pasta_id}")
    return {"message": f"Linha {linha_id} removida da pasta com sucesso."}


# ── Documentos da Pasta (atalhos) ─────────────────────────────────────

@router.post(
    "/{pasta_id}/documentos",
    summary="Upload de documento PDF",
    description="Redireciona para endpoint de upload de documentos. Use POST /api/v1/documentos/pasta/{pasta_id}."
)
def pasta_upload_doc_redirect(pasta_id: int):
    """Atalho: use POST /api/v1/documentos/pasta/{pasta_id} para upload."""
    raise HTTPException(
        status_code=307,
        detail="Use POST /api/v1/documentos/pasta/{pasta_id}",
        headers={"Location": f"/api/v1/documentos/pasta/{pasta_id}"}
    )


@router.get(
    "/{pasta_id}/documentos",
    response_model=List[DocumentoResponse],
    summary="Listar documentos da pasta",
    description="Retorna todos os documentos PDF associados à pasta."
)
def get_pasta_documentos(
    pasta_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Listar documentos de uma pasta."""
    _get_pasta_or_404(pasta_id, db)
    docs = db.query(DocumentoPasta).filter(DocumentoPasta.pasta_id == pasta_id).all()
    return [
        DocumentoResponse(
            id=doc.id,
            pasta_id=doc.pasta_id,
            tipo=doc.tipo.value if hasattr(doc.tipo, 'value') else str(doc.tipo),
            nome_arquivo=doc.nome_arquivo,
            tamanho_bytes=doc.tamanho_bytes,
            download_url=_build_download_url(doc),
            criado_em=doc.criado_em,
        )
        for doc in docs
    ]


@router.delete(
    "/{pasta_id}/documentos/{doc_id}",
    summary="Excluir documento da pasta",
    description="Remove documento da pasta. Use DELETE /api/v1/documentos/{doc_id}."
)
def pasta_delete_doc_redirect(pasta_id: int, doc_id: int):
    """Atalho: use DELETE /api/v1/documentos/{doc_id}."""
    raise HTTPException(
        status_code=307,
        detail="Use DELETE /api/v1/documentos/{doc_id}",
        headers={"Location": f"/api/v1/documentos/{doc_id}"}
    )


# ── Testes/Templates da Pasta (atalhos) ───────────────────────────────

@router.post(
    "/{pasta_id}/testes",
    summary="Atribuir templates à pasta",
    description="Redireciona para POST /api/v1/testes/pasta/{pasta_id}."
)
def pasta_assign_testes_redirect(pasta_id: int):
    """Atalho: use POST /api/v1/testes/pasta/{pasta_id}."""
    raise HTTPException(
        status_code=307,
        detail="Use POST /api/v1/testes/pasta/{pasta_id}",
        headers={"Location": f"/api/v1/testes/pasta/{pasta_id}"}
    )


@router.get(
    "/{pasta_id}/testes",
    response_model=List[PastaTesteResponse],
    summary="Listar testes da pasta",
    description="Retorna todos os testes/templates atribuídos à pasta."
)
def get_pasta_testes(
    pasta_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Listar testes atribuídos a uma pasta."""
    _get_pasta_or_404(pasta_id, db)

    pts = (
        db.query(PastaTeste_Teste)
        .filter(PastaTeste_Teste.pasta_id == pasta_id)
        .order_by(PastaTeste_Teste.ordem)
        .all()
    )
    return [
        PastaTesteResponse(
            id=pt.id,
            pasta_id=pt.pasta_id,
            modelo_id=pt.modelo_id,
            ordem=pt.ordem,
            obrigatorio=pt.obrigatorio,
            modelo=ModeloResponse.model_validate(pt.modelo) if pt.modelo else None,
            criado_em=pt.criado_em,
        )
        for pt in pts
    ]


@router.delete(
    "/{pasta_id}/testes/{template_id}",
    summary="Remover template da pasta",
    description="Remove um template/teste específico da pasta."
)
def remove_teste_from_pasta(
    pasta_id: int,
    template_id: int,
    current_user=Depends(require_roles(["Administrador", "Comissionamento"])),
    db: Session = Depends(get_db)
):
    """Remover um teste/template de uma pasta."""
    _get_pasta_or_404(pasta_id, db)

    pt = db.query(PastaTeste_Teste).filter(
        PastaTeste_Teste.pasta_id == pasta_id,
        PastaTeste_Teste.modelo_id == template_id,
    ).first()

    if not pt:
        raise HTTPException(
            status_code=404,
            detail=f"Template {template_id} não está atribuído à pasta {pasta_id}."
        )

    db.delete(pt)
    db.commit()
    logger.info(f"Template {template_id} removido da pasta {pasta_id}")
    return {"message": f"Template {template_id} removido da pasta com sucesso."}
