"""Email service — envoi SMTP via smtplib (synchronous)."""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(
    to: str,
    subject: str,
    body: str,
    body_type: str = "plain",
    cc: Optional[str] = None,
) -> dict:
    """Envoie un email via SMTP.

    Args:
        to:        Adresse email du destinataire.
        subject:   Objet de l'email.
        body:      Corps de l'email (texte brut ou HTML).
        body_type: ``"plain"`` ou ``"html"``.
        cc:        Adresse optionnelle en copie.

    Returns:
        dict ``{"success": bool, "message": str}``.
    """
    if not settings.smtp_user or not settings.smtp_password:
        logger.error("SMTP credentials not configured — smtp_user or smtp_password is empty")
        return {
            "success": False,
            "message": (
                "Impossible d'envoyer l'email : les identifiants SMTP ne sont pas configurés."
            ),
        }

    from_addr = settings.smtp_from or settings.smtp_user

    msg = MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc

    msg.attach(MIMEText(body, body_type, "utf-8"))

    recipients = [to] + ([cc] if cc else [])

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.ehlo()
            if settings.smtp_use_tls:
                server.starttls()
                server.ehlo()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(from_addr, recipients, msg.as_string())

        logger.info("Email envoyé à %s — objet : %s", to, subject)
        return {"success": True, "message": f"Email envoyé avec succès à {to}."}

    except smtplib.SMTPAuthenticationError as exc:
        logger.exception("SMTP auth error: %s", exc)
        return {
            "success": False,
            "message": f"Échec de l'authentification SMTP : {exc}",
        }
    except smtplib.SMTPException as exc:
        logger.exception("SMTP error sending to %s: %s", to, exc)
        return {"success": False, "message": f"Erreur SMTP : {exc}"}
    except OSError as exc:
        logger.exception("Network error reaching SMTP server: %s", exc)
        return {"success": False, "message": f"Erreur réseau SMTP : {exc}"}
