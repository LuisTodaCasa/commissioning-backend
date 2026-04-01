"""
Testes do módulo Execução de Testes (relatorios_execucao).

Cobre:
- Geração automática de relatórios quando templates são atribuídos
- CRUD de relatórios de execução
- Lógica de auto-fill
- Transições de status
- Sincronização individual e em lote
- Geração de relatórios quando linhas são adicionadas
- Estatísticas
- Permissões por role
"""
import os
import sys
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Garantir que o diretório raiz do projeto esteja no sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.security import get_current_user, require_roles
from app.main import app


# ── Mock Users ─────────────────────────────────────────────────────────

def _mock_admin_user():
    user = MagicMock()
    user.id = 1
    user.nome = "Admin Teste"
    user.email = "admin@test.com"
    user.role = "Administrador"
    user.ativo = True
    return user


def _mock_campo_user():
    user = MagicMock()
    user.id = 2
    user.nome = "Campo Teste"
    user.email = "campo@test.com"
    user.role = "Campo"
    user.ativo = True
    return user


def _mock_comissionamento_user():
    user = MagicMock()
    user.id = 3
    user.nome = "Comiss Teste"
    user.email = "comiss@test.com"
    user.role = "Comissionamento"
    user.ativo = True
    return user


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def admin_client():
    """Client autenticado como Administrador."""
    admin = _mock_admin_user()
    app.dependency_overrides[get_current_user] = lambda: admin
    # Override require_roles to return admin for any role
    original_require_roles = require_roles

    def mock_require_roles(roles):
        def dep():
            return admin
        return dep

    app.dependency_overrides[require_roles] = mock_require_roles
    # Patch require_roles at module level for decorators
    with patch("app.core.security.require_roles", mock_require_roles):
        client = TestClient(app)
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def campo_client():
    """Client autenticado como Campo."""
    campo = _mock_campo_user()
    app.dependency_overrides[get_current_user] = lambda: campo

    def mock_require_roles(roles):
        def dep():
            if "Campo" in roles or campo.role in roles:
                return campo
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Sem permissão")
        return dep

    with patch("app.core.security.require_roles", mock_require_roles):
        client = TestClient(app)
        yield client
    app.dependency_overrides.clear()


# ── Helpers ────────────────────────────────────────────────────────────

def _unique_id():
    return os.urandom(4).hex()


def _create_linha(client, suffix=""):
    """Criar uma linha de tubulação de teste."""
    uid = _unique_id()
    resp = client.post("/api/v1/linhas/", json={
        "numero_linha": f"L-{uid}{suffix}",
        "tag": f"TAG-{uid}",
        "malha": f"M-{uid}",
        "sistema": f"SIS-{uid}",
        "sop": f"SOP-{uid}",
        "sub_sop": f"SUB-{uid}",
        "sth": f"STH-{uid}",
        "pressao_teste": 150.5,
        "descricao_sistema": f"Sistema teste {uid}",
    })
    assert resp.status_code in (200, 201), f"Erro ao criar linha: {resp.text}"
    return resp.json()


def _create_pasta(client, suffix=""):
    """Criar uma pasta de teste."""
    uid = _unique_id()
    resp = client.post("/api/v1/pastas/", json={
        "numero_pasta": f"PT-{uid}{suffix}",
        "sth": f"STH-{uid}",
        "descricao_sistema": f"Pasta teste {uid}",
        "pressao_teste": 100.0,
    })
    assert resp.status_code in (200, 201), f"Erro ao criar pasta: {resp.text}"
    return resp.json()


def _create_modelo(client, suffix=""):
    """Criar um modelo/template de relatório."""
    uid = _unique_id()
    resp = client.post("/api/v1/modelos/", json={
        "nome": f"Template-{uid}{suffix}",
        "descricao": f"Template teste {uid}",
        "tipo": "teste_hidrostatico",
    })
    assert resp.status_code in (200, 201), f"Erro ao criar modelo: {resp.text}"
    return resp.json()


def _assign_linhas(client, pasta_id, linha_ids):
    """Atribuir linhas a uma pasta."""
    resp = client.post(f"/api/v1/pastas/{pasta_id}/linhas", json={
        "linha_ids": linha_ids,
    })
    assert resp.status_code == 200, f"Erro ao atribuir linhas: {resp.text}"
    return resp.json()


def _assign_testes(client, pasta_id, modelo_ids):
    """Atribuir templates a uma pasta."""
    resp = client.post(f"/api/v1/testes/pasta/{pasta_id}", json={
        "modelo_ids": modelo_ids,
    })
    assert resp.status_code == 200, f"Erro ao atribuir testes: {resp.text}"
    return resp.json()


# ── Test: Geração Automática de Relatórios ─────────────────────────────

class TestAutoGeneration:
    """Testes de geração automática de relatórios de execução."""

    def test_generate_reports_on_template_assignment(self, admin_client):
        """Quando templates são atribuídos, relatórios devem ser gerados para cada (linha, template)."""
        pasta = _create_pasta(admin_client)
        linha1 = _create_linha(admin_client, "-a")
        linha2 = _create_linha(admin_client, "-b")
        modelo1 = _create_modelo(admin_client, "-1")
        modelo2 = _create_modelo(admin_client, "-2")

        # Atribuir 2 linhas
        _assign_linhas(admin_client, pasta["id"], [linha1["id"], linha2["id"]])

        # Atribuir 2 templates → deve gerar 2×2 = 4 relatórios
        result = _assign_testes(admin_client, pasta["id"], [modelo1["id"], modelo2["id"]])
        assert result["relatorios_gerados"] == 4

        # Verificar que os relatórios existem
        resp = admin_client.get(f"/api/v1/execucao/pastas/{pasta['id']}/relatorios")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_relatorios"] == 4

    def test_no_duplicate_on_reassignment(self, admin_client):
        """Reatribuir mesmos templates não deve duplicar relatórios."""
        pasta = _create_pasta(admin_client)
        linha = _create_linha(admin_client)
        modelo = _create_modelo(admin_client)

        _assign_linhas(admin_client, pasta["id"], [linha["id"]])
        result1 = _assign_testes(admin_client, pasta["id"], [modelo["id"]])
        assert result1["relatorios_gerados"] == 1

        # Re-atribuir os mesmos
        result2 = _assign_testes(admin_client, pasta["id"], [modelo["id"]])
        assert result2["relatorios_gerados"] == 0
        assert result2["relatorios_existentes"] == 1

    def test_generate_reports_on_line_assignment(self, admin_client):
        """Quando linhas são adicionadas a uma pasta com templates, relatórios devem ser gerados."""
        pasta = _create_pasta(admin_client)
        modelo = _create_modelo(admin_client)
        linha1 = _create_linha(admin_client, "-first")

        # Atribuir template primeiro (sem linhas, 0 relatórios)
        _assign_linhas(admin_client, pasta["id"], [linha1["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo["id"]])

        # Agora adicionar nova linha → deve gerar relatório para ela
        linha2 = _create_linha(admin_client, "-second")
        result = _assign_linhas(admin_client, pasta["id"], [linha1["id"], linha2["id"]])
        assert result["relatorios_gerados"] == 1  # Apenas para a nova linha

    def test_generate_reports_manual(self, admin_client):
        """Endpoint manual de geração de relatórios."""
        pasta = _create_pasta(admin_client)
        linha = _create_linha(admin_client)
        modelo = _create_modelo(admin_client)

        _assign_linhas(admin_client, pasta["id"], [linha["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo["id"]])

        # Gerar manualmente (todos já existem)
        resp = admin_client.post(f"/api/v1/execucao/pastas/{pasta['id']}/gerar-relatorios")
        assert resp.status_code == 200
        data = resp.json()
        assert data["relatorios_existentes"] >= 1


# ── Test: Auto-fill ────────────────────────────────────────────────────

class TestAutoFill:
    """Testes da lógica de auto-preenchimento."""

    def test_auto_fill_fields_from_line(self, admin_client):
        """Dados da linha devem ser preenchidos automaticamente em dados_preenchidos.auto_filled."""
        pasta = _create_pasta(admin_client)
        linha = _create_linha(admin_client)
        modelo = _create_modelo(admin_client)

        _assign_linhas(admin_client, pasta["id"], [linha["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo["id"]])

        # Buscar relatórios e verificar auto_filled
        resp = admin_client.get(
            "/api/v1/execucao/relatorios",
            params={"pasta_id": pasta["id"]}
        )
        assert resp.status_code == 200
        relatorios = resp.json()
        assert len(relatorios) == 1

        rel = relatorios[0]
        assert rel["dados_preenchidos"] is not None
        auto_filled = rel["dados_preenchidos"]["auto_filled"]
        assert auto_filled["tag"] == linha["tag"]
        assert auto_filled["malha"] == linha["malha"]
        assert auto_filled["numero_linha"] == linha["numero_linha"]
        assert auto_filled["pressao_teste"] == linha["pressao_teste"]
        assert auto_filled["sop"] == linha["sop"]
        assert auto_filled["sth"] == linha["sth"]
        assert rel["dados_preenchidos"]["user_filled"] == {}


# ── Test: CRUD de Relatórios ───────────────────────────────────────────

class TestRelatorioCRUD:
    """Testes de CRUD de relatórios de execução."""

    def test_list_relatorios_filter_by_status(self, admin_client):
        """Filtrar relatórios por status."""
        pasta = _create_pasta(admin_client)
        linha = _create_linha(admin_client)
        modelo = _create_modelo(admin_client)

        _assign_linhas(admin_client, pasta["id"], [linha["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo["id"]])

        # Todos devem ser pendentes
        resp = admin_client.get("/api/v1/execucao/relatorios", params={"status": "pendente"})
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        # Nenhum em_execucao
        resp = admin_client.get(
            "/api/v1/execucao/relatorios",
            params={"status": "em_execucao", "pasta_id": pasta["id"]}
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_list_relatorios_filter_by_template(self, admin_client):
        """Filtrar relatórios por template_id."""
        pasta = _create_pasta(admin_client)
        linha = _create_linha(admin_client)
        modelo1 = _create_modelo(admin_client, "-t1")
        modelo2 = _create_modelo(admin_client, "-t2")

        _assign_linhas(admin_client, pasta["id"], [linha["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo1["id"], modelo2["id"]])

        resp = admin_client.get(
            "/api/v1/execucao/relatorios",
            params={"template_id": modelo1["id"], "pasta_id": pasta["id"]}
        )
        assert resp.status_code == 200
        relatorios = resp.json()
        assert len(relatorios) == 1
        assert relatorios[0]["template_id"] == modelo1["id"]

    def test_get_relatorio_detail(self, admin_client):
        """GET de detalhe deve incluir info da pasta, linha e template."""
        pasta = _create_pasta(admin_client)
        linha = _create_linha(admin_client)
        modelo = _create_modelo(admin_client)

        _assign_linhas(admin_client, pasta["id"], [linha["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo["id"]])

        # Buscar lista para obter ID
        resp = admin_client.get(
            "/api/v1/execucao/relatorios",
            params={"pasta_id": pasta["id"]}
        )
        rel_id = resp.json()[0]["id"]

        # Detalhe
        resp = admin_client.get(f"/api/v1/execucao/relatorios/{rel_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["pasta"] is not None
        assert detail["pasta"]["numero_pasta"] == pasta["numero_pasta"]
        assert detail["linha"] is not None
        assert detail["linha"]["tag"] == linha["tag"]
        assert detail["template"] is not None
        assert detail["template"]["nome"] == modelo["nome"]

    def test_get_relatorio_not_found(self, admin_client):
        resp = admin_client.get("/api/v1/execucao/relatorios/999999")
        assert resp.status_code == 404

    def test_update_relatorio_dados(self, admin_client):
        """Atualizar dados_preenchidos (merge user_filled)."""
        pasta = _create_pasta(admin_client)
        linha = _create_linha(admin_client)
        modelo = _create_modelo(admin_client)

        _assign_linhas(admin_client, pasta["id"], [linha["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo["id"]])

        resp = admin_client.get(
            "/api/v1/execucao/relatorios",
            params={"pasta_id": pasta["id"]}
        )
        rel_id = resp.json()[0]["id"]

        # Atualizar com dados do usuário
        resp = admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={
            "dados_preenchidos": {
                "user_filled": {
                    "pressao_inicial": 0,
                    "pressao_final": 150.5,
                    "tempo_teste": 30,
                    "resultado": "Aprovado",
                    "observacoes": "Teste OK",
                }
            }
        })
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["dados_preenchidos"]["user_filled"]["pressao_inicial"] == 0
        assert updated["dados_preenchidos"]["user_filled"]["resultado"] == "Aprovado"
        # auto_filled deve ser preservado
        assert updated["dados_preenchidos"]["auto_filled"]["tag"] == linha["tag"]

    def test_update_relatorio_merge_user_filled(self, admin_client):
        """Merge progressivo de user_filled."""
        pasta = _create_pasta(admin_client)
        linha = _create_linha(admin_client)
        modelo = _create_modelo(admin_client)

        _assign_linhas(admin_client, pasta["id"], [linha["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo["id"]])

        resp = admin_client.get("/api/v1/execucao/relatorios", params={"pasta_id": pasta["id"]})
        rel_id = resp.json()[0]["id"]

        # Primeiro update
        admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={
            "dados_preenchidos": {"user_filled": {"pressao_inicial": 10}}
        })

        # Segundo update (merge)
        resp = admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={
            "dados_preenchidos": {"user_filled": {"pressao_final": 150}}
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["dados_preenchidos"]["user_filled"]["pressao_inicial"] == 10
        assert data["dados_preenchidos"]["user_filled"]["pressao_final"] == 150


# ── Test: Transições de Status ─────────────────────────────────────────

class TestStatusTransitions:
    """Testes de validação de transições de status."""

    def _create_report(self, client):
        pasta = _create_pasta(client)
        linha = _create_linha(client)
        modelo = _create_modelo(client)
        _assign_linhas(client, pasta["id"], [linha["id"]])
        _assign_testes(client, pasta["id"], [modelo["id"]])
        resp = client.get("/api/v1/execucao/relatorios", params={"pasta_id": pasta["id"]})
        return resp.json()[0]["id"]

    def test_pendente_to_em_execucao(self, admin_client):
        rel_id = self._create_report(admin_client)
        resp = admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={
            "status": "em_execucao"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "em_execucao"

    def test_em_execucao_to_concluido(self, admin_client):
        rel_id = self._create_report(admin_client)
        admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={"status": "em_execucao"})
        resp = admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={"status": "concluido"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "concluido"
        assert resp.json()["data_execucao"] is not None
        assert resp.json()["usuario_execucao"] is not None

    def test_em_execucao_to_reprovado(self, admin_client):
        rel_id = self._create_report(admin_client)
        admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={"status": "em_execucao"})
        resp = admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={"status": "reprovado"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "reprovado"

    def test_concluido_cannot_go_back(self, admin_client):
        """Concluído é estado final - não pode voltar."""
        rel_id = self._create_report(admin_client)
        admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={"status": "em_execucao"})
        admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={"status": "concluido"})
        resp = admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={"status": "pendente"})
        assert resp.status_code == 400

    def test_pendente_to_concluido_invalid(self, admin_client):
        """Não pode pular de pendente direto para concluido."""
        rel_id = self._create_report(admin_client)
        resp = admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={"status": "concluido"})
        assert resp.status_code == 400

    def test_reprovado_to_em_execucao(self, admin_client):
        """Reprovado pode reabrir para nova execução."""
        rel_id = self._create_report(admin_client)
        admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={"status": "em_execucao"})
        admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={"status": "reprovado"})
        resp = admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={"status": "em_execucao"})
        assert resp.status_code == 200

    def test_invalid_status_value(self, admin_client):
        rel_id = self._create_report(admin_client)
        resp = admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={"status": "invalido"})
        assert resp.status_code == 400


# ── Test: Sincronização ────────────────────────────────────────────────

class TestSynchronization:
    """Testes de sincronização individual e em lote."""

    def _create_report(self, client):
        pasta = _create_pasta(client)
        linha = _create_linha(client)
        modelo = _create_modelo(client)
        _assign_linhas(client, pasta["id"], [linha["id"]])
        _assign_testes(client, pasta["id"], [modelo["id"]])
        resp = client.get("/api/v1/execucao/relatorios", params={"pasta_id": pasta["id"]})
        return resp.json()[0]["id"]

    def test_sincronizar_individual(self, admin_client):
        """Sincronizar um relatório individual."""
        rel_id = self._create_report(admin_client)

        # Mover para em_execucao primeiro
        admin_client.put(f"/api/v1/execucao/relatorios/{rel_id}", json={"status": "em_execucao"})

        resp = admin_client.post(f"/api/v1/execucao/relatorios/{rel_id}/sincronizar", json={
            "dados_preenchidos": {
                "user_filled": {"pressao_final": 150.0}
            },
            "status": "concluido",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["data_sincronizacao"] is not None
        assert data["status"] == "concluido"

    def test_sincronizar_lote(self, admin_client):
        """Sincronizar múltiplos relatórios em lote."""
        # Criar 2 relatórios
        pasta = _create_pasta(admin_client)
        linha1 = _create_linha(admin_client, "-s1")
        linha2 = _create_linha(admin_client, "-s2")
        modelo = _create_modelo(admin_client)

        _assign_linhas(admin_client, pasta["id"], [linha1["id"], linha2["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo["id"]])

        resp = admin_client.get("/api/v1/execucao/relatorios", params={"pasta_id": pasta["id"]})
        rel_ids = [r["id"] for r in resp.json()]
        assert len(rel_ids) == 2

        # Mover para em_execucao
        for rid in rel_ids:
            admin_client.put(f"/api/v1/execucao/relatorios/{rid}", json={"status": "em_execucao"})

        # Sincronizar em lote
        resp = admin_client.post("/api/v1/execucao/relatorios/sincronizar-lote", json={
            "relatorios": [
                {
                    "relatorio_id": rel_ids[0],
                    "dados_preenchidos": {"user_filled": {"resultado": "Aprovado"}},
                    "status": "concluido",
                },
                {
                    "relatorio_id": rel_ids[1],
                    "dados_preenchidos": {"user_filled": {"resultado": "Reprovado"}},
                    "status": "reprovado",
                },
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["sucesso"] == 2
        assert data["falhas"] == 0

    def test_sincronizar_lote_with_errors(self, admin_client):
        """Lote com alguns erros deve reportar falhas individuais."""
        rel_id = self._create_report(admin_client)

        resp = admin_client.post("/api/v1/execucao/relatorios/sincronizar-lote", json={
            "relatorios": [
                {
                    "relatorio_id": rel_id,
                    "status": "em_execucao",  # Valid
                },
                {
                    "relatorio_id": 999999,  # Não existe
                    "status": "concluido",
                },
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["sucesso"] == 1
        assert data["falhas"] == 1

    def test_sincronizar_not_found(self, admin_client):
        resp = admin_client.post("/api/v1/execucao/relatorios/999999/sincronizar", json={})
        assert resp.status_code == 404


# ── Test: Estatísticas ─────────────────────────────────────────────────

class TestStatistics:
    """Testes de estatísticas por pasta."""

    def test_stats_basic(self, admin_client):
        """Estatísticas devem retornar contagens corretas."""
        pasta = _create_pasta(admin_client)
        linha1 = _create_linha(admin_client, "-st1")
        linha2 = _create_linha(admin_client, "-st2")
        modelo = _create_modelo(admin_client)

        _assign_linhas(admin_client, pasta["id"], [linha1["id"], linha2["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo["id"]])

        resp = admin_client.get(f"/api/v1/execucao/pastas/{pasta['id']}/relatorios/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total_relatorios"] == 2
        assert stats["por_status"]["pendente"] == 2
        assert stats["percentual_conclusao"] == 0.0

    def test_stats_after_completion(self, admin_client):
        """Percentual de conclusão deve ser calculado corretamente."""
        pasta = _create_pasta(admin_client)
        linha1 = _create_linha(admin_client, "-sc1")
        linha2 = _create_linha(admin_client, "-sc2")
        modelo = _create_modelo(admin_client)

        _assign_linhas(admin_client, pasta["id"], [linha1["id"], linha2["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo["id"]])

        resp = admin_client.get("/api/v1/execucao/relatorios", params={"pasta_id": pasta["id"]})
        rel_ids = [r["id"] for r in resp.json()]

        # Concluir 1 de 2
        admin_client.put(f"/api/v1/execucao/relatorios/{rel_ids[0]}", json={"status": "em_execucao"})
        admin_client.put(f"/api/v1/execucao/relatorios/{rel_ids[0]}", json={"status": "concluido"})

        resp = admin_client.get(f"/api/v1/execucao/pastas/{pasta['id']}/relatorios/stats")
        stats = resp.json()
        assert stats["percentual_conclusao"] == 50.0
        assert stats["por_status"]["concluido"] == 1
        assert stats["por_status"]["pendente"] == 1

    def test_stats_pasta_not_found(self, admin_client):
        resp = admin_client.get("/api/v1/execucao/pastas/999999/relatorios/stats")
        assert resp.status_code == 404


# ── Test: Template Removal ─────────────────────────────────────────────

class TestTemplateRemoval:
    """Testes de remoção de templates e impacto em relatórios."""

    def test_remove_template_deletes_pending_reports(self, admin_client):
        """Remover template deve deletar relatórios pendentes."""
        pasta = _create_pasta(admin_client)
        linha = _create_linha(admin_client)
        modelo1 = _create_modelo(admin_client, "-r1")
        modelo2 = _create_modelo(admin_client, "-r2")

        _assign_linhas(admin_client, pasta["id"], [linha["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo1["id"], modelo2["id"]])

        # Verificar 2 relatórios
        resp = admin_client.get("/api/v1/execucao/relatorios", params={"pasta_id": pasta["id"]})
        assert len(resp.json()) == 2

        # Remover modelo1
        resp = admin_client.delete(f"/api/v1/testes/pasta/{pasta['id']}/{modelo1['id']}")
        assert resp.status_code == 200
        assert resp.json()["relatorios_pendentes_removidos"] == 1

        # Verificar que sobrou apenas 1
        resp = admin_client.get("/api/v1/execucao/relatorios", params={"pasta_id": pasta["id"]})
        assert len(resp.json()) == 1

    def test_reassign_templates_removes_pending_from_removed(self, admin_client):
        """Reatribuir templates deve remover pendentes dos templates removidos."""
        pasta = _create_pasta(admin_client)
        linha = _create_linha(admin_client)
        modelo1 = _create_modelo(admin_client, "-ra1")
        modelo2 = _create_modelo(admin_client, "-ra2")

        _assign_linhas(admin_client, pasta["id"], [linha["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo1["id"], modelo2["id"]])

        # Reatribuir apenas modelo2 (modelo1 removido)
        result = _assign_testes(admin_client, pasta["id"], [modelo2["id"]])

        # Verificar que só sobrou 1 relatório
        resp = admin_client.get("/api/v1/execucao/relatorios", params={"pasta_id": pasta["id"]})
        assert len(resp.json()) == 1
        assert resp.json()[0]["template_id"] == modelo2["id"]


# ── Test: Pasta Relatorios Grouped ─────────────────────────────────────

class TestPastaRelatorios:
    """Testes do endpoint de relatórios agrupados por pasta."""

    def test_grouped_by_template(self, admin_client):
        """Relatórios devem ser agrupados por template."""
        pasta = _create_pasta(admin_client)
        linha = _create_linha(admin_client)
        modelo1 = _create_modelo(admin_client, "-g1")
        modelo2 = _create_modelo(admin_client, "-g2")

        _assign_linhas(admin_client, pasta["id"], [linha["id"]])
        _assign_testes(admin_client, pasta["id"], [modelo1["id"], modelo2["id"]])

        resp = admin_client.get(f"/api/v1/execucao/pastas/{pasta['id']}/relatorios")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_relatorios"] == 2
        assert len(data["grupos"]) == 2

    def test_pasta_not_found(self, admin_client):
        resp = admin_client.get("/api/v1/execucao/pastas/999999/relatorios")
        assert resp.status_code == 404


# ── Test: Invalid Status Filter ────────────────────────────────────────

class TestValidation:
    """Testes de validação."""

    def test_invalid_status_filter(self, admin_client):
        resp = admin_client.get("/api/v1/execucao/relatorios", params={"status": "invalido"})
        assert resp.status_code == 400
