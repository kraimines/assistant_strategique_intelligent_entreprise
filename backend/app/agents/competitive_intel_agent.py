"""Competitive Intelligence agent node.

Implements a tool-calling ReAct loop (up to MAX_TOOL_ITERATIONS rounds) that
uses the four competitive intelligence tools to scrape public sources and
synthesize a structured strategic analysis, then stores the result in AgentState.
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
    scrape_company_news,
    scrape_job_postings,
    scrape_company_blog,
    analyze_competitive_landscape,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 4  # slightly higher — scraping needs more steps

COMPETITIVE_INTEL_TOOLS = [
    scrape_company_news,
    scrape_job_postings,
    scrape_company_blog,
    analyze_competitive_landscape,
]


def _build_tools_by_name() -> Dict[str, Any]:
    return {tool.name: tool for tool in COMPETITIVE_INTEL_TOOLS}


def competitive_intel_agent_node(state: AgentState) -> AgentState:
    """Competitive intelligence agent: scrapes public sources and synthesizes
    a structured strategic analysis via a bounded tool-calling ReAct loop.

    Workflow
    --------
    1. Bind all competitive intel tools to the LLM.
    2. Invoke the LLM with the system prompt + conversation history.
    3. Execute tool calls (scrape_company_news → scrape_job_postings →
       analyze_competitive_landscape).
    4. Re-invoke LLM with accumulated tool results.
    5. Repeat up to MAX_TOOL_ITERATIONS or until no more tool_calls.
    6. Store the final AIMessage and tool results in AgentState.

    Args:
        state: Current shared AgentState.

    Returns:
        Updated AgentState with new messages and tool_results populated.
    """
    t0 = time.perf_counter()
    user_id = state.get("user_id", "unknown")
    logger.info("competitive_intel_agent_node start — user_id=%s", user_id)

    accumulated_tool_results: Dict[str, Any] = {}
    tools_by_name = _build_tools_by_name()
    new_messages: List[Any] = []

    # ── Bind tools to LLM ────────────────────────────────────────────────────
    try:
        llm_with_tools = get_llm_with_tools(COMPETITIVE_INTEL_TOOLS)
    except Exception as exc:
        logger.exception("competitive_intel_agent_node: failed to bind tools — %s", exc)
        return {
            **state,
            "error_message": f"Erreur d'initialisation de l'agent de veille : {exc}",
        }

    system_msg = SystemMessage(content=COMPETITIVE_INTEL_SYSTEM_PROMPT)
    messages: List[Any] = [system_msg] + list(state.get("messages", []))

    # ── ReAct loop ────────────────────────────────────────────────────────────
    for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
        logger.debug("competitive_intel_agent_node: LLM iteration %d", iteration)

        try:
            t_llm = time.perf_counter()
            ai_response: AIMessage = invoke_with_retry(llm_with_tools, messages)
            logger.debug(
                "competitive_intel_agent_node: iteration %d — %.1f ms",
                iteration,
                (time.perf_counter() - t_llm) * 1000,
            )
        except Exception as exc:
            logger.exception(
                "competitive_intel_agent_node: LLM failed at iteration %d — %s", iteration, exc
            )
            return {
                **state,
                "messages": new_messages,
                "tool_results": accumulated_tool_results or None,
                "error_message": f"Erreur lors de l'analyse de veille : {exc}",
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

        # ── Execute tool calls ────────────────────────────────────────────────
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
                "competitive_intel_agent_node: calling tool '%s' args=%s",
                tool_name, tool_args,
            )

            if tool_name not in tools_by_name:
                tool_result: Any = {"error": f"Outil inconnu : '{tool_name}'"}
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

        # Force final response on last allowed iteration
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

    # If no SQL tools ran but the LLM answered from context, store it
    if not accumulated_tool_results and new_messages:
        last_ai = new_messages[-1]
        if isinstance(last_ai, AIMessage) and last_ai.content:
            accumulated_tool_results["competitive_intel_answer"] = str(last_ai.content)

    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "competitive_intel_agent_node done — %d messages, %d tool results — %.1f ms",
        len(new_messages),
        len(accumulated_tool_results),
        elapsed_ms,
    )

    return {
        **state,
        "messages": new_messages,
        "tool_results": accumulated_tool_results if accumulated_tool_results else None,
    }
