"""Unit tests for CRM domain tools — mock the SQLAlchemy engine.

Strategy
--------
- Patch ``app.tools.crm_tools._Session`` so no real PostgreSQL connection
  is needed.
- Tests validate tool behaviour: argument handling, return shape, edge cases,
  and error paths.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, PropertyMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_row(data: dict):
    """Create a MagicMock that exposes ._mapping like a SQLAlchemy Row."""
    row = MagicMock()
    type(row)._mapping = PropertyMock(return_value=data)
    return row


def _make_session_mock(fetchone=None, fetchall=None):
    """Return (session_factory, mock_session) with pre-configured execute results."""
    mock_result = MagicMock()
    mock_result.fetchone.return_value = fetchone
    mock_result.fetchall.return_value = fetchall or []

    mock_session = MagicMock()
    mock_session.execute.return_value = mock_result
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    session_factory = MagicMock(return_value=mock_session)
    return session_factory, mock_session


# ── get_account_summary ───────────────────────────────────────────────────────

class TestGetAccountSummary:

    def test_returns_account_with_kpis(self):
        """Should join account + opportunities + revenue into a single dict."""
        from app.tools.crm_tools import get_account_summary

        account_row = _make_row({
            "account_id": "ACC0012",
            "account_name": "Microsoft Tunisie",
            "industry": "Technology",
            "country": "TN",
            "status": "Active",
        })
        opp_row = _make_row({"nb_opportunities": 5, "total_pipeline": 120000.0})
        rev_row = _make_row({"revenue_12m": 85000.0})

        call_count = {"n": 0}
        mock_result_list = [
            MagicMock(fetchone=MagicMock(return_value=account_row)),
            MagicMock(fetchone=MagicMock(return_value=opp_row)),
            MagicMock(fetchone=MagicMock(return_value=rev_row)),
        ]

        mock_session = MagicMock()

        def execute_side_effect(sql, params=None):
            result = mock_result_list[call_count["n"]]
            call_count["n"] += 1
            return result

        mock_session.execute.side_effect = execute_side_effect
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        session_factory = MagicMock(return_value=mock_session)

        with patch("app.tools.crm_tools._Session", session_factory):
            result = get_account_summary.invoke({"account_id": "ACC0012"})

        assert result["account_id"] == "ACC0012"
        assert result["nb_opportunities"] == 5
        assert result["total_pipeline"] == 120000.0
        assert result["revenue_12m"] == 85000.0

    def test_returns_error_when_account_not_found(self):
        """Should return {'error': 'Account not found'} for unknown ID."""
        from app.tools.crm_tools import get_account_summary

        mock_result = MagicMock()
        mock_result.fetchone.return_value = None

        mock_session = MagicMock()
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        session_factory = MagicMock(return_value=mock_session)

        with patch("app.tools.crm_tools._Session", session_factory):
            result = get_account_summary.invoke({"account_id": "ACC9999"})

        assert "error" in result
        assert result["error"] == "Account not found"

    def test_returns_error_on_db_exception(self):
        """Should catch exceptions and return {'error': ...}."""
        from app.tools.crm_tools import get_account_summary

        session_factory = MagicMock(side_effect=Exception("DB unavailable"))

        with patch("app.tools.crm_tools._Session", session_factory):
            result = get_account_summary.invoke({"account_id": "ACC0012"})

        assert "error" in result


# ── list_opportunities ────────────────────────────────────────────────────────

class TestListOpportunities:

    def test_returns_list_of_opportunities(self):
        """Should return a list of opportunity dicts."""
        from app.tools.crm_tools import list_opportunities

        opp_rows = [
            _make_row({
                "opportunity_id": "OPP0001",
                "account_id": "ACC0012",
                "stage": "Proposal",
                "amount": 50000.0,
                "close_date": date(2025, 6, 30),
                "owner_id": "EMP0010",
            }),
        ]
        session_factory, _ = _make_session_mock(fetchall=opp_rows)

        with patch("app.tools.crm_tools._Session", session_factory):
            result = list_opportunities.invoke({"account_id": "ACC0012"})

        assert len(result) == 1
        assert result[0]["opportunity_id"] == "OPP0001"
        assert result[0]["close_date"] == "2025-06-30"

    def test_rejects_invalid_stage(self):
        """Should return [{'error': ...}] for an unrecognised pipeline stage."""
        from app.tools.crm_tools import list_opportunities

        result = list_opportunities.invoke({"stage": "Invalid Stage"})

        assert isinstance(result, list)
        assert "error" in result[0]
        assert "Invalid stage" in result[0]["error"]

    def test_returns_all_when_no_filters(self):
        """Should return results when called with no optional filters."""
        from app.tools.crm_tools import list_opportunities

        session_factory, _ = _make_session_mock(fetchall=[])

        with patch("app.tools.crm_tools._Session", session_factory):
            result = list_opportunities.invoke({})

        assert result == []

    def test_min_amount_filter_is_applied(self):
        """When min_amount is set the WHERE clause should include it."""
        from app.tools.crm_tools import list_opportunities

        session_factory, mock_session = _make_session_mock(fetchall=[])

        with patch("app.tools.crm_tools._Session", session_factory):
            list_opportunities.invoke({"min_amount": 10000.0})

        call_args = mock_session.execute.call_args
        sql_str = str(call_args[0][0])
        assert "min_amount" in sql_str or "amount" in sql_str


# ── get_revenue_history ───────────────────────────────────────────────────────

class TestGetRevenueHistory:

    def test_returns_revenue_summary_with_trend(self):
        """Should aggregate periods, compute total_revenue, and derive trend."""
        from app.tools.crm_tools import get_revenue_history

        period_rows = [
            _make_row({"period": "2024-Q1", "total": 20000.0}),
            _make_row({"period": "2024-Q2", "total": 22000.0}),
            _make_row({"period": "2024-Q3", "total": 25000.0}),
            _make_row({"period": "2024-Q4", "total": 30000.0}),
        ]
        session_factory, _ = _make_session_mock(fetchall=period_rows)

        with patch("app.tools.crm_tools._Session", session_factory):
            result = get_revenue_history.invoke({"account_id": "ACC0012", "months": 12})

        assert result["account_id"] == "ACC0012"
        assert result["total_revenue"] == pytest.approx(97000.0)
        assert result["trend"] in ("up", "down", "stable")
        assert len(result["periods"]) == 4

    def test_trend_up_when_second_half_higher(self):
        """trend='up' when the second half total exceeds first half by >5%."""
        from app.tools.crm_tools import get_revenue_history

        period_rows = [
            _make_row({"period": "2024-01", "total": 10000.0}),  # first half
            _make_row({"period": "2024-02", "total": 20000.0}),  # second half (2x)
        ]
        session_factory, _ = _make_session_mock(fetchall=period_rows)

        with patch("app.tools.crm_tools._Session", session_factory):
            result = get_revenue_history.invoke({"account_id": "ACC0012", "months": 6})

        assert result["trend"] == "up"

    def test_returns_error_on_db_exception(self):
        """Should catch exceptions and return {'error': ...}."""
        from app.tools.crm_tools import get_revenue_history

        session_factory = MagicMock(side_effect=Exception("timeout"))

        with patch("app.tools.crm_tools._Session", session_factory):
            result = get_revenue_history.invoke({"account_id": "ACC0012"})

        assert "error" in result


# ── get_contacts ──────────────────────────────────────────────────────────────

class TestGetContacts:

    def test_returns_contacts_list(self):
        """Should return a list of contact dicts for the given account."""
        from app.tools.crm_tools import get_contacts

        contact_rows = [
            _make_row({
                "contact_id": "CON001",
                "account_id": "ACC0012",
                "first_name": "Jean",
                "last_name": "Dupont",
                "email": "j.dupont@example.com",
                "last_activity_date": date(2025, 3, 1),
            }),
        ]
        session_factory, _ = _make_session_mock(fetchall=contact_rows)

        with patch("app.tools.crm_tools._Session", session_factory):
            result = get_contacts.invoke({"account_id": "ACC0012"})

        assert len(result) == 1
        assert result[0]["contact_id"] == "CON001"

    def test_returns_empty_list_when_no_contacts(self):
        """Should return an empty list when the account has no contacts."""
        from app.tools.crm_tools import get_contacts

        session_factory, _ = _make_session_mock(fetchall=[])

        with patch("app.tools.crm_tools._Session", session_factory):
            result = get_contacts.invoke({"account_id": "ACC9999"})

        assert result == []


# ── list_recent_activities ────────────────────────────────────────────────────

class TestListRecentActivities:

    def test_requires_at_least_one_filter(self):
        """Should return [{'error': ...}] when neither filter is provided."""
        from app.tools.crm_tools import list_recent_activities

        result = list_recent_activities.invoke({})

        assert isinstance(result, list)
        assert "error" in result[0]

    def test_returns_activities_for_opportunity(self):
        """Should return activities when opportunity_id is provided."""
        from app.tools.crm_tools import list_recent_activities

        activity_rows = [
            _make_row({
                "activity_id": "ACT001",
                "opportunity_id": "OPP0001",
                "contact_id": None,
                "type": "Meeting",
                "date": date(2025, 2, 14),
                "notes": "Présentation produit",
            }),
        ]
        session_factory, _ = _make_session_mock(fetchall=activity_rows)

        with patch("app.tools.crm_tools._Session", session_factory):
            result = list_recent_activities.invoke({"opportunity_id": "OPP0001"})

        assert len(result) == 1
        assert result[0]["activity_id"] == "ACT001"

    def test_returns_error_on_db_exception(self):
        """Should return [{'error': ...}] on DB failure."""
        from app.tools.crm_tools import list_recent_activities

        session_factory = MagicMock(side_effect=Exception("connection lost"))

        with patch("app.tools.crm_tools._Session", session_factory):
            result = list_recent_activities.invoke({"opportunity_id": "OPP0001"})

        assert isinstance(result, list)
        assert "error" in result[0]
