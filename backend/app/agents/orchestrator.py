"""Orchestrator node — entry point of the LangGraph pipeline.

Classifies the user's intent into a domain (hr | crm | erp | rag | multi),
measures confidence, enforces write-permission guards, and populates the
shared AgentState before routing to the appropriate domain agent.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage

from app.agents.state import AgentState
from app.core.llm import get_json_llm
from app.prompts.orchestrator_prompts import CLASSIFICATION_PROMPT

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

VALID_DOMAINS = {"hr", "crm", "erp", "rag", "multi", "competitive_intel"}
FALLBACK_DOMAIN = "rag"
CONFIDENCE_THRESHOLD = 0.7
MAX_RETRIES = 1  # one retry after the first low-confidence attempt

# Write permissions: maps each role to the domains where mutations are allowed.
WRITE_OPERATIONS_ALLOWED: Dict[str, list[str]] = {
    "employee": ["hr"],
    "manager": ["hr", "crm"],
    "admin": ["hr", "crm", "erp"],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_last_human_message(state: AgentState) -> str:
    """Return the content of the last HumanMessage in the conversation.

    Falls back to an empty string if the message list is empty or the last
    message is not a HumanMessage.

    Args:
        state: Current AgentState.

    Returns:
        String content of the last human turn.
    """
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    # Fallback: try to read content from any message-like dict
    if messages:
        last = messages[-1]
        if hasattr(last, "content"):
            return str(last.content)
        if isinstance(last, dict):
            return str(last.get("content", ""))
    return ""


def _parse_classification(raw: str) -> Dict[str, Any]:
    """Parse the JSON classification response from the LLM.

    Strips markdown code fences if present, then attempts json.loads.
    Returns a dict with sensible defaults on any parse failure.

    Args:
        raw: Raw string returned by the JSON LLM.

    Returns:
        Parsed classification dict.
    """
    import re as _re
    # Strip <think>...</think> CoT blocks (qwen3-32b, deepseek-r1…)
    text = _re.sub(r"<think>.*?</think>", "", raw, flags=_re.DOTALL).strip()
    # Strip optional ```json ... ``` fences
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        # Last resort: find the first {...} block
        m = _re.search(r"\{.*\}", text, _re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except (json.JSONDecodeError, ValueError):
                pass
        logger.warning("JSON parse failed — raw=%r", raw[:200])
        return {}


def _build_retry_prompt(user_message: str, candidates: list[str]) -> str:
    """Build a more directive retry classification prompt.

    Args:
        user_message: The original user question.
        candidates:   The two most likely domain names from the first attempt.

    Returns:
        Formatted prompt string for the retry call.
    """
    candidate_str = " ou ".join(f'"{d}"' for d in candidates)
    return (
        f"La question suivante a été difficile à classer.\n"
        f"Les domaines les plus probables sont : {candidate_str}.\n"
        f"Analyse à nouveau et produis le JSON de classification.\n\n"
        f"QUESTION : {user_message}\n\n"
        + CLASSIFICATION_PROMPT.format(user_message=user_message)
    )


# ── Node ──────────────────────────────────────────────────────────────────────

def orchestrator_node(state: AgentState) -> AgentState:
    """Classify the user's request and populate routing fields in AgentState.

    This is the pipeline entry point. It reads the last HumanMessage, calls
    the JSON LLM to classify the domain and intent, and populates:
      - detected_domain
      - domain_confidence
      - requires_write
      - secondary_domain
      - error_message (on permission violation)
      - iteration_count (incremented)

    Algorithm
    ---------
    1. Extract the last HumanMessage content from state["messages"].
    2. Invoke get_json_llm() with CLASSIFICATION_PROMPT formatted with the message.
    3. Parse the JSON response; fall back to FALLBACK_DOMAIN on malformed output.
    4. If confidence < CONFIDENCE_THRESHOLD: retry once with a directive prompt
       listing the two most likely candidate domains.
    5. If still below threshold after retry: force domain to FALLBACK_DOMAIN.
    6. Enforce write permissions: if requires_write is True and the effective
       domain is not in WRITE_OPERATIONS_ALLOWED[user_role], set error_message.
    7. Return updated state dict.

    Args:
        state: Current shared AgentState.

    Returns:
        Updated AgentState with classification fields populated.
    """
    t0 = time.perf_counter()
    user_message = _extract_last_human_message(state)
    user_role = state.get("user_role", "employee")
    iteration_count = state.get("iteration_count", 0)

    logger.info(
        "orchestrator_node start — user_id=%s role=%s message_len=%d",
        state.get("user_id", "unknown"),
        user_role,
        len(user_message),
    )

    # ── Default classification values ─────────────────────────────────────────
    detected_domain: str = FALLBACK_DOMAIN
    domain_confidence: float = 0.0
    requires_write: bool = False
    requires_email: bool = False
    requires_report: bool = False
    secondary_domain: Optional[str] = None
    error_message: Optional[str] = state.get("error_message")  # preserve existing

    if not user_message:
        logger.warning("orchestrator_node received empty user message")
        return {
            **state,
            "detected_domain": FALLBACK_DOMAIN,
            "domain_confidence": 0.0,
            "requires_write": False,
            "secondary_domain": None,
            "error_message": "Message utilisateur vide.",
            "iteration_count": iteration_count + 1,
        }

    # ── First classification attempt ──────────────────────────────────────────
    llm = get_json_llm()
    classification: Dict[str, Any] = {}

    try:
        prompt = CLASSIFICATION_PROMPT.format(user_message=user_message)
        t_llm = time.perf_counter()
        response = llm.invoke(prompt)
        llm_ms = (time.perf_counter() - t_llm) * 1000
        logger.debug("LLM classification call 1 — %.1f ms", llm_ms)

        raw_content = (
            response.content
            if hasattr(response, "content")
            else str(response)
        )
        classification = _parse_classification(raw_content)

    except Exception as exc:
        logger.exception("orchestrator_node LLM call 1 failed: %s", exc)
        classification = {}

    # ── Extract fields from first attempt ────────────────────────────────────
    domain_raw: str = str(classification.get("domain", "")).lower().strip()
    primary_domain_raw: str = str(
        classification.get("primary_domain", domain_raw)
    ).lower().strip()
    confidence_raw = classification.get("confidence", 0.0)

    try:
        domain_confidence = float(confidence_raw)
    except (TypeError, ValueError):
        domain_confidence = 0.0

    detected_domain = domain_raw if domain_raw in VALID_DOMAINS else FALLBACK_DOMAIN
    secondary_domain_raw = classification.get("secondary_domain")
    secondary_domain = (
        str(secondary_domain_raw).lower().strip()
        if secondary_domain_raw and str(secondary_domain_raw).lower() != "null"
        else None
    )
    requires_write = bool(classification.get("requires_write", False))
    requires_email = bool(classification.get("requires_email", False))
    requires_report = bool(classification.get("requires_report", False))

    logger.info(
        "Classification attempt 1 — domain=%s confidence=%.2f requires_write=%s",
        detected_domain,
        domain_confidence,
        requires_write,
    )

    # ── Retry if confidence is below threshold ────────────────────────────────
    if domain_confidence < CONFIDENCE_THRESHOLD:
        logger.info(
            "Confidence %.2f < %.2f — retrying classification",
            domain_confidence,
            CONFIDENCE_THRESHOLD,
        )

        # Build candidate list: primary + secondary (or a generic fallback pair)
        candidate_1 = primary_domain_raw if primary_domain_raw in VALID_DOMAINS else "rag"
        candidate_2 = (
            secondary_domain
            if secondary_domain and secondary_domain in VALID_DOMAINS
            else ("hr" if candidate_1 != "hr" else "crm")
        )
        candidates = list(dict.fromkeys([candidate_1, candidate_2]))  # deduplicate

        retry_classification: Dict[str, Any] = {}
        try:
            retry_prompt = _build_retry_prompt(user_message, candidates)
            t_retry = time.perf_counter()
            retry_response = llm.invoke(retry_prompt)
            retry_ms = (time.perf_counter() - t_retry) * 1000
            logger.debug("LLM classification call 2 (retry) — %.1f ms", retry_ms)

            retry_raw = (
                retry_response.content
                if hasattr(retry_response, "content")
                else str(retry_response)
            )
            retry_classification = _parse_classification(retry_raw)

        except Exception as exc:
            logger.exception("orchestrator_node LLM retry call failed: %s", exc)
            retry_classification = {}

        # Use retry result only if it improves confidence
        retry_domain_raw = str(
            retry_classification.get("domain", "")
        ).lower().strip()
        retry_confidence_raw = retry_classification.get("confidence", 0.0)
        try:
            retry_confidence = float(retry_confidence_raw)
        except (TypeError, ValueError):
            retry_confidence = 0.0

        if retry_confidence >= domain_confidence and retry_domain_raw in VALID_DOMAINS:
            detected_domain = retry_domain_raw
            domain_confidence = retry_confidence
            retry_secondary_raw = retry_classification.get("secondary_domain")
            secondary_domain = (
                str(retry_secondary_raw).lower().strip()
                if retry_secondary_raw
                and str(retry_secondary_raw).lower() != "null"
                else None
            )
            requires_write = bool(retry_classification.get("requires_write", requires_write))
            requires_email = bool(retry_classification.get("requires_email", requires_email))
            requires_report = bool(retry_classification.get("requires_report", requires_report))
            logger.info(
                "Retry improved — domain=%s confidence=%.2f",
                detected_domain,
                domain_confidence,
            )
        else:
            logger.info(
                "Retry did not improve (retry_conf=%.2f) — keeping domain=%s conf=%.2f",
                retry_confidence,
                detected_domain,
                domain_confidence,
            )

        # If still below threshold after retry → force fallback
        if domain_confidence < CONFIDENCE_THRESHOLD:
            logger.info(
                "Confidence still below threshold after retry (%.2f) — forcing domain=%s",
                domain_confidence,
                FALLBACK_DOMAIN,
            )
            detected_domain = FALLBACK_DOMAIN
            secondary_domain = None

    # ── For multi-domain queries: effective domain for permission checks ───────
    # We check write permissions against the primary_domain, not "multi".
    effective_domain_for_perms = (
        str(classification.get("primary_domain", detected_domain)).lower().strip()
        if detected_domain == "multi"
        else detected_domain
    )
    if effective_domain_for_perms not in VALID_DOMAINS:
        effective_domain_for_perms = detected_domain

    # ── Write permission check ────────────────────────────────────────────────
    if requires_write:
        allowed_domains = WRITE_OPERATIONS_ALLOWED.get(user_role, [])
        if effective_domain_for_perms not in allowed_domains:
            error_message = (
                "Vous n'avez pas les permissions nécessaires pour cette action."
            )
            logger.warning(
                "Write permission denied — user_role=%s domain=%s allowed=%s",
                user_role,
                effective_domain_for_perms,
                allowed_domains,
            )
        else:
            # Clear any pre-existing permission error if now resolved
            error_message = None

    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "orchestrator_node done — domain=%s confidence=%.2f requires_write=%s "
        "requires_email=%s requires_report=%s secondary=%s error=%s — total %.1f ms",
        detected_domain,
        domain_confidence,
        requires_write,
        requires_email,
        requires_report,
        secondary_domain,
        error_message,
        elapsed_ms,
    )

    return {
        **state,
        "detected_domain": detected_domain,
        "domain_confidence": domain_confidence,
        "requires_write": requires_write,
        "requires_email": requires_email,
        "requires_report": requires_report,
        "secondary_domain": secondary_domain,
        "error_message": error_message,
        "iteration_count": iteration_count + 1,
    }
