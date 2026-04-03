"""Schemas Pydantic para validação de dados da API."""
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, EmailStr, Field


# ── Auth ───────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    senha: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: "UsuarioResponse"

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    nova_senha: str = Field(min_length=6)


# ── Usuário ────────────────────────────────────────────────────────────

class UsuarioCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=200)
    email: EmailStr
    senha: str = Field(min_length=6)
    role: str = "Campo"

class UsuarioUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    ativo: Optional[bool] = None

class UsuarioResponse(BaseModel):
    id: int
    nome: str
    email: str
    role: str
    ativo: bool
    criado_em: datetime
    disciplinas: List["DisciplinaSimples"] = []

    class Config:
        from_attributes = True


# ── Disciplina ─────────────────────────────────────────────────────────

class DisciplinaSimples(BaseModel):
    id: int
    nome: str
    class Config:
        from_attributes = True

class DisciplinaResponse(BaseModel):
    id: int
    nome: str
    descricao: Optional[str] = None
    ativo: bool
    class Config:
        from_attributes = True

class AssignDisciplinasRequest(BaseModel):
    disciplina_ids: List[int]


# ── Linha de Tubulação ─────────────────────────────────────────────────

class LinhaCreate(BaseModel):
    numero_linha: str
    tag: Optional[str] = None
    malha: Optional[str] = None
    sistema: Optional[str] = None
    sop: Optional[str] = None
    sub_sop: Optional[str] = None
    sth: Optional[str] = None
    pressao_teste: Optional[float] = None
    descricao_sistema: Optional[str] = None

class LinhaResponse(BaseModel):
    id: int
    numero_linha: str
    tag: Optional[str] = None
    malha: Optional[str] = None
    sistema: Optional[str] = None
    sop: Optional[str] = None
    sub_sop: Optional[str] = None
    sth: Optional[str] = None
    pressao_teste: Optional[float] = None
    descricao_sistema: Optional[str] = None
    criado_em: datetime

    class Config:
        from_attributes = True

class ImportResult(BaseModel):
    total_linhas: int
    importadas: int
    duplicadas: int = 0
    falhas: int = 0
    erros: List[str] = []


# ── Pasta de Teste ─────────────────────────────────────────────────────

class PastaCreate(BaseModel):
    """Criar uma nova pasta de teste."""
    numero_pasta: str = Field(..., min_length=1, description="Número único da pasta de teste")
    sth: Optional[str] = Field(None, description="STH da pasta")
    descricao_sistema: Optional[str] = Field(None, description="Descrição do sistema")
    pressao_teste: Optional[float] = Field(None, gt=0, description="Pressão de teste (deve ser positiva)")
    data_criacao: Optional[datetime] = Field(None, description="Data de criação da pasta")

class PastaUpdate(BaseModel):
    """Atualizar uma pasta de teste existente."""
    numero_pasta: Optional[str] = Field(None, min_length=1, description="Número único da pasta")
    sth: Optional[str] = None
    descricao_sistema: Optional[str] = None
    pressao_teste: Optional[float] = Field(None, gt=0, description="Pressão de teste (deve ser positiva)")
    status: Optional[str] = Field(None, description="Status: CRIADA, EM_ANDAMENTO, CONCLUIDA, CANCELADA")
    data_criacao: Optional[datetime] = None

class PastaLinhaAssign(BaseModel):
    """Atribuir linhas de tubulação a uma pasta."""
    linha_ids: List[int] = Field(..., min_length=1, description="Lista de IDs das linhas a atribuir")

class PastaResponse(BaseModel):
    """Resposta com dados básicos da pasta e linhas associadas."""
    id: int
    numero_pasta: str
    sth: Optional[str] = None
    descricao_sistema: Optional[str] = None
    pressao_teste: Optional[float] = None
    status: str
    data_criacao: Optional[datetime] = None
    criado_em: datetime
    atualizado_em: Optional[datetime] = None
    linhas: List[LinhaResponse] = []
    total_documentos: int = 0
    total_testes: int = 0
    total_relatorios: int = 0

    class Config:
        from_attributes = True

class PastaListResponse(BaseModel):
    """Resposta resumida para listagem de pastas."""
    id: int
    numero_pasta: str
    sth: Optional[str] = None
    descricao_sistema: Optional[str] = None
    pressao_teste: Optional[float] = None
    status: str
    data_criacao: Optional[datetime] = None
    total_linhas: int = 0
    total_documentos: int = 0
    total_testes: int = 0
    total_relatorios: int = 0
    criado_em: datetime

    class Config:
        from_attributes = True


# ── Documento ──────────────────────────────────────────────────────────

class DocumentoResponse(BaseModel):
    """Resposta com dados do documento PDF."""
    id: int
    pasta_id: int
    tipo: str
    nome_arquivo: str
    tamanho_bytes: Optional[int] = None
    download_url: Optional[str] = None
    criado_em: datetime

    class Config:
        from_attributes = True


# ── Documento de Linha (STH) ────────────────────────────────────────────

class DocumentoLinhaResponse(BaseModel):
    """Resposta com dados do documento de linha."""
    id: int
    sth_id: int
    linha_id: int
    tipo_documento: str
    nome_arquivo: Optional[str] = None
    tamanho_bytes: Optional[int] = None
    numero_documento: Optional[str] = None
    uploaded_by_id: Optional[int] = None
    ativo: bool = True
    download_url: Optional[str] = None
    data_upload: Optional[datetime] = None
    criado_em: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentoLinhaStatusItem(BaseModel):
    """Status de documentos para uma linha específica."""
    linha_id: int
    numero_linha: str
    documentos_esperados: List[str] = []
    documentos_enviados: List[str] = []
    documentos_pendentes: List[str] = []
    percentual: float = 0.0


class DocumentoLinhaStatusResponse(BaseModel):
    """Status geral de documentos de um STH."""
    sth_id: int
    codigo_sth: str
    total_esperados: int = 0
    total_enviados: int = 0
    percentual_geral: float = 0.0
    linhas: List[DocumentoLinhaStatusItem] = []


# ── Pasta Detalhada (com documentos e templates) ──────────────────────

class PastaTesteDetail(BaseModel):
    """Resposta completa da pasta com todas as associações."""
    id: int
    numero_pasta: str
    sth: Optional[str] = None
    sth_id: Optional[int] = None
    descricao_sistema: Optional[str] = None
    pressao_teste: Optional[float] = None
    status: str
    disciplina: Optional[str] = None
    data_criacao: Optional[datetime] = None
    criado_em: datetime
    atualizado_em: Optional[datetime] = None
    linhas: List[LinhaResponse] = []
    documentos: List[DocumentoResponse] = []
    testes: List["PastaTesteResponse"] = []
    total_relatorios: int = 0
    spools: List[dict] = []

    class Config:
        from_attributes = True


# ── Modelo de Relatório / Template ─────────────────────────────────────

# Tipos de modelo válidos
TIPOS_MODELO_VALIDOS = [
    "teste_hidrostatico", "descarga_linha", "flush_line",
    "teste_estanqueidade", "certificado_teste",
]

# Campos auto-preenchidos a partir dos dados da linha de tubulação
AUTO_FILL_FIELDS = [
    "tag", "malha", "numero_linha", "sop", "sub_sop",
    "sth", "pressao_teste", "descricao_sistema",
]


class CampoTemplate(BaseModel):
    """Definição de um campo de template para futuro preenchimento."""
    nome_campo: str = Field(..., description="Nome identificador do campo")
    tipo_campo: str = Field("text", description="Tipo do campo: text, number, date, select, textarea")
    label: Optional[str] = Field(None, description="Rótulo de exibição do campo")
    obrigatorio: bool = Field(False, description="Se o campo é obrigatório")
    auto_fill: bool = Field(False, description="Se o campo é preenchido automaticamente a partir de dados da linha")
    opcoes: Optional[List[str]] = Field(None, description="Opções para campos tipo select")
    valor_padrao: Optional[str] = Field(None, description="Valor padrão do campo")

    class Config:
        json_schema_extra = {
            "example": {
                "nome_campo": "pressao_teste",
                "tipo_campo": "number",
                "label": "Pressão de Teste (kgf/cm²)",
                "obrigatorio": True,
                "auto_fill": True,
            }
        }


class CamposTemplateRequest(BaseModel):
    """Request para configurar campos de um template."""
    campos: List[CampoTemplate] = Field(..., description="Lista de definições de campos")


class ModeloCreate(BaseModel):
    """Criar um novo modelo/template de relatório (sem upload de PDF)."""
    nome: str = Field(..., min_length=1, max_length=200, description="Nome do template")
    descricao: Optional[str] = Field(None, description="Descrição do template")
    tipo: str = Field(..., description="Tipo: teste_hidrostatico, descarga_linha, flush_line, teste_estanqueidade, certificado_teste")
    campos: Optional[Dict[str, Any]] = Field(None, description="Campos editáveis (legacy)")
    campos_template: Optional[List[CampoTemplate]] = Field(None, description="Definições de campos do template")


class ModeloUpdate(BaseModel):
    """Atualizar metadados de um modelo/template."""
    nome: Optional[str] = Field(None, min_length=1, max_length=200, description="Nome do template")
    descricao: Optional[str] = None
    tipo: Optional[str] = Field(None, description="Tipo do modelo")
    campos: Optional[Dict[str, Any]] = None
    campos_template: Optional[List[CampoTemplate]] = None
    ativo: Optional[bool] = None


class ModeloResponse(BaseModel):
    """Resposta com dados do modelo/template."""
    id: int
    nome: str
    descricao: Optional[str] = None
    tipo: str
    arquivo_pdf: Optional[str] = None
    caminho_template: Optional[str] = None
    campos: Optional[Dict[str, Any]] = None
    ativo: bool
    data_criacao: Optional[datetime] = None
    criado_em: datetime
    atualizado_em: Optional[datetime] = None
    download_url: Optional[str] = None
    total_pastas_usando: int = 0

    class Config:
        from_attributes = True


class ModeloDetail(BaseModel):
    """Resposta detalhada do modelo com configuração de campos."""
    id: int
    nome: str
    descricao: Optional[str] = None
    tipo: str
    arquivo_pdf: Optional[str] = None
    caminho_template: Optional[str] = None
    campos: Optional[Dict[str, Any]] = None
    campos_template: Optional[List[CampoTemplate]] = None
    ativo: bool
    data_criacao: Optional[datetime] = None
    criado_em: datetime
    atualizado_em: Optional[datetime] = None
    download_url: Optional[str] = None
    total_pastas_usando: int = 0

    class Config:
        from_attributes = True


# ── Pasta Testes (Assignment) ──────────────────────────────────────────

class AssignTestesRequest(BaseModel):
    modelo_ids: List[int]

class PastaTesteResponse(BaseModel):
    id: int
    pasta_id: int
    modelo_id: int
    ordem: int
    obrigatorio: bool
    modelo: Optional[ModeloResponse] = None
    criado_em: datetime

    class Config:
        from_attributes = True


# ── Relatório ──────────────────────────────────────────────────────────

class RelatorioCreate(BaseModel):
    pasta_id: int
    modelo_id: int
    linha_id: Optional[int] = None
    dados_execucao: Optional[Dict[str, Any]] = None
    pressao_inicial: Optional[float] = None
    pressao_final: Optional[float] = None
    tempo_teste: Optional[float] = None
    resultado: Optional[str] = None
    observacoes: Optional[str] = None
    status: str = "rascunho"
    offline_id: Optional[str] = None

class RelatorioUpdate(BaseModel):
    dados_execucao: Optional[Dict[str, Any]] = None
    pressao_inicial: Optional[float] = None
    pressao_final: Optional[float] = None
    tempo_teste: Optional[float] = None
    resultado: Optional[str] = None
    observacoes: Optional[str] = None
    status: Optional[str] = None

class RelatorioResponse(BaseModel):
    id: int
    pasta_id: int
    modelo_id: int
    linha_id: Optional[int] = None
    usuario_id: Optional[int] = None
    dados_linha: Optional[Dict[str, Any]] = None
    dados_execucao: Optional[Dict[str, Any]] = None
    pressao_inicial: Optional[float] = None
    pressao_final: Optional[float] = None
    tempo_teste: Optional[float] = None
    resultado: Optional[str] = None
    observacoes: Optional[str] = None
    status: str
    sincronizado: bool
    sincronizado_em: Optional[datetime] = None
    offline_id: Optional[str] = None
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True


# ── Sync ───────────────────────────────────────────────────────────────

class SyncDownloadResponse(BaseModel):
    pasta: PastaResponse
    documentos: List[DocumentoResponse] = []
    testes: List[PastaTesteResponse] = []
    relatorios: List[RelatorioResponse] = []

class SyncUploadRequest(BaseModel):
    relatorios: List[RelatorioCreate]

class SyncStatusResponse(BaseModel):
    total_relatorios: int
    sincronizados: int
    pendentes: int
    ultima_sincronizacao: Optional[datetime] = None


# ── Dashboard ──────────────────────────────────────────────────────────

class DashboardResponse(BaseModel):
    total_pastas: int = 0
    pastas_abertas: int = 0
    pastas_concluidas: int = 0
    total_linhas: int = 0
    total_relatorios: int = 0
    relatorios_rascunho: int = 0
    relatorios_preenchidos: int = 0
    relatorios_aprovados: int = 0
    relatorios_pendentes_sync: int = 0
    total_usuarios: int = 0


# ── Relatório de Execução (Execução de Testes) ────────────────────────

STATUS_EXECUCAO_VALIDOS = ["pendente", "em_execucao", "concluido", "reprovado"]

# Transições de status permitidas
TRANSICOES_STATUS_EXECUCAO = {
    "pendente": ["em_execucao"],
    "em_execucao": ["concluido", "reprovado", "pendente"],
    "concluido": [],        # Estado final - não pode voltar
    "reprovado": ["em_execucao"],  # Pode reabrir para nova execução
}


class RelatorioExecucaoResponse(BaseModel):
    """Resposta de relatório de execução."""
    id: int
    pasta_id: int
    linha_id: int
    template_id: int
    dados_preenchidos: Optional[Dict[str, Any]] = None
    status: str
    data_execucao: Optional[datetime] = None
    usuario_execucao: Optional[str] = None
    data_sincronizacao: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RelatorioExecucaoDetail(BaseModel):
    """Resposta detalhada do relatório de execução com informações associadas."""
    id: int
    pasta_id: int
    linha_id: int
    template_id: int
    dados_preenchidos: Optional[Dict[str, Any]] = None
    status: str
    data_execucao: Optional[datetime] = None
    usuario_execucao: Optional[str] = None
    data_sincronizacao: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Nested info
    pasta: Optional[Dict[str, Any]] = Field(None, description="Informações da pasta de teste")
    linha: Optional[Dict[str, Any]] = Field(None, description="Informações da linha de tubulação")
    template: Optional[Dict[str, Any]] = Field(None, description="Informações do template/modelo")

    class Config:
        from_attributes = True


class RelatorioExecucaoUpdate(BaseModel):
    """Atualizar relatório de execução (preenchimento de dados pelo técnico de campo)."""
    dados_preenchidos: Optional[Dict[str, Any]] = Field(
        None, description="Dados preenchidos pelo usuário (merge com existentes)"
    )
    status: Optional[str] = Field(
        None, description="Novo status: pendente, em_execucao, concluido, reprovado"
    )


class RelatorioExecucaoStats(BaseModel):
    """Estatísticas de relatórios de execução para uma pasta."""
    total_relatorios: int = 0
    por_status: Dict[str, int] = Field(default_factory=dict, description="Contagem por status")
    percentual_conclusao: float = Field(0.0, description="Percentual de relatórios concluídos")
    por_template: List[Dict[str, Any]] = Field(default_factory=list, description="Relatórios agrupados por template")
    ultima_sincronizacao: Optional[datetime] = None


class SincronizacaoExecucaoRequest(BaseModel):
    """Request de sincronização de um relatório de execução."""
    dados_preenchidos: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class SincronizacaoLoteItem(BaseModel):
    """Item individual para sincronização em lote."""
    relatorio_id: int
    dados_preenchidos: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class SincronizacaoLoteRequest(BaseModel):
    """Request de sincronização em lote."""
    relatorios: List[SincronizacaoLoteItem] = Field(..., description="Lista de relatórios para sincronizar")


class SincronizacaoLoteResultItem(BaseModel):
    """Resultado individual de sincronização em lote."""
    relatorio_id: int
    sucesso: bool
    mensagem: str


class SincronizacaoLoteResponse(BaseModel):
    """Resposta de sincronização em lote."""
    total: int
    sucesso: int
    falhas: int
    resultados: List[SincronizacaoLoteResultItem]


class GeracaoRelatoriosResponse(BaseModel):
    """Resposta da geração automática de relatórios."""
    mensagem: str
    total_gerados: int
    total_linhas: int
    total_templates: int
    relatorios_existentes: int = 0


# ── Tubulação (STH / Spools) ────────────────────────────────────────────

class SpoolResponse(BaseModel):
    """Resposta com dados de um spool."""
    id: int
    codigo_spool: str
    origem: Optional[str] = None
    destino: Optional[str] = None
    isometrico_ref: Optional[str] = None
    fluxograma: Optional[str] = None
    linha_numero: Optional[str] = None
    criado_em: Optional[datetime] = None

    class Config:
        from_attributes = True


class LinhaCatalogoResponse(BaseModel):
    """Resposta com dados de uma linha do catálogo."""
    id: int
    numero_linha: str
    fluido: Optional[str] = None
    descricao_fluido: Optional[str] = None
    pressao_teste: Optional[float] = None
    pressao_operacao: Optional[float] = None
    total_spools: int = 0

    class Config:
        from_attributes = True


class STHListResponse(BaseModel):
    """Resposta resumida para listagem de STHs."""
    id: int
    codigo_sth: str
    sop: Optional[str] = None
    ssop: Optional[str] = None
    descricao: Optional[str] = None
    total_linhas: int = 0
    total_spools: int = 0
    pasta_id: Optional[int] = None
    criado_em: Optional[datetime] = None

    class Config:
        from_attributes = True


class STHDetailResponse(BaseModel):
    """Resposta detalhada de um STH com linhas e spools."""
    id: int
    codigo_sth: str
    sop: Optional[str] = None
    ssop: Optional[str] = None
    descricao: Optional[str] = None
    pasta_id: Optional[int] = None
    pasta_numero: Optional[str] = None
    linhas: List[LinhaCatalogoResponse] = []
    spools: List[SpoolResponse] = []
    criado_em: Optional[datetime] = None

    class Config:
        from_attributes = True


class ImportacaoExcelResponse(BaseModel):
    """Resposta da importação de planilha Excel."""
    mensagem: str
    total_sths: int = 0
    total_linhas: int = 0
    total_spools: int = 0
    erros: List[str] = []


class CriarPastaPorSTHRequest(BaseModel):
    """Criar pasta de teste a partir de um STH."""
    sth_id: int = Field(..., description="ID do STH")
    numero_pasta: str = Field(..., min_length=1, description="Número da pasta de teste")
    data_criacao: Optional[datetime] = Field(None, description="Data de criação da pasta")
    # Dados opcionais do STH para criação automática se não existir
    codigo_sth: Optional[str] = Field(None, description="Código do STH")
    descricao: Optional[str] = Field(None, description="Descrição do STH")
    sop: Optional[str] = Field(None, description="SOP do STH")
    ssop: Optional[str] = Field(None, description="Sub-SOP do STH")


# Resolve forward refs
UsuarioResponse.model_rebuild()
TokenResponse.model_rebuild()
PastaTesteDetail.model_rebuild()
