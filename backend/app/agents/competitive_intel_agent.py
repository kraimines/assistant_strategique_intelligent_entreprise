"""Autonomous Competitive Intelligence agent node.

Implements a 7-tool ReAct loop (up to MAX_TOOL_ITERATIONS rounds).

Tool usage priority:
  1. query_stored_intel        — reads PostgreSQL, never scrapes (always first)
  2. detect_strategic_shift    — temporal delta analysis
  3. get_competitor_financial_data — yfinance real-time
  4. get_competitor_kg_context — Neo4j graph context
  5. scrape_company_news       — live Google News RSS (only when stale)
  6. scrape_job_postings       — live hiring signals (only when stale)
  7. analyze_competitive_landscape — synthesis (called after scraping)

The agent is backed by an autonomous scanner (CompetitiveIntelScanner) that
populates the PostgreSQL knowledge base every 6h. Most conversational answers
can be served entirely from stored data without live scraping.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from app.agents.state import AgentState
from app.core.llm import get_llm_with_tools, invoke_with_retry, truncate_tool_result
from app.prompts.competitive_intel_prompts import COMPETITIVE_INTEL_SYSTEM_PROMPT
from app.tools.competitive_intel_tools import (
    # Agentic tools — read stored intelligence (no live scraping)
    query_stored_intel,
    detect_strategic_shift,
    get_competitor_financial_data,
    get_competitor_kg_context,
    # Live scraping tools — used only when data is stale
    scrape_company_news,
    scrape_job_postings,
    analyze_competitive_landscape,
)

logger = logging.getLogger(__name__)

# Higher than other agents — stored queries + live scraping may need more steps
MAX_TOOL_ITERATIONS = 5

COMPETITIVE_INTEL_TOOLS = [
    query_stored_intel,              # 1 — stored KB (no cost)
    detect_strategic_shift,          # 2 — temporal delta
    get_competitor_financial_data,   # 3 — yfinance
    get_competitor_kg_context,       # 4 — Neo4j
    scrape_company_news,             # 5 — live (stale only)
    scrape_job_postings,             # 6 — live (stale only)
    analyze_competitive_landscape,   # 7 — synthesis
]


def _build_tools_by_name() -> Dict[str, Any]:
    return {tool.name: tool for tool in COMPETITIVE_INTEL_TOOLS}


def _build_context_prefix() -> str:
    """Inject latest watchlist summary into the system prompt as live context.

    Fetches the most recent snapshot for each watched company so the LLM
    starts with awareness of the current threat landscape — not just instructions.
    Falls back gracefully if the DB is unavailable.
    """
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session
        from app.core.config import settings
        from functools import lru_cache

        @lru_cache(maxsize=1)
        def _engine():
            return create_engine(settings.database_url("hr"), pool_pre_ping=True)

        engine = _engine()
        with Session(engine) as session:
            rows = session.execute(
                text(
                    "SELECT DISTINCT ON (company_name) "
                    "company_name, threat_level, threat_label, "
                    "is_significant, change_summary, snapshot_at "
                    "FROM ci_snapshots "
                    "ORDER BY company_name, snapshot_at DESC"
                )
            ).fetchall()

        if not rows:
            return ""

        lines = ["## Current Watchlist Status (from knowledge base)\n"]
        lines.append("| Company | Threat | Label | Significant | Last scan |")
        lines.append("|---|---|---|---|---|")
        for r in rows:
            sig = "⚠️ YES" if r[3] else "—"
            lines.append(
                f"| {r[0]} | {(r[1] or 0):.0%} | {r[2] or '?'} | {sig} | {str(r[5])[:16]} |"
            )

        # Unacknowledged alerts
        with Session(engine) as session:
            alerts = session.execute(
                text(
                    "SELECT company_name, level, title FROM ci_alerts "
                    "WHERE acknowledged = false "
                    "ORDER BY created_at DESC LIMIT 5"
                )
            ).fetchall()

        if alerts:
            lines.append("\n## Pending Alerts")
            for a in alerts:
                lines.append(f"- [{a[1].upper()}] **{a[0]}**: {a[2][:80]}")

        return "\n".join(lines) + "\n\n"
    except Exception:
        return ""


def competitive_intel_agent_node(state: AgentState) -> AgentState:
    """Agentic competitive intelligence node.

    Serves queries from the PostgreSQL knowledge base first (no scraping cost).
    Falls back to live scraping only when data is stale (> 6h) or company
    is not in the watchlist. Reasons over time (delta detection) and across
    the Neo4j knowledge graph.

    Args:
        state: Shared LangGraph AgentState.

    Returns:
        Updated AgentState with new messages and tool_results.
    """
    t0 = time.perf_counter()
    user_id = state.get("user_id", "unknown")
    logger.info("competitive_intel_agent_node start — user_id=%s", user_id)

    # ── Build system prompt with live watchlist context ────────────────────────
    context_prefix = _build_context_prefix()
    system_content = context_prefix + COMPETITIVE_INTEL_SYSTEM_PROMPT

    accumulated_tool_results: Dict[str, Any] = {}
    tools_by_name = _build_tools_by_name()
    new_messages: List[Any] = []

    # ── Bind tools ─────────────────────────────────────────────────────────────
    try:
        llm_with_tools = get_llm_with_tools(COMPETITIVE_INTEL_TOOLS)
    except Exception as exc:
        logger.exception("competitive_intel_agent_node: failed to bind tools — %s", exc)
        return {
            **state,
            "error_message": f"Erreur d'initialisation de l'agent de veille : {exc}",
        }

    messages: List[Any] = [
        SystemMessage(content=system_content)
    ] + list(state.get("messages", []))

    # ── ReAct loop ─────────────────────────────────────────────────────────────
    for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
        logger.debug("competitive_intel_agent_node: iteration %d/%d", iteration, MAX_TOOL_ITERATIONS)

        try:
            t_llm = time.perf_counter()
            ai_response: AIMessage = invoke_with_retry(llm_with_tools, messages)
            logger.debug(
                "competitive_intel_agent_node: iteration %d — %.0fms",
                iteration, (time.perf_counter() - t_llm) * 1000,
            )
        except Exception as exc:
            logger.exception(
                "competitive_intel_agent_node: LLM failed at iteration %d — %s", iteration, exc
            )
            return {
                **state,
                "messages": new_messages,
                "tool_results": accumulated_tool_results or None,
                "error_message": f"Erreur LLM veille concurrentielle : {exc}",
            }

        messages.append(ai_response)
        tool_calls = getattr(ai_response, "tool_calls", None) or []

        if not tool_calls:
            logger.info(
                "competitive_intel_agent_node: no tool calls at iteration %d — final answer",
                iteration,
            )
            new_messages.append(ai_response)
            break

        # ── Execute tool calls ─────────────────────────────────────────────────
        tool_messages: List[ToolMessage] = []

        for tool_call in tool_calls:
            tool_name: str = (
                tool_call.get("name", "") if isinstance(tool_call, dict)
                else getattr(tool_call, "name", "")
            )
            tool_args: Dict[str, Any] = (
                tool_call.get("args", {}) if isinstance(tool_call, dict)
                else getattr(tool_call, "args", {})
            )
            tool_call_id: str = (
                tool_call.get("id", "") if isinstance(tool_call, dict)
                else getattr(tool_call, "id", "")
            )

            logger.info(
                "competitive_intel_agent_node: tool '%s' args=%s",
                tool_name, tool_args,
            )

            if tool_name not in tools_by_name:
                tool_result: Any = {"error": f"Unknown tool: '{tool_name}'"}
                logger.warning("competitive_intel_agent_node: unknown tool '%s'", tool_name)
            else:
                try:
                    tool_result = tools_by_name[tool_name].invoke(tool_args)
                except Exception as exc:
                    logger.exception(
                        "competitive_intel_agent_node: tool '%s' raised — %s", tool_name, exc
                    )
                    tool_result = {"error": str(exc)}

            try:
                result_str = json.dumps(tool_result, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                result_str = str(tool_result)
            result_str = truncate_tool_result(result_str)

            tool_messages.append(ToolMessage(
                content=result_str,
                tool_call_id=tool_call_id,
                name=tool_name,
            ))
            accumulated_tool_results[tool_name] = tool_result

        messages.extend(tool_messages)

        # Force final response on last iteration
        if iteration == MAX_TOOL_ITERATIONS:
            logger.warning(
                "competitive_intel_agent_node: reached MAX_TOOL_ITERATIONS=%d — forcing final",
                MAX_TOOL_ITERATIONS,
            )
            try:
                final_response: AIMessage = invoke_with_retry(llm_with_tools, messages)
                new_messages.append(final_response)
            except Exception as exc:
                logger.exception(
                    "competitive_intel_agent_node: forced final LLM call failed — %s", exc
                )
                return {
                    **state,
                    "messages": new_messages,
                    "tool_results": accumulated_tool_results or None,
                    "error_message": f"Erreur lors de la synthèse finale : {exc}",
                }

    # Fallback: if LLM answered from context without tools
    if not accumulated_tool_results and new_messages:
        last = new_messages[-1]
        if isinstance(last, AIMessage) and last.content:
            accumulated_tool_results["competitive_intel_answer"] = str(last.content)

    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "competitive_intel_agent_node done — %d messages, %d tools called — %.0fms",
        len(new_messages), len(accumulated_tool_results), elapsed_ms,
    )

    return {
        **state,
        "messages": new_messages,
        "tool_results": accumulated_tool_results if accumulated_tool_results else None,
    }
