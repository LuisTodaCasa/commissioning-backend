# Sistema de Comissionamento - Backend API

Backend FastAPI para o Sistema de Pastas de Teste de Comissionamento Industrial.

## 📋 Funcionalidades

- **Autenticação JWT** com controle de acesso por roles (5 perfis)
- **Gestão de Usuários** e permissões por disciplina (8 disciplinas)
- **Importação Excel** de linhas de tubulação
- **CRUD de Pastas de Teste** com associação de linhas
- **Upload de Documentos PDF** (fluxograma, isométrico, etc.)
- **Templates de Relatório** com detecção automática de campos PDF
- **Relatórios de Campo** com auto-preenchimento de dados
- **Sincronização Offline** para uso em tablet/campo
- **Dashboard** com estatísticas gerais

## 🏗️ Estrutura do Projeto

```
commissioning_system_backend/
├── app/
│   ├── core/           # Configuração, banco, segurança, logging
│   ├── models/         # Modelos SQLAlchemy
│   ├── schemas/        # Schemas Pydantic (validação)
│   ├── routers/        # Endpoints da API
│   ├── services/       # Lógica de negócio
│   ├── utils/          # Utilitários (e-mail, etc.)
│   └── main.py         # Ponto de entrada FastAPI
├── alembic/            # Migrações de banco
├── uploads/            # Armazenamento de PDFs
├── seed.py             # Dados iniciais (disciplinas + admin)
├── requirements.txt
├── .env.example
└── README.md
```

## 🚀 Instalação

### 1. Pré-requisitos
- Python 3.10+
- PostgreSQL 14+

### 2. Configurar ambiente

```bash
cd commissioning_system_backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Editar .env com suas configurações de banco, SMTP, etc.
```

### 4. Criar banco de dados

```bash
createdb commissioning_db
# Ou via psql: CREATE DATABASE commissioning_db;
```

### 5. Executar migrações

```bash
# Gerar migração inicial
alembic revision --autogenerate -m "initial"
alembic upgrade head

# Ou deixar o FastAPI criar as tabelas automaticamente (dev)
```

### 6. Popular dados iniciais

```bash
python seed.py
```

### 7. Iniciar servidor

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 📚 Documentação da API

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 👥 Roles de Usuário

| Role | Permissões |
|------|-----------|
| **Administrador** | Gestão completa de usuários, disciplinas, templates |
| **Engenharia** | Importar dados, programar testes |
| **Comissionamento** | Criar pastas, atribuir linhas e testes |
| **Campo** | Executar testes, preencher relatórios, uso offline |
| **CQ** | Revisar e aprovar relatórios |

## 🔧 Endpoints Principais

| Módulo | Prefixo | Descrição |
|--------|---------|-----------|
| Auth | `/api/v1/auth` | Login, registro, reset de senha |
| Usuários | `/api/v1/usuarios` | CRUD de usuários e disciplinas |
| Disciplinas | `/api/v1/disciplinas` | Listar disciplinas |
| Linhas | `/api/v1/linhas` | CRUD e importação Excel |
| Pastas | `/api/v1/pastas` | CRUD de pastas de teste |
| Documentos | `/api/v1/documentos` | Upload/download de PDFs |
| Modelos | `/api/v1/modelos` | Templates de relatório |
| Testes | `/api/v1/testes` | Atribuição de testes a pastas |
| Relatórios | `/api/v1/relatorios` | CRUD de relatórios de campo |
| Sync | `/api/v1/sync` | Sincronização offline |
| Dashboard | `/api/v1/dashboard` | Estatísticas gerais |

## 🔐 Autenticação

Todas as rotas (exceto login/register) requerem token JWT no header:
```
Authorization: Bearer <token>
```

### Login padrão (após seed):
- **Email:** admin@consorciouhn.com.br
- **Senha:** admin123

## 📊 Tabelas do Banco

- `usuarios` - Usuários do sistema
- `disciplinas` - 8 disciplinas de comissionamento
- `usuario_disciplinas` - Permissões de disciplina por usuário
- `linhas_tubulacao` - Dados importados do Excel
- `pastas_teste` - Pastas de teste de comissionamento
- `pasta_linhas` - Associação pasta ↔ linhas
- `documentos_pasta` - PDFs das pastas
- `modelos_relatorio` - Templates de relatório
- `pasta_testes` - Testes atribuídos a pastas
- `relatorios` - Relatórios de campo preenchidos

## 🌐 CORS

Configurado para aceitar requisições do frontend React em:
- `http://localhost:3000`
- `http://localhost:5173`

Edite `CORS_ORIGINS` no `.env` para adicionar outros domínios.
