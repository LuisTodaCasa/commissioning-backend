"""Verificação de tabelas faltantes (production hardening)

Revision ID: 20260801_add_missing_tables
Revises: 142d0392172d
Create Date: 2026-08-01

--------------------------------------------------------------------------
VERIFICAÇÃO DE COBERTURA DE SCHEMA
--------------------------------------------------------------------------
Foi feita a comparação entre os modelos SQLAlchemy em `app/models/models.py`
e a migration inicial `142d0392172d_create_initial_schema_from_models.py`.

Todas as tabelas dos modelos JÁ estão cobertas pela migration inicial:

    - usuarios
    - disciplinas
    - usuario_disciplinas
    - linhas_tubulacao
    - pastas_teste
    - pasta_linhas
    - documentos_pasta
    - modelos_relatorio
    - pasta_testes
    - relatorios
    - sths
    - linhas_tubulacao_catalogo
    - sth_linhas
    - spools
    - documentos_linha
    - relatorios_execucao

Não há tabelas nem colunas faltando. Esta migration é intencionalmente um
"no-op" (não altera o schema) e serve apenas para:

  1. Documentar formalmente que a verificação de cobertura foi realizada.
  2. Fixar uma nova cabeça (head) de migração para futuras alterações.

Caso, no futuro, novos modelos/colunas sejam adicionados, gere a migração
correspondente com:

    alembic revision --autogenerate -m "descricao da mudanca"
--------------------------------------------------------------------------
"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = '20260801_add_missing_tables'
down_revision = '142d0392172d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nenhuma alteração necessária — todas as tabelas dos modelos já foram
    # criadas pela migration inicial (142d0392172d). Ver docstring acima.
    pass


def downgrade() -> None:
    # No-op: nada a reverter.
    pass
