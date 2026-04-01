"""Rotas de linhas de tubulação e importação Excel."""
import logging
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.models import LinhaTubulacao
from app.schemas.schemas import LinhaResponse, LinhaCreate, ImportResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/linhas", tags=["Linhas de Tubulação"])


@router.get("/", response_model=List[LinhaResponse])
def list_linhas(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    sth: Optional[str] = None,
    sistema: Optional[str] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Listar linhas de tubulação com filtros."""
    query = db.query(LinhaTubulacao)
    if search:
        query = query.filter(
            or_(
                LinhaTubulacao.numero_linha.ilike(f"%{search}%"),
                LinhaTubulacao.tag.ilike(f"%{search}%"),
                LinhaTubulacao.malha.ilike(f"%{search}%"),
                LinhaTubulacao.descricao_sistema.ilike(f"%{search}%"),
            )
        )
    if sth:
        query = query.filter(LinhaTubulacao.sth.ilike(f"%{sth}%"))
    if sistema:
        query = query.filter(LinhaTubulacao.sistema.ilike(f"%{sistema}%"))

    return query.order_by(LinhaTubulacao.numero_linha).offset(skip).limit(limit).all()


@router.get("/count")
def count_linhas(
    search: Optional[str] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(LinhaTubulacao)
    if search:
        query = query.filter(
            or_(
                LinhaTubulacao.numero_linha.ilike(f"%{search}%"),
                LinhaTubulacao.tag.ilike(f"%{search}%"),
            )
        )
    return {"total": query.count()}


@router.get("/{linha_id}", response_model=LinhaResponse)
def get_linha(
    linha_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    linha = db.query(LinhaTubulacao).filter(LinhaTubulacao.id == linha_id).first()
    if not linha:
        raise HTTPException(status_code=404, detail="Linha não encontrada.")
    return linha


@router.post("/", response_model=LinhaResponse, status_code=201)
def create_linha(
    data: LinhaCreate,
    current_user=Depends(require_roles(["Administrador", "Engenharia"])),
    db: Session = Depends(get_db)
):
    """Criar linha de tubulação manualmente."""
    linha = LinhaTubulacao(**data.model_dump())
    db.add(linha)
    db.commit()
    db.refresh(linha)
    return linha


@router.post("/import-excel", response_model=ImportResult)
async def import_excel(
    file: UploadFile = File(...),
    current_user=Depends(require_roles(["Administrador", "Engenharia"])),
    db: Session = Depends(get_db)
):
    """
    Importar linhas de tubulação a partir de arquivo Excel (.xlsx / .xls).

    Utiliza pandas para leitura. Valida todas as 9 colunas obrigatórias,
    verifica tipos de dados, trata duplicatas e retorna resumo detalhado.
    """
    # ── 1. Validar formato do arquivo ──────────────────────────────────
    if not file.filename or not file.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Formato inválido. Envie um arquivo .xlsx ou .xls"
        )

    try:
        import pandas as pd

        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Arquivo vazio.")

        # ── 2. Ler Excel com pandas ────────────────────────────────────
        try:
            engine = "openpyxl" if file.filename.lower().endswith('.xlsx') else "xlrd"
            df = pd.read_excel(io.BytesIO(content), engine=engine)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Erro ao ler o arquivo Excel: {str(exc)}"
            )

        if df.empty:
            raise HTTPException(status_code=400, detail="Planilha vazia (sem dados).")

        # ── 3. Normalizar nomes das colunas ────────────────────────────
        df.columns = [
            str(c).strip().lower().replace(" ", "_").replace("-", "_")
            for c in df.columns
        ]

        REQUIRED_COLUMNS = [
            "numero_linha", "tag", "malha", "sistema", "sop",
            "sub_sop", "sth", "pressao_teste", "descricao_sistema"
        ]

        # ── 4. Verificar colunas obrigatórias ─────────────────────────
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            raise HTTPException(
                status_code=400,
                detail=f"Colunas obrigatórias ausentes: {', '.join(missing_cols)}"
            )

        # Manter apenas as colunas esperadas
        df = df[REQUIRED_COLUMNS]
        total = len(df)

        # ── 5. Buscar numero_linha existentes no banco para checar duplicatas
        existing_numbers = set(
            r[0] for r in db.query(LinhaTubulacao.numero_linha).all()
        )

        imported = 0
        duplicates = 0
        failures = 0
        errors: List[str] = []

        # ── 6. Iterar e validar cada linha ─────────────────────────────
        for idx, row in df.iterrows():
            excel_row = idx + 2  # +2 porque idx=0 é a 1ª linha de dados (linha 2 no Excel)
            row_errors: List[str] = []

            # 6a. Validar numero_linha (obrigatório e não vazio)
            numero_linha_val = row.get("numero_linha")
            if pd.isna(numero_linha_val) or str(numero_linha_val).strip() == "":
                errors.append(f"Linha {excel_row}: campo 'numero_linha' é obrigatório e está vazio.")
                failures += 1
                continue

            numero_linha_str = str(numero_linha_val).strip()

            # 6b. Checar duplicata no banco
            if numero_linha_str in existing_numbers:
                errors.append(
                    f"Linha {excel_row}: numero_linha '{numero_linha_str}' já existe no banco (duplicata ignorada)."
                )
                duplicates += 1
                continue

            # 6c. Validar pressao_teste (deve ser numérico quando presente)
            pressao_teste_val = row.get("pressao_teste")
            pressao_teste_float = None
            if not pd.isna(pressao_teste_val) and str(pressao_teste_val).strip() != "":
                try:
                    pressao_teste_float = float(pressao_teste_val)
                except (ValueError, TypeError):
                    row_errors.append(
                        f"'pressao_teste' valor '{pressao_teste_val}' não é numérico"
                    )

            # 6d. Validar campos de texto obrigatórios (tag e sistema)
            tag_val = row.get("tag")
            if pd.isna(tag_val) or str(tag_val).strip() == "":
                row_errors.append("campo 'tag' está vazio")

            sistema_val = row.get("sistema")
            if pd.isna(sistema_val) or str(sistema_val).strip() == "":
                row_errors.append("campo 'sistema' está vazio")

            if row_errors:
                errors.append(f"Linha {excel_row}: {'; '.join(row_errors)}")
                failures += 1
                continue

            # ── 6e. Montar dados e inserir ─────────────────────────────
            def clean_str(val):
                if pd.isna(val) or val is None:
                    return None
                s = str(val).strip()
                return s if s else None

            data = {
                "numero_linha": numero_linha_str,
                "tag": clean_str(row.get("tag")),
                "malha": clean_str(row.get("malha")),
                "sistema": clean_str(row.get("sistema")),
                "sop": clean_str(row.get("sop")),
                "sub_sop": clean_str(row.get("sub_sop")),
                "sth": clean_str(row.get("sth")),
                "pressao_teste": pressao_teste_float,
                "descricao_sistema": clean_str(row.get("descricao_sistema")),
            }

            try:
                linha = LinhaTubulacao(**data)
                db.add(linha)
                # Adicionar ao set para evitar duplicatas dentro do próprio arquivo
                existing_numbers.add(numero_linha_str)
                imported += 1
            except Exception as e:
                errors.append(f"Linha {excel_row}: erro ao criar registro – {str(e)}")
                failures += 1

        # ── 7. Commit no banco ─────────────────────────────────────────
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Erro de banco de dados na importação: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao salvar dados no banco: {str(e)}"
            )

        logger.info(
            f"Importação Excel: {imported}/{total} importadas, "
            f"{duplicates} duplicatas, {failures} falhas – por {current_user.email}"
        )

        return ImportResult(
            total_linhas=total,
            importadas=imported,
            duplicadas=duplicates,
            falhas=failures,
            erros=errors[:100]  # Limitar a 100 mensagens de erro
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Erro na importação Excel: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar arquivo: {str(e)}")


@router.delete("/{linha_id}")
def delete_linha(
    linha_id: int,
    current_user=Depends(require_roles(["Administrador", "Engenharia"])),
    db: Session = Depends(get_db)
):
    linha = db.query(LinhaTubulacao).filter(LinhaTubulacao.id == linha_id).first()
    if not linha:
        raise HTTPException(status_code=404, detail="Linha não encontrada.")
    db.delete(linha)
    db.commit()
    return {"message": "Linha removida com sucesso."}
