"""Utilitário para envio de e-mails (redefinição de senha)."""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_reset_email(to_email: str, reset_token: str):
    """Envia e-mail com link de redefinição de senha."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Redefinição de Senha - Sistema de Comissionamento"
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to_email

        reset_link = f"http://localhost:3000/reset-password?token={reset_token}"

        html = f"""
        <html>
        <body>
            <h2>Redefinição de Senha</h2>
            <p>Você solicitou a redefinição de sua senha no Sistema de Comissionamento.</p>
            <p>Clique no link abaixo para redefinir sua senha:</p>
            <p><a href="{reset_link}">Redefinir Senha</a></p>
            <p>Este link é válido por 30 minutos.</p>
            <p>Se você não solicitou esta redefinição, ignore este e-mail.</p>
            <br>
            <p><em>Sistema de Comissionamento - Consórcio UHN</em></p>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_TLS:
                server.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM, to_email, msg.as_string())

        logger.info(f"E-mail de redefinição enviado para {to_email}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar e-mail para {to_email}: {e}")
        return False
