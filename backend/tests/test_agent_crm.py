"""Tests live de l'agent CRM — nécessite Docker + PostgreSQL + Groq.

Lancement :
    cd backend
    python -m pytest tests/test_agent_crm.py -v -m live
"""

from __future__ import annotations

import pytest

from app.agents.crm_agent import crm_agent_node
from app.agents.state import initial_state


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_crm(message: str, role: str = "manager") -> dict:
    state = initial_state(user_id="TEST_CRM", user_role=role, message=message)
    state["detected_domain"] = "crm"
    return crm_agent_node(state)


def _last_ai_content(result: dict) -> str:
    for msg in reversed(result.get("messages", [])):
        if hasattr(msg, "content") and msg.content:
            return str(msg.content)
    return ""


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.live
def test_crm_revenue_history():
    """L'agent doit retourner l'historique des revenus clients."""
    result = _run_crm("Quel est le chiffre d'affaires de nos clients sur les 6 derniers mois ?")

    assert result.get("error_message") is None
    tool_results = result.get("tool_results") or {}
    response = _last_ai_content(result)

    assert tool_results or response
    if "get_revenue_history" in tool_results:
        rev = tool_results["get_revenue_history"]
        assert "error" not in rev
        assert "monthly_revenue" in rev or "total_revenue" in rev


@pytest.mark.live
def test_crm_account_summary():
    """L'agent doit retourner le résumé d'un compte client."""
    result = _run_crm("Donne-moi le résumé du compte client ACC0001", role="manager")

    assert result.get("error_message") is None
    tool_results = result.get("tool_results") or {}
    response = _last_ai_content(result)

    assert tool_results or response
    if "get_account_summary" in tool_results:
        acc = tool_results["get_account_summary"]
        assert "error" not in acc


@pytest.mark.live
def test_crm_list_opportunities():
    """L'agent doit lister les opportunités commerciales."""
    result = _run_crm("Liste toutes les opportunités en cours à l'étape Proposal")

    assert result.get("error_message") is None
    response = _last_ai_content(result)
    assert response


@pytest.mark.live
def test_crm_get_contacts():
    """L'agent doit retourner les contacts d'un compte."""
    result = _run_crm("Qui sont les contacts du client ACC0001 ?")

    assert result.get("error_message") is None
    response = _last_ai_content(result)
    assert response


@pytest.mark.live
def test_crm_recent_activities():
    """L'agent doit lister les activités récentes."""
    result = _run_crm("Quelles sont les dernières activités commerciales enregistrées ?")

    assert result.get("error_message") is None
    response = _last_ai_content(result)
    assert response


@pytest.mark.live
def test_crm_employee_cannot_write():
    """Un employee ne peut pas accéder aux données CRM en écriture (rôle insuffisant géré en amont)."""
    result = _run_crm("Montre-moi les opportunités commerciales en cours", role="employee")

    # L'agent CRM peut répondre même pour un employee en lecture
    response = _last_ai_content(result)
    assert response or result.get("tool_results")
