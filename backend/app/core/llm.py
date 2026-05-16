"""LLM factory — supporte Groq, Google Gemini et Mistral AI.

Provider actif contrôlé par LLM_PROVIDER dans .env :
  LLM_PROVIDER=groq    → Llama 3.3 70B via Groq (14 400 req/jour gratuit)
  LLM_PROVIDER=gemini  → Gemini 2.0 Flash via Google AI
  LLM_PROVIDER=mistral → Mistral Large via Mistral AI (256K ctx, 500K TPM)
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

def _is_daily_quota_exhausted(exc_str: str) -> bool:
    """Retourne True si le quota JOURNALIER est épuisé (pas juste TPM)."""
    return (
        "limit: 0" in exc_str
        or "PerDay" in exc_str
        or "per_day" in exc_str.lower()
        or "tokens per day" in exc_str.lower()
        or "TPD" in exc_str
    )


def invoke_with_retry(llm: Any, messages: Any, max_retries: int = 3) -> Any:
    """Invoke the LLM avec retry intelligent et rotation automatique de modèles.

    Stratégie :
    - Quota par minute (RPM/TPM) → attend le délai suggéré, réessaie sur le même modèle.
    - Quota journalier épuisé    → passe au modèle suivant dans la chaîne de fallback
      sans attendre (Groq: 70b → scout → qwen → Gemini).

    Args:
        llm:         LangChain chat model (ou bound model avec tools).
        messages:    Messages à passer à llm.invoke().
        max_retries: Nombre max de tentatives avant abandon.

    Returns:
        AIMessage retourné par le LLM actif.

    Raises:
        Dernière exception si tous les fallbacks échouent.
    """
    import re
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return llm.invoke(messages)
        except Exception as exc:
            exc_str = str(exc)
            if "429" not in exc_str and "rate_limit" not in exc_str.lower():
                raise
            last_exc = exc

            # Quota journalier → rotation de modèles immédiate
            if _is_daily_quota_exhausted(exc_str):
                logger.warning("Daily quota exhausted on current LLM — trying fallback chain")
                for fallback_llm in _get_fallback_chain(llm):
                    try:
                        logger.info("Trying fallback LLM: %s", getattr(fallback_llm, 'model_name', '?'))
                        return fallback_llm.invoke(messages)
                    except Exception as fb_exc:
                        if _is_daily_quota_exhausted(str(fb_exc)):
                            logger.warning("Fallback also exhausted, trying next...")
                            last_exc = fb_exc
                            continue
                        raise
                raise last_exc

            # Quota par minute → attendre et réessayer
            match = re.search(r"try again in ([0-9.]+)s", exc_str)
            wait = float(match.group(1)) + 0.5 if match else (2 ** attempt) * 2.0
            logger.warning(
                "Rate limit hit (attempt %d/%d) — waiting %.1fs before retry",
                attempt + 1, max_retries + 1, wait,
            )
            time.sleep(wait)
    raise last_exc


# ── GROQ ──────────────────────────────────────────────────────────────────────

# Chaîne de fallback Groq — chaque modèle a un quota TPD indépendant :
# qwen (100k TPD, 6k TPM) → scout (500k TPD, 30k TPM) → llama-3.3-70b (100k TPD, 12k TPM)
GROQ_FALLBACK_MODELS = [
    "qwen/qwen3-32b",                                 # quota séparé, bon JSON
    "meta-llama/llama-4-scout-17b-16e-instruct",     # 500k TPD — quota 5× plus grand
    "llama-3.3-70b-versatile",                       # meilleur tool calling
]

_groq_cache: Dict[str, Any] = {}  # model_key → ChatGroq instance


def _get_groq_by_model(model: str, json_mode: bool = False) -> Any:
    """Retourne un ChatGroq caché pour le modèle donné."""
    from langchain_groq import ChatGroq
    _configure_langsmith()
    cache_key = f"{model}:{'json' if json_mode else 'text'}"
    if cache_key not in _groq_cache:
        # qwen3-32b has a hard 6000 TPM limit (input + output counted together).
        # Keep output budget small so total stays under 5500 tokens.
        max_tok = 1800 if "qwen" in model else settings.gemini_max_tokens
        kwargs: Dict[str, Any] = {
            "model": model,
            "api_key": settings.groq_api_key,
            "temperature": 0.0 if json_mode else settings.gemini_temperature,
            "max_tokens": max_tok,
            "streaming": False,
            "request_timeout": 30,
        }
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        logger.info("Initialising Groq LLM — model=%s json=%s", model, json_mode)
        _groq_cache[cache_key] = ChatGroq(**kwargs)
    return _groq_cache[cache_key]


def _get_groq_llm() -> Any:
    """Groq LLM principal (settings.groq_model)."""
    return _get_groq_by_model(settings.groq_model)


def _get_groq_json_llm() -> Any:
    """Groq LLM JSON strict (settings.groq_model)."""
    return _get_groq_by_model(settings.groq_model, json_mode=True)


def _get_fallback_chain(current_llm: Any) -> List[Any]:
    """Construit la chaîne de fallback LLM en excluant le modèle courant.

    Ordre : modèles Groq alternatifs → Gemini (si configuré).
    """
    fallbacks: List[Any] = []
    # Identifie le modèle courant pour l'exclure
    current_model = getattr(current_llm, 'model_name', '') or getattr(current_llm, 'model', '')
    for model in GROQ_FALLBACK_MODELS:
        if model != current_model:
            fallbacks.append(_get_groq_by_model(model))
    # Mistral en second fallback si clé disponible (256K ctx, 500K TPM, pas de cap journalier)
    if settings.mistral_api_key:
        fallbacks.append(_get_mistral_llm())
    # Gemini en dernier recours si clé disponible
    if settings.google_api_key:
        fallbacks.append(_get_gemini_llm())
    return fallbacks


# ── MISTRAL ───────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_mistral_llm() -> Any:
    from langchain_mistralai import ChatMistralAI
    _configure_langsmith()
    logger.info("Initialising Mistral LLM — model=%s", settings.mistral_model)
    return ChatMistralAI(
        model=settings.mistral_model,
        api_key=settings.mistral_api_key,
        temperature=0.1,
        max_tokens=4096,
    )


@lru_cache(maxsize=1)
def _get_mistral_json_llm() -> Any:
    from langchain_mistralai import ChatMistralAI
    _configure_langsmith()
    return ChatMistralAI(
        model=settings.mistral_model,
        api_key=settings.mistral_api_key,
        temperature=0.0,
        max_tokens=4096,
        response_format={"type": "json_object"},
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
    """Retourne le LLM générique selon LLM_PROVIDER (.env). Usage: backward compat."""
    provider = settings.llm_provider.lower()
    if provider == "groq":
        return _get_groq_llm()
    if provider == "mistral" and settings.mistral_api_key:
        return _get_mistral_llm()
    return _get_gemini_llm()


def get_json_llm():
    """LLM pour classification JSON (orchestrateur, analyst, scanner).

    Utilise JSON_LLM_PROVIDER (défaut: groq) — modèle rapide, faible
    consommation de tokens, résultat JSON strict.
    """
    provider = settings.json_llm_provider.lower()
    if provider == "groq":
        return _get_groq_json_llm()
    if provider == "mistral" and settings.mistral_api_key:
        return _get_mistral_json_llm()
    return _get_gemini_json_llm()


def get_tool_llm() -> Any:
    """LLM pour les agents à tool calling (HR, CRM, ERP, market, competitive).

    Utilise TOOL_LLM_PROVIDER (défaut: groq) — meilleur tool calling sur
    le free tier, 100k tokens/jour.
    """
    provider = settings.tool_llm_provider.lower()
    if provider == "groq":
        return _get_groq_llm()
    if provider == "mistral" and settings.mistral_api_key:
        return _get_mistral_llm()
    return _get_gemini_llm()


def get_text_llm() -> Any:
    """LLM pour la génération de texte libre (email, final_response).

    Utilise TEXT_LLM_PROVIDER (défaut: gemini) — meilleure qualité de
    français, fenêtre de contexte 1M tokens.
    """
    provider = settings.text_llm_provider.lower()
    if provider == "mistral" and settings.mistral_api_key:
        return _get_mistral_llm()
    if provider == "gemini":
        return _get_gemini_llm()
    return _get_groq_llm()


def get_explain_llm() -> Any:
    """LLM dédié aux explications + recommandations stratégiques (simulation manuelle).

    Utilise EXPLAIN_LLM_PROVIDER (défaut: groq llama-3.3-70b) — tâche séparée
    de l'extraction JSON pour ne pas saturer un seul modèle.
    Génère du texte consultatif en français, une tâche par LLM.
    """
    provider = settings.explain_llm_provider.lower()
    if provider == "mistral" and settings.mistral_api_key:
        return _get_mistral_llm()
    if provider == "gemini":
        return _get_gemini_llm()
    return _get_groq_llm()


def get_llm_with_tools(tools: List[Any]) -> Any:
    """Retourne le LLM tool-calling (TOOL_LLM_PROVIDER) avec les tools bindés."""
    llm = get_tool_llm()
    logger.debug("Binding %d tool(s) to LLM [provider=%s]", len(tools), settings.tool_llm_provider)
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
