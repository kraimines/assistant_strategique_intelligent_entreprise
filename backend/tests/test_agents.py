"""Tests live end-to-end — orchestrateur + agents (pipeline complet).

Nécessite : Docker + PostgreSQL + Groq API key dans backend/.env

Lancement :
    cd backend
    python -m pytest tests/test_agents.py -v -m live
"""

from __future__ import annotations

import pytest

from app.agents.orchestrator import orchestrator_node
from app.agents.hr_agent import hr_agent_node
from app.agents.crm_agent import crm_agent_node
from app.agents.erp_agent import erp_agent_node
from app.agents.state import initial_state


# ── Pipeline helper ───────────────────────────────────────────────────────────

AGENT_MAP = {
    "hr":  hr_agent_node,
    "crm": crm_agent_node,
    "erp": erp_agent_node,
}


def _run_pipeline(message: str, role: str) -> dict:
    """Orchestrateur → agent de domaine (pipeline complet, sans RAG)."""
    state = initial_state(user_id="TEST_E2E", user_role=role, message=message)
    state = orchestrator_node(state)

    if state.get("error_message"):
        return state

    domain = state.get("detected_domain", "rag")
    agent_fn = AGENT_MAP.get(domain)
    if agent_fn:
        state = agent_fn(state)
    return state


def _last_ai_content(result: dict) -> str:
    for msg in reversed(result.get("messages", [])):
        if hasattr(msg, "content") and msg.content:
            return str(msg.content)
    return ""


# ── Tests end-to-end ──────────────────────────────────────────────────────────

@pytest.mark.live
def test_pipeline_hr_employee_skills():
    """Pipeline complet : question RH → orchestrateur → hr_agent."""
    result = _run_pipeline("Quelles sont les compétences de EMP0002 ?", role="employee")

    assert result.get("detected_domain") == "hr"
    assert result.get("error_message") is None
    response = _last_ai_content(result)
    assert response, "Aucune réponse générée"


@pytest.mark.live
def test_pipeline_crm_revenue():
    """Pipeline complet : question CRM → orchestrateur → crm_agent."""
    result = _run_pipeline(
        "Quel est le chiffre d'affaires de nos clients sur les 3 derniers mois ?",
        role="manager",
    )

    assert result.get("detected_domain") == "crm"
    assert result.get("error_message") is None
    response = _last_ai_content(result)
    assert response


@pytest.mark.live
def test_pipeline_erp_invoices():
    """Pipeline complet : question ERP → orchestrateur → erp_agent."""
    result = _run_pipeline(
        "Montre-moi toutes les factures impayées du client CUS0022",
        role="admin",
    )

    assert result.get("detected_domain") == "erp"
    assert result.get("error_message") is None
    response = _last_ai_content(result)
    assert response


@pytest.mark.live
def test_pipeline_permission_denied():
    """Un employee ne peut pas créer une commande ERP — permission refusée."""
    result = _run_pipeline(
        "Crée une commande fournisseur pour le fournisseur SUP001",
        role="employee",
    )

    assert result.get("detected_domain") == "erp"
    assert result.get("error_message") is not None
    assert "permission" in result["error_message"].lower()


@pytest.mark.live
def test_pipeline_confidence_and_routing():
    """L'orchestrateur doit classifier avec confiance >= 0.7 et router correctement."""
    state = initial_state(
        user_id="TEST_E2E",
        user_role="manager",
        message="Quel est le budget alloué au projet PRJ0001 ?",
    )
    state = orchestrator_node(state)

    assert state.get("domain_confidence", 0) >= 0.7
    assert state.get("detected_domain") in {"hr", "erp", "multi"}
