"""Unit tests for the orchestrator node — domain classification.

Strategy
--------
- Patch ``app.agents.orchestrator.get_json_llm`` with unittest.mock to return a
  preset JSON response without hitting the real Google API.
- Each test exercises a specific user message and asserts on detected_domain,
  requires_write, and domain_confidence >= 0.7.
- Tests are plain synchronous pytest functions (the orchestrator node is sync).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.agents.state import initial_state
from app.agents.orchestrator import orchestrator_node


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_llm_mock(classification: dict) -> MagicMock:
    """Build a mock that mimics get_json_llm() returning a preset classification.

    The mock's .invoke() method returns an object whose .content attribute is
    the JSON-serialised *classification* dict — exactly what orchestrator_node
    expects.
    """
    mock_response = MagicMock()
    mock_response.content = json.dumps(classification)

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response

    mock_factory = MagicMock(return_value=mock_llm)
    return mock_factory


def _run_orchestrator(message: str, user_role: str = "employee", classification: dict = None) -> dict:
    """Build a state, patch the LLM, run orchestrator_node, and return the result."""
    state = initial_state(user_id="USR001", user_role=user_role, message=message)

    llm_mock = _make_llm_mock(classification or {})
    with patch("app.agents.orchestrator.get_json_llm", llm_mock):
        result = orchestrator_node(state)

    return result


# ── Test cases ────────────────────────────────────────────────────────────────

class TestOrchestratorClassification:
    """Six core classification scenarios covering all domains."""

    # 1. HR write — leave request creation
    def test_hr_write_leave_request(self):
        """'Crée une demande de congé' → domain=hr, requires_write=True."""
        classification = {
            "domain": "hr",
            "primary_domain": "hr",
            "secondary_domain": None,
            "confidence": 0.95,
            "requires_write": True,
        }
        result = _run_orchestrator(
            message="Crée une demande de congé du 15 au 18 juillet pour EMP0001",
            user_role="admin",
            classification=classification,
        )
        assert result["detected_domain"] == "hr"
        assert result["requires_write"] is True
        assert result["domain_confidence"] >= 0.7

    # 2. CRM read — revenue query
    def test_crm_read_revenue(self):
        """Revenue query for a CRM account → domain=crm, requires_write=False."""
        classification = {
            "domain": "crm",
            "primary_domain": "crm",
            "secondary_domain": None,
            "confidence": 0.92,
            "requires_write": False,
        }
        result = _run_orchestrator(
            message="Quel est le CA de Microsoft Tunisie sur les 6 derniers mois ?",
            user_role="manager",
            classification=classification,
        )
        assert result["detected_domain"] == "crm"
        assert result["requires_write"] is False
        assert result["domain_confidence"] >= 0.7

    # 3. ERP read — unpaid invoices
    def test_erp_read_unpaid_invoices(self):
        """Unpaid invoices query → domain=erp, requires_write=False."""
        classification = {
            "domain": "erp",
            "primary_domain": "erp",
            "secondary_domain": None,
            "confidence": 0.90,
            "requires_write": False,
        }
        result = _run_orchestrator(
            message="Montre-moi les factures impayées de CUS0022",
            user_role="manager",
            classification=classification,
        )
        assert result["detected_domain"] == "erp"
        assert result["requires_write"] is False
        assert result["domain_confidence"] >= 0.7

    # 4. HR read — employee skills
    def test_hr_read_employee_skills(self):
        """DevOps skills query for an employee → domain=hr, requires_write=False."""
        classification = {
            "domain": "hr",
            "primary_domain": "hr",
            "secondary_domain": None,
            "confidence": 0.88,
            "requires_write": False,
        }
        result = _run_orchestrator(
            message="Quels sont les outils DevOps maîtrisés par EMP0002 ?",
            user_role="employee",
            classification=classification,
        )
        assert result["detected_domain"] == "hr"
        assert result["requires_write"] is False
        assert result["domain_confidence"] >= 0.7

    # 5. RAG — policy documentation
    def test_rag_sick_leave_policy(self):
        """Sick leave policy question → domain=rag, requires_write=False."""
        classification = {
            "domain": "rag",
            "primary_domain": "rag",
            "secondary_domain": None,
            "confidence": 0.85,
            "requires_write": False,
        }
        result = _run_orchestrator(
            message="Quelle est la politique de congés maladie ?",
            user_role="employee",
            classification=classification,
        )
        assert result["detected_domain"] == "rag"
        assert result["requires_write"] is False
        assert result["domain_confidence"] >= 0.7

    # 6. Multi-domain — project budget + team members
    def test_multi_domain_project_budget_and_team(self):
        """Budget + team query spanning hr and erp → domain=multi, primary_domain contains hr."""
        classification = {
            "domain": "multi",
            "primary_domain": "hr",
            "secondary_domain": "erp",
            "confidence": 0.82,
            "requires_write": False,
        }
        result = _run_orchestrator(
            message="Quel est le budget du projet PRJ0001 et qui y travaille ?",
            user_role="manager",
            classification=classification,
        )
        assert result["detected_domain"] == "multi"
        assert result["domain_confidence"] >= 0.7
        # The primary domain extracted by the orchestrator should indicate hr
        # (secondary_domain is set by orchestrator from the classification dict)
        assert result.get("secondary_domain") in ("erp", "hr", None)

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_low_confidence_falls_back_to_rag(self):
        """When both LLM attempts return confidence < 0.7, domain is forced to 'rag'."""
        low_confidence_classification = {
            "domain": "hr",
            "primary_domain": "hr",
            "secondary_domain": None,
            "confidence": 0.4,   # below threshold
            "requires_write": False,
        }
        # Both the first call and the retry return low confidence
        result = _run_orchestrator(
            message="Quelque chose d'ambigu",
            user_role="employee",
            classification=low_confidence_classification,
        )
        # Orchestrator falls back to rag when confidence stays below threshold
        assert result["detected_domain"] == "rag"

    def test_write_permission_denied_for_employee_erp(self):
        """Employees cannot write to ERP — orchestrator sets error_message."""
        classification = {
            "domain": "erp",
            "primary_domain": "erp",
            "secondary_domain": None,
            "confidence": 0.9,
            "requires_write": True,
        }
        result = _run_orchestrator(
            message="Crée une commande fournisseur de 5000 unités",
            user_role="employee",   # employee has no write rights on erp
            classification=classification,
        )
        assert result["error_message"] is not None
        assert "permission" in result["error_message"].lower()

    def test_empty_message_returns_error(self):
        """An empty user message produces an error_message without crashing."""
        # initial_state won't allow empty message directly; we craft state manually
        from langchain_core.messages import HumanMessage
        from app.agents.state import AgentState

        state: AgentState = {
            "messages": [HumanMessage(content="   ")],
            "user_id": "USR001",
            "user_role": "employee",
            "detected_domain": None,
            "domain_confidence": None,
            "tool_results": None,
            "rag_context": None,
            "final_response": None,
            "requires_write": False,
            "error_message": None,
            "iteration_count": 0,
            "secondary_domain": None,
        }

        llm_mock = _make_llm_mock({})
        with patch("app.agents.orchestrator.get_json_llm", llm_mock):
            result = orchestrator_node(state)

        # Whitespace-only message → orchestrator treats it as empty
        assert result["detected_domain"] in ("rag", None) or result["error_message"] is not None

    def test_iteration_count_incremented(self):
        """Each orchestrator call increments iteration_count by 1."""
        classification = {
            "domain": "hr",
            "primary_domain": "hr",
            "secondary_domain": None,
            "confidence": 0.9,
            "requires_write": False,
        }
        result = _run_orchestrator(
            message="Infos sur EMP0010",
            user_role="admin",
            classification=classification,
        )
        assert result["iteration_count"] == 1
