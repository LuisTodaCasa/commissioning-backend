"""Configuração de logging da aplicação."""
import logging
import re
import sys
from app.core.config import settings

# Campos sensíveis cujos valores nunca devem aparecer em texto de log.
_SENSITIVE_FIELDS = [
    "DATABASE_URL",
    "JWT_SECRET_KEY",
    "password",
    "senha",
    "token",
    "Authorization",
    "Cookie",
    "smtp_password",
    "SMTP_PASSWORD",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_SECRET",
    "S3_SECRET",
]

_REDACTED = "[REDACTED]"

# Casa padrões como: campo=valor, "campo": "valor", campo: valor
_FIELD_NAMES = "|".join(re.escape(f) for f in _SENSITIVE_FIELDS)
_KV_PATTERN = re.compile(
    r'(?i)(["\']?(?:' + _FIELD_NAMES + r')["\']?\s*[:=]\s*)'
    r'(?:"[^"]*"|\'[^\']*\'|[^\s,;}&]+)'
)
# Casa "Bearer <token>" em cabeçalhos Authorization.
_BEARER_PATTERN = re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._\-]+')
# Casa a senha embutida em uma URL de conexão (ex.: postgresql://user:senha@host).
_URL_CRED_PATTERN = re.compile(r'(://[^:/\s]+:)[^@/\s]+(@)')


def _redact(text: str) -> str:
    # Mascara "Bearer <token>" antes do padrão chave=valor, para que o token
    # após "Bearer" não escape da redação.
    text = _BEARER_PATTERN.sub(lambda m: m.group(1) + _REDACTED, text)
    text = _KV_PATTERN.sub(lambda m: m.group(1) + _REDACTED, text)
    text = _URL_CRED_PATTERN.sub(lambda m: m.group(1) + _REDACTED + m.group(2), text)
    return text


class RedactingFilter(logging.Filter):
    """Filtro que mascara valores sensíveis na mensagem final do log."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
            redacted = _redact(message)
            if redacted != message:
                record.msg = redacted
                record.args = ()
        except Exception:
            # Nunca deixar a redação quebrar o logging.
            pass
        return True


def setup_logging():
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    redacting_filter = RedactingFilter()
    handler.addFilter(redacting_filter)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)

    # Garante que a redação também se aplique aos handlers do uvicorn.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(logger_name)
        for h in lg.handlers:
            h.addFilter(RedactingFilter())

    # Reduzir verbosidade de libs externas
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
