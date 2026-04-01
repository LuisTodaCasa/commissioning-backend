"""
Rotas do módulo Execução de Testes (relatorios_execucao).

Gerencia relatórios de execução gerados automaticamente para cada combinação
(linha, template) em uma pasta de teste. Suporta preenchimento offline e
sincronização em lote.
"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.models import (
    RelatorioExecucao, PastaTeste, PastaLinha, LinhaTubulacao,
    ModeloRelatorio, PastaTeste_Teste, StatusExecucao
)
from app.schemas.schemas import (
    RelatorioExecucaoResponse, RelatorioExecucaoDetail,
    RelatorioExecucaoUpdate, RelatorioExecucaoStats,
    SincronizacaoExecucaoRequest, SincronizacaoLoteRequest,
    SincronizacaoLoteResponse, SincronizacaoLoteResultItem,
    GeracaoRelatoriosResponse,
    STATUS_EXECUCAO_VALIDOS, TRANSICOES_STATUS_EXECUCAO, AUTO_FILL_FIELDS
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/execucao", tags=["Execução de Testes"])


# ── Helpers ────────────────────────────────────────────────────────────

def _auto_fill_from_linha(linha: LinhaTubulacao) -> dict:
    """Gera dicionário auto_filled a partir dos dados da linha de tubulação."""
    return {
        "tag": linha.tag,
        "malha": linha.malha,
        "numero_linha": linha.numero_linha,
        "sop": linha.sop,
        "sub_sop": linha.sub_sop,
        "sth": linha.sth,
        "pressao_teste": linha.pressao_teste,
        "descricao_sistema": linha.descricao_sistema,
    }


def _validate_status_transition(current_status: str, new_status: str):
    """Valida transição de status. Levanta HTTPException se inválida."""
    if new_status not in STATUS_EXECUCAO_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Status inválido: '{new_status}'. Valores permitidos: {STATUS_EXECUCAO_VALIDOS}"
        )
    allowed = TRANSICOES_STATUS_EXECUCAO.get(current_status, [])
    if new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Transição de status não permitida: '{current_status}' → '{new_status}'. "
                   f"Transições permitidas a partir de '{current_status}': {allowed}"
        )


def _relatorio_to_detail(rel: RelatorioExecucao) -> dict:
    """Converte RelatorioExecucao ORM para dicionário detalhado com info aninhada."""
    pasta_info = None
    if rel.pasta:
        pasta_info = {
            "id": rel.pasta.id,
            "numero_pasta": rel.pasta.numero_pasta,
            "sth": rel.pasta.sth,
            "descricao_sistema": rel.pasta.descricao_sistema,
            "pressao_teste": rel.pasta.pressao_teste,
            "status": rel.pasta.status.value if hasattr(rel.pasta.status, 'value') else str(rel.pasta.status),
        }

    linha_info = None
    if rel.linha:
        linha_info = {
            "id": rel.linha.id,
            "numero_linha": rel.linha.numero_linha,
            "tag": rel.linha.tag,
            "malha": rel.linha.malha,
            "sop": rel.linha.sop,
            "sub_sop": rel.linha.sub_sop,
            "sth": rel.linha.sth,
            "pressao_teste": rel.linha.pressao_teste,
            "descricao_sistema": rel.linha.descricao_sistema,
        }

    template_info = None
    if rel.template:
        template_info = {
            "id": rel.template.id,
            "nome": rel.template.nome,
            "tipo": rel.template.tipo.value if hasattr(rel.template.tipo, 'value') else str(rel.template.tipo),
            "descricao": rel.template.descricao,
        }

    return {
        "id": rel.id,
        "pasta_id": rel.pasta_id,
        "linha_id": rel.linha_id,
        "template_id": rel.template_id,
        "dados_preenchidos": rel.dados_preenchidos,
        "status": rel.status.value if hasattr(rel.status, 'value') else str(rel.status),
        "data_execucao": rel.data_execucao,
        "usuario_execucao": rel.usuario_execucao,
        "data_sincronizacao": rel.data_sincronizacao,
        "created_at": rel.created_at,
        "updated_at": rel.updated_at,
        "pasta": pasta_info,
        "linha": linha_info,
        "template": template_info,
    }


def generate_reports_for_pasta(db: Session, pasta_id: int) -> GeracaoRelatoriosResponse:
    """
    Gera relatórios de execução para todas as combinações (linha, template) de uma pasta.
    Chamado quando templates são atribuídos a uma pasta.
    """
    pasta = db.query(PastaTeste).filter(PastaTeste.id == pasta_id).first()
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    # Buscar linhas da pasta
    pasta_linhas = db.query(PastaLinha).filter(PastaLinha.pasta_id == pasta_id).all()
    linhas = []
    for pl in pasta_linhas:
        linha = db.query(LinhaTubulacao).filter(LinhaTubulacao.id == pl.linha_id).first()
        if linha:
            linhas.append(linha)

    # Buscar templates atribuídos à pasta
    pasta_testes = db.query(PastaTeste_Teste).filter(PastaTeste_Teste.pasta_id == pasta_id).all()
    templates = []
    for pt in pasta_testes:
        tmpl = db.query(ModeloRelatorio).filter(ModeloRelatorio.id == pt.modelo_id).first()
        if tmpl:
            templates.append(tmpl)

    total_gerados = 0
    total_existentes = 0

    for linha in linhas:
        auto_filled = _auto_fill_from_linha(linha)
        for tmpl in templates:
            # Verificar se já existe
            existing = db.query(RelatorioExecucao).filter(
                RelatorioExecucao.pasta_id == pasta_id,
                RelatorioExecucao.linha_id == linha.id,
                RelatorioExecucao.template_id == tmpl.id,
            ).first()

            if existing:
                total_existentes += 1
                continue

            # Criar relatório
            rel = RelatorioExecucao(
                pasta_id=pasta_id,
                linha_id=linha.id,
                template_id=tmpl.id,
                dados_preenchidos={
                    "auto_filled": auto_filled,
                    "user_filled": {},
                },
                status=StatusExecucao.PENDENTE,
            )
            db.add(rel)
            total_gerados += 1

    db.commit()
    logger.info(
        f"Gerados {total_gerados} relatórios de execução para pasta {pasta_id} "
        f"({len(linhas)} linhas × {len(templates)} templates, {total_existentes} já existiam)"
    )

    return GeracaoRelatoriosResponse(
        mensagem=f"Relatórios de execução gerados com sucesso.",
        total_gerados=total_gerados,
        total_linhas=len(linhas),
        total_templates=len(templates),
        relatorios_existentes=total_existentes,
    )


# ── Endpoints CRUD ────────────────────────────────────────────────────

@router.get(
    "/relatorios",
    response_model=List[RelatorioExecucaoResponse],
    summary="Listar relatórios de execução",
    description="Lista relatórios de execução com filtros por pasta, status, template e usuário. Suporta paginação.",
)
def list_relatorios_execucao(
    skip: int = Query(0, ge=0, description="Número de registros a pular"),
    limit: int = Query(100, ge=1, le=500, description="Limite de registros"),
    pasta_id: Optional[int] = Query(None, description="Filtrar por pasta de teste"),
    status: Optional[str] = Query(None, description="Filtrar por status: pendente, em_execucao, concluido, reprovado"),
    template_id: Optional[int] = Query(None, description="Filtrar por template/modelo"),
    usuario_execucao: Optional[str] = Query(None, description="Filtrar por usuário de execução"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(RelatorioExecucao)

    if pasta_id is not None:
        query = query.filter(RelatorioExecucao.pasta_id == pasta_id)
    if status is not None:
        if status not in STATUS_EXECUCAO_VALIDOS:
            raise HTTPException(status_code=400, detail=f"Status inválido: {status}")
        query = query.filter(RelatorioExecucao.status == status)
    if template_id is not None:
        query = query.filter(RelatorioExecucao.template_id == template_id)
    if usuario_execucao is not None:
        query = query.filter(RelatorioExecucao.usuario_execucao.ilike(f"%{usuario_execucao}%"))

    return query.order_by(RelatorioExecucao.created_at.desc()).offset(skip).limit(limit).all()


@router.get(
    "/relatorios/{relatorio_id}",
    response_model=RelatorioExecucaoDetail,
    summary="Detalhes de um relatório de execução",
    description="Retorna o relatório com dados da pasta, linha e template associados.",
)
def get_relatorio_execucao(
    relatorio_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rel = db.query(RelatorioExecucao).filter(RelatorioExecucao.id == relatorio_id).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relatório de execução não encontrado.")
    return _relatorio_to_detail(rel)


@router.put(
    "/relatorios/{relatorio_id}",
    response_model=RelatorioExecucaoResponse,
    summary="Atualizar relatório de execução",
    description="Permite atualizar dados_preenchidos (merge com existentes) e status. "
                "Define data_execucao quando status muda para concluido ou reprovado.",
)
def update_relatorio_execucao(
    relatorio_id: int,
    data: RelatorioExecucaoUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rel = db.query(RelatorioExecucao).filter(RelatorioExecucao.id == relatorio_id).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relatório de execução não encontrado.")

    current_status = rel.status.value if hasattr(rel.status, 'value') else str(rel.status)

    # Permissões por role
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
    if user_role == "Campo":
        # Campo pode atualizar dados_preenchidos e status (pendente → em_execucao, em_execucao → concluido)
        pass
    elif user_role in ("Comissionamento", "CQ"):
        # Pode ver e atualizar status
        pass
    elif user_role in ("Administrador", "Engenharia"):
        # Acesso total
        pass
    else:
        raise HTTPException(status_code=403, detail="Sem permissão para atualizar relatórios.")

    # Atualizar dados_preenchidos (merge)
    if data.dados_preenchidos is not None:
        existing = rel.dados_preenchidos or {"auto_filled": {}, "user_filled": {}}
        # Se enviou user_filled, faz merge
        if "user_filled" in data.dados_preenchidos:
            existing_user = existing.get("user_filled", {})
            existing_user.update(data.dados_preenchidos["user_filled"])
            existing["user_filled"] = existing_user
        # Se enviou auto_filled, faz merge (raro, mas suportado)
        if "auto_filled" in data.dados_preenchidos:
            existing_auto = existing.get("auto_filled", {})
            existing_auto.update(data.dados_preenchidos["auto_filled"])
            existing["auto_filled"] = existing_auto
        # Se enviou campos soltos (atalho), coloca em user_filled
        for key, value in data.dados_preenchidos.items():
            if key not in ("auto_filled", "user_filled"):
                existing.setdefault("user_filled", {})[key] = value
        rel.dados_preenchidos = existing
        flag_modified(rel, "dados_preenchidos")

    # Atualizar status com validação de transição
    if data.status is not None:
        _validate_status_transition(current_status, data.status)
        rel.status = data.status
        # Definir data_execucao quando finalizado
        if data.status in ("concluido", "reprovado"):
            rel.data_execucao = datetime.utcnow()
        rel.usuario_execucao = current_user.nome if hasattr(current_user, 'nome') else str(current_user.email)

    db.commit()
    db.refresh(rel)
    logger.info(f"Relatório execução {relatorio_id} atualizado por {current_user.email}")
    return rel


# ── Endpoints por Pasta ───────────────────────────────────────────────

@router.get(
    "/pastas/{pasta_id}/relatorios",
    summary="Relatórios de execução de uma pasta",
    description="Retorna todos os relatórios de execução de uma pasta, agrupados por template, com estatísticas de conclusão.",
)
def get_relatorios_pasta(
    pasta_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pasta = db.query(PastaTeste).filter(PastaTeste.id == pasta_id).first()
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    relatorios = db.query(RelatorioExecucao).filter(
        RelatorioExecucao.pasta_id == pasta_id
    ).all()

    # Agrupar por template
    by_template = {}
    for rel in relatorios:
        tid = rel.template_id
        if tid not in by_template:
            tmpl = rel.template
            by_template[tid] = {
                "template_id": tid,
                "template_nome": tmpl.nome if tmpl else "Desconhecido",
                "template_tipo": (tmpl.tipo.value if tmpl and hasattr(tmpl.tipo, 'value') else str(tmpl.tipo)) if tmpl else None,
                "relatorios": [],
                "total": 0,
                "concluidos": 0,
                "em_execucao": 0,
                "pendentes": 0,
                "reprovados": 0,
            }
        status_val = rel.status.value if hasattr(rel.status, 'value') else str(rel.status)
        by_template[tid]["relatorios"].append(
            RelatorioExecucaoResponse.model_validate(rel).model_dump()
        )
        by_template[tid]["total"] += 1
        if status_val == "concluido":
            by_template[tid]["concluidos"] += 1
        elif status_val == "em_execucao":
            by_template[tid]["em_execucao"] += 1
        elif status_val == "pendente":
            by_template[tid]["pendentes"] += 1
        elif status_val == "reprovado":
            by_template[tid]["reprovados"] += 1

    total = len(relatorios)
    concluidos = sum(g["concluidos"] for g in by_template.values())

    return {
        "pasta_id": pasta_id,
        "total_relatorios": total,
        "concluidos": concluidos,
        "percentual_conclusao": round((concluidos / total * 100) if total > 0 else 0, 2),
        "grupos": list(by_template.values()),
    }


@router.get(
    "/pastas/{pasta_id}/relatorios/stats",
    response_model=RelatorioExecucaoStats,
    summary="Estatísticas de relatórios de execução de uma pasta",
    description="Retorna estatísticas: total, por status, percentual de conclusão, por template e última sincronização.",
)
def get_relatorios_stats(
    pasta_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pasta = db.query(PastaTeste).filter(PastaTeste.id == pasta_id).first()
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    relatorios = db.query(RelatorioExecucao).filter(
        RelatorioExecucao.pasta_id == pasta_id
    ).all()

    total = len(relatorios)
    por_status = {}
    por_template_map = {}
    ultima_sync = None

    for rel in relatorios:
        status_val = rel.status.value if hasattr(rel.status, 'value') else str(rel.status)
        por_status[status_val] = por_status.get(status_val, 0) + 1

        tid = rel.template_id
        if tid not in por_template_map:
            tmpl = rel.template
            por_template_map[tid] = {
                "template_id": tid,
                "template_nome": tmpl.nome if tmpl else "Desconhecido",
                "total": 0,
                "concluidos": 0,
            }
        por_template_map[tid]["total"] += 1
        if status_val == "concluido":
            por_template_map[tid]["concluidos"] += 1

        if rel.data_sincronizacao:
            if ultima_sync is None or rel.data_sincronizacao > ultima_sync:
                ultima_sync = rel.data_sincronizacao

    concluidos = por_status.get("concluido", 0)
    percentual = round((concluidos / total * 100) if total > 0 else 0, 2)

    return RelatorioExecucaoStats(
        total_relatorios=total,
        por_status=por_status,
        percentual_conclusao=percentual,
        por_template=list(por_template_map.values()),
        ultima_sincronizacao=ultima_sync,
    )


# ── Sincronização ─────────────────────────────────────────────────────

@router.post(
    "/relatorios/{relatorio_id}/sincronizar",
    response_model=RelatorioExecucaoResponse,
    summary="Sincronizar relatório de execução",
    description="Marca o relatório como sincronizado. Opcionalmente atualiza dados_preenchidos e status.",
)
def sincronizar_relatorio(
    relatorio_id: int,
    data: SincronizacaoExecucaoRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rel = db.query(RelatorioExecucao).filter(RelatorioExecucao.id == relatorio_id).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relatório de execução não encontrado.")

    # Atualizar dados_preenchidos se fornecido
    if data.dados_preenchidos is not None:
        existing = rel.dados_preenchidos or {"auto_filled": {}, "user_filled": {}}
        if "user_filled" in data.dados_preenchidos:
            existing_user = existing.get("user_filled", {})
            existing_user.update(data.dados_preenchidos["user_filled"])
            existing["user_filled"] = existing_user
        if "auto_filled" in data.dados_preenchidos:
            existing_auto = existing.get("auto_filled", {})
            existing_auto.update(data.dados_preenchidos["auto_filled"])
            existing["auto_filled"] = existing_auto
        for key, value in data.dados_preenchidos.items():
            if key not in ("auto_filled", "user_filled"):
                existing.setdefault("user_filled", {})[key] = value
        rel.dados_preenchidos = existing
        flag_modified(rel, "dados_preenchidos")

    # Atualizar status se fornecido
    if data.status is not None:
        current_status = rel.status.value if hasattr(rel.status, 'value') else str(rel.status)
        _validate_status_transition(current_status, data.status)
        rel.status = data.status
        if data.status in ("concluido", "reprovado"):
            rel.data_execucao = datetime.utcnow()
        rel.usuario_execucao = current_user.nome if hasattr(current_user, 'nome') else str(current_user.email)

    # Marcar como sincronizado
    rel.data_sincronizacao = datetime.utcnow()

    db.commit()
    db.refresh(rel)
    logger.info(f"Relatório execução {relatorio_id} sincronizado por {current_user.email}")
    return rel


@router.post(
    "/relatorios/sincronizar-lote",
    response_model=SincronizacaoLoteResponse,
    summary="Sincronização em lote de relatórios de execução",
    description="Sincroniza múltiplos relatórios em uma única transação. Retorna resultado individual para cada relatório.",
)
def sincronizar_lote(
    data: SincronizacaoLoteRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resultados = []
    sucesso_count = 0
    falha_count = 0

    for item in data.relatorios:
        try:
            rel = db.query(RelatorioExecucao).filter(
                RelatorioExecucao.id == item.relatorio_id
            ).first()

            if not rel:
                resultados.append(SincronizacaoLoteResultItem(
                    relatorio_id=item.relatorio_id,
                    sucesso=False,
                    mensagem=f"Relatório {item.relatorio_id} não encontrado.",
                ))
                falha_count += 1
                continue

            # Atualizar dados_preenchidos
            if item.dados_preenchidos is not None:
                existing = rel.dados_preenchidos or {"auto_filled": {}, "user_filled": {}}
                if "user_filled" in item.dados_preenchidos:
                    existing_user = existing.get("user_filled", {})
                    existing_user.update(item.dados_preenchidos["user_filled"])
                    existing["user_filled"] = existing_user
                if "auto_filled" in item.dados_preenchidos:
                    existing_auto = existing.get("auto_filled", {})
                    existing_auto.update(item.dados_preenchidos["auto_filled"])
                    existing["auto_filled"] = existing_auto
                for key, value in item.dados_preenchidos.items():
                    if key not in ("auto_filled", "user_filled"):
                        existing.setdefault("user_filled", {})[key] = value
                rel.dados_preenchidos = existing
                flag_modified(rel, "dados_preenchidos")

            # Atualizar status
            if item.status is not None:
                current_status = rel.status.value if hasattr(rel.status, 'value') else str(rel.status)
                if item.status not in STATUS_EXECUCAO_VALIDOS:
                    raise ValueError(f"Status inválido: {item.status}")
                allowed = TRANSICOES_STATUS_EXECUCAO.get(current_status, [])
                if item.status not in allowed:
                    raise ValueError(
                        f"Transição não permitida: '{current_status}' → '{item.status}'"
                    )
                rel.status = item.status
                if item.status in ("concluido", "reprovado"):
                    rel.data_execucao = datetime.utcnow()
                rel.usuario_execucao = current_user.nome if hasattr(current_user, 'nome') else str(current_user.email)

            rel.data_sincronizacao = datetime.utcnow()
            sucesso_count += 1
            resultados.append(SincronizacaoLoteResultItem(
                relatorio_id=item.relatorio_id,
                sucesso=True,
                mensagem="Sincronizado com sucesso.",
            ))

        except ValueError as e:
            resultados.append(SincronizacaoLoteResultItem(
                relatorio_id=item.relatorio_id,
                sucesso=False,
                mensagem=str(e),
            ))
            falha_count += 1
        except Exception as e:
            resultados.append(SincronizacaoLoteResultItem(
                relatorio_id=item.relatorio_id,
                sucesso=False,
                mensagem=f"Erro interno: {str(e)}",
            ))
            falha_count += 1

    db.commit()
    logger.info(
        f"Sincronização em lote: {sucesso_count} sucesso, {falha_count} falhas "
        f"por {current_user.email}"
    )

    return SincronizacaoLoteResponse(
        total=len(data.relatorios),
        sucesso=sucesso_count,
        falhas=falha_count,
        resultados=resultados,
    )


# ── Geração Manual ────────────────────────────────────────────────────

@router.post(
    "/pastas/{pasta_id}/gerar-relatorios",
    response_model=GeracaoRelatoriosResponse,
    summary="Gerar relatórios de execução para uma pasta",
    description="Gera relatórios para todas as combinações (linha, template) que ainda não existem na pasta.",
)
def gerar_relatorios_pasta(
    pasta_id: int,
    current_user=Depends(require_roles(["Administrador", "Comissionamento", "Engenharia"])),
    db: Session = Depends(get_db),
):
    return generate_reports_for_pasta(db, pasta_id)