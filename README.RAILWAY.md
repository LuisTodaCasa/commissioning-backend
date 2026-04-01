# Deploy do Backend FastAPI no Railway

## Pré-requisitos
- Conta no Railway (https://railway.app)
- Banco de dados PostgreSQL (Neon recomendado)
- JWT Secret Key gerado

## Passo a Passo

### 1. Preparação no Railway

1. Acesse https://railway.app e faça login
2. Clique em "New Project" > "Deploy from GitHub"
3. Selecione este repositório ou faça upload do ZIP
4. Railway detectará automaticamente `Procfile` e `requirements.txt`

### 2. Configurar Variáveis de Ambiente

No painel do Railway, vá para **Variables** e defina:

```
DATABASE_URL=postgresql://seu-usuario:senha@host:porta/banco?sslmode=require&channel_binding=require
JWT_SECRET_KEY=seu-secret-key-super-seguro-aqui
CORS_ORIGINS=["https://seu-frontend-url"]
APP_ENV=production
APP_DEBUG=false
```

### 3. Conectar ao Banco de Dados

#### Opção A: Usar Neon (Recomendado)
1. Crie um banco em https://console.neon.tech
2. Copie a connection string
3. Cole em `DATABASE_URL` no Railway

#### Opção B: Usar PostgreSQL do Railway
1. No Railway, clique em "Add Service" > "PostgreSQL"
2. A URL será gerada automaticamente como `DATABASE_URL`

### 4. Deploy

Railway automaticamente:
1. Detecta `Procfile` e instala dependências de `requirements.txt`
2. Executa migrations Alembic (crie um pré-deploy hook se necessário)
3. Inicia o servidor com: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### 5. Migrations (Importante!)

Após o primeiro deploy, execute o seed no Railway:

```bash
# Via SSH no Railway
python seed.py
```

Ou crie um **deployment webhook** para executar automaticamente.

### 6. Verificar Status

```bash
# Log do Railway mostrará:
# "Application startup complete"
# "Uvicorn running on http://0.0.0.0:PORT"

# Teste a API:
curl https://seu-app.railway.app/docs
```

## Variáveis de Ambiente Completas

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `DATABASE_URL` | Connection string PostgreSQL | `postgresql://user:pass@host/db?sslmode=require` |
| `JWT_SECRET_KEY` | Chave JWT (use openssl rand -hex 32) | `abc123xyz...` |
| `CORS_ORIGINS` | URLs permitidas | `["https://frontend.railway.app"]` |
| `APP_ENV` | production / development | `production` |
| `APP_DEBUG` | Debug mode | `false` |
| `SMTP_HOST` | Email SMTP (opcional) | `smtp.gmail.com` |
| `SMTP_USER` | Email user (opcional) | `seu@email.com` |
| `SMTP_PASSWORD` | Email password (opcional) | `sua-senha` |

## Troubleshooting

### "Module not found"
- Verifique se `requirements.txt` está na raiz
- Verifique se Python 3.11+ está disponível

### "Database connection failed"
- Teste a DATABASE_URL localmente: `psql $DATABASE_URL`
- Verifique se SSL está habilitado em Neon

### "Uvicorn not found"
- Verifique se `Procfile` está na raiz com conteúdo correto

## Gerar JWT Secret Key Seguro

```bash
# No seu terminal local:
openssl rand -hex 32

# Ou Python:
python -c "import secrets; print(secrets.token_hex(32))"
```

Copie o resultado e use como `JWT_SECRET_KEY` no Railway.

## URLs Úteis

- **API Docs**: `https://seu-app.railway.app/docs`
- **Redoc**: `https://seu-app.railway.app/redoc`
- **Health Check**: `https://seu-app.railway.app/health` (se implementado)

## Suporte

Documentação Railway: https://docs.railway.app/
