"""Outgoing e-mail.

EMAIL_MODE=console : SIMULATED. Messages are kept in an in-memory outbox (and logged) - nothing is sent.
EMAIL_MODE=smtp    : really sends through your SMTP server (SMTP_HOST / SMTP_PORT / SMTP_USERNAME / ...).
                     Not exercised against a live mail server in the automated tests.

send_email never raises: it returns False on failure so a mail outage cannot break a request; callers
record the delivery status and the user can ask for a resend.
"""
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger("acbridge.email")


@dataclass(frozen=True)
class SentEmail:
    to: str
    subject: str
    body: str


OUTBOX: list[SentEmail] = []   # console mode only; bounded so it cannot grow without limit
_OUTBOX_LIMIT = 200


def clear_outbox() -> None:
    OUTBOX.clear()


def _single_line(text: str) -> str:
    return " ".join(text.split())   # strips CR/LF: no e-mail header injection through names


def send_email(to: str, subject: str, body: str) -> bool:
    settings = get_settings()
    subject = _single_line(subject)
    if settings.email_mode == "console":
        OUTBOX.append(SentEmail(to, subject, body))
        del OUTBOX[:-_OUTBOX_LIMIT]
        logger.info("SIMULATED e-mail to %s: %s", to, subject)
        return True
    try:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = settings.smtp_from, to, subject
        message.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        return True
    except Exception:   # network / auth / bad address: report, never crash the request
        logger.exception("E-mail delivery to %s failed", to)
        return False
