import smtplib
from email.message import EmailMessage

from app.core.config import settings


def send_email_sync(subject: str, to_addr: str, body_text: str) -> None:
    """Gửi mail đồng bộ (gọi trong thread pool từ async endpoint)."""
    if not settings.smtp_user or not settings.smtp_password:
        raise RuntimeError("SMTP not configured (SMTP_USER / SMTP_PASSWORD)")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email or settings.smtp_user
    msg["To"] = to_addr
    msg.set_content(body_text)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
