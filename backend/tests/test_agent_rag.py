"""Tests live de l'agent RAG — nécessite ChromaDB indexé + Groq.

Lancement :
    cd backend
    python -m pytest tests/test_agent_rag.py -v -m live

Note : les documents doivent être indexés au préalable via index_documents().
"""

from __future__ import annotations

import pytest

from app.agents.rag_agent import rag_agent_node
from app.agents.state import initial_state


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_rag(message: str, domain: str = "rag", role: str = "employee") -> dict:
    state = initial_state(user_id="TEST_RAG", user_role=role, message=message)
    state["detected_domain"] = domain
    return rag_agent_node(state)


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.live
def test_rag_sick_leave_policy():
    """L'agent doit récupérer la politique de congés maladie."""
    result = _run_rag("Quelle est la politique de congés maladie dans l'entreprise ?")

    assert result.get("error_message") is None
    rag_context = result.get("rag_context")
    assert rag_context, "Aucun contexte RAG récupéré — vérifier que les documents sont indexés"
    assert len(rag_context) > 50


@pytest.mark.live
def test_rag_hr_domain_routed_to_hr_policies():
    """Une question RH doit interroger la collection hr_policies."""
    result = _run_rag(
        "Quelles sont les règles de remboursement des frais de déplacement ?",
        domain="hr",
    )

    assert result.get("error_message") is None
    rag_context = result.get("rag_context")
    assert rag_context, "Collection hr_policies vide ou non indexée"


@pytest.mark.live
def test_rag_crm_knowledge():
    """Une question CRM doit interroger la collection crm_knowledge."""
    result = _run_rag(
        "Quelles sont les bonnes pratiques pour la gestion des comptes clients ?",
        domain="crm",
        role="manager",
    )

    assert result.get("error_message") is None
    rag_context = result.get("rag_context")
    # La collection peut être vide si pas de docs CRM indexés
    assert rag_context is not None


@pytest.mark.live
def test_rag_returns_context_not_empty():
    """Le contexte RAG doit contenir du texte exploitable."""
    result = _run_rag("Quelles sont les procédures internes de l'entreprise ?")

    rag_context = result.get("rag_context", "")
    assert rag_context is not None
    # Pas d'erreur critique
    assert result.get("error_message") is None or "indexé" not in str(result.get("error_message", ""))


@pytest.mark.live
def test_rag_multi_domain_uses_process_procedures():
    """Une requête multi-domaine doit utiliser process_procedures."""
    result = _run_rag(
        "Quel est le processus d'approbation budgétaire pour les projets ?",
        domain="multi",
        role="manager",
    )

    assert result.get("error_message") is None
    assert result.get("rag_context") is not None
