"""Modelos SQLAlchemy para o sistema de comissionamento."""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime,
    ForeignKey, Index, JSON, Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


# ── Enums ──────────────────────────────────────────────────────────────

class RoleEnum(str, enum.Enum):
    ADMINISTRADOR = "Administrador"
    ENGENHARIA = "Engenharia"
    COMISSIONAMENTO = "Comissionamento"
    CAMPO = "Campo"
    CQ = "CQ"


class StatusRelatorio(str, enum.Enum):
    RASCUNHO = "rascunho"
    PREENCHIDO = "preenchido"
    SINCRONIZADO = "sincronizado"
    APROVADO = "aprovado"
    REJEITADO = "rejeitado"


class StatusPasta(str, enum.Enum):
    CRIADA = "CRIADA"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDA = "CONCLUIDA"
    CANCELADA = "CANCELADA"


class StatusExecucao(str, enum.Enum):
    """Status de execução de relatório."""
    PENDENTE = "pendente"
    EM_EXECUCAO = "em_execucao"
    CONCLUIDO = "concluido"
    REPROVADO = "reprovado"


class TipoDocumento(str, enum.Enum):
    FLUXOGRAMA = "fluxograma"
    FLUXOTESTE = "fluxoteste"
    ISOMETRICO = "isometrico"
    LISTA_SUPORTES = "lista_suportes"
    MAPA_JUNTAS = "mapa_juntas"
    OUTRO = "outro"


class TipoModelo(str, enum.Enum):
    """Tipos de modelos/templates de relatório suportados."""
    TESTE_HIDROSTATICO = "teste_hidrostatico"
    DESCARGA_LINHA = "descarga_linha"
    FLUSH_LINE = "flush_line"
    TESTE_ESTANQUEIDADE = "teste_estanqueidade"
    CERTIFICADO_TESTE = "certificado_teste"


# ── Tabelas ────────────────────────────────────────────────────────────

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(200), nullable=False)
    email = Column(String(200), unique=True, nullable=False, index=True)
    senha_hash = Column(String(255), nullable=False)
    role = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.CAMPO)
    ativo = Column(Boolean, default=True)
    reset_token = Column(String(500), nullable=True)
    reset_token_expira = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    disciplinas = relationship("UsuarioDisciplina", back_populates="usuario", cascade="all, delete-orphan")


class Disciplina(Base):
    __tablename__ = "disciplinas"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), unique=True, nullable=False)
    descricao = Column(Text, nullable=True)
    ativo = Column(Boolean, default=True)

    # Relacionamentos
    usuarios = relationship("UsuarioDisciplina", back_populates="disciplina")


class UsuarioDisciplina(Base):
    __tablename__ = "usuario_disciplinas"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    disciplina_id = Column(Integer, ForeignKey("disciplinas.id", ondelete="CASCADE"), nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    usuario = relationship("Usuario", back_populates="disciplinas")
    disciplina = relationship("Disciplina", back_populates="usuarios")


class LinhaTubulacao(Base):
    __tablename__ = "linhas_tubulacao"

    id = Column(Integer, primary_key=True, index=True)
    numero_linha = Column(String(100), nullable=False)
    tag = Column(String(100), nullable=True)
    malha = Column(String(100), nullable=True)
    sistema = Column(String(200), nullable=True)
    sop = Column(String(50), nullable=True)
    sub_sop = Column(String(50), nullable=True)
    sth = Column(String(100), nullable=True)
    pressao_teste = Column(Float, nullable=True)
    descricao_sistema = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    pastas = relationship("PastaLinha", back_populates="linha")

    __table_args__ = (
        Index("ix_linhas_numero_linha", "numero_linha"),
        Index("ix_linhas_tag", "tag"),
        Index("ix_linhas_sth", "sth"),
    )


class PastaTeste(Base):
    __tablename__ = "pastas_teste"

    id = Column(Integer, primary_key=True, index=True)
    numero_pasta = Column(String(100), unique=True, nullable=False)
    sth = Column(String(100), nullable=True)
    descricao_sistema = Column(Text, nullable=True)
    pressao_teste = Column(Float, nullable=True)
    status = Column(SAEnum(StatusPasta), default=StatusPasta.CRIADA, nullable=False)
    data_criacao = Column(DateTime, nullable=True, doc="Data de criação da pasta de teste (informada pelo usuário)")
    criado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    sth_id = Column(Integer, ForeignKey("sths.id", ondelete="SET NULL"), nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    linhas = relationship("PastaLinha", back_populates="pasta", cascade="all, delete-orphan", lazy="selectin")
    documentos = relationship("DocumentoPasta", back_populates="pasta", cascade="all, delete-orphan", lazy="selectin")
    testes = relationship("PastaTeste_Teste", back_populates="pasta", cascade="all, delete-orphan", lazy="selectin")
    relatorios = relationship("Relatorio", back_populates="pasta", cascade="all, delete-orphan")
    criado_por = relationship("Usuario")
    sth_ref = relationship("STH", back_populates="pasta")

    __table_args__ = (
        Index("ix_pastas_teste_numero", "numero_pasta"),
        Index("ix_pastas_teste_sth", "sth"),
        Index("ix_pastas_teste_status", "status"),
    )


class PastaLinha(Base):
    __tablename__ = "pasta_linhas"

    id = Column(Integer, primary_key=True, index=True)
    pasta_id = Column(Integer, ForeignKey("pastas_teste.id", ondelete="CASCADE"), nullable=False)
    linha_id = Column(Integer, ForeignKey("linhas_tubulacao.id", ondelete="CASCADE"), nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    pasta = relationship("PastaTeste", back_populates="linhas")
    linha = relationship("LinhaTubulacao", back_populates="pastas", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("pasta_id", "linha_id", name="uq_pasta_linha"),
        Index("ix_pasta_linhas_pasta_id", "pasta_id"),
        Index("ix_pasta_linhas_linha_id", "linha_id"),
    )


class DocumentoPasta(Base):
    __tablename__ = "documentos_pasta"

    id = Column(Integer, primary_key=True, index=True)
    pasta_id = Column(Integer, ForeignKey("pastas_teste.id", ondelete="CASCADE"), nullable=False)
    tipo = Column(SAEnum(TipoDocumento), nullable=False)
    nome_arquivo = Column(String(500), nullable=False)
    caminho_arquivo = Column(String(1000), nullable=False)
    tamanho_bytes = Column(Integer, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    pasta = relationship("PastaTeste", back_populates="documentos")

    __table_args__ = (
        Index("ix_documentos_pasta_pasta_id", "pasta_id"),
    )


class ModeloRelatorio(Base):
    __tablename__ = "modelos_relatorio"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)
    tipo = Column(SAEnum(TipoModelo), nullable=False, doc="Tipo do modelo de relatório")
    arquivo_pdf = Column(String(1000), nullable=True, doc="Caminho do arquivo PDF template")
    # Alias mantido por compatibilidade — aponta para o mesmo dado
    caminho_template = Column(String(1000), nullable=True, doc="(deprecated) use arquivo_pdf")
    campos = Column(JSON, nullable=True, doc="Estrutura dos campos editáveis (legacy)")
    campos_template = Column(JSON, nullable=True, doc="Definições de campos do template para futuro preenchimento")
    data_criacao = Column(DateTime, default=datetime.utcnow, doc="Data de criação do template")
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    pasta_testes = relationship("PastaTeste_Teste", back_populates="modelo", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("nome", "tipo", name="uq_modelo_nome_tipo"),
        Index("ix_modelos_relatorio_tipo", "tipo"),
        Index("ix_modelos_relatorio_nome", "nome"),
    )


class PastaTeste_Teste(Base):
    """Associação entre pasta de teste e testes (quais testes serão executados)."""
    __tablename__ = "pasta_testes"

    id = Column(Integer, primary_key=True, index=True)
    pasta_id = Column(Integer, ForeignKey("pastas_teste.id", ondelete="CASCADE"), nullable=False)
    modelo_id = Column(Integer, ForeignKey("modelos_relatorio.id", ondelete="CASCADE"), nullable=False)
    ordem = Column(Integer, default=0)
    obrigatorio = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    pasta = relationship("PastaTeste", back_populates="testes")
    modelo = relationship("ModeloRelatorio", back_populates="pasta_testes", lazy="selectin")

    __table_args__ = (
        Index("ix_pasta_testes_pasta_id", "pasta_id"),
    )


class Relatorio(Base):
    __tablename__ = "relatorios"

    id = Column(Integer, primary_key=True, index=True)
    pasta_id = Column(Integer, ForeignKey("pastas_teste.id", ondelete="CASCADE"), nullable=False)
    modelo_id = Column(Integer, ForeignKey("modelos_relatorio.id", ondelete="CASCADE"), nullable=False)
    linha_id = Column(Integer, ForeignKey("linhas_tubulacao.id"), nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    # Dados preenchidos automaticamente (da linha de tubulação)
    dados_linha = Column(JSON, nullable=True)

    # Dados preenchidos pelo usuário de campo
    dados_execucao = Column(JSON, nullable=True)
    # Campos individuais comuns para consulta rápida
    pressao_inicial = Column(Float, nullable=True)
    pressao_final = Column(Float, nullable=True)
    tempo_teste = Column(Float, nullable=True)
    resultado = Column(String(100), nullable=True)
    observacoes = Column(Text, nullable=True)

    status = Column(SAEnum(StatusRelatorio), default=StatusRelatorio.RASCUNHO)
    sincronizado = Column(Boolean, default=False)
    sincronizado_em = Column(DateTime, nullable=True)
    offline_id = Column(String(200), nullable=True)  # ID local do dispositivo offline

    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    pasta = relationship("PastaTeste", back_populates="relatorios")
    modelo = relationship("ModeloRelatorio")
    linha = relationship("LinhaTubulacao")
    usuario = relationship("Usuario")

    __table_args__ = (
        Index("ix_relatorios_pasta_id", "pasta_id"),
    )


# ── Módulo Tubulação (STH / Spools) ──────────────────────────────────

class STH(Base):
    """Sistema Técnico de Teste Hidrostático."""
    __tablename__ = "sths"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(150), unique=True, nullable=False, index=True)
    sop = Column(String(50), nullable=True)
    sub_sop = Column(String(50), nullable=True)
    descricao = Column(Text, nullable=True)
    status = Column(String(50), default="ATIVO")
    criado_em = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    sth_linhas = relationship("STHLinha", back_populates="sth", cascade="all, delete-orphan", lazy="selectin")
    spools = relationship("Spool", back_populates="sth", cascade="all, delete-orphan", lazy="selectin")
    pasta = relationship("PastaTeste", back_populates="sth_ref", uselist=False)


class LinhaTubulacaoCatalogo(Base):
    """Catálogo de linhas de tubulação (importado da planilha)."""
    __tablename__ = "linhas_tubulacao_catalogo"

    id = Column(Integer, primary_key=True, index=True)
    numero_linha = Column(String(150), unique=True, nullable=False, index=True)
    fluido = Column(String(50), nullable=True)
    descricao_fluido = Column(Text, nullable=True)
    pressao_teste = Column(Float, nullable=True)
    pressao_operacao = Column(Float, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    # Relacionamentos
    sth_linhas = relationship("STHLinha", back_populates="linha_cat", lazy="selectin")
    spools = relationship("Spool", back_populates="linha_cat", lazy="selectin")


class STHLinha(Base):
    """Relacionamento muitos-para-muitos entre STH e Linhas do catálogo."""
    __tablename__ = "sth_linhas"

    id = Column(Integer, primary_key=True, index=True)
    sth_id = Column(Integer, ForeignKey("sths.id", ondelete="CASCADE"), nullable=False)
    linha_id = Column(Integer, ForeignKey("linhas_tubulacao_catalogo.id", ondelete="CASCADE"), nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)

    sth = relationship("STH", back_populates="sth_linhas")
    linha_cat = relationship("LinhaTubulacaoCatalogo", back_populates="sth_linhas")

    __table_args__ = (
        UniqueConstraint("sth_id", "linha_id", name="uq_sth_linha"),
    )


class Spool(Base):
    """Spool de tubulação pertencente a um STH e uma linha."""
    __tablename__ = "spools"

    id = Column(Integer, primary_key=True, index=True)
    sth_id = Column(Integer, ForeignKey("sths.id", ondelete="CASCADE"), nullable=False)
    linha_id = Column(Integer, ForeignKey("linhas_tubulacao_catalogo.id", ondelete="CASCADE"), nullable=False)
    codigo_spool = Column(String(150), nullable=False)
    origem = Column(String(150), nullable=True)
    destino = Column(String(150), nullable=True)
    isometrico_ref = Column(String(200), nullable=True)
    fluxograma = Column(String(500), nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    sth = relationship("STH", back_populates="spools")
    linha_cat = relationship("LinhaTubulacaoCatalogo", back_populates="spools")

    __table_args__ = (
        UniqueConstraint("sth_id", "codigo_spool", name="uq_sth_spool"),
        Index("ix_spools_sth_id", "sth_id"),
        Index("ix_spools_linha_id", "linha_id"),
    )


class DocumentoLinha(Base):
    """Documento PDF associado a uma linha dentro de um STH (isométrico, fluxograma, etc.)."""
    __tablename__ = "documentos_linha"

    id = Column(Integer, primary_key=True, index=True)
    sth_id = Column(Integer, ForeignKey("sths.id", ondelete="CASCADE"), nullable=False)
    linha_id = Column(Integer, ForeignKey("linhas_tubulacao_catalogo.id", ondelete="CASCADE"), nullable=False)
    tipo_documento = Column(SAEnum(TipoDocumento), nullable=False)
    nome_arquivo = Column(String(500), nullable=True, doc="Nome original do arquivo PDF")
    caminho_arquivo = Column(String(1000), nullable=True, doc="Caminho no sistema de arquivos")
    tamanho_bytes = Column(Integer, nullable=True)
    numero_documento = Column(String(200), nullable=True, doc="Número/referência do documento (ex: código do isométrico)")
    uploaded_by_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    ativo = Column(Boolean, default=True)
    data_upload = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    sth = relationship("STH", backref="documentos_linha")
    linha_cat = relationship("LinhaTubulacaoCatalogo", backref="documentos_linha")
    uploaded_by = relationship("Usuario")

    __table_args__ = (
        Index("ix_doc_linha_sth_id", "sth_id"),
        Index("ix_doc_linha_linha_id", "linha_id"),
        Index("ix_doc_linha_tipo", "tipo_documento"),
        Index("ix_doc_linha_sth_linha_tipo", "sth_id", "linha_id", "tipo_documento"),
    )


class RelatorioExecucao(Base):
    """Relatório de execução de testes - gerado automaticamente para cada combinação (linha, template) em uma pasta."""
    __tablename__ = "relatorios_execucao"

    id = Column(Integer, primary_key=True, index=True)
    pasta_id = Column(Integer, ForeignKey("pastas_teste.id", ondelete="CASCADE"), nullable=False)
    linha_id = Column(Integer, ForeignKey("linhas_tubulacao.id", ondelete="CASCADE"), nullable=False)
    template_id = Column(Integer, ForeignKey("modelos_relatorio.id", ondelete="CASCADE"), nullable=False)

    dados_preenchidos = Column(JSON, nullable=True, doc="Dados preenchidos (auto_filled + user_filled)")
    status = Column(
        SAEnum(StatusExecucao),
        default=StatusExecucao.PENDENTE,
        nullable=False,
        doc="Status: pendente, em_execucao, concluido, reprovado"
    )

    data_execucao = Column(DateTime, nullable=True, doc="Data em que o teste foi executado")
    usuario_execucao = Column(String(200), nullable=True, doc="Usuário que executou o teste")
    data_sincronizacao = Column(DateTime, nullable=True, doc="Data da última sincronização offline")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    pasta = relationship("PastaTeste", backref="relatorios_execucao")
    linha = relationship("LinhaTubulacao")
    template = relationship("ModeloRelatorio")

    __table_args__ = (
        UniqueConstraint("pasta_id", "linha_id", "template_id", name="uq_execucao_pasta_linha_template"),
        Index("ix_relatorios_execucao_pasta_id", "pasta_id"),
        Index("ix_relatorios_execucao_status", "status"),
        Index("ix_relatorios_execucao_template_id", "template_id"),
    )
