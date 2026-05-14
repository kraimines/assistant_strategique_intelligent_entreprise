"""Email agent node — compose et envoie un email basé sur le contexte du pipeline.

Stratégie deterministe (pas de tool calling) :
  1. Le LLM compose le contenu de l'email (JSON : to, subject, body).
  2. On parse le JSON et on appelle directement email_service.send_email().
  3. Le résultat SMTP réel est stocké dans state["email_result"].

Cette approche garantit l'envoi indépendamment de la fiabilité du tool-calling
du modèle courant.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.core.llm import get_text_llm, invoke_with_retry
from app.services.email_service import send_email as smtp_send

logger = logging.getLogger(__name__)

# ── Prompt de composition ─────────────────────────────────────────────────────

_COMPOSE_PROMPT = """\
Tu es un assistant expert en rédaction d'emails professionnels pour Talan.

CONTEXTE :
{context}

INSTRUCTIONS :
- Identifie l'adresse email du destinataire dans la demande.
  • Si un email est explicitement mentionné (ex. jean@talan.com), utilise-le.
  • Si seul un nom est donné (ex. "Ahmed Ben Ali"), déduis l'email : prenom.nom@talan.com
    (minuscules, accents supprimés, ex. ahmed.benali@talan.com).
  • Si aucun destinataire n'est identifiable, mets "INCONNU" dans le champ "to".
- Compose un email professionnel en français (sauf demande contraire).
- Utilise les données disponibles (tool_results, rag_context) pour enrichir le contenu.
- Termine le corps par : "Cordialement,\\nL'équipe Talan"

Réponds UNIQUEMENT avec ce JSON valide (aucun texte avant ni après) :
{{
  "to": "<email du destinataire>",
  "subject": "<objet de l'email, ≤10 mots>",
  "body": "<corps complet de l'email>",
  "cc": ""
}}
"""


def _build_context(state: AgentState) -> str:
    """Construit le contexte à injecter dans le prompt de composition."""
    user_message = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            user_message = str(msg.content)
            break

    tool_results = state.get("tool_results") or {}
    rag_context = state.get("rag_context") or ""

    parts = [f"DEMANDE UTILISATEUR :\n{user_message}"]

    if tool_results:
        try:
            tr_str = json.dumps(tool_results, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError):
            tr_str = str(tool_results)
        parts.append(f"DONNÉES BASE DE DONNÉES :\n{tr_str}")

    if rag_context:
        parts.append(f"CONTEXTE DOCUMENTAIRE :\n{rag_context}")

    return "\n\n".join(parts)


def _parse_email_json(raw: str) -> Optional[Dict[str, str]]:
    """Extrait le JSON d'email depuis la réponse LLM."""
    text = raw.strip()

    # Retire les fences markdown ```json ... ```
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Tente un parse direct
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "to" in data:
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback : cherche le premier bloc JSON dans la réponse
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, dict) and "to" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning("email_agent: impossible de parser le JSON LLM — raw=%r", raw[:300])
    return None


# ── Node ──────────────────────────────────────────────────────────────────────

def email_agent_node(state: AgentState) -> AgentState:
    """Compose et envoie un email de façon déterministe.

    1. Appelle le LLM pour obtenir un JSON {to, subject, body, cc}.
    2. Parse le JSON.
    3. Appelle directement smtp_send() — sans dépendre du tool calling.
    4. Stocke le résultat dans state["email_result"].

    Args:
        state: AgentState courant après le domain agent (et éventuellement rag).

    Returns:
        AgentState mis à jour avec email_result.
    """
    t0 = time.perf_counter()
    user_id = state.get("user_id", "unknown")
    logger.info("email_agent_node start — user_id=%s", user_id)

    # ── Garde : ne pas envoyer si toutes les données DB sont en erreur ────────
    tool_results = state.get("tool_results") or {}
    if tool_results:
        all_errors = all(
            isinstance(v, dict) and "error" in v
            for v in tool_results.values()
        )
        if all_errors:
            errors_str = "; ".join(
                f"{k}: {v['error']}" for k, v in tool_results.items()
            )
            logger.warning("email_agent_node: all tool results are errors — aborting send")
            return {
                **state,
                "email_result": {
                    "success": False,
                    "error": f"Données indisponibles pour composer l'email : {errors_str}",
                },
                "error_message": f"Impossible d'envoyer l'email : les données demandées n'ont pas pu être récupérées ({errors_str}).",
            }

    context = _build_context(state)
    prompt = _COMPOSE_PROMPT.format(context=context)

    # ── Appel LLM pour composer l'email ──────────────────────────────────────
    try:
        llm = get_text_llm()
        messages = [
            SystemMessage(content="Tu es un assistant de rédaction d'emails professionnels. Réponds UNIQUEMENT en JSON valide."),
            HumanMessage(content=prompt),
        ]
        response = invoke_with_retry(llm, messages)
        raw_content = response.content if hasattr(response, "content") else str(response)
        logger.debug("email_agent_node: LLM response — %r", raw_content[:200])
    except Exception as exc:
        logger.exception("email_agent_node: LLM composition failed — %s", exc)
        return {
            **state,
            "email_result": {"success": False, "error": str(exc)},
            "error_message": f"Erreur lors de la composition de l'email : {exc}",
        }

    # ── Parse du JSON de composition ──────────────────────────────────────────
    email_data = _parse_email_json(raw_content)

    if not email_data:
        return {
            **state,
            "email_result": {
                "success": False,
                "error": "Impossible de parser la composition de l'email.",
            },
            "error_message": "L'agent email n'a pas pu extraire les champs de l'email.",
        }

    to: str = email_data.get("to", "").strip()
    subject: str = email_data.get("subject", "Message de Talan").strip()
    body: str = email_data.get("body", "").strip()
    cc: str = email_data.get("cc", "").strip()

    if not to or to == "INCONNU":
        logger.warning("email_agent_node: destinataire non identifié")
        return {
            **state,
            "email_result": {
                "success": False,
                "error": "Destinataire non identifié dans la demande.",
            },
        }

    # ── Envoi SMTP direct ─────────────────────────────────────────────────────
    logger.info("email_agent_node: sending email to=%s subject=%r", to, subject)
    smtp_result = smtp_send(
        to=to,
        subject=subject,
        body=body,
        cc=cc if cc else None,
    )

    email_result: Dict[str, Any] = {
        "success": smtp_result["success"],
        "to": to,
        "subject": subject,
        "smtp_message": smtp_result["message"],
    }

    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "email_agent_node done — success=%s to=%s — %.1f ms",
        smtp_result["success"], to, elapsed_ms,
    )

    return {
        **state,
        "email_result": email_result,
        # Efface toute erreur précédente du domain agent (ex. tentative d'appel send_email)
        # pour que final_response_node affiche uniquement le résultat de l'email.
        "error_message": None if email_result.get("success") else state.get("error_message"),
    }
