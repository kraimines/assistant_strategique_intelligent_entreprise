"""Report agent node — generates a formal Markdown French report.

Triggered when the orchestrator classifies the user's request as a report
demand (``requires_report = True``). The report agent runs *after* the
domain agents and RAG have gathered data: it consumes ``tool_results`` and
``rag_context`` already present in the state, then synthesises a structured
French report (executive summary, KPIs, alerts, recommendations) using
``REPORT_PROMPT``.

The result is written to ``state["final_response"]`` and appended to
``state["messages"]`` as an :class:`AIMessage`, so the graph can end after
this node without going through :func:`final_response_node`.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.state import AgentState
from app.core.llm import get_text_llm, invoke_with_retry
from app.prompts.final_response_prompts import REPORT_PROMPT

logger = logging.getLogger(__name__)


def report_agent_node(state: AgentState) -> AgentState:
    """Synthesise a formal Markdown French report from the gathered context.

    Reads ``tool_results`` (DB data from domain agents) and ``rag_context``
    (documentary context from the RAG agent) and produces a structured
    report following ``REPORT_PROMPT``. On LLM failure, produces a graceful
    French apology rather than raising.

    Args:
        state: Current shared AgentState — typically after a domain agent
            and/or rag_agent has run.

    Returns:
        Updated AgentState with ``final_response`` populated and a new
        :class:`AIMessage` appended to ``messages``.
    """
    t0 = time.perf_counter()
    logger.info(
        "report_agent_node start — user_id=%s domain=%s",
        state.get("user_id", "unknown"),
        state.get("detected_domain"),
    )

    user_message = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            user_message = str(msg.content)
            break

    user_role: str = state.get("user_role", "employee")
    tool_results = dict(state.get("tool_results") or {})
    rag_context: str = state.get("rag_context") or ""
    error_message: str = state.get("error_message") or ""

    if error_message and not tool_results:
        tool_results_str = f"Erreur rencontrée : {error_message}"
    elif tool_results:
        try:
            tool_results_str = json.dumps(
                tool_results, ensure_ascii=False, indent=2, default=str
            )
        except (TypeError, ValueError):
            tool_results_str = str(tool_results)
    else:
        tool_results_str = "Aucune donnée d'outil disponible."

    rag_ctx_str = (
        rag_context if rag_context else "Aucun contexte documentaire disponible."
    )

    prompt = REPORT_PROMPT.format(
        user_role=user_role,
        user_message=user_message,
        tool_results=tool_results_str,
        rag_context=rag_ctx_str,
        report_date=date.today().strftime("%d/%m/%Y"),
    )

    try:
        llm = get_text_llm()
        response = invoke_with_retry(llm, prompt)
        final_text = (
            response.content if hasattr(response, "content") else str(response)
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "report_agent_node: report generated (%d chars) — %.1f ms",
            len(final_text),
            elapsed_ms,
        )
    except Exception as exc:
        logger.exception("report_agent_node: LLM invocation failed — %s", exc)
        final_text = (
            "Désolé, une erreur s'est produite lors de la génération du rapport. "
            f"Détail : {exc}"
        )

    ai_msg = AIMessage(content=final_text)
    return {
        **state,
        "final_response": final_text,
        "messages": [ai_msg],
    }
