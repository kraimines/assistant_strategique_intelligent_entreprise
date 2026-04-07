"""LLM factory — supporte Groq (gratuit) et Google Gemini.

Provider actif contrôlé par LLM_PROVIDER dans .env :
  LLM_PROVIDER=groq    → Llama 3.3 70B via Groq (14 400 req/jour gratuit)
  LLM_PROVIDER=gemini  → Gemini 2.0 Flash via Google AI
"""
from __future__ import annotations

import logging
import os
import time
from functools import lru_cache
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMConnectionError(Exception):
    """Raised when the LLM backend cannot be reached."""


# ── LangSmith ─────────────────────────────────────────────────────────────────

def _configure_langsmith() -> None:
    if settings.langsmith_api_key:
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")


# ── Retry helper ──────────────────────────────────────────────────────────────

def invoke_with_retry(llm: Any, messages: Any, max_retries: int = 3) -> Any:
    """Invoke the LLM with automatic retry on rate-limit (429) errors.

    Waits the duration indicated in the error message (or a default backoff)
    before each retry.  Other errors are re-raised immediately.

    Args:
        llm:         A LangChain chat model (or bound model with tools).
        messages:    The message list to pass to llm.invoke().
        max_retries: Maximum number of retry attempts after the first failure.

    Returns:
        The AIMessage returned by the LLM.

    Raises:
        The last exception if all retries are exhausted.
    """
    import re
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return llm.invoke(messages)
        except Exception as exc:
            exc_str = str(exc)
            # Only retry on rate-limit errors
            if "429" not in exc_str and "rate_limit" not in exc_str.lower():
                raise
            last_exc = exc
            # Try to parse wait time from error message: "try again in 2.04s"
            match = re.search(r"try again in ([0-9.]+)s", exc_str)
            wait = float(match.group(1)) + 0.5 if match else (2 ** attempt) * 2.0
            logger.warning(
                "Rate limit hit (attempt %d/%d) — waiting %.1fs before retry",
                attempt + 1, max_retries + 1, wait,
            )
            time.sleep(wait)
    raise last_exc


# ── GROQ ──────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_groq_llm():
    """Groq LLM — Llama 3.3 70B, streaming désactivé pour la stabilité."""
    from langchain_groq import ChatGroq
    _configure_langsmith()
    logger.info("Initialising Groq LLM — model=%s", settings.groq_model)
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=settings.gemini_temperature,
        max_tokens=settings.gemini_max_tokens,
        streaming=False,
    )


@lru_cache(maxsize=1)
def _get_groq_json_llm():
    """Groq LLM configuré pour retourner du JSON strict."""
    from langchain_groq import ChatGroq
    _configure_langsmith()
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0.0,
        max_tokens=settings.gemini_max_tokens,
        streaming=False,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


# ── GEMINI ────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_gemini_llm():
    """Google Gemini LLM — streaming activé."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    _configure_langsmith()
    logger.info("Initialising Gemini LLM — model=%s", settings.gemini_model)
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key,
        temperature=settings.gemini_temperature,
        max_output_tokens=settings.gemini_max_tokens,
        streaming=True,
        convert_system_message_to_human=True,
    )


@lru_cache(maxsize=1)
def _get_gemini_json_llm():
    """Google Gemini LLM configuré pour JSON strict."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    _configure_langsmith()
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key,
        temperature=0.0,
        max_output_tokens=settings.gemini_max_tokens,
        streaming=False,
        convert_system_message_to_human=True,
        response_mime_type="application/json",
    )


# ── Interface publique ────────────────────────────────────────────────────────

def get_llm():
    """Retourne le LLM principal selon LLM_PROVIDER (.env)."""
    provider = settings.llm_provider.lower()
    if provider == "groq":
        return _get_groq_llm()
    return _get_gemini_llm()


def get_json_llm():
    """Retourne le LLM configuré pour retourner du JSON pur."""
    provider = settings.llm_provider.lower()
    if provider == "groq":
        return _get_groq_json_llm()
    return _get_gemini_json_llm()


def get_llm_with_tools(tools: List[Any]) -> Any:
    """Retourne le LLM avec les tools bindés."""
    llm = get_llm()
    logger.debug("Binding %d tool(s) to LLM [provider=%s]", len(tools), settings.llm_provider)
    return llm.bind_tools(tools)


def truncate_tool_result(result_str: str, max_chars: int = 1500) -> str:
    """Tronque un résultat d'outil trop long pour tenir dans la fenêtre de contexte.

    Si le résultat JSON dépasse max_chars, tronque intelligemment en conservant
    les premiers éléments et en ajoutant une note de troncature.
    """
    if len(result_str) <= max_chars:
        return result_str
    # Essaie de tronquer proprement sur une liste JSON
    truncated = result_str[:max_chars]
    # Ferme le JSON si possible
    last_brace = max(truncated.rfind("},"), truncated.rfind("]"))
    if last_brace > max_chars // 2:
        truncated = truncated[: last_brace + 1]
    return truncated + f'\n[... résultat tronqué — {len(result_str)} caractères total]'


async def test_llm_connection() -> Dict[str, Any]:
    """Teste la connexion au LLM actif et retourne un dict de statut."""
    start = time.monotonic()
    provider = settings.llm_provider.lower()
    model = settings.groq_model if provider == "groq" else settings.gemini_model
    try:
        llm = get_llm()
        response = await llm.ainvoke([HumanMessage(content="Réponds uniquement: OK")])
        latency_ms = (time.monotonic() - start) * 1000
        logger.info("LLM connection OK — provider=%s model=%s %.1fms", provider, model, latency_ms)
        return {"status": "ok", "provider": provider, "model": model, "latency_ms": round(latency_ms, 2)}
    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000
        logger.error("LLM connection FAILED: %s", exc)
        return {"status": "error", "provider": provider, "model": model,
                "latency_ms": round(latency_ms, 2), "error": str(exc)}
