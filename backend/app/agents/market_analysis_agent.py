"""Market Analysis Agent — LangGraph node.

Handles user questions about market conditions, Talan risk exposure,
and GNN predictions via the conversation interface.

When the orchestrator detects domain='market' the pipeline routes here.
The agent:
1. Queries the World Model for a KG snapshot around Talan.
2. Fetches the latest analyses and GNN predictions from the DB.
3. Injects this context into MARKET_AGENT_SYSTEM_PROMPT.
4. Runs a bounded ReAct loop with market-specific tools.
5. Returns a structured Markdown response in French.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agents.state import AgentState
from app.core.llm import get_llm_with_tools, invoke_with_retry, truncate_tool_result
from app.prompts.market_analysis_prompts import MARKET_AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 3


# ── Market Analysis Tools (LangChain @tool) ───────────────────────────────────

@tool
def get_talan_risk_snapshot() -> str:
    """Retrieve the current risk exposure of Talan from the Knowledge Graph.

    Returns a JSON summary of all causal relations pointing at Talan,
    including impact scores, confidence, and reasons.
    """
    try:
        from app.services.market_analysis.world_model import WorldModel
        wm = WorldModel()
        if not wm.is_available():
            return json.dumps({"error": "Knowledge Graph unavailable", "risks": []})
        risks = wm.get_talan_risks()
        stats = wm.get_stats()
        return json.dumps({
            "talan_risks": risks[:20],
            "kg_stats": stats,
            "snapshot_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_latest_market_analyses(hours: int = 24, limit: int = 10) -> str:
    """Fetch the latest LLM-extracted causal analyses from the database.

    Args:
        hours: Look-back window in hours (default 24).
        limit: Maximum number of analyses to return (default 10).

    Returns JSON list of analyses sorted by talan_impact_score.
    """
    try:
        from app.services.market_analysis.analyst import NewsAnalyst
        analyst = NewsAnalyst()
        analyses = analyst.get_recent_analyses(hours=hours, limit=limit)
        # Trim for token budget
        trimmed = []
        for a in analyses:
            trimmed.append({
                "title": a.get("article_title", "")[:100],
                "event_summary": a.get("event_summary", "")[:200],
                "event_type": a.get("event_type"),
                "severity": a.get("severity"),
                "urgency": a.get("urgency"),
                "talan_impact_score": a.get("talan_impact_score"),
                "talan_impact_reason": a.get("talan_impact_reason", "")[:200],
                "talan_action": a.get("talan_action_recommended", "")[:150],
                "analysis_timestamp": str(a.get("analysis_timestamp", "")),
            })
        return json.dumps({"analyses": trimmed}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_gnn_predictions(trigger_event: str = "market_scan") -> str:
    """Run the GNN predictor on the current Knowledge Graph state.

    Returns impact predictions for all tracked companies, with special
    focus on Talan and hidden second/third-order risks.

    Args:
        trigger_event: Description of the event triggering this prediction.
    """
    try:
        from app.services.market_analysis.world_model import WorldModel
        from app.services.market_analysis.gnn_predictor import GNNPredictor
        from app.services.market_analysis.collector import MarketDataCollector

        wm = WorldModel()
        if not wm.is_available():
            return json.dumps({"error": "Knowledge Graph unavailable"})

        kg_snapshot = wm.get_snapshot("Talan", hops=2)
        price_data = MarketDataCollector().fetch_price_snapshot()
        gnn = GNNPredictor()
        result = gnn.predict(kg_snapshot, price_data=price_data, trigger_event=trigger_event)

        return json.dumps({
            "talan_impact": result.talan_prediction.model_dump() if result.talan_prediction else None,
            "systemic_risk": result.systemic_risk_score,
            "top_hidden_risks": [p.model_dump() for p in result.top_hidden_risks],
            "all_predictions": [p.model_dump() for p in result.predictions[:15]],
        }, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_hidden_risks(max_hops: int = 3) -> str:
    """Discover hidden second/third-order causal risks reaching Talan.

    Traverses the Knowledge Graph causal chains to find non-obvious risks
    that could propagate to Talan within the given number of hops.

    Args:
        max_hops: Maximum number of causal hops to explore (2-3 recommended).
    """
    try:
        from app.services.market_analysis.world_model import WorldModel
        wm = WorldModel()
        if not wm.is_available():
            return json.dumps({"error": "Knowledge Graph unavailable"})
        risks = wm.find_hidden_risks("Talan", max_hops=min(max_hops, 4))
        return json.dumps({"hidden_risks": risks}, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_pipeline_status() -> str:
    """Return the status of the market analysis pipeline (last run, articles count, etc.)."""
    try:
        from app.services.market_analysis.orchestrator import MarketAnalysisOrchestrator
        orchestrator = MarketAnalysisOrchestrator.get_instance()
        status = orchestrator.get_status()
        return json.dumps(status.model_dump(), ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


MARKET_TOOLS = [
    get_talan_risk_snapshot,
    get_latest_market_analyses,
    get_gnn_predictions,
    get_hidden_risks,
    get_pipeline_status,
]

_TOOLS_BY_NAME = {t.name: t for t in MARKET_TOOLS}


# ── LangGraph Node ────────────────────────────────────────────────────────────

def market_analysis_agent_node(state: AgentState) -> AgentState:
    """LangGraph node: handles market analysis queries via ReAct loop.

    Injects KG snapshot + recent analyses into the system prompt,
    then runs a tool-calling loop to answer the user's question.
    """
    t0 = time.perf_counter()
    user_id = state.get("user_id", "unknown")
    logger.info("market_analysis_agent_node start — user_id=%s", user_id)

    # Build system prompt with live KG context
    kg_snapshot_str = "{}"
    recent_str = "[]"
    try:
        from app.services.market_analysis.world_model import WorldModel
        wm = WorldModel()
        if wm.is_available():
            snap = wm.get_snapshot("Talan", hops=2)
            kg_snapshot_str = json.dumps(
                {
                    "nodes": snap["nodes"][:20],
                    "edges": snap["edges"][:30],
                    "kg_stats": wm.get_stats(),
                },
                ensure_ascii=False, default=str,
            )[:1500]
    except Exception as e:
        logger.debug("Could not load KG snapshot: %s", e)

    try:
        from app.services.market_analysis.analyst import NewsAnalyst
        analyses = NewsAnalyst().get_recent_analyses(hours=24, limit=5)
        recent_str = json.dumps(
            [
                {
                    "title": a.get("article_title", "")[:80],
                    "summary": a.get("event_summary", "")[:150],
                    "talan_impact": a.get("talan_impact_score"),
                    "urgency": a.get("urgency"),
                }
                for a in analyses
            ],
            ensure_ascii=False,
        )[:1000]
    except Exception as e:
        logger.debug("Could not load recent analyses: %s", e)

    system_content = MARKET_AGENT_SYSTEM_PROMPT.format(
        kg_snapshot=kg_snapshot_str,
        recent_analyses=recent_str,
    )

    accumulated_tool_results: Dict[str, Any] = {}
    new_messages: List[Any] = []

    try:
        llm_with_tools = get_llm_with_tools(MARKET_TOOLS)
    except Exception as exc:
        logger.exception("market_analysis_agent_node: failed to bind tools — %s", exc)
        return {**state, "error_message": f"Erreur d'initialisation de l'agent marché : {exc}"}

    messages: List[Any] = [
        SystemMessage(content=system_content)
    ] + list(state.get("messages", []))

    for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
        logger.debug("market_analysis_agent_node: iteration %d", iteration)
        try:
            ai_response: AIMessage = invoke_with_retry(llm_with_tools, messages)
        except Exception as exc:
            logger.exception("market_analysis_agent_node: LLM error at iter %d — %s", iteration, exc)
            return {
                **state,
                "messages": new_messages,
                "tool_results": accumulated_tool_results or None,
                "error_message": f"Erreur LLM analyse de marché : {exc}",
            }

        messages.append(ai_response)
        tool_calls = getattr(ai_response, "tool_calls", None) or []

        if not tool_calls:
            new_messages.append(ai_response)
            break

        tool_messages: List[ToolMessage] = []
        for tc in tool_calls:
            tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            tool_args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
            tool_call_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")

            logger.info("market_analysis_agent_node: tool '%s' args=%s", tool_name, tool_args)

            if tool_name not in _TOOLS_BY_NAME:
                tool_result = json.dumps({"error": f"Outil inconnu: {tool_name}"})
            else:
                try:
                    tool_result = _TOOLS_BY_NAME[tool_name].invoke(tool_args)
                    if not isinstance(tool_result, str):
                        tool_result = json.dumps(tool_result, ensure_ascii=False, default=str)
                except Exception as exc:
                    logger.exception("market_analysis_agent_node: tool '%s' failed — %s", tool_name, exc)
                    tool_result = json.dumps({"error": str(exc)})

            tool_result = truncate_tool_result(tool_result)
            tool_messages.append(ToolMessage(
                content=tool_result, tool_call_id=tool_call_id, name=tool_name
            ))
            accumulated_tool_results[tool_name] = tool_result

        messages.extend(tool_messages)

        if iteration == MAX_TOOL_ITERATIONS:
            logger.warning("market_analysis_agent_node: reached MAX_TOOL_ITERATIONS — forcing final")
            try:
                final: AIMessage = invoke_with_retry(llm_with_tools, messages)
                new_messages.append(final)
            except Exception as exc:
                return {
                    **state,
                    "messages": new_messages,
                    "tool_results": accumulated_tool_results or None,
                    "error_message": f"Erreur lors de la synthèse finale : {exc}",
                }

    if not accumulated_tool_results and new_messages:
        last = new_messages[-1]
        if isinstance(last, AIMessage) and last.content:
            accumulated_tool_results["market_answer"] = str(last.content)

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(
        "market_analysis_agent_node done — %d messages, %.0fms",
        len(new_messages), elapsed,
    )
    return {
        **state,
        "messages": new_messages,
        "tool_results": accumulated_tool_results if accumulated_tool_results else None,
    }
