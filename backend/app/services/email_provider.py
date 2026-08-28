"""EmailProvider abstraction (spec section 17).

The app must work with zero email configuration: ConsoleEmailProvider never
claims a message was sent externally — callers always persist an
AlertDelivery row so the message is visible in the /alerts preview tray
regardless of which provider is active.
"""

import logging
import smtplib
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from app.config import Settings

logger = logging.getLogger("radarin.email")


class EmailProvider(ABC):
    @abstractmethod
    async def send(self, *, to: str, subject: str, html: str) -> bool:
        """Return True only if the message was actually handed off to a real
        delivery channel. Console provider always returns False."""
        ...


class ConsoleEmailProvider(EmailProvider):
    async def send(self, *, to: str, subject: str, html: str) -> bool:
        logger.info("EMAIL PREVIEW (not sent) to=%s subject=%s", to, subject)
        return False


class SMTPEmailProvider(EmailProvider):
    def __init__(self, settings: Settings):
        self._settings = settings

    async def send(self, *, to: str, subject: str, html: str) -> bool:
        s = self._settings
        if not (s.smtp_host and s.smtp_port and s.email_from):
            logger.warning("SMTP not fully configured; falling back to preview-only")
            return False
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = s.email_from
        msg["To"] = to
        msg.attach(MIMEText(html, "html"))
        try:
            with smtplib.SMTP(s.smtp_host, int(s.smtp_port), timeout=10) as server:
                server.starttls()
                if s.smtp_user:
                    server.login(s.smtp_user, s.smtp_password)
                server.sendmail(s.email_from, [to], msg.as_string())
            return True
        except Exception:  # pragma: no cover - network
            logger.exception("SMTP send failed")
            return False


class ResendEmailProvider(EmailProvider):
    def __init__(self, settings: Settings):
        self._settings = settings

    async def send(self, *, to: str, subject: str, html: str) -> bool:  # pragma: no cover - network
        s = self._settings
        if not s.resend_api_key:
            return False
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {s.resend_api_key}"},
                json={"from": s.email_from, "to": [to], "subject": subject, "html": html},
            )
            return resp.status_code < 300


def get_email_provider(settings: Settings) -> EmailProvider:
    if settings.email_provider == "smtp":
        return SMTPEmailProvider(settings)
    if settings.email_provider == "resend":
        return ResendEmailProvider(settings)
    return ConsoleEmailProvider()
