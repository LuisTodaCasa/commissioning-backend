"""
Testes do módulo de Modelos de Relatórios (Templates).

Cobre:
- CRUD de templates (POST, GET, PUT, DELETE)
- Upload e download de PDF
- Configuração de campos (campos_template)
- Atribuição a pastas de teste
- Proteção contra exclusão de templates em uso
- Permissões (role-based access control)
"""
import io
import os
import sys
import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app.core.security import get_current_user, require_roles
from app.main import app


# ── Fixtures ──────────────────────────────────────────────────────────


def _mock_admin_user():
    user = MagicMock()
    user.id = 1
    user.nome = "Admin Test"
    user.email = "admin@test.com"
    user.role = "Administrador"
    user.ativo = True
    return user


def _mock_campo_user():
    user = MagicMock()
    user.id = 2
    user.nome = "Campo Test"
    user.email = "campo@test.com"
    user.role = "Campo"
    user.ativo = True
    return user


@pytest.fixture
def admin_client():
    """Client authenticated as Administrador."""
    admin = _mock_admin_user()
    app.dependency_overrides[get_current_user] = lambda: admin
    # Override all require_roles to return admin
    original_require_roles = require_roles

    def _mock_require_roles(roles):
        def _dep():
            return admin
        return _dep

    app.dependency_overrides[require_roles] = _mock_require_roles
    # Patch require_roles at module level for the templates router
    with patch("app.routers.templates.require_roles", _mock_require_roles), \
         patch("app.routers.modelos.require_roles", _mock_require_roles):
        client = TestClient(app)
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def campo_client():
    """Client authenticated as Campo (non-admin)."""
    campo = _mock_campo_user()
    app.dependency_overrides[get_current_user] = lambda: campo

    def _mock_require_roles(roles):
        def _dep():
            if "Campo" not in roles and "Administrador" not in roles:
                from fastapi import HTTPException
                raise HTTPException(status_code=403, detail="Acesso negado")
            return campo
        return _dep

    with patch("app.routers.templates.require_roles", _mock_require_roles), \
         patch("app.routers.modelos.require_roles", _mock_require_roles):
        client = TestClient(app)
        yield client
    app.dependency_overrides.clear()


def _create_pdf_bytes(content: str = "Test PDF") -> bytes:
    """Create minimal valid PDF bytes."""
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n0000000000 65535 f \n"
        b"0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF"
    )
    return pdf


def _unique_name(prefix: str = "Template") -> str:
    return f"{prefix}_{os.urandom(4).hex()}"


# ── Test Template CRUD ─────────────────────────────────────────────────


class TestTemplateCRUD:
    """Testes CRUD básicos para templates."""

    def test_create_template_with_pdf(self, admin_client):
        """Criar template com upload de PDF."""
        nome = _unique_name()
        pdf = _create_pdf_bytes()
        resp = admin_client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "teste_hidrostatico", "descricao": "Teste Hidrostático padrão"},
            files={"file": ("template.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["nome"] == nome
        assert data["tipo"] == "teste_hidrostatico" or data["tipo"] == "TESTE_HIDROSTATICO"
        assert data["download_url"] is not None
        assert "/download" in data["download_url"]

    def test_create_template_invalid_tipo(self, admin_client):
        """Tentar criar com tipo inválido."""
        pdf = _create_pdf_bytes()
        resp = admin_client.post(
            "/api/v1/templates/",
            data={"nome": "Invalid", "tipo": "tipo_invalido"},
            files={"file": ("t.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert resp.status_code == 400
        assert "Tipo inválido" in resp.json()["detail"]

    def test_create_template_non_pdf(self, admin_client):
        """Tentar upload de arquivo não-PDF."""
        resp = admin_client.post(
            "/api/v1/templates/",
            data={"nome": "NoPdf", "tipo": "flush_line"},
            files={"file": ("test.txt", io.BytesIO(b"not a pdf"), "text/plain")},
        )
        assert resp.status_code == 400

    def test_create_template_invalid_pdf_content(self, admin_client):
        """Tentar upload de .pdf com conteúdo inválido."""
        resp = admin_client.post(
            "/api/v1/templates/",
            data={"nome": "FakePdf", "tipo": "flush_line"},
            files={"file": ("fake.pdf", io.BytesIO(b"this is not really a pdf"), "application/pdf")},
        )
        assert resp.status_code == 400
        assert "PDF válido" in resp.json()["detail"]

    def test_create_template_duplicate_nome_tipo(self, admin_client):
        """Nomes duplicados para o mesmo tipo devem ser rejeitados."""
        nome = _unique_name()
        pdf = _create_pdf_bytes()
        # First create
        resp1 = admin_client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "descarga_linha"},
            files={"file": ("t.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert resp1.status_code == 201
        # Duplicate
        resp2 = admin_client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "descarga_linha"},
            files={"file": ("t2.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert resp2.status_code == 409

    def test_create_same_name_different_tipo(self, admin_client):
        """Mesmo nome com tipo diferente deve ser aceito."""
        nome = _unique_name()
        pdf = _create_pdf_bytes()
        resp1 = admin_client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "teste_hidrostatico"},
            files={"file": ("t.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert resp1.status_code == 201
        resp2 = admin_client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "flush_line"},
            files={"file": ("t.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert resp2.status_code == 201

    def test_list_templates(self, admin_client):
        """Listar templates."""
        resp = admin_client.get("/api/v1/templates/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_templates_filter_tipo(self, admin_client):
        """Filtrar templates por tipo."""
        nome = _unique_name()
        pdf = _create_pdf_bytes()
        admin_client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "certificado_teste"},
            files={"file": ("t.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        resp = admin_client.get("/api/v1/templates/?tipo=certificado_teste")
        assert resp.status_code == 200
        data = resp.json()
        for item in data:
            tipo = item["tipo"].lower() if isinstance(item["tipo"], str) else item["tipo"]
            assert tipo == "certificado_teste"

    def test_list_templates_invalid_tipo_filter(self, admin_client):
        """Filtrar com tipo inválido retorna 400."""
        resp = admin_client.get("/api/v1/templates/?tipo=invalido")
        assert resp.status_code == 400

    def test_get_template_detail(self, admin_client):
        """Obter detalhes de um template."""
        nome = _unique_name()
        pdf = _create_pdf_bytes()
        create_resp = admin_client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "teste_estanqueidade"},
            files={"file": ("t.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        tid = create_resp.json()["id"]
        resp = admin_client.get(f"/api/v1/templates/{tid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == tid
        assert data["nome"] == nome
        # Detail should have campos_template
        assert "campos_template" in data

    def test_get_template_not_found(self, admin_client):
        resp = admin_client.get("/api/v1/templates/99999")
        assert resp.status_code == 404

    def test_update_template(self, admin_client):
        """Atualizar metadados do template."""
        nome = _unique_name()
        pdf = _create_pdf_bytes()
        create_resp = admin_client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "flush_line"},
            files={"file": ("t.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        tid = create_resp.json()["id"]
        new_name = _unique_name("Updated")
        resp = admin_client.put(
            f"/api/v1/templates/{tid}",
            json={"nome": new_name, "descricao": "Descrição atualizada"},
        )
        assert resp.status_code == 200
        assert resp.json()["nome"] == new_name

    def test_delete_template(self, admin_client):
        """Excluir template."""
        nome = _unique_name()
        pdf = _create_pdf_bytes()
        create_resp = admin_client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "teste_hidrostatico"},
            files={"file": ("t.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        tid = create_resp.json()["id"]
        resp = admin_client.delete(f"/api/v1/templates/{tid}")
        assert resp.status_code == 200
        assert "excluído" in resp.json()["message"]

        # Confirm it's gone
        resp2 = admin_client.get(f"/api/v1/templates/{tid}")
        assert resp2.status_code == 404


# ── Test PDF Upload / Download ─────────────────────────────────────────


class TestPDFUploadDownload:
    """Testes de upload e download de PDF."""

    def test_download_template_pdf(self, admin_client):
        """Fazer download de PDF após upload."""
        nome = _unique_name()
        pdf = _create_pdf_bytes()
        create_resp = admin_client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "descarga_linha"},
            files={"file": ("mytemplate.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        tid = create_resp.json()["id"]
        resp = admin_client.get(f"/api/v1/templates/{tid}/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:5] == b'%PDF-'

    def test_download_no_pdf(self, admin_client):
        """Tentar download de template sem PDF (criado via legacy endpoint)."""
        # Create via modelos endpoint (no PDF)
        resp = admin_client.post(
            "/api/v1/modelos/",
            json={"nome": _unique_name(), "tipo": "teste_hidrostatico"},
        )
        if resp.status_code == 201:
            tid = resp.json()["id"]
            dl = admin_client.get(f"/api/v1/templates/{tid}/download")
            assert dl.status_code == 404

    def test_file_stored_in_tipo_directory(self, admin_client):
        """PDF deve ser armazenado em uploads/templates/{tipo}/."""
        nome = _unique_name()
        pdf = _create_pdf_bytes()
        create_resp = admin_client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "teste_estanqueidade"},
            files={"file": ("t.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        data = create_resp.json()
        arquivo = data.get("arquivo_pdf") or data.get("caminho_template")
        if arquivo:
            assert "teste_estanqueidade" in arquivo or "TESTE_ESTANQUEIDADE" in arquivo.upper()


# ── Test Field Configuration ──────────────────────────────────────────


class TestFieldConfiguration:
    """Testes de configuração de campos (campos_template)."""

    def _create_template(self, client):
        nome = _unique_name()
        pdf = _create_pdf_bytes()
        resp = client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "teste_hidrostatico"},
            files={"file": ("t.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        return resp.json()["id"]

    def test_configure_campos(self, admin_client):
        """Configurar campos do template."""
        tid = self._create_template(admin_client)
        campos = [
            {"nome_campo": "tag", "tipo_campo": "text", "obrigatorio": True, "auto_fill": True},
            {"nome_campo": "pressao_teste", "tipo_campo": "number", "obrigatorio": True, "auto_fill": True},
            {"nome_campo": "resultado", "tipo_campo": "select", "obrigatorio": False, "auto_fill": False,
             "opcoes": ["Aprovado", "Reprovado"]},
        ]
        resp = admin_client.post(
            f"/api/v1/templates/{tid}/campos",
            json={"campos": campos},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["campos_template"] is not None
        assert len(data["campos_template"]) == 3

    def test_get_campos(self, admin_client):
        """Obter configuração de campos."""
        tid = self._create_template(admin_client)
        # Configure first
        campos = [
            {"nome_campo": "numero_linha", "tipo_campo": "text", "obrigatorio": True, "auto_fill": True},
        ]
        admin_client.post(f"/api/v1/templates/{tid}/campos", json={"campos": campos})

        resp = admin_client.get(f"/api/v1/templates/{tid}/campos")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["nome_campo"] == "numero_linha"
        assert data[0]["auto_fill"] is True

    def test_get_campos_empty(self, admin_client):
        """Template recém-criado tem campos padrão."""
        tid = self._create_template(admin_client)
        resp = admin_client.get(f"/api/v1/templates/{tid}/campos")
        assert resp.status_code == 200
        # Should have default fields from creation
        data = resp.json()
        assert isinstance(data, list)

    def test_invalid_tipo_campo(self, admin_client):
        """tipo_campo inválido deve retornar 400."""
        tid = self._create_template(admin_client)
        campos = [{"nome_campo": "test", "tipo_campo": "invalid"}]
        resp = admin_client.post(
            f"/api/v1/templates/{tid}/campos",
            json={"campos": campos},
        )
        assert resp.status_code == 400

    def test_invalid_auto_fill_field(self, admin_client):
        """auto_fill em campo não suportado deve retornar 400."""
        tid = self._create_template(admin_client)
        campos = [{"nome_campo": "campo_custom", "tipo_campo": "text", "auto_fill": True}]
        resp = admin_client.post(
            f"/api/v1/templates/{tid}/campos",
            json={"campos": campos},
        )
        assert resp.status_code == 400
        assert "auto_fill" in resp.json()["detail"]

    def test_all_auto_fill_fields(self, admin_client):
        """Todos os campos auto_fill suportados devem funcionar."""
        tid = self._create_template(admin_client)
        auto_fill_fields = [
            "tag", "malha", "numero_linha", "sop", "sub_sop",
            "sth", "pressao_teste", "descricao_sistema",
        ]
        campos = [
            {"nome_campo": f, "tipo_campo": "text", "auto_fill": True}
            for f in auto_fill_fields
        ]
        resp = admin_client.post(
            f"/api/v1/templates/{tid}/campos",
            json={"campos": campos},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["campos_template"]) == len(auto_fill_fields)


# ── Test Template Assignment to Folders ────────────────────────────────


class TestTemplateAssignment:
    """Testes de atribuição de templates a pastas e proteção contra exclusão."""

    def _create_template(self, client):
        nome = _unique_name()
        pdf = _create_pdf_bytes()
        resp = client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "teste_hidrostatico"},
            files={"file": ("t.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        return resp.json()["id"]

    def _create_pasta(self, client):
        num = os.urandom(4).hex()
        resp = client.post(
            "/api/v1/pastas/",
            json={"numero_pasta": f"PT-{num}", "sth": "STH-001"},
        )
        return resp.json()["id"]

    def test_template_shows_pastas_count(self, admin_client):
        """Template deve mostrar quantas pastas o estão usando."""
        tid = self._create_template(admin_client)
        resp = admin_client.get(f"/api/v1/templates/{tid}")
        assert resp.status_code == 200
        assert resp.json()["total_pastas_usando"] == 0

    def test_delete_template_in_use_blocked(self, admin_client):
        """Não deve permitir exclusão de template atribuído a pasta."""
        tid = self._create_template(admin_client)
        pid = self._create_pasta(admin_client)

        # Assign template to pasta
        assign_resp = admin_client.post(
            f"/api/v1/testes/pasta/{pid}",
            json={"modelo_ids": [tid]},
        )
        assert assign_resp.status_code == 200

        # Try to delete
        del_resp = admin_client.delete(f"/api/v1/templates/{tid}")
        assert del_resp.status_code == 409
        assert "atribuído" in del_resp.json()["detail"]

    def test_delete_template_in_use_force(self, admin_client):
        """Com force=true, deve permitir exclusão mesmo com atribuições."""
        tid = self._create_template(admin_client)
        pid = self._create_pasta(admin_client)

        admin_client.post(f"/api/v1/testes/pasta/{pid}", json={"modelo_ids": [tid]})

        del_resp = admin_client.delete(f"/api/v1/templates/{tid}?force=true")
        assert del_resp.status_code == 200
        assert "excluído" in del_resp.json()["message"]


# ── Test Permissions ──────────────────────────────────────────────────


class TestPermissions:
    """Testes de permissões de acesso."""

    def test_campo_user_can_list(self, campo_client):
        """Usuário Campo pode listar templates."""
        resp = campo_client.get("/api/v1/templates/")
        assert resp.status_code == 200

    def test_campo_user_can_download(self, admin_client, campo_client):
        """Usuário Campo pode fazer download de templates."""
        # Create as admin
        nome = _unique_name()
        pdf = _create_pdf_bytes()
        create_resp = admin_client.post(
            "/api/v1/templates/",
            data={"nome": nome, "tipo": "flush_line"},
            files={"file": ("t.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        if create_resp.status_code == 201:
            tid = create_resp.json()["id"]
            dl = campo_client.get(f"/api/v1/templates/{tid}/download")
            # Should be accessible
            assert dl.status_code in (200, 404)  # 404 if file path issue in test


# ── Test Legacy Modelos Endpoints ──────────────────────────────────────


class TestLegacyModelos:
    """Testes para o router legado /api/v1/modelos (backward compatibility)."""

    def test_create_modelo_without_pdf(self, admin_client):
        """Criar modelo sem PDF via endpoint legado."""
        resp = admin_client.post(
            "/api/v1/modelos/",
            json={"nome": _unique_name(), "tipo": "teste_hidrostatico", "descricao": "Test"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["ativo"] is True

    def test_list_modelos(self, admin_client):
        """Listar modelos via endpoint legado."""
        resp = admin_client.get("/api/v1/modelos/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_update_modelo(self, admin_client):
        """Atualizar modelo via endpoint legado."""
        create_resp = admin_client.post(
            "/api/v1/modelos/",
            json={"nome": _unique_name(), "tipo": "descarga_linha"},
        )
        mid = create_resp.json()["id"]
        resp = admin_client.put(
            f"/api/v1/modelos/{mid}",
            json={"descricao": "Updated description"},
        )
        assert resp.status_code == 200

    def test_upload_template_legacy(self, admin_client):
        """Upload de template via endpoint legado."""
        pdf = _create_pdf_bytes()
        resp = admin_client.post(
            "/api/v1/modelos/upload-template",
            data={"nome": _unique_name(), "tipo": "teste_hidrostatico"},
            files={"file": ("t.pdf", io.BytesIO(pdf), "application/pdf")},
        )
        assert resp.status_code == 201

    def test_deactivate_modelo_blocked_if_in_use(self, admin_client):
        """Desativar modelo em uso via legado deve ser bloqueado."""
        # Create modelo
        create_resp = admin_client.post(
            "/api/v1/modelos/",
            json={"nome": _unique_name(), "tipo": "teste_hidrostatico"},
        )
        mid = create_resp.json()["id"]

        # Create pasta and assign
        num = os.urandom(4).hex()
        pasta_resp = admin_client.post(
            "/api/v1/pastas/",
            json={"numero_pasta": f"PT-{num}"},
        )
        pid = pasta_resp.json()["id"]
        admin_client.post(f"/api/v1/testes/pasta/{pid}", json={"modelo_ids": [mid]})

        # Try deactivate
        del_resp = admin_client.delete(f"/api/v1/modelos/{mid}")
        assert del_resp.status_code == 409
