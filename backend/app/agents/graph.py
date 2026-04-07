"""LangGraph StateGraph — full pipeline wiring for the Talan enterprise assistant.

Graph topology
--------------
  orchestrator
      │
      ├─ hr_agent  ─┬─ rag_agent ──┐
      ├─ crm_agent ─┤              │
      ├─ erp_agent ─┘              ▼
      ├─ rag_agent ──────── final_response_node ── END
      └─ final_response_node (on error) ───────────┘

Routing
-------
- route_from_orchestrator : dispatches to the appropriate domain agent.
- route_after_domain_agent: optionally calls rag_agent for documentary queries.
- rag_agent always feeds directly into final_response_node.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.crm_agent import crm_agent_node
from app.agents.erp_agent import erp_agent_node
from app.agents.hr_agent import hr_agent_node
from app.agents.orchestrator import orchestrator_node
from app.agents.rag_agent import rag_agent_node
from app.agents.state import AgentState
from app.core.llm import get_llm, invoke_with_retry
from app.prompts.final_response_prompts import FINAL_RESPONSE_PROMPT

logger = logging.getLogger(__name__)

# ── Documentary intent keywords ───────────────────────────────────────────────

_DOCUMENTARY_KEYWORDS = [
    "politique",
    "procédure",
    "comment",
    "guide",
    "règlement",
    "FAQ",
    "documentation",
]


# ── Routing functions ─────────────────────────────────────────────────────────

def route_from_orchestrator(state: AgentState) -> str:
    """Dispatch from the orchestrator to the appropriate domain agent.

    Returns the node name to visit next based on the classified domain stored
    in state["detected_domain"].  Short-circuits to final_response_node on error.

    Args:
        state: Current shared AgentState after the orchestrator has run.

    Returns:
        Name of the next node to visit (str).
    """
    if state.get("error_message"):
        logger.debug("route_from_orchestrator: error present → final_response_node")
        return "final_response_node"

    domain: str = (state.get("detected_domain") or "rag").lower()

    if domain == "hr":
        return "hr_agent"
    if domain == "crm":
        return "crm_agent"
    if domain == "erp":
        return "erp_agent"
    if domain == "rag":
        return "rag_agent"

    if domain == "multi":
        # For multi-domain queries, start with the primary domain agent.
        # Check secondary_domain and detected_domain for "hr" presence.
        secondary = (state.get("secondary_domain") or "").lower()
        detected = (state.get("detected_domain") or "").lower()
        if "hr" in secondary or "hr" in detected:
            return "hr_agent"
        return "crm_agent"

    # Fallback
    logger.debug("route_from_orchestrator: unknown domain '%s' → rag_agent", domain)
    return "rag_agent"


def route_after_domain_agent(state: AgentState) -> str:
    """Decide whether to supplement with RAG after a domain agent has run.

    If the last user message contains documentary keywords and no RAG context
    has been gathered yet, routes to rag_agent.  Otherwise goes directly to
    final_response_node.

    Args:
        state: Current shared AgentState after a domain agent has run.

    Returns:
        "rag_agent" or "final_response_node".
    """
    if state.get("error_message"):
        logger.debug("route_after_domain_agent: error present → final_response_node")
        return "final_response_node"

    # If RAG context is already populated, skip rag_agent
    if state.get("rag_context"):
        return "final_response_node"

    # Check if the last human message contains documentary keywords
    last_human_msg = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            last_human_msg = str(msg.content).lower()
            break

    if any(kw.lower() in last_human_msg for kw in _DOCUMENTARY_KEYWORDS):
        logger.debug("route_after_domain_agent: documentary intent detected → rag_agent")
        return "rag_agent"

    return "final_response_node"


# ── Final response synthesis node ─────────────────────────────────────────────

def final_response_node(state: AgentState) -> AgentState:
    """Synthesise a Markdown French response from tool results + RAG context.

    Assembles all available data (tool_results, rag_context, last user message,
    user_role) into FINAL_RESPONSE_PROMPT and invokes the LLM to produce a
    polished response.  The result is stored in state["final_response"] and also
    appended to state["messages"] as an AIMessage.

    On error, produces a graceful French apology message instead of raising.

    Args:
        state: Current shared AgentState.

    Returns:
        Updated AgentState with final_response and updated messages.
    """
    # ── Extract last human message ────────────────────────────────────────────
    user_message = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            user_message = str(msg.content)
            break

    user_role: str = state.get("user_role", "employee")
    tool_results = state.get("tool_results") or {}
    rag_context: str = state.get("rag_context") or ""
    error_message: str = state.get("error_message") or ""

    # ── Format tool_results for the prompt ───────────────────────────────────
    if error_message and not tool_results:
        tool_results_str = f"Erreur rencontrée : {error_message}"
    elif tool_results:
        try:
            tool_results_str = json.dumps(tool_results, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError):
            tool_results_str = str(tool_results)
    else:
        tool_results_str = "Aucun résultat d'outil disponible."

    rag_ctx_str = rag_context if rag_context else "Aucun contexte documentaire disponible."

    # ── Build and invoke prompt ───────────────────────────────────────────────
    prompt = FINAL_RESPONSE_PROMPT.format(
        user_role=user_role,
        user_message=user_message,
        tool_results=tool_results_str,
        rag_context=rag_ctx_str,
    )

    final_response_text: str
    try:
        llm = get_llm()
        response = invoke_with_retry(llm, prompt)
        final_response_text = (
            response.content
            if hasattr(response, "content")
            else str(response)
        )
        logger.info(
            "final_response_node: response generated (%d chars)", len(final_response_text)
        )
    except Exception as exc:
        logger.exception("final_response_node: LLM invocation failed — %s", exc)
        final_response_text = (
            "Désolé, une erreur s'est produite lors de la génération de la réponse. "
            f"Détail : {exc}"
        )

    ai_msg = AIMessage(content=final_response_text)

    return {
        **state,
        "final_response": final_response_text,
        "messages": [ai_msg],
    }


# ── Graph construction ────────────────────────────────────────────────────────

builder = StateGraph(AgentState)

builder.add_node("orchestrator", orchestrator_node)
builder.add_node("hr_agent", hr_agent_node)
builder.add_node("crm_agent", crm_agent_node)
builder.add_node("erp_agent", erp_agent_node)
builder.add_node("rag_agent", rag_agent_node)
builder.add_node("final_response_node", final_response_node)

builder.set_entry_point("orchestrator")

builder.add_conditional_edges(
    "orchestrator",
    route_from_orchestrator,
    {
        "hr_agent":             "hr_agent",
        "crm_agent":            "crm_agent",
        "erp_agent":            "erp_agent",
        "rag_agent":            "rag_agent",
        "final_response_node":  "final_response_node",
    },
)

for _agent in ("hr_agent", "crm_agent", "erp_agent"):
    builder.add_conditional_edges(
        _agent,
        route_after_domain_agent,
        {
            "rag_agent":           "rag_agent",
            "final_response_node": "final_response_node",
        },
    )

builder.add_edge("rag_agent", "final_response_node")
builder.add_edge("final_response_node", END)

graph = builder.compile(checkpointer=MemorySaver())

logger.info("LangGraph pipeline compiled successfully.")


# ── Async SSE streaming helper ────────────────────────────────────────────────

async def run_agent_graph(
    state: AgentState,
    conversation_id: str,
) -> AsyncGenerator[str, None]:
    """Stream the LangGraph pipeline execution as Server-Sent Events.

    Each yielded string is a fully-formed SSE data line:
      ``data: <JSON>\\n\\n``

    Event types emitted
    -------------------
    - ``{"type": "token",       "content": "..."}``   — response text chunk (~50 chars)
    - ``{"type": "tool_result", "tool": "name", "success": true}`` — tool execution
    - ``{"type": "done",        "conversation_id": "...", "tokens_used": 0}``
    - ``{"type": "error",       "message": "..."}``

    Args:
        state:           Initial AgentState for this pipeline run.
        conversation_id: Thread identifier for MemorySaver checkpointing.

    Yields:
        SSE-formatted JSON strings.
    """
    config = {"configurable": {"thread_id": conversation_id}}

    try:
        async for event in graph.astream(state, config=config):
            for node_name, node_output in event.items():
                if not isinstance(node_output, dict):
                    continue

                if node_name == "final_response_node":
                    response_text: str = node_output.get("final_response") or ""
                    if response_text:
                        # Yield in chunks of ~50 chars to simulate token streaming
                        chunk_size = 50
                        for i in range(0, len(response_text), chunk_size):
                            chunk = response_text[i: i + chunk_size]
                            yield (
                                f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
                            )

                elif node_name in ("hr_agent", "crm_agent", "erp_agent"):
                    tool_results: dict = node_output.get("tool_results") or {}
                    for tool_name in tool_results:
                        yield (
                            f"data: {json.dumps({'type': 'tool_result', 'tool': tool_name, 'success': True})}\n\n"
                        )

        yield (
            f"data: {json.dumps({'type': 'done', 'conversation_id': conversation_id, 'tokens_used': 0})}\n\n"
        )

    except Exception as exc:
        logger.exception("run_agent_graph: unhandled exception — %s", exc)
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
