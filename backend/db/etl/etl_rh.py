"""
etl_rh.py — ETL complet pour le domaine RH (base talan_hr, schéma hr).

Tables chargées (10) :
  hr_departments, hr_employees, hr_projects, hr_employee_projects,
  hr_project_milestones, hr_timesheets, hr_skills, hr_leave_requests,
  hr_performance_reviews, hr_recruitment_pipeline
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import EXCEL_FILES
from utils import (
    get_logger, pg_conn, execute_ddl, read_sheet,
    clean_str_cols, coerce_dates, to_int_nullable, to_float_nullable,
    get_valid_ids, filter_fk, nullify_fk, upsert_dataframe, get_row_count,
)

log = get_logger("ETL-RH")
RH_PATH = EXCEL_FILES["rh"]

# ── DDL ───────────────────────────────────────────────────────────────────────

DDL = """
CREATE SCHEMA IF NOT EXISTS hr;

CREATE TABLE IF NOT EXISTS hr.hr_departments (
    department_id   VARCHAR(20)  PRIMARY KEY,
    department_name VARCHAR(150) NOT NULL,
    cost_center     VARCHAR(30),
    location        VARCHAR(150),
    budget          BIGINT,
    manager_id      VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS hr.hr_employees (
    employee_id             VARCHAR(20)  PRIMARY KEY,
    first_name              VARCHAR(80)  NOT NULL,
    last_name               VARCHAR(80)  NOT NULL,
    email                   VARCHAR(150) UNIQUE NOT NULL,
    phone                   VARCHAR(40),
    role                    VARCHAR(150),
    department_id           VARCHAR(20)  REFERENCES hr.hr_departments(department_id),
    hire_date               DATE,
    salary                  NUMERIC(14,2),
    manager_id              VARCHAR(20),
    contract_type           VARCHAR(50),
    country                 VARCHAR(80),
    city                    VARCHAR(80),
    hourly_cost             NUMERIC(10,2),
    capacity_hours_per_week INTEGER
);

CREATE TABLE IF NOT EXISTS hr.hr_projects (
    project_id         VARCHAR(20)  PRIMARY KEY,
    project_name       VARCHAR(250) NOT NULL,
    client_account_id  VARCHAR(20),
    department_id      VARCHAR(20)  REFERENCES hr.hr_departments(department_id),
    start_date         DATE,
    end_date           DATE,
    budget             NUMERIC(16,2),
    status             VARCHAR(50),
    project_manager_id VARCHAR(20)  REFERENCES hr.hr_employees(employee_id),
    currency           VARCHAR(10),
    required_skills    TEXT
);

CREATE TABLE IF NOT EXISTS hr.hr_employee_projects (
    assignment_id   VARCHAR(20)  PRIMARY KEY,
    employee_id     VARCHAR(20)  NOT NULL REFERENCES hr.hr_employees(employee_id),
    project_id      VARCHAR(20)  NOT NULL REFERENCES hr.hr_projects(project_id),
    role            VARCHAR(150),
    allocation_pct  NUMERIC(5,2),
    start_date      DATE,
    end_date        DATE
);

CREATE TABLE IF NOT EXISTS hr.hr_project_milestones (
    milestone_id     VARCHAR(20)  PRIMARY KEY,
    project_id       VARCHAR(20)  REFERENCES hr.hr_projects(project_id),
    milestone_name   VARCHAR(250),
    due_date         DATE,
    completion_pct   INTEGER,
    status           VARCHAR(50),
    owner_id         VARCHAR(20)  REFERENCES hr.hr_employees(employee_id),
    budget_allocated NUMERIC(14,2),
    actual_cost      NUMERIC(14,2),
    notes            TEXT
);

CREATE TABLE IF NOT EXISTS hr.hr_timesheets (
    timesheet_id    VARCHAR(20)  PRIMARY KEY,
    employee_id     VARCHAR(20)  NOT NULL REFERENCES hr.hr_employees(employee_id),
    project_id      VARCHAR(20)  REFERENCES hr.hr_projects(project_id),
    week_start_date DATE,
    planned_hours   INTEGER,
    actual_hours    NUMERIC(6,2),
    overtime_hours  NUMERIC(6,2),
    billable        VARCHAR(10),
    status          VARCHAR(30),
    submitted_by    VARCHAR(20),
    approved_by     VARCHAR(20),
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS hr.hr_skills (
    skill_id         VARCHAR(20)  PRIMARY KEY,
    employee_id      VARCHAR(20)  NOT NULL REFERENCES hr.hr_employees(employee_id),
    skill_name       VARCHAR(150) NOT NULL,
    level            VARCHAR(50),
    years_experience NUMERIC(5,1),
    certified        VARCHAR(30),
    last_assessed    DATE
);

CREATE TABLE IF NOT EXISTS hr.hr_leave_requests (
    leave_id       VARCHAR(20)  PRIMARY KEY,
    employee_id    VARCHAR(20)  NOT NULL REFERENCES hr.hr_employees(employee_id),
    leave_type     VARCHAR(80),
    start_date     DATE,
    end_date       DATE,
    days_requested INTEGER,
    status         VARCHAR(30),
    approved_by    VARCHAR(20),
    request_date   DATE,
    notes          TEXT
);

CREATE TABLE IF NOT EXISTS hr.hr_performance_reviews (
    review_id              VARCHAR(20)  PRIMARY KEY,
    employee_id            VARCHAR(20)  NOT NULL REFERENCES hr.hr_employees(employee_id),
    review_period          VARCHAR(20),
    overall_score          NUMERIC(4,2),
    delivery_quality_score NUMERIC(4,2),
    teamwork_score         NUMERIC(4,2),
    innovation_score       NUMERIC(4,2),
    technical_skills_score NUMERIC(4,2),
    goals_achieved_pct     INTEGER,
    promotion_eligible     VARCHAR(30),
    reviewer_id            VARCHAR(20),
    review_date            DATE,
    comments               TEXT
);

CREATE TABLE IF NOT EXISTS hr.hr_recruitment_pipeline (
    job_id             VARCHAR(20)  PRIMARY KEY,
    role               VARCHAR(150),
    department_id      VARCHAR(20)  REFERENCES hr.hr_departments(department_id),
    seniority_level    VARCHAR(50),
    required_skill     VARCHAR(150),
    status             VARCHAR(50),
    source             VARCHAR(100),
    open_date          DATE,
    expected_hire_date DATE,
    actual_hire_date   DATE,
    salary_budget      NUMERIC(14,2),
    n_candidates       INTEGER,
    recruiter_id       VARCHAR(20),
    priority           VARCHAR(30)
);

CREATE INDEX IF NOT EXISTS idx_hr_emp_dept    ON hr.hr_employees(department_id);
CREATE INDEX IF NOT EXISTS idx_hr_emp_manager ON hr.hr_employees(manager_id);
CREATE INDEX IF NOT EXISTS idx_hr_proj_dept   ON hr.hr_projects(department_id);
CREATE INDEX IF NOT EXISTS idx_hr_proj_mgr    ON hr.hr_projects(project_manager_id);
CREATE INDEX IF NOT EXISTS idx_hr_ep_emp      ON hr.hr_employee_projects(employee_id);
CREATE INDEX IF NOT EXISTS idx_hr_ep_proj     ON hr.hr_employee_projects(project_id);
CREATE INDEX IF NOT EXISTS idx_hr_ts_emp      ON hr.hr_timesheets(employee_id);
CREATE INDEX IF NOT EXISTS idx_hr_ts_proj     ON hr.hr_timesheets(project_id);
CREATE INDEX IF NOT EXISTS idx_hr_skill_emp   ON hr.hr_skills(employee_id);
CREATE INDEX IF NOT EXISTS idx_hr_leave_emp   ON hr.hr_leave_requests(employee_id);
CREATE INDEX IF NOT EXISTS idx_hr_review_emp  ON hr.hr_performance_reviews(employee_id);
CREATE INDEX IF NOT EXISTS idx_hr_recr_dept   ON hr.hr_recruitment_pipeline(department_id);
"""


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_departments(conn) -> int:
    log.info("  Chargement des départements …")
    df = read_sheet(RH_PATH, "departments")
    df = clean_str_cols(df)
    df = to_float_nullable(df, ["budget"])
    cols = ["department_id", "department_name", "cost_center", "location",
            "budget", "manager_id"]
    df = df[[c for c in cols if c in df.columns]].dropna(subset=["department_id"])
    df = df.drop_duplicates(subset=["department_id"])
    n = upsert_dataframe(conn, df, "hr.hr_departments", ["department_id"])
    log.info(f"    → {n} ligne(s) dans hr_departments")
    return n


def load_employees(conn) -> int:
    log.info("  Chargement des employés …")
    df = read_sheet(RH_PATH, "employees")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["hire_date"])
    df = to_float_nullable(df, ["salary", "hourly_cost"])
    df = to_int_nullable(df, ["capacity_hours_per_week"], lo=0, hi=168)

    valid_depts = get_valid_ids(conn, "hr.hr_departments", "department_id")

    cols = ["employee_id", "first_name", "last_name", "email", "phone", "role",
            "department_id", "hire_date", "salary", "manager_id", "contract_type",
            "country", "city", "hourly_cost", "capacity_hours_per_week"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["employee_id", "email"])
    df = df.drop_duplicates(subset=["employee_id"])
    df = df.drop_duplicates(subset=["email"], keep="first")
    df = nullify_fk(df, "department_id", valid_depts)
    # manager_id : pas de FK en base (auto-référence chargée après) → garder tel quel
    n = upsert_dataframe(conn, df, "hr.hr_employees", ["employee_id"])
    log.info(f"    → {n} ligne(s) dans hr_employees")
    return n


def load_projects(conn) -> int:
    log.info("  Chargement des projets …")
    df = read_sheet(RH_PATH, "projects")
    df = clean_str_cols(df)
    df = coerce_dates(df, ["start_date", "end_date"])
    df = to_float_nullable(df, ["budget"])

    valid_depts = get_valid_ids(conn, "hr.hr_departments", "department_id")
    valid_emps  = get_valid_ids(conn, "hr.hr_employees",   "employee_id")

    cols = ["project_id", "project_name", "client_account_id", "department_id",
            "start_date", "end_date", "budget", "status", "project_manager_id",
            "currency", "required_skills"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["project_id"])
    df = df.drop_duplicates(subset=["project_id"])
    df = nullify_fk(df, "department_id",      valid_depts)
    df = nullify_fk(df, "project_manager_id", valid_emps)
    n = upsert_dataframe(conn, df, "hr.hr_projects", ["project_id"])
    log.info(f"    → {n} ligne(s) dans hr_projects")
    return n


def load_employee_projects(conn) -> int:
    log.info("  Chargement des affectations employé-projet …")
    try:
        df = read_sheet(RH_PATH, "employee_projects")
    except ValueError:
        log.warning("  Feuille 'employee_projects' absente, ignorée.")
        return 0
    df = clean_str_cols(df)
    df = coerce_dates(df, ["start_date", "end_date"])
    df = to_float_nullable(df, ["allocation_pct"])

    valid_emps  = get_valid_ids(conn, "hr.hr_employees", "employee_id")
    valid_projs = get_valid_ids(conn, "hr.hr_projects",  "project_id")

    # La feuille a "assignment_id" comme PK
    cols = ["assignment_id", "employee_id", "project_id", "role",
            "allocation_pct", "start_date", "end_date"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["assignment_id"])
    df = df.drop_duplicates(subset=["assignment_id"])
    df = filter_fk(df, "employee_id", valid_emps)
    df = filter_fk(df, "project_id",  valid_projs)
    n = upsert_dataframe(conn, df, "hr.hr_employee_projects", ["assignment_id"])
    log.info(f"    → {n} ligne(s) dans hr_employee_projects")
    return n


def load_project_milestones(conn) -> int:
    log.info("  Chargement des jalons de projet …")
    try:
        df = read_sheet(RH_PATH, "project_milestones")
    except ValueError:
        log.warning("  Feuille 'project_milestones' absente, ignorée.")
        return 0
    df = clean_str_cols(df)
    df = coerce_dates(df, ["due_date"])
    df = to_float_nullable(df, ["budget_allocated", "actual_cost"])
    df = to_int_nullable(df, ["completion_pct"], lo=0, hi=100)

    valid_projs = get_valid_ids(conn, "hr.hr_projects",  "project_id")
    valid_emps  = get_valid_ids(conn, "hr.hr_employees", "employee_id")

    cols = ["milestone_id", "project_id", "milestone_name", "due_date",
            "completion_pct", "status", "owner_id", "budget_allocated",
            "actual_cost", "notes"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["milestone_id"])
    df = df.drop_duplicates(subset=["milestone_id"])
    df = nullify_fk(df, "project_id", valid_projs)
    df = nullify_fk(df, "owner_id",   valid_emps)
    n = upsert_dataframe(conn, df, "hr.hr_project_milestones", ["milestone_id"])
    log.info(f"    → {n} ligne(s) dans hr_project_milestones")
    return n


def load_timesheets(conn) -> int:
    log.info("  Chargement des feuilles de temps …")
    try:
        df = read_sheet(RH_PATH, "timesheets")
    except ValueError:
        log.warning("  Feuille 'timesheets' absente, ignorée.")
        return 0
    df = clean_str_cols(df)
    df = coerce_dates(df, ["week_start_date"])
    df = to_int_nullable(df, ["planned_hours"], lo=0, hi=168)
    df = to_float_nullable(df, ["actual_hours", "overtime_hours"])

    valid_emps  = get_valid_ids(conn, "hr.hr_employees", "employee_id")
    valid_projs = get_valid_ids(conn, "hr.hr_projects",  "project_id")

    cols = ["timesheet_id", "employee_id", "project_id", "week_start_date",
            "planned_hours", "actual_hours", "overtime_hours", "billable",
            "status", "submitted_by", "approved_by", "notes"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["timesheet_id"])
    df = df.drop_duplicates(subset=["timesheet_id"])
    df = filter_fk(df, "employee_id", valid_emps)
    df = nullify_fk(df, "project_id",  valid_projs)
    df = nullify_fk(df, "submitted_by", valid_emps)
    df = nullify_fk(df, "approved_by",  valid_emps)
    n = upsert_dataframe(conn, df, "hr.hr_timesheets", ["timesheet_id"])
    log.info(f"    → {n} ligne(s) dans hr_timesheets")
    return n


def load_skills(conn) -> int:
    log.info("  Chargement des compétences …")
    try:
        df = read_sheet(RH_PATH, "skills")
    except ValueError:
        log.warning("  Feuille 'skills' absente, ignorée.")
        return 0
    df = clean_str_cols(df)
    df = coerce_dates(df, ["last_assessed"])
    df = to_float_nullable(df, ["years_experience"])

    valid_emps = get_valid_ids(conn, "hr.hr_employees", "employee_id")

    cols = ["skill_id", "employee_id", "skill_name", "level",
            "years_experience", "certified", "last_assessed"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["skill_id"])
    df = df.drop_duplicates(subset=["skill_id"])
    df = filter_fk(df, "employee_id", valid_emps)
    n = upsert_dataframe(conn, df, "hr.hr_skills", ["skill_id"])
    log.info(f"    → {n} ligne(s) dans hr_skills")
    return n


def load_leave_requests(conn) -> int:
    log.info("  Chargement des congés …")
    try:
        df = read_sheet(RH_PATH, "leave_requests")
    except ValueError:
        log.warning("  Feuille 'leave_requests' absente, ignorée.")
        return 0
    df = clean_str_cols(df)
    df = coerce_dates(df, ["start_date", "end_date", "request_date"])
    df = to_int_nullable(df, ["days_requested"], lo=0, hi=365)

    valid_emps = get_valid_ids(conn, "hr.hr_employees", "employee_id")

    cols = ["leave_id", "employee_id", "leave_type", "start_date", "end_date",
            "days_requested", "status", "approved_by", "request_date", "notes"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["leave_id"])
    df = df.drop_duplicates(subset=["leave_id"])
    df = filter_fk(df, "employee_id", valid_emps)
    df = nullify_fk(df, "approved_by", valid_emps)
    n = upsert_dataframe(conn, df, "hr.hr_leave_requests", ["leave_id"])
    log.info(f"    → {n} ligne(s) dans hr_leave_requests")
    return n


def load_performance_reviews(conn) -> int:
    log.info("  Chargement des évaluations …")
    try:
        df = read_sheet(RH_PATH, "performance_reviews")
    except ValueError:
        log.warning("  Feuille 'performance_reviews' absente, ignorée.")
        return 0
    df = clean_str_cols(df)
    df = coerce_dates(df, ["review_date"])
    df = to_float_nullable(df, ["overall_score", "delivery_quality_score",
                                 "teamwork_score", "innovation_score",
                                 "technical_skills_score"])
    df = to_int_nullable(df, ["goals_achieved_pct"], lo=0, hi=100)

    valid_emps = get_valid_ids(conn, "hr.hr_employees", "employee_id")

    cols = ["review_id", "employee_id", "review_period", "overall_score",
            "delivery_quality_score", "teamwork_score", "innovation_score",
            "technical_skills_score", "goals_achieved_pct", "promotion_eligible",
            "reviewer_id", "review_date", "comments"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["review_id"])
    df = df.drop_duplicates(subset=["review_id"])
    df = filter_fk(df, "employee_id", valid_emps)
    df = nullify_fk(df, "reviewer_id", valid_emps)
    n = upsert_dataframe(conn, df, "hr.hr_performance_reviews", ["review_id"])
    log.info(f"    → {n} ligne(s) dans hr_performance_reviews")
    return n


def load_recruitment_pipeline(conn) -> int:
    log.info("  Chargement du pipeline de recrutement …")
    try:
        df = read_sheet(RH_PATH, "recruitment_pipeline")
    except ValueError:
        log.warning("  Feuille 'recruitment_pipeline' absente, ignorée.")
        return 0
    df = clean_str_cols(df)
    df = coerce_dates(df, ["open_date", "expected_hire_date", "actual_hire_date"])
    df = to_float_nullable(df, ["salary_budget"])
    df = to_int_nullable(df, ["n_candidates"], lo=0)

    valid_depts = get_valid_ids(conn, "hr.hr_departments", "department_id")
    valid_emps  = get_valid_ids(conn, "hr.hr_employees",   "employee_id")

    cols = ["job_id", "role", "department_id", "seniority_level", "required_skill",
            "status", "source", "open_date", "expected_hire_date", "actual_hire_date",
            "salary_budget", "n_candidates", "recruiter_id", "priority"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.dropna(subset=["job_id"])
    df = df.drop_duplicates(subset=["job_id"])
    df = nullify_fk(df, "department_id", valid_depts)
    df = nullify_fk(df, "recruiter_id",  valid_emps)
    n = upsert_dataframe(conn, df, "hr.hr_recruitment_pipeline", ["job_id"])
    log.info(f"    → {n} ligne(s) dans hr_recruitment_pipeline")
    return n


# ── Point d'entrée ────────────────────────────────────────────────────────────

def run():
    log.info("=" * 70)
    log.info("ETL RH — Démarrage")
    log.info("=" * 70)

    with pg_conn("hr") as conn:
        log.info("DDL : création du schéma et des tables …")
        execute_ddl(conn, DDL)
        log.info("  ✓ DDL appliqué")

        log.info("\n┌─ Données de base ─────────────────────────────────────────────┐")
        load_departments(conn)
        load_employees(conn)
        load_projects(conn)
        load_employee_projects(conn)
        load_project_milestones(conn)
        log.info("└───────────────────────────────────────────────────────────────┘")

        log.info("\n┌─ Données de gestion ───────────────────────────────────────────┐")
        load_timesheets(conn)
        load_skills(conn)
        load_leave_requests(conn)
        load_performance_reviews(conn)
        load_recruitment_pipeline(conn)
        log.info("└───────────────────────────────────────────────────────────────┘")

        log.info("\nStatistiques finales :")
        tables = [
            "hr.hr_departments", "hr.hr_employees", "hr.hr_projects",
            "hr.hr_employee_projects", "hr.hr_project_milestones",
            "hr.hr_timesheets", "hr.hr_skills", "hr.hr_leave_requests",
            "hr.hr_performance_reviews", "hr.hr_recruitment_pipeline",
        ]
        total = 0
        for t in tables:
            try:
                n = get_row_count(conn, t)
                total += n
                log.info(f"  {t}: {n} lignes")
            except Exception:
                pass
        log.info(f"  TOTAL : {total} lignes")

    log.info("\n✅ ETL RH terminé avec succès.\n")


if __name__ == "__main__":
    run()
