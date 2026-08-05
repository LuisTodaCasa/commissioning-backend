"""Configurações da aplicação via variáveis de ambiente."""
import json
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = ""

    # JWT
    JWT_SECRET_KEY: str = "dev-secret-key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_ENDPOINT_URL: str = ""
    R2_BUCKET_NAME: str = ""
    R2_PUBLIC_URL: str = ""

    # SMTP
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@consorciouhn.com.br"
    SMTP_TLS: bool = True

    # CORS
    CORS_ORIGINS: str = '["http://localhost:3000","http://localhost:5173"]'

    @property
    def cors_origins_list(self) -> List[str]:
        try:
            return json.loads(self.CORS_ORIGINS)
        except (json.JSONDecodeError, TypeError):
            return ["http://localhost:3000"]

    # Upload
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # App
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def _validate_production(s: "Settings") -> None:
    """Valida variáveis obrigatórias quando APP_ENV == 'production'.

    Levanta RuntimeError nomeando apenas a variável ofensora (sem expor valores).
    """
    if s.APP_ENV != "production":
        return

    if not s.DATABASE_URL or not s.DATABASE_URL.strip():
        raise RuntimeError("DATABASE_URL é obrigatória em produção.")

    weak_secrets = {"secret", "changeme", "your_secret_here", "insecure"}
    jwt_secret = s.JWT_SECRET_KEY or ""
    if (
        not jwt_secret.strip()
        or jwt_secret.strip().lower() in weak_secrets
        or len(jwt_secret) < 32
    ):
        raise RuntimeError(
            "JWT_SECRET_KEY é obrigatória em produção e deve ser forte "
            "(mínimo de 32 caracteres, não pode ser um valor padrão/inseguro)."
        )


settings = Settings()
_validate_production(settings)
