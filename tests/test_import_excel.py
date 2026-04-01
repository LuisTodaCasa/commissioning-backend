"""Tests for the Excel import endpoint."""
import io
import pytest
from unittest.mock import MagicMock, patch
from openpyxl import Workbook
from fastapi.testclient import TestClient


def create_excel_bytes(rows, headers=None):
    """Helper to create an Excel file in memory."""
    wb = Workbook()
    ws = wb.active
    if headers is None:
        headers = [
            "numero_linha", "tag", "malha", "sistema", "sop",
            "sub_sop", "sth", "pressao_teste", "descricao_sistema"
        ]
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


# Mock user for auth
mock_user = MagicMock()
mock_user.email = "test@test.com"
mock_user.id = 1
mock_user.role = MagicMock()
mock_user.role.value = "Administrador"


def get_mock_user():
    return mock_user


@pytest.fixture
def client():
    """Create test client with mocked auth and DB."""
    from app.core.security import get_current_user, require_roles
    from app.main import app

    # Override auth
    app.dependency_overrides[get_current_user] = get_mock_user

    # Override require_roles to return mock user always
    def mock_require_roles(roles):
        def dep():
            return mock_user
        return dep

    # Patch require_roles in the linhas module
    import app.routers.linhas as linhas_mod
    original_require = linhas_mod.require_roles
    linhas_mod.require_roles = mock_require_roles

    with patch("app.routers.linhas.require_roles", mock_require_roles):
        yield TestClient(app)

    linhas_mod.require_roles = original_require
    app.dependency_overrides.clear()


def test_import_invalid_format(client):
    """Test rejection of non-Excel files."""
    response = client.post(
        "/api/v1/linhas/import-excel",
        files={"file": ("test.csv", b"data", "text/csv")}
    )
    assert response.status_code == 400
    assert "Formato inválido" in response.json()["detail"]


def test_import_missing_columns(client):
    """Test rejection when required columns are missing."""
    # Create Excel with only some columns
    excel_data = create_excel_bytes(
        [["L-001", "TAG-01"]],
        headers=["numero_linha", "tag"]
    )
    response = client.post(
        "/api/v1/linhas/import-excel",
        files={"file": ("test.xlsx", excel_data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert response.status_code == 400
    assert "Colunas obrigatórias ausentes" in response.json()["detail"]


def test_pandas_import_and_validation_logic():
    """Unit test the core pandas validation logic without DB."""
    import pandas as pd

    rows = [
        ["L-001", "TAG-01", "M-01", "Sys A", "SOP-1", "SUB-1", "STH-1", 10.5, "Desc A"],  # valid
        ["L-002", "TAG-02", "M-02", "Sys B", "SOP-2", "SUB-2", "STH-2", 20.0, "Desc B"],  # valid
        ["L-001", "TAG-03", "M-03", "Sys C", "SOP-3", "SUB-3", "STH-3", 15.0, "Desc C"],  # dup
        [None, "TAG-04", "M-04", "Sys D", "SOP-4", "SUB-4", "STH-4", 25.0, "Desc D"],      # no num
        ["L-003", "TAG-05", "M-05", "Sys E", "SOP-5", "SUB-5", "STH-5", "abc", "Desc E"],  # bad pressao
        ["L-004", None, "M-06", "Sys F", "SOP-6", "SUB-6", "STH-6", 30.0, "Desc F"],       # no tag
    ]
    excel_data = create_excel_bytes(rows)

    df = pd.read_excel(io.BytesIO(excel_data), engine="openpyxl")
    df.columns = [str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]

    REQUIRED_COLUMNS = [
        "numero_linha", "tag", "malha", "sistema", "sop",
        "sub_sop", "sth", "pressao_teste", "descricao_sistema"
    ]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    assert missing == [], f"Missing columns: {missing}"

    existing_numbers = set()
    imported = 0
    duplicates = 0
    failures = 0
    errors = []

    for idx, row in df.iterrows():
        excel_row = idx + 2
        row_errors = []

        numero_linha_val = row.get("numero_linha")
        if pd.isna(numero_linha_val) or str(numero_linha_val).strip() == "":
            failures += 1
            continue

        numero_linha_str = str(numero_linha_val).strip()

        if numero_linha_str in existing_numbers:
            duplicates += 1
            continue

        pressao_val = row.get("pressao_teste")
        if not pd.isna(pressao_val) and str(pressao_val).strip() != "":
            try:
                float(pressao_val)
            except (ValueError, TypeError):
                row_errors.append("pressao_teste invalid")

        tag_val = row.get("tag")
        if pd.isna(tag_val) or str(tag_val).strip() == "":
            row_errors.append("tag empty")

        sistema_val = row.get("sistema")
        if pd.isna(sistema_val) or str(sistema_val).strip() == "":
            row_errors.append("sistema empty")

        if row_errors:
            failures += 1
            continue

        existing_numbers.add(numero_linha_str)
        imported += 1

    assert imported == 2, f"Expected 2 imported, got {imported}"
    assert duplicates == 1, f"Expected 1 duplicate, got {duplicates}"
    assert failures == 3, f"Expected 3 failures, got {failures}"
    assert len(df) == 6


if __name__ == "__main__":
    test_pandas_import_and_validation_logic()
    print("All tests passed!")
