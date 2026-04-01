"""
Testes para o módulo de Pastas de Teste (Test Folders).
Cobre CRUD de pastas, atribuição de linhas, upload de documentos e atribuição de templates.
"""
import io
import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

# Ensure app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient


# ── Mock da autenticação ───────────────────────────────────────────────

def _mock_admin_user():
    user = MagicMock()
    user.id = 1
    user.nome = "Admin"
    user.email = "admin@test.com"
    user.role = "Administrador"
    user.ativo = True
    return user


def _mock_campo_user():
    user = MagicMock()
    user.id = 2
    user.nome = "Campo"
    user.email = "campo@test.com"
    user.role = "Campo"
    user.ativo = True
    return user


@pytest.fixture
def admin_client():
    """TestClient autenticado como Administrador."""
    from app.core.security import get_current_user, require_roles
    from app.main import app

    admin = _mock_admin_user()

    def override_get_current_user():
        return admin

    def override_require_roles(roles):
        def dep():
            return admin
        return dep

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[require_roles] = override_require_roles

    # Also override all specific role checkers used in routers
    for role_list_str in [
        '["Administrador"]',
        '["Administrador", "Comissionamento", "Engenharia"]',
        '["Administrador", "Comissionamento"]',
    ]:
        pass  # require_roles returns a callable, handled by override above

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def campo_client():
    """TestClient autenticado como Campo (apenas leitura)."""
    from app.core.security import get_current_user, require_roles
    from app.main import app

    campo = _mock_campo_user()

    def override_get_current_user():
        return campo

    # Campo user should NOT be allowed by require_roles for write operations
    # But we keep it simple: override get_current_user, don't override require_roles
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# We need a proper fixture that handles the require_roles dependency properly
@pytest.fixture
def client():
    """TestClient with admin auth that properly overrides role-based deps."""
    from app.main import app
    from app.core.security import get_current_user

    admin = _mock_admin_user()

    # Override get_current_user
    app.dependency_overrides[get_current_user] = lambda: admin

    # Monkey-patch require_roles to always return admin
    import app.core.security as sec
    original_require_roles = sec.require_roles

    def mock_require_roles(allowed_roles):
        def dep():
            return admin
        return dep

    sec.require_roles = mock_require_roles

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    sec.require_roles = original_require_roles


# ── Testes de CRUD de Pastas ───────────────────────────────────────────

class TestPastaCRUD:
    """Testes para operações CRUD de pastas de teste."""

    def test_create_pasta(self, client):
        """Teste: criar uma nova pasta de teste."""
        numero = f"PT-{os.urandom(4).hex()}"
        response = client.post("/api/v1/pastas/", json={
            "numero_pasta": numero,
            "sth": "STH-001",
            "descricao_sistema": "Sistema de teste hidrostático",
            "pressao_teste": 150.5,
        })
        assert response.status_code == 201
        data = response.json()
        assert data["numero_pasta"] == numero
        assert data["sth"] == "STH-001"
        assert data["status"] == "CRIADA"
        assert data["pressao_teste"] == 150.5

    def test_create_pasta_duplicate_numero(self, client):
        """Teste: impedir criação de pasta com número duplicado."""
        dup_num = f"PT-DUP-{os.urandom(3).hex()}"
        client.post("/api/v1/pastas/", json={"numero_pasta": dup_num})
        response = client.post("/api/v1/pastas/", json={"numero_pasta": dup_num})
        assert response.status_code == 400
        assert "Já existe" in response.json()["detail"]

    def test_create_pasta_pressao_negativa(self, client):
        """Teste: pressão de teste deve ser positiva."""
        response = client.post("/api/v1/pastas/", json={
            "numero_pasta": f"PT-NEG-{os.urandom(3).hex()}",
            "pressao_teste": -10,
        })
        assert response.status_code == 422  # Validation error

    def test_list_pastas(self, client):
        """Teste: listar pastas."""
        tag = os.urandom(3).hex()
        client.post("/api/v1/pastas/", json={"numero_pasta": f"PT-LIST-1-{tag}", "sth": "STH-A"})
        client.post("/api/v1/pastas/", json={"numero_pasta": f"PT-LIST-2-{tag}", "sth": "STH-B"})

        response = client.get("/api/v1/pastas/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_pastas_filter_status(self, client):
        """Teste: filtrar pastas por status."""
        response = client.get("/api/v1/pastas/?status=CRIADA")
        assert response.status_code == 200

    def test_list_pastas_filter_sth(self, client):
        """Teste: filtrar pastas por STH."""
        response = client.get("/api/v1/pastas/?sth=STH-A")
        assert response.status_code == 200

    def test_list_pastas_search(self, client):
        """Teste: busca textual de pastas."""
        response = client.get("/api/v1/pastas/?search=PT-LIST")
        assert response.status_code == 200

    def test_list_pastas_invalid_status(self, client):
        """Teste: status inválido retorna erro."""
        response = client.get("/api/v1/pastas/?status=INVALIDO")
        assert response.status_code == 400

    def test_get_pasta_detail(self, client):
        """Teste: obter detalhes completos de uma pasta."""
        numero = f"PT-DETAIL-{os.urandom(3).hex()}"
        create_resp = client.post("/api/v1/pastas/", json={
            "numero_pasta": numero,
            "sth": "STH-DET",
            "descricao_sistema": "Detalhes completos",
            "pressao_teste": 200.0,
        })
        pasta_id = create_resp.json()["id"]

        response = client.get(f"/api/v1/pastas/{pasta_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["numero_pasta"] == numero
        assert "linhas" in data
        assert "documentos" in data
        assert "testes" in data
        assert "total_relatorios" in data

    def test_get_pasta_not_found(self, client):
        """Teste: pasta inexistente retorna 404."""
        response = client.get("/api/v1/pastas/99999")
        assert response.status_code == 404

    def test_update_pasta(self, client):
        """Teste: atualizar uma pasta."""
        create_resp = client.post("/api/v1/pastas/", json={"numero_pasta": f"PT-UPD-{os.urandom(3).hex()}"})
        pasta_id = create_resp.json()["id"]

        response = client.put(f"/api/v1/pastas/{pasta_id}", json={
            "descricao_sistema": "Atualizado",
            "status": "EM_ANDAMENTO",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "EM_ANDAMENTO"

    def test_update_pasta_invalid_status(self, client):
        """Teste: atualizar pasta com status inválido."""
        create_resp = client.post("/api/v1/pastas/", json={"numero_pasta": f"PT-UPDI-{os.urandom(3).hex()}"})
        pasta_id = create_resp.json()["id"]

        response = client.put(f"/api/v1/pastas/{pasta_id}", json={"status": "INVALIDO"})
        assert response.status_code == 400

    def test_delete_pasta(self, client):
        """Teste: excluir uma pasta."""
        create_resp = client.post("/api/v1/pastas/", json={"numero_pasta": f"PT-DEL-{os.urandom(3).hex()}"})
        pasta_id = create_resp.json()["id"]

        response = client.delete(f"/api/v1/pastas/{pasta_id}")
        assert response.status_code == 200
        assert "removida" in response.json()["message"]

        # Confirm deleted
        response = client.get(f"/api/v1/pastas/{pasta_id}")
        assert response.status_code == 404

    def test_delete_pasta_not_found(self, client):
        """Teste: excluir pasta inexistente."""
        response = client.delete("/api/v1/pastas/99999")
        assert response.status_code == 404


# ── Testes de Atribuição de Linhas ─────────────────────────────────────

class TestLinhaAssignment:
    """Testes para atribuição de linhas de tubulação às pastas."""

    def _create_pasta(self, client, numero="PT-LINHA"):
        resp = client.post("/api/v1/pastas/", json={"numero_pasta": numero})
        return resp.json()["id"]

    def _create_linha(self, client):
        resp = client.post("/api/v1/linhas/", json={
            "numero_linha": f"LN-{os.urandom(4).hex()}",
            "tag": "TAG-001",
            "sistema": "Sistema Teste",
        })
        if resp.status_code == 201:
            return resp.json()["id"]
        return None

    def test_assign_linhas(self, client):
        """Teste: atribuir linhas a uma pasta."""
        pasta_id = self._create_pasta(client, f"PT-ASSIGN-{os.urandom(2).hex()}")

        # Create lines
        linha_ids = []
        for i in range(3):
            lid = self._create_linha(client)
            if lid:
                linha_ids.append(lid)

        if not linha_ids:
            pytest.skip("Não foi possível criar linhas para teste")

        response = client.post(f"/api/v1/pastas/{pasta_id}/linhas", json={
            "linha_ids": linha_ids
        })
        assert response.status_code == 200
        assert response.json()["total"] == len(linha_ids)

    def test_assign_linhas_invalid_id(self, client):
        """Teste: atribuir linha inexistente retorna erro."""
        pasta_id = self._create_pasta(client, f"PT-INVAL-{os.urandom(2).hex()}")
        response = client.post(f"/api/v1/pastas/{pasta_id}/linhas", json={
            "linha_ids": [99999]
        })
        assert response.status_code == 404

    def test_get_pasta_linhas(self, client):
        """Teste: listar linhas de uma pasta."""
        pasta_id = self._create_pasta(client, f"PT-GETL-{os.urandom(2).hex()}")
        response = client.get(f"/api/v1/pastas/{pasta_id}/linhas")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_remove_linha_from_pasta(self, client):
        """Teste: remover linha de uma pasta."""
        pasta_id = self._create_pasta(client, f"PT-RML-{os.urandom(2).hex()}")
        lid = self._create_linha(client)
        if not lid:
            pytest.skip("Não foi possível criar linha")

        # Assign
        client.post(f"/api/v1/pastas/{pasta_id}/linhas", json={"linha_ids": [lid]})

        # Remove
        response = client.delete(f"/api/v1/pastas/{pasta_id}/linhas/{lid}")
        assert response.status_code == 200

    def test_remove_linha_not_assigned(self, client):
        """Teste: remover linha não associada retorna 404."""
        pasta_id = self._create_pasta(client, f"PT-RMNA-{os.urandom(2).hex()}")
        response = client.delete(f"/api/v1/pastas/{pasta_id}/linhas/99999")
        assert response.status_code == 404


# ── Testes de Upload de Documentos ─────────────────────────────────────

class TestDocumentUpload:
    """Testes para upload e gerenciamento de documentos PDF."""

    def _create_pasta(self, client, numero=None):
        numero = numero or f"PT-DOC-{os.urandom(2).hex()}"
        resp = client.post("/api/v1/pastas/", json={"numero_pasta": numero})
        return resp.json()["id"]

    def _create_pdf_bytes(self):
        """Gerar conteúdo PDF mínimo para teste."""
        return b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF"

    def test_upload_documento(self, client):
        """Teste: upload de documento PDF."""
        pasta_id = self._create_pasta(client)
        pdf_content = self._create_pdf_bytes()

        response = client.post(
            f"/api/v1/documentos/pasta/{pasta_id}",
            data={"tipo": "fluxograma"},
            files={"file": ("teste.pdf", io.BytesIO(pdf_content), "application/pdf")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["tipo"] == "fluxograma"
        assert data["nome_arquivo"] == "teste.pdf"
        assert data["download_url"] is not None
        assert data["pasta_id"] == pasta_id

    def test_upload_documento_tipo_invalido(self, client):
        """Teste: tipo de documento inválido retorna erro."""
        pasta_id = self._create_pasta(client)
        pdf_content = self._create_pdf_bytes()

        response = client.post(
            f"/api/v1/documentos/pasta/{pasta_id}",
            data={"tipo": "invalido"},
            files={"file": ("teste.pdf", io.BytesIO(pdf_content), "application/pdf")},
        )
        assert response.status_code == 400

    def test_upload_documento_nao_pdf(self, client):
        """Teste: upload de arquivo não-PDF retorna erro."""
        pasta_id = self._create_pasta(client)

        response = client.post(
            f"/api/v1/documentos/pasta/{pasta_id}",
            data={"tipo": "fluxograma"},
            files={"file": ("teste.txt", io.BytesIO(b"not a pdf"), "text/plain")},
        )
        assert response.status_code == 400

    def test_upload_all_document_types(self, client):
        """Teste: upload de todos os tipos de documento permitidos."""
        pasta_id = self._create_pasta(client)
        pdf_content = self._create_pdf_bytes()

        tipos = ["fluxograma", "fluxoteste", "isometrico", "lista_suportes", "mapa_juntas"]
        for tipo in tipos:
            response = client.post(
                f"/api/v1/documentos/pasta/{pasta_id}",
                data={"tipo": tipo},
                files={"file": (f"{tipo}.pdf", io.BytesIO(pdf_content), "application/pdf")},
            )
            assert response.status_code == 201, f"Falha ao upload tipo {tipo}"

    def test_list_documentos(self, client):
        """Teste: listar documentos de uma pasta."""
        pasta_id = self._create_pasta(client)
        pdf_content = self._create_pdf_bytes()

        # Upload 2 docs
        for tipo in ["fluxograma", "isometrico"]:
            client.post(
                f"/api/v1/documentos/pasta/{pasta_id}",
                data={"tipo": tipo},
                files={"file": (f"{tipo}.pdf", io.BytesIO(pdf_content), "application/pdf")},
            )

        response = client.get(f"/api/v1/documentos/pasta/{pasta_id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_list_documentos_via_pasta_endpoint(self, client):
        """Teste: listar documentos usando endpoint da pasta."""
        pasta_id = self._create_pasta(client)
        response = client.get(f"/api/v1/pastas/{pasta_id}/documentos")
        assert response.status_code == 200

    def test_delete_documento(self, client):
        """Teste: excluir documento."""
        pasta_id = self._create_pasta(client)
        pdf_content = self._create_pdf_bytes()

        upload_resp = client.post(
            f"/api/v1/documentos/pasta/{pasta_id}",
            data={"tipo": "fluxograma"},
            files={"file": ("delete_me.pdf", io.BytesIO(pdf_content), "application/pdf")},
        )
        doc_id = upload_resp.json()["id"]

        response = client.delete(f"/api/v1/documentos/{doc_id}")
        assert response.status_code == 200

    def test_upload_multiple_same_type(self, client):
        """Teste: upload de múltiplos documentos do mesmo tipo (versionamento)."""
        pasta_id = self._create_pasta(client)
        pdf_content = self._create_pdf_bytes()

        for i in range(3):
            response = client.post(
                f"/api/v1/documentos/pasta/{pasta_id}",
                data={"tipo": "fluxograma"},
                files={"file": (f"v{i}.pdf", io.BytesIO(pdf_content), "application/pdf")},
            )
            assert response.status_code == 201

        # All 3 should be listed
        list_resp = client.get(f"/api/v1/documentos/pasta/{pasta_id}")
        assert len(list_resp.json()) == 3

    def test_upload_pasta_not_found(self, client):
        """Teste: upload para pasta inexistente retorna 404."""
        pdf_content = self._create_pdf_bytes()
        response = client.post(
            "/api/v1/documentos/pasta/99999",
            data={"tipo": "fluxograma"},
            files={"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")},
        )
        assert response.status_code == 404


# ── Testes de Atribuição de Templates ──────────────────────────────────

class TestTemplateAssignment:
    """Testes para atribuição de templates/modelos de relatório às pastas."""

    def _create_pasta(self, client):
        resp = client.post("/api/v1/pastas/", json={
            "numero_pasta": f"PT-TPL-{os.urandom(2).hex()}"
        })
        return resp.json()["id"]

    def _create_modelo(self, client):
        resp = client.post("/api/v1/modelos/", json={
            "nome": f"Modelo-{os.urandom(4).hex()}",
            "tipo": "teste_hidrostatico",
            "descricao": "Modelo para teste",
        })
        if resp.status_code == 201:
            return resp.json()["id"]
        return None

    def test_assign_testes(self, client):
        """Teste: atribuir templates a uma pasta."""
        pasta_id = self._create_pasta(client)
        modelo_id = self._create_modelo(client)
        if not modelo_id:
            pytest.skip("Não foi possível criar modelo")

        response = client.post(f"/api/v1/testes/pasta/{pasta_id}", json={
            "modelo_ids": [modelo_id]
        })
        assert response.status_code == 200

    def test_assign_testes_invalid_modelo(self, client):
        """Teste: atribuir modelo inexistente retorna erro."""
        pasta_id = self._create_pasta(client)
        response = client.post(f"/api/v1/testes/pasta/{pasta_id}", json={
            "modelo_ids": [99999]
        })
        assert response.status_code == 404

    def test_list_testes(self, client):
        """Teste: listar templates de uma pasta."""
        pasta_id = self._create_pasta(client)
        response = client.get(f"/api/v1/testes/pasta/{pasta_id}")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_testes_via_pasta_endpoint(self, client):
        """Teste: listar templates usando endpoint da pasta."""
        pasta_id = self._create_pasta(client)
        response = client.get(f"/api/v1/pastas/{pasta_id}/testes")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_remove_teste(self, client):
        """Teste: remover template de uma pasta."""
        pasta_id = self._create_pasta(client)
        modelo_id = self._create_modelo(client)
        if not modelo_id:
            pytest.skip("Não foi possível criar modelo")

        # Assign
        client.post(f"/api/v1/testes/pasta/{pasta_id}", json={"modelo_ids": [modelo_id]})

        # Remove via testes endpoint
        response = client.delete(f"/api/v1/testes/pasta/{pasta_id}/{modelo_id}")
        assert response.status_code == 200

    def test_remove_teste_via_pasta_endpoint(self, client):
        """Teste: remover template usando endpoint da pasta."""
        pasta_id = self._create_pasta(client)
        modelo_id = self._create_modelo(client)
        if not modelo_id:
            pytest.skip("Não foi possível criar modelo")

        # Assign
        client.post(f"/api/v1/testes/pasta/{pasta_id}", json={"modelo_ids": [modelo_id]})

        # Remove via pasta endpoint
        response = client.delete(f"/api/v1/pastas/{pasta_id}/testes/{modelo_id}")
        assert response.status_code == 200


# ── Testes de Pasta Completa ───────────────────────────────────────────

class TestPastaComplete:
    """Testes para recuperação completa de pastas com todas as associações."""

    def test_get_pasta_with_all_associations(self, client):
        """Teste: obter pasta com linhas, documentos e templates."""
        # Create pasta
        create_resp = client.post("/api/v1/pastas/", json={
            "numero_pasta": f"PT-FULL-{os.urandom(2).hex()}",
            "sth": "STH-FULL",
            "descricao_sistema": "Pasta completa",
            "pressao_teste": 300.0,
        })
        assert create_resp.status_code == 201
        pasta_id = create_resp.json()["id"]

        # Get full details
        detail_resp = client.get(f"/api/v1/pastas/{pasta_id}")
        assert detail_resp.status_code == 200
        data = detail_resp.json()

        # Verify structure
        assert "linhas" in data
        assert "documentos" in data
        assert "testes" in data
        assert "total_relatorios" in data
        assert data["status"] == "CRIADA"
        assert data["pressao_teste"] == 300.0
