"""Rotas de sincronização offline."""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import (
    PastaTeste, PastaLinha, DocumentoPasta, PastaTeste_Teste,
    Relatorio, LinhaTubulacao, ModeloRelatorio
)
from app.schemas.schemas import (
    SyncDownloadResponse, SyncUploadRequest, SyncStatusResponse,
    PastaResponse, DocumentoResponse, PastaTesteResponse,
    RelatorioResponse, RelatorioCreate, LinhaResponse, ModeloResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync", tags=["Sincronização Offline"])


@router.get("/pasta/{pasta_id}/download", response_model=SyncDownloadResponse)
def download_pasta_offline(
    pasta_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Baixar dados completos de uma pasta para uso offline."""
    pasta = db.query(PastaTeste).filter(PastaTeste.id == pasta_id).first()
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    # Linhas
    pasta_linhas = db.query(PastaLinha).filter(PastaLinha.pasta_id == pasta_id).all()
    linhas = []
    for pl in pasta_linhas:
        linha = db.query(LinhaTubulacao).filter(LinhaTubulacao.id == pl.linha_id).first()
        if linha:
            linhas.append(LinhaResponse.model_validate(linha))

    pasta_resp = PastaResponse(
        id=pasta.id, numero_pasta=pasta.numero_pasta, sth=pasta.sth,
        descricao_sistema=pasta.descricao_sistema, pressao_teste=pasta.pressao_teste,
        status=pasta.status, criado_em=pasta.criado_em, linhas=linhas,
        total_documentos=0, total_testes=0, total_relatorios=0,
    )

    # Documentos
    docs = db.query(DocumentoPasta).filter(DocumentoPasta.pasta_id == pasta_id).all()

    # Testes
    pts = db.query(PastaTeste_Teste).filter(PastaTeste_Teste.pasta_id == pasta_id).all()
    testes = []
    for pt in pts:
        modelo = db.query(ModeloRelatorio).filter(ModeloRelatorio.id == pt.modelo_id).first()
        testes.append(PastaTesteResponse(
            id=pt.id, pasta_id=pt.pasta_id, modelo_id=pt.modelo_id,
            ordem=pt.ordem, obrigatorio=pt.obrigatorio,
            modelo=ModeloResponse.model_validate(modelo) if modelo else None,
            criado_em=pt.criado_em,
        ))

    # Relatórios
    rels = db.query(Relatorio).filter(Relatorio.pasta_id == pasta_id).all()

    logger.info(f"Dados offline baixados para pasta {pasta_id} por {current_user.email}")
    return SyncDownloadResponse(
        pasta=pasta_resp,
        documentos=docs,
        testes=testes,
        relatorios=rels,
    )


@router.post("/upload")
def upload_offline_reports(
    data: SyncUploadRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload de relatórios criados offline."""
    created = 0
    updated = 0
    errors = []

    for rel_data in data.relatorios:
        try:
            # Verificar se já existe pelo offline_id
            existing = None
            if rel_data.offline_id:
                existing = db.query(Relatorio).filter(
                    Relatorio.offline_id == rel_data.offline_id
                ).first()

            if existing:
                # Atualizar existente (resolução de conflito: offline ganha)
                for field, value in rel_data.model_dump(exclude_unset=True, exclude={"pasta_id", "modelo_id"}).items():
                    setattr(existing, field, value)
                existing.sincronizado = True
                existing.sincronizado_em = datetime.utcnow()
                existing.status = "sincronizado"
                updated += 1
            else:
                # Auto-fill dados da linha
                dados_linha = {}
                if rel_data.linha_id:
                    linha = db.query(LinhaTubulacao).filter(LinhaTubulacao.id == rel_data.linha_id).first()
                    if linha:
                        dados_linha = {
                            "numero_linha": linha.numero_linha, "tag": linha.tag,
                            "malha": linha.malha, "sop": linha.sop, "sub_sop": linha.sub_sop,
                            "pressao_teste": linha.pressao_teste, "descricao_sistema": linha.descricao_sistema,
                        }

                rel = Relatorio(
                    pasta_id=rel_data.pasta_id,
                    modelo_id=rel_data.modelo_id,
                    linha_id=rel_data.linha_id,
                    usuario_id=current_user.id,
                    dados_linha=dados_linha,
                    dados_execucao=rel_data.dados_execucao,
                    pressao_inicial=rel_data.pressao_inicial,
                    pressao_final=rel_data.pressao_final,
                    tempo_teste=rel_data.tempo_teste,
                    resultado=rel_data.resultado,
                    observacoes=rel_data.observacoes,
                    status="sincronizado",
                    sincronizado=True,
                    sincronizado_em=datetime.utcnow(),
                    offline_id=rel_data.offline_id,
                )
                db.add(rel)
                created += 1

        except Exception as e:
            errors.append(f"Erro ao sincronizar relatório: {str(e)}")

    db.commit()
    logger.info(f"Sync upload: {created} criados, {updated} atualizados por {current_user.email}")
    return {
        "message": "Sincronização concluída.",
        "criados": created,
        "atualizados": updated,
        "erros": errors,
    }


@router.get("/status", response_model=SyncStatusResponse)
def sync_status(
    pasta_id: Optional[int] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Verificar status de sincronização."""
    query = db.query(Relatorio)
    if pasta_id:
        query = query.filter(Relatorio.pasta_id == pasta_id)

    total = query.count()
    sincronizados = query.filter(Relatorio.sincronizado == True).count()
    pendentes = total - sincronizados

    ultima = query.filter(
        Relatorio.sincronizado_em.isnot(None)
    ).order_by(Relatorio.sincronizado_em.desc()).first()

    return SyncStatusResponse(
        total_relatorios=total,
        sincronizados=sincronizados,
        pendentes=pendentes,
        ultima_sincronizacao=ultima.sincronizado_em if ultima else None,
    )
