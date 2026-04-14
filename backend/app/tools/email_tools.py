"""LangChain tool — envoi d'email via le service SMTP."""
from __future__ import annotations

from langchain_core.tools import tool

from app.services.email_service import send_email as _send_email


@tool
def send_email(to: str, subject: str, body: str, cc: str = "") -> str:
    """Envoie un email professionnel à un destinataire.

    Utilise le serveur SMTP configuré dans les variables d'environnement.

    Args:
        to:      Adresse email du destinataire (ex. jean.dupont@talan.com).
        subject: Objet de l'email (ligne de sujet).
        body:    Corps de l'email en texte brut. Peut contenir des sauts de ligne.
        cc:      Adresse email optionnelle en copie (chaîne vide si aucune).

    Returns:
        Message de confirmation ou d'erreur.
    """
    result = _send_email(
        to=to,
        subject=subject,
        body=body,
        cc=cc if cc else None,
    )
    return result["message"]
