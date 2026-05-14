"""CRM domain agent node.

Implements a tool-calling ReAct loop (up to MAX_TOOL_ITERATIONS rounds) that
uses the five CRM tools to answer the user's question, then stores the final AI
response and all tool results in AgentState.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from app.agents.state import AgentState
from app.core.llm import get_llm_with_tools, invoke_with_retry, truncate_tool_result
from app.prompts.crm_prompts import CRM_SYSTEM_PROMPT
from app.tools.crm_tools import (
    search_account_by_name,
    get_account_summary,
    get_contacts,
    get_global_revenue_summary,
    get_revenue_history,
    list_opportunities,
    list_recent_activities,
)

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_TOOL_ITERATIONS = 3

# ── Tool registry ─────────────────────────────────────────────────────────────

CRM_TOOLS = [
    search_account_by_name,
    get_account_summary,
    get_global_revenue_summary,
    list_opportunities,
    get_revenue_history,
    get_contacts,
    list_recent_activities,
]


def _build_tools_by_name() -> Dict[str, Any]:
    """Return a mapping of tool name → tool callable for fast lookup.

    Returns:
        Dict mapping each tool's .name attribute to the tool object.
    """
    return {tool.name: tool for tool in CRM_TOOLS}


# ── Node ──────────────────────────────────────────────────────────────────────

def crm_agent_node(state: AgentState) -> AgentState:
    """CRM domain agent: answers CRM questions via a bounded tool-calling loop.

    Workflow
    --------
    1. Build ``llm_with_tools`` by binding all CRM tools to the base LLM.
    2. Prepend a SystemMessage containing CRM_SYSTEM_PROMPT to the conversation.
    3. Invoke the LLM; if tool_calls are present in the response, execute each
       tool and collect ToolMessages.
    4. Re-invoke the LLM with the tool results appended to the message list.
    5. Repeat up to MAX_TOOL_ITERATIONS times or until no more tool_calls.
    6. Store the final AIMessage in state["messages"] and aggregated tool
       results in state["tool_results"].

    Error handling: any exception at the LLM or tool level is caught, logged,
    and surfaced via state["error_message"].  The node always returns a valid
    AgentState dict.

    Args:
        state: Current shared AgentState.

    Returns:
        Updated AgentState with new messages and tool_results populated.
    """
    t0 = time.perf_counter()
    user_id = state.get("user_id", "unknown")
    logger.info("crm_agent_node start — user_id=%s", user_id)

    # ── Initialise accumulators ───────────────────────────────────────────────
    accumulated_tool_results: Dict[str, Any] = {}  # fresh per turn
    tools_by_name = _build_tools_by_name()
    new_messages: List[Any] = []  # messages produced by this node only

    # ── Bind tools to LLM ────────────────────────────────────────────────────
    try:
        llm_with_tools = get_llm_with_tools(CRM_TOOLS)
    except Exception as exc:
        logger.exception("crm_agent_node: failed to bind tools to LLM — %s", exc)
        return {
            **state,
            "error_message": f"Erreur d'initialisation de l'agent CRM : {exc}",
        }

    # ── Build initial message list ────────────────────────────────────────────
    _wm = state.get("world_model_snapshot") or {}
    _wm_context = ""
    if _wm and _wm.get("records"):
        lines = ["opportunity_id | deal_name | stage | amount | account | owner"]
        lines.append("---|---|---|---|---|---")
        for r in _wm["records"]:
            lines.append(
                f"{r.get('opportunity_id','?')} | {r.get('deal_name','?')} | "
                f"{r.get('stage','?')} | {r.get('amount','?')} | "
                f"{r.get('account','?')} | {r.get('owner') or '—'}"
            )
        _wm_context = (
            "\n\nCONTEXTE ENTREPRISE (World Model — données Neo4j) :\n"
            + "\n".join(lines)
        )
    system_msg = SystemMessage(content=CRM_SYSTEM_PROMPT + _wm_context)
    messages: List[Any] = [system_msg] + list(state.get("messages", []))

    requires_report: bool = bool(state.get("requires_report", False))

    # ── Tool-calling ReAct loop ───────────────────────────────────────────────
    for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
        logger.debug("crm_agent_node: LLM invoke iteration %d", iteration)

        try:
            t_llm = time.perf_counter()
            ai_response: AIMessage = invoke_with_retry(llm_with_tools, messages)
            llm_ms = (time.perf_counter() - t_llm) * 1000
            logger.debug(
                "crm_agent_node: LLM iteration %d completed in %.1f ms", iteration, llm_ms
            )
        except Exception as exc:
            logger.exception(
                "crm_agent_node: LLM invocation failed at iteration %d — %s",
                iteration,
                exc,
            )
            error_msg = f"Erreur lors de la génération de la réponse CRM : {exc}"
            return {
                **state,
                "messages": new_messages,
                "tool_results": accumulated_tool_results or None,
                "error_message": error_msg,
            }

        # Append AI response to our working message list
        messages.append(ai_response)

        # ── Check for tool calls ──────────────────────────────────────────────
        tool_calls = getattr(ai_response, "tool_calls", None) or []

        if not tool_calls:
            # No more tool calls — this is the final answer
            logger.info(
                "crm_agent_node: no tool calls at iteration %d — treating as final answer",
                iteration,
            )
            new_messages.append(ai_response)
            break

        # ── Execute each requested tool ───────────────────────────────────────
        tool_messages: List[ToolMessage] = []

        for tool_call in tool_calls:
            tool_name: str = tool_call.get("name", "") if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
            tool_args: Dict[str, Any] = tool_call.get("args", {}) if isinstance(tool_call, dict) else getattr(tool_call, "args", {})
            tool_call_id: str = tool_call.get("id", "") if isinstance(tool_call, dict) else getattr(tool_call, "id", "")

            logger.info("crm_agent_node: calling tool '%s' args=%s", tool_name, tool_args)
            t_tool = time.perf_counter()

            if tool_name not in tools_by_name:
                tool_result: Any = {"error": f"Outil inconnu : '{tool_name}'"}
                logger.warning("crm_agent_node: unknown tool requested — '%s'", tool_name)
            else:
                try:
                    tool_result = tools_by_name[tool_name].invoke(tool_args)
                except Exception as exc:
                    logger.exception(
                        "crm_agent_node: tool '%s' raised an exception — %s",
                        tool_name,
                        exc,
                    )
                    tool_result = {"error": str(exc)}

            tool_ms = (time.perf_counter() - t_tool) * 1000
            logger.info(
                "crm_agent_node: tool '%s' completed in %.1f ms", tool_name, tool_ms
            )

            # Serialise result for ToolMessage content (truncate if too large)
            try:
                result_str = json.dumps(tool_result, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                result_str = str(tool_result)
            result_str = truncate_tool_result(result_str)

            tool_msg = ToolMessage(
                content=result_str,
                tool_call_id=tool_call_id,
                name=tool_name,
            )
            tool_messages.append(tool_msg)

            # Accumulate structured results keyed by tool name
            accumulated_tool_results[tool_name] = tool_result

        # Append tool results to the working message list for next LLM call
        messages.extend(tool_messages)

        # Report mode: skip agent synthesis — final_response_node handles it
        if requires_report and accumulated_tool_results:
            logger.info(
                "crm_agent_node: report mode — skipping synthesis LLM call, "
                "passing raw tool results to final_response_node"
            )
            new_messages.append(ai_response)
            break

        # If this was the last allowed iteration, force a final LLM call
        if iteration == MAX_TOOL_ITERATIONS:
            logger.warning(
                "crm_agent_node: reached MAX_TOOL_ITERATIONS=%d — forcing final response",
                MAX_TOOL_ITERATIONS,
            )
            try:
                t_final = time.perf_counter()
                final_response: AIMessage = invoke_with_retry(llm_with_tools, messages)
                final_ms = (time.perf_counter() - t_final) * 1000
                logger.debug(
                    "crm_agent_node: final forced LLM call completed in %.1f ms", final_ms
                )
                new_messages.append(final_response)
            except Exception as exc:
                logger.exception(
                    "crm_agent_node: final forced LLM call failed — %s", exc
                )
                return {
                    **state,
                    "messages": new_messages,
                    "tool_results": accumulated_tool_results or None,
                    "error_message": f"Erreur lors de la synthèse finale CRM : {exc}",
                }

    if not accumulated_tool_results and new_messages:
        last_ai = new_messages[-1]
        if isinstance(last_ai, AIMessage) and last_ai.content:
            accumulated_tool_results["world_model_answer"] = str(last_ai.content)

    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "crm_agent_node done — %d new messages, %d tool results — %.1f ms total",
        len(new_messages),
        len(accumulated_tool_results),
        elapsed_ms,
    )

    return {
        **state,
        "messages": new_messages,
        "tool_results": accumulated_tool_results if accumulated_tool_results else None,
    }
