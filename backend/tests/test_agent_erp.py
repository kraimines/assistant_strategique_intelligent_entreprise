"""Tests live de l'agent ERP — nécessite Docker + PostgreSQL + Groq.

Lancement :
    cd backend
    python -m pytest tests/test_agent_erp.py -v -m live
"""

from __future__ import annotations

import pytest

from app.agents.erp_agent import erp_agent_node
from app.agents.state import initial_state


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_erp(message: str, role: str = "admin") -> dict:
    state = initial_state(user_id="TEST_ERP", user_role=role, message=message)
    state["detected_domain"] = "erp"
    return erp_agent_node(state)


def _last_ai_content(result: dict) -> str:
    for msg in reversed(result.get("messages", [])):
        if hasattr(msg, "content") and msg.content:
            return str(msg.content)
    return ""


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.live
def test_erp_invoice_status():
    """L'agent doit retourner les factures impayées d'un client."""
    result = _run_erp("Montre-moi toutes les factures impayées du client CUS0022")

    assert result.get("error_message") is None
    tool_results = result.get("tool_results") or {}
    response = _last_ai_content(result)

    assert tool_results or response
    if "get_invoice_status" in tool_results:
        inv = tool_results["get_invoice_status"]
        assert isinstance(inv, list), "Le résultat doit être une liste"


@pytest.mark.live
def test_erp_payment_history():
    """L'agent doit calculer le taux de recouvrement des paiements."""
    result = _run_erp("Quel est l'historique des paiements et le taux de recouvrement ?")

    assert result.get("error_message") is None
    tool_results = result.get("tool_results") or {}
    response = _last_ai_content(result)

    assert tool_results or response
    if "get_payment_history" in tool_results:
        ph = tool_results["get_payment_history"]
        assert "error" not in ph
        assert "recovery_rate_pct" in ph


@pytest.mark.live
def test_erp_list_sales_orders():
    """L'agent doit lister les commandes clients."""
    result = _run_erp("Liste les commandes clients en cours de livraison")

    assert result.get("error_message") is None
    response = _last_ai_content(result)
    assert response


@pytest.mark.live
def test_erp_supplier_info():
    """L'agent doit retourner les informations sur un fournisseur."""
    result = _run_erp("Donne-moi les informations sur le fournisseur SUP001")

    assert result.get("error_message") is None
    tool_results = result.get("tool_results") or {}
    response = _last_ai_content(result)

    assert tool_results or response
    if "get_supplier_info" in tool_results:
        sup = tool_results["get_supplier_info"]
        assert isinstance(sup, list)


@pytest.mark.live
def test_erp_purchase_orders():
    """L'agent doit lister les bons de commande fournisseurs."""
    result = _run_erp("Quels sont les bons de commande fournisseurs en attente ?")

    assert result.get("error_message") is None
    response = _last_ai_content(result)
    assert response


@pytest.mark.live
def test_erp_manager_read_only():
    """Un manager peut lire les données ERP."""
    result = _run_erp("Quel est le statut des factures ce mois-ci ?", role="manager")

    assert result.get("error_message") is None
    response = _last_ai_content(result)
    assert response
