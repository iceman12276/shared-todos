"""Email sending via SMTP (mailhog in dev, real SMTP in prod)."""
from email.message import EmailMessage

import aiosmtplib

from app.config import settings


async def send_password_reset_email(to_email: str, token: str) -> None:
    reset_url = f"{settings.frontend_url}/reset-password?token={token}"
    msg = EmailMessage()
    msg["From"] = "noreply@shared-todos.local"
    msg["To"] = to_email
    msg["Subject"] = "Reset your password"
    msg.set_content(
        f"Click the link below to reset your password. "
        f"This link expires in 1 hour and can only be used once.\n\n{reset_url}\n"
    )
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        start_tls=False,
    )
