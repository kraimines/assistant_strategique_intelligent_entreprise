"""Unit tests for HR domain tools — mock the SQLAlchemy engine.

Strategy
--------
- Each tool imports a module-level ``_Session`` from ``app.tools.hr_tools``.
- We patch ``app.tools.hr_tools._Session`` with a context-manager mock so
  that no real PostgreSQL connection is needed.
- Tests verify the tool logic (argument handling, return shape, error paths)
  rather than the SQL queries themselves.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_session_mock(fetchone=None, fetchall=None):
    """Return a mock _Session factory whose context manager returns a session stub.

    Args:
        fetchone: Value returned by session.execute(...).fetchone()
        fetchall: Value returned by session.execute(...).fetchall()
    """
    mock_result = MagicMock()
    mock_result.fetchone.return_value = fetchone
    mock_result.fetchall.return_value = fetchall or []

    mock_session = MagicMock()
    mock_session.execute.return_value = mock_result
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    mock_session_factory = MagicMock(return_value=mock_session)
    return mock_session_factory, mock_session


def _make_row(data: dict):
    """Create a MagicMock that exposes ._mapping like a SQLAlchemy Row."""
    row = MagicMock()
    row._mapping = data
    # Make hasattr(row, "_mapping") return True
    type(row)._mapping = PropertyMock(return_value=data)
    return row


# ── get_employee_info ─────────────────────────────────────────────────────────

class TestGetEmployeeInfo:

    def test_returns_employee_dict_when_found(self):
        """Should return a dict with employee fields when the row exists."""
        from app.tools.hr_tools import get_employee_info

        row_data = {
            "employee_id": "EMP0001",
            "first_name": "Alice",
            "last_name": "Martin",
            "role": "Engineer",
            "department_id": "DEP001",
            "hire_date": date(2020, 6, 1),
            "salary": 55000.0,
            "manager_id": "EMP0010",
            "contract_type": "CDI",
            "city": "Paris",
            "hourly_cost": 35.0,
            "capacity_hours_per_week": 40.0,
        }
        row = _make_row(row_data)
        session_factory, _ = _make_session_mock(fetchone=row)

        with patch("app.tools.hr_tools._Session", session_factory):
            result = get_employee_info.invoke({"employee_id": "EMP0001"})

        assert result["employee_id"] == "EMP0001"
        assert result["first_name"] == "Alice"
        assert result["hire_date"] == "2020-06-01"  # date → ISO string

    def test_returns_error_when_not_found(self):
        """Should return {'error': 'Employee not found'} for unknown ID."""
        from app.tools.hr_tools import get_employee_info

        session_factory, _ = _make_session_mock(fetchone=None)

        with patch("app.tools.hr_tools._Session", session_factory):
            result = get_employee_info.invoke({"employee_id": "EMP9999"})

        assert "error" in result
        assert result["error"] == "Employee not found"

    def test_returns_error_on_db_exception(self):
        """Should catch DB exceptions and return {'error': ...}."""
        from app.tools.hr_tools import get_employee_info

        session_factory = MagicMock(side_effect=Exception("Connection refused"))

        with patch("app.tools.hr_tools._Session", session_factory):
            result = get_employee_info.invoke({"employee_id": "EMP0001"})

        assert "error" in result


# ── get_leave_balance ─────────────────────────────────────────────────────────

class TestGetLeaveBalance:

    def test_returns_balance_summary(self):
        """Should aggregate leave_type rows and compute remaining_annual."""
        from app.tools.hr_tools import get_leave_balance

        row1 = _make_row({"leave_type": "Annual Leave", "days_consumed": 8})
        row2 = _make_row({"leave_type": "Sick Leave",   "days_consumed": 3})

        session_factory, _ = _make_session_mock(fetchall=[row1, row2])

        with patch("app.tools.hr_tools._Session", session_factory):
            result = get_leave_balance.invoke({"employee_id": "EMP0001", "year": 2025})

        assert result["employee_id"] == "EMP0001"
        assert result["year"] == 2025
        assert result["leave_consumed"]["Annual Leave"] == 8
        assert result["remaining_annual"] == 30 - 8   # allowance - consumed

    def test_uses_current_year_by_default(self):
        """Should default year to the current calendar year."""
        from app.tools.hr_tools import get_leave_balance

        session_factory, _ = _make_session_mock(fetchall=[])

        with patch("app.tools.hr_tools._Session", session_factory):
            result = get_leave_balance.invoke({"employee_id": "EMP0002"})

        assert result["year"] == date.today().year
        assert result["remaining_annual"] == 30  # no leave consumed


# ── create_leave_request ──────────────────────────────────────────────────────

class TestCreateLeaveRequest:

    def test_rejects_invalid_leave_type(self):
        """Should return an error dict for unknown leave types without hitting DB."""
        from app.tools.hr_tools import create_leave_request

        result = create_leave_request.invoke({
            "employee_id": "EMP0001",
            "leave_type": "Vacation",   # not in _VALID_LEAVE_TYPES
            "start_date": "2025-07-15",
            "end_date": "2025-07-18",
        })

        assert "error" in result
        assert "Invalid leave_type" in result["error"]

    def test_rejects_end_before_start(self):
        """Should return an error when end_date < start_date."""
        from app.tools.hr_tools import create_leave_request

        result = create_leave_request.invoke({
            "employee_id": "EMP0001",
            "leave_type": "Annual Leave",
            "start_date": "2025-07-18",
            "end_date": "2025-07-15",   # end before start
        })

        assert "error" in result
        assert "end_date" in result["error"].lower() or "start" in result["error"].lower()

    def test_creates_new_leave_request_successfully(self):
        """Should insert a new record and return leave_id + days_requested."""
        from app.tools.hr_tools import create_leave_request

        # No existing duplicate
        check_row = None
        # Max id query → "LVE0042"
        max_row = _make_row({"max_id": "LVE0042"})

        mock_result_check = MagicMock()
        mock_result_check.fetchone.return_value = check_row

        mock_result_max = MagicMock()
        mock_result_max.fetchone.return_value = max_row

        call_count = {"n": 0}

        def execute_side_effect(sql, params=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return mock_result_check   # idempotency check
            if call_count["n"] == 2:
                return mock_result_max     # MAX(leave_id)
            return MagicMock()             # INSERT

        mock_session = MagicMock()
        mock_session.execute.side_effect = execute_side_effect
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        session_factory = MagicMock(return_value=mock_session)

        with patch("app.tools.hr_tools._Session", session_factory):
            result = create_leave_request.invoke({
                "employee_id": "EMP0001",
                "leave_type": "Annual Leave",
                "start_date": "2025-07-15",
                "end_date": "2025-07-18",
                "notes": "Vacances",
            })

        assert "error" not in result
        assert result["leave_id"] == "LVE0043"
        assert result["days_requested"] >= 1
        assert result["status"] == "Pending"

    def test_returns_existing_on_duplicate(self):
        """Should return the existing leave_id when a duplicate Pending request exists."""
        from app.tools.hr_tools import create_leave_request

        existing_row = _make_row({"leave_id": "LVE0020"})
        session_factory, _ = _make_session_mock(fetchone=existing_row)

        with patch("app.tools.hr_tools._Session", session_factory):
            result = create_leave_request.invoke({
                "employee_id": "EMP0001",
                "leave_type": "Annual Leave",
                "start_date": "2025-07-15",
                "end_date": "2025-07-18",
            })

        assert result["leave_id"] == "LVE0020"
        assert "Duplicate" in result["message"]


# ── get_employee_skills ───────────────────────────────────────────────────────

class TestGetEmployeeSkills:

    def test_returns_skill_list(self):
        """Should return a list of skill dicts ordered by years_experience."""
        from app.tools.hr_tools import get_employee_skills

        skill_rows = [
            _make_row({"skill_name": "Python",   "level": "Expert",        "years_experience": 5.0, "certified": "Yes", "last_assessed": date(2024, 1, 1)}),
            _make_row({"skill_name": "Docker",   "level": "Intermediate",  "years_experience": 3.0, "certified": "No",  "last_assessed": date(2023, 6, 1)}),
        ]
        session_factory, _ = _make_session_mock(fetchall=skill_rows)

        with patch("app.tools.hr_tools._Session", session_factory):
            result = get_employee_skills.invoke({"employee_id": "EMP0002", "certified_only": False})

        assert len(result) == 2
        assert result[0]["skill_name"] == "Python"

    def test_certified_only_filter_is_passed(self):
        """When certified_only=True the WHERE clause includes the filter."""
        from app.tools.hr_tools import get_employee_skills

        session_factory, mock_session = _make_session_mock(fetchall=[])

        with patch("app.tools.hr_tools._Session", session_factory):
            get_employee_skills.invoke({"employee_id": "EMP0002", "certified_only": True})

        # Verify execute was called with a SQL text containing certified filter
        call_args = mock_session.execute.call_args
        sql_str = str(call_args[0][0])   # first positional arg is the text() object
        assert "certified" in sql_str


# ── get_performance_review ────────────────────────────────────────────────────

class TestGetPerformanceReview:

    def test_returns_review_dict(self):
        """Should return the most recent performance review as a dict."""
        from app.tools.hr_tools import get_performance_review

        review_data = {
            "review_id": "REV001",
            "employee_id": "EMP0003",
            "review_period": "2024-H1",
            "overall_score": 4.2,
            "review_date": date(2024, 7, 1),
            "reviewer_id": "EMP0010",
            "comments": "Excellent travail.",
        }
        row = _make_row(review_data)
        session_factory, _ = _make_session_mock(fetchone=row)

        with patch("app.tools.hr_tools._Session", session_factory):
            result = get_performance_review.invoke({"employee_id": "EMP0003"})

        assert result["review_id"] == "REV001"
        assert result["review_date"] == "2024-07-01"

    def test_returns_error_when_no_review_found(self):
        """Should return {'error': 'No performance review found'} when empty."""
        from app.tools.hr_tools import get_performance_review

        session_factory, _ = _make_session_mock(fetchone=None)

        with patch("app.tools.hr_tools._Session", session_factory):
            result = get_performance_review.invoke({"employee_id": "EMP9999"})

        assert "error" in result
        assert "No performance review found" in result["error"]


# ── get_timesheets ────────────────────────────────────────────────────────────

class TestGetTimesheets:

    def test_returns_list_of_timesheets(self):
        """Should return a list of timesheet dicts."""
        from app.tools.hr_tools import get_timesheets

        ts_rows = [
            _make_row({
                "timesheet_id": "TS001",
                "employee_id": "EMP0001",
                "project_id": "PRJ0001",
                "week_start_date": date(2025, 1, 6),
                "hours_logged": 40.0,
                "billable": True,
            }),
        ]
        session_factory, _ = _make_session_mock(fetchall=ts_rows)

        with patch("app.tools.hr_tools._Session", session_factory):
            result = get_timesheets.invoke({"employee_id": "EMP0001"})

        assert len(result) == 1
        assert result[0]["timesheet_id"] == "TS001"

    def test_returns_error_list_on_db_failure(self):
        """Should return [{'error': '...'}] on DB exception."""
        from app.tools.hr_tools import get_timesheets

        session_factory = MagicMock(side_effect=Exception("DB down"))

        with patch("app.tools.hr_tools._Session", session_factory):
            result = get_timesheets.invoke({"employee_id": "EMP0001"})

        assert isinstance(result, list)
        assert "error" in result[0]
