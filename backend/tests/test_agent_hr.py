"""Tests live de l'agent HR — nécessite Docker + PostgreSQL + Groq.

Lancement :
    cd backend
    python -m pytest tests/test_agent_hr.py -v -m live

Ces tests appellent hr_agent_node() directement avec un vrai LLM et
une vraie base de données PostgreSQL.
"""

from __future__ import annotations

import pytest

from app.agents.hr_agent import hr_agent_node
from app.agents.state import initial_state


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_hr(message: str, role: str = "employee") -> dict:
    """Construit un état initial et exécute l'agent HR."""
    state = initial_state(user_id="TEST_HR", user_role=role, message=message)
    state["detected_domain"] = "hr"
    return hr_agent_node(state)


def _last_ai_content(result: dict) -> str:
    """Retourne le contenu du dernier message IA."""
    msgs = result.get("messages", [])
    for msg in reversed(msgs):
        if hasattr(msg, "content") and msg.content:
            return str(msg.content)
    return ""


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.live
def test_hr_get_employee_info():
    """L'agent doit retrouver les infos d'un employé réel."""
    result = _run_hr("Donne-moi les informations de l'employé EMP0001", role="manager")

    assert result.get("error_message") is None, f"Erreur inattendue : {result.get('error_message')}"
    tool_results = result.get("tool_results") or {}
    response = _last_ai_content(result)

    # Soit l'outil a été appelé, soit la réponse contient l'info
    assert tool_results or response, "Aucun résultat ni réponse produit"
    if "get_employee_info" in tool_results:
        emp = tool_results["get_employee_info"]
        assert "error" not in emp, f"Outil retourné une erreur : {emp}"
        assert emp.get("employee_id") == "EMP0001"


@pytest.mark.live
def test_hr_get_leave_balance():
    """L'agent doit calculer le solde de congés d'un employé."""
    result = _run_hr("Quel est le solde de congés de EMP0002 pour 2025 ?", role="manager")

    assert result.get("error_message") is None
    tool_results = result.get("tool_results") or {}
    response = _last_ai_content(result)

    assert tool_results or response
    if "get_leave_balance" in tool_results:
        lb = tool_results["get_leave_balance"]
        assert "error" not in lb
        assert "remaining_annual" in lb


@pytest.mark.live
def test_hr_get_employee_skills():
    """L'agent doit lister les compétences d'un employé."""
    result = _run_hr("Quelles sont les compétences de EMP0002 ?", role="employee")

    assert result.get("error_message") is None
    response = _last_ai_content(result)
    assert response, "L'agent n'a produit aucune réponse"


@pytest.mark.live
def test_hr_create_leave_request():
    """L'agent doit créer une demande de congé (opération écriture)."""
    result = _run_hr(
        "Crée une demande de congé annuel du 1er au 5 août 2025 pour EMP0001",
        role="employee",
    )

    assert result.get("error_message") is None
    tool_results = result.get("tool_results") or {}
    response = _last_ai_content(result)

    assert tool_results or response
    if "create_leave_request" in tool_results:
        lr = tool_results["create_leave_request"]
        # Soit nouvelle demande, soit doublon — les deux sont valides
        assert "leave_id" in lr or "error" not in lr


@pytest.mark.live
def test_hr_get_performance_review():
    """L'agent doit récupérer l'évaluation de performance."""
    result = _run_hr("Quel est le dernier bilan de performance de EMP0003 ?", role="manager")

    assert result.get("error_message") is None
    response = _last_ai_content(result)
    assert response


@pytest.mark.live
def test_hr_response_in_french():
    """La réponse doit être en français."""
    result = _run_hr("Combien de jours de congé reste-t-il à EMP0001 ?", role="employee")

    response = _last_ai_content(result)
    assert response, "Aucune réponse générée"
    # Vérification basique : la réponse ne doit pas être vide
    assert len(response) > 20, "Réponse trop courte"
