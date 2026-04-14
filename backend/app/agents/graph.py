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
from datetime import date
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.competitive_intel_agent import competitive_intel_agent_node
from app.agents.crm_agent import crm_agent_node
from app.agents.email_agent import email_agent_node
from app.agents.erp_agent import erp_agent_node
from app.agents.hr_agent import hr_agent_node
from app.agents.orchestrator import orchestrator_node
from app.agents.rag_agent import rag_agent_node
from app.agents.state import AgentState
from app.core.llm import get_llm, invoke_with_retry
from app.prompts.final_response_prompts import FINAL_RESPONSE_PROMPT, REPORT_PROMPT
from app.services.world_model_service import get_world_model_snapshot

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
    requires_email: bool = bool(state.get("requires_email"))

    # Envoi d'email sans données DB : aller directement à email_agent
    # (pas besoin de passer par rag_agent ni un domain agent)
    if requires_email and domain == "rag":
        logger.debug("route_from_orchestrator: pure email request (domain=rag) → email_agent")
        return "email_agent"

    # Domaines qui bénéficient du world model → passer par world_model_node
    if domain in {"hr", "crm", "erp", "multi"}:
        logger.debug("route_from_orchestrator: domain='%s' → world_model", domain)
        return "world_model"

    if domain == "competitive_intel":
        logger.debug("route_from_orchestrator: domain='competitive_intel' → competitive_intel_agent")
        return "competitive_intel_agent"

    if domain == "rag":
        return "rag_agent"

    # Fallback
    logger.debug("route_from_orchestrator: unknown domain '%s' → rag_agent", domain)
    return "rag_agent"


def route_after_domain_agent(state: AgentState) -> str:
    """Decide whether to supplement with RAG or email after a domain agent has run.

    Priority: error → final_response_node
              documentary keywords (no RAG yet) → rag_agent
              requires_email → email_agent
              default → final_response_node

    Args:
        state: Current shared AgentState after a domain agent has run.

    Returns:
        "rag_agent", "email_agent", or "final_response_node".
    """
    error = state.get("error_message")
    if error:
        # Si requires_email=True et que les données DB ont été récupérées malgré l'erreur
        # (erreur causée par tentative d'appel send_email dans le domain agent),
        # on route quand même vers email_agent pour effectuer l'envoi réel.
        if state.get("requires_email") and state.get("tool_results"):
            logger.debug(
                "route_after_domain_agent: error=%r but requires_email + tool_results → email_agent",
                error,
            )
            return "email_agent"
        logger.debug("route_after_domain_agent: error present → final_response_node")
        return "final_response_node"

    # If RAG context is already populated, skip rag_agent
    if state.get("rag_context"):
        if state.get("requires_email"):
            logger.debug("route_after_domain_agent: rag done + requires_email → email_agent")
            return "email_agent"
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

    if state.get("requires_email"):
        logger.debug("route_after_domain_agent: requires_email → email_agent")
        return "email_agent"

    return "final_response_node"


def route_from_world_model(state: AgentState) -> str:
    """Dispatch depuis world_model_node vers le bon domain agent.

    Applique la logique hr/crm/erp/multi après que le snapshot Neo4j
    a été récupéré et stocké dans state["world_model_snapshot"].

    Args:
        state: Current shared AgentState after world_model_node has run.

    Returns:
        Name of the next domain agent node (str).
    """
    domain: str = (state.get("detected_domain") or "rag").lower()

    if domain == "hr":
        return "hr_agent"
    if domain == "crm":
        return "crm_agent"
    if domain == "erp":
        return "erp_agent"

    if domain == "multi":
        secondary = (state.get("secondary_domain") or "").lower()
        if "hr" in secondary:
            return "hr_agent"
        return "crm_agent"

    logger.warning("route_from_world_model: domain inattendu '%s' → hr_agent", domain)
    return "hr_agent"


async def world_model_node(state: AgentState) -> AgentState:
    """Fetch a domain-scoped Neo4j snapshot and attach it to state.

    Runs between the orchestrator and the domain agents for hr / crm /
    erp / multi domains.  Enriches state with a graph snapshot that
    domain agents inject into their system prompts.

    Guarantees:
    - Never raises (all exceptions return empty snapshot)
    - Always returns within 3 seconds (timeout enforced by service)
    - world_model_snapshot is always set (Dict, possibly empty {})

    Args:
        state: Current shared AgentState after orchestrator has run.

    Returns:
        Updated AgentState with world_model_snapshot populated.
    """
    domain: str = (state.get("detected_domain") or "rag").lower()
    print(f"[WM] world_model_node CALLED — domain='{domain}'", flush=True)
    logger.debug("world_model_node: fetching snapshot for domain='%s'", domain)

    try:
        snapshot = await get_world_model_snapshot(domain)
        count = snapshot.get("count", 0) if snapshot else 0
        print(f"[WM] snapshot fetched — domain='{domain}' count={count}", flush=True)
        logger.info(
            "world_model_node: snapshot fetched — domain='%s' count=%d",
            domain,
            count,
        )
    except Exception as exc:
        print(f"[WM] unexpected error — {exc}", flush=True)
        logger.warning("world_model_node: unexpected error — %s", exc)
        snapshot = {}

    return {**state, "world_model_snapshot": snapshot}


def route_after_rag(state: AgentState) -> str:
    """Decide whether to send an email after rag_agent has run.

    Args:
        state: Current shared AgentState after rag_agent has run.

    Returns:
        "email_agent" or "final_response_node".
    """
    if state.get("error_message"):
        return "final_response_node"
    if state.get("requires_email"):
        logger.debug("route_after_rag: requires_email → email_agent")
        return "email_agent"
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
    tool_results = dict(state.get("tool_results") or {})
    rag_context: str = state.get("rag_context") or ""
    error_message: str = state.get("error_message") or ""
    email_result = state.get("email_result") or {}

    # ── Court-circuit email : réponse directe sans LLM ───────────────────────
    # Si le pipeline a uniquement envoyé un email (pas de tool_results DB),
    # on génère une réponse de confirmation directe pour économiser les tokens.
    if email_result and not tool_results:
        if email_result.get("success"):
            final_response_text = (
                f"## Email envoyé\n\n"
                f"L'email a été envoyé avec succès.\n\n"
                f"| Champ | Valeur |\n"
                f"|---|---|\n"
                f"| **Destinataire** | {email_result.get('to', '—')} |\n"
                f"| **Objet** | {email_result.get('subject', '—')} |\n"
            )
        else:
            err = email_result.get('smtp_message') or email_result.get('error', 'Erreur inconnue')
            final_response_text = (
                f"## Échec de l'envoi\n\n"
                f"L'email n'a pas pu être envoyé.\n\n"
                f"**Raison :** {err}"
            )
        ai_msg = AIMessage(content=final_response_text)
        return {**state, "final_response": final_response_text, "messages": [ai_msg]}

    # ── Court-circuit World Model : réponse directe sans re-synthèse LLM ────────
    # Quand un domain agent répond depuis le World Model (sans SQL), il stocke sa réponse
    # dans tool_results["world_model_answer"]. On la retourne directement.
    if "world_model_answer" in tool_results and len(tool_results) == 1 and not email_result:
        final_text = tool_results["world_model_answer"]
        logger.info("final_response_node: returning world_model_answer directly (%d chars)", len(final_text))
        ai_msg = AIMessage(content=final_text)
        return {**state, "final_response": final_text, "messages": [ai_msg]}

    # Injecte le résultat email dans tool_results pour que le LLM en soit informé
    if email_result:
        tool_results["email_sent"] = email_result

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
    requires_report: bool = bool(state.get("requires_report"))
    if requires_report:
        prompt = REPORT_PROMPT.format(
            user_role=user_role,
            user_message=user_message,
            tool_results=tool_results_str,
            rag_context=rag_ctx_str,
            report_date=date.today().strftime("%d/%m/%Y"),
        )
    else:
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
builder.add_node("world_model", world_model_node)
builder.add_node("hr_agent", hr_agent_node)
builder.add_node("crm_agent", crm_agent_node)
builder.add_node("erp_agent", erp_agent_node)
builder.add_node("rag_agent", rag_agent_node)
builder.add_node("email_agent", email_agent_node)
builder.add_node("competitive_intel_agent", competitive_intel_agent_node)
builder.add_node("final_response_node", final_response_node)

builder.set_entry_point("orchestrator")

builder.add_conditional_edges(
    "orchestrator",
    route_from_orchestrator,
    {
        "world_model":              "world_model",
        "hr_agent":                 "hr_agent",
        "crm_agent":                "crm_agent",
        "erp_agent":                "erp_agent",
        "rag_agent":                "rag_agent",
        "email_agent":              "email_agent",
        "competitive_intel_agent":  "competitive_intel_agent",
        "final_response_node":      "final_response_node",
    },
)

builder.add_conditional_edges(
    "world_model",
    route_from_world_model,
    {
        "hr_agent":  "hr_agent",
        "crm_agent": "crm_agent",
        "erp_agent": "erp_agent",
    },
)

for _agent in ("hr_agent", "crm_agent", "erp_agent"):
    builder.add_conditional_edges(
        _agent,
        route_after_domain_agent,
        {
            "rag_agent":           "rag_agent",
            "email_agent":         "email_agent",
            "final_response_node": "final_response_node",
        },
    )

builder.add_conditional_edges(
    "rag_agent",
    route_after_rag,
    {
        "email_agent":         "email_agent",
        "final_response_node": "final_response_node",
    },
)

builder.add_edge("email_agent", "final_response_node")
builder.add_edge("competitive_intel_agent", "final_response_node")
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

                elif node_name in ("hr_agent", "crm_agent", "erp_agent", "competitive_intel_agent"):
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
