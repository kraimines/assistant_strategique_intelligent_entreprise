"""
neo4j_schema_talan.py
======================
Définition complète du schéma Neo4j pour la Plateforme Intelligente Talan.
Contient :
  - Labels (nœuds) avec propriétés typées
  - Relations avec cardinalités
  - Contraintes d'unicité (CREATE CONSTRAINT)
  - Index de performance (CREATE INDEX)
  - Requêtes Cypher de validation

Usage : exécuter via py2neo ou neo4j-driver après population ETL.
"""

# ===========================================================================
# 1. LABELS (NŒUDS) — 11 types
# ===========================================================================

NODE_SCHEMA = {

    # ── RH DOMAIN ───────────────────────────────────────────────────────────

    "Department": {
        "source_table": "hr_departments",
        "properties": {
            "department_id":   "STRING",   # PK — ex: DEPT001
            "department_name": "STRING",
            "cost_center":     "STRING",
            "location":        "STRING",
            "budget":          "FLOAT",
            "manager_id":      "STRING",   # FK → Employee.employee_id
        },
        "unique_key": "department_id",
        "fulltext_index": ["department_name"],
    },

    "Employee": {
        "source_table": "hr_employees",
        "properties": {
            "employee_id":              "STRING",   # PK — ex: EMP0001
            "first_name":               "STRING",
            "last_name":                "STRING",
            "email":                    "STRING",
            "phone":                    "STRING",
            "role":                     "STRING",
            "department_id":            "STRING",   # FK → Department
            "hire_date":                "DATE",
            "salary":                   "FLOAT",
            "manager_id":               "STRING",   # FK → Employee (self-ref)
            "contract_type":            "STRING",   # CDI / CDD / Freelance
            "country":                  "STRING",
            "city":                     "STRING",
            "hourly_cost":              "FLOAT",
            "capacity_hours_per_week":  "INTEGER",
        },
        "unique_key": "employee_id",
        "fulltext_index": ["first_name", "last_name", "role", "email"],
    },

    "Skill": {
        "source_table": "hr_skills",
        "properties": {
            "skill_id":         "STRING",   # PK
            "employee_id":      "STRING",   # FK → Employee
            "skill_name":       "STRING",
            "level":            "STRING",   # Beginner / Intermediate / Expert
            "years_experience": "FLOAT",
            "certified":        "BOOLEAN",
            "last_assessed":    "DATE",
        },
        "unique_key": "skill_id",
        "fulltext_index": ["skill_name"],
    },

    "LeaveRequest": {
        "source_table": "hr_leave_requests",
        "properties": {
            "leave_id":       "STRING",   # PK
            "employee_id":    "STRING",   # FK → Employee
            "leave_type":     "STRING",   # Congé annuel / Maladie / etc.
            "start_date":     "DATE",
            "end_date":       "DATE",
            "days_requested": "INTEGER",
            "status":         "STRING",   # Pending / Approved / Rejected
            "approved_by":    "STRING",   # FK → Employee (manager)
            "request_date":   "DATE",
            "notes":          "STRING",
        },
        "unique_key": "leave_id",
    },

    "PerformanceReview": {
        "source_table": "hr_performance_reviews",
        "properties": {
            "review_id":              "STRING",
            "employee_id":            "STRING",   # FK → Employee
            "review_period":          "STRING",   # ex: 2024-Q1
            "overall_score":          "FLOAT",
            "delivery_quality_score": "FLOAT",
            "teamwork_score":         "FLOAT",
            "innovation_score":       "FLOAT",
            "technical_skills_score": "FLOAT",
            "goals_achieved_pct":     "FLOAT",
            "promotion_eligible":     "BOOLEAN",
            "reviewer_id":            "STRING",   # FK → Employee
            "review_date":            "DATE",
            "comments":               "STRING",
        },
        "unique_key": "review_id",
    },

    "JobOpening": {
        "source_table": "hr_recruitment_pipeline",
        "properties": {
            "job_id":             "STRING",   # PK
            "role":               "STRING",
            "department_id":      "STRING",   # FK → Department
            "seniority_level":    "STRING",
            "required_skill":     "STRING",
            "status":             "STRING",   # Open / Closed / In Progress
            "source":             "STRING",
            "open_date":          "DATE",
            "expected_hire_date": "DATE",
            "actual_hire_date":   "DATE",
            "salary_budget":      "FLOAT",
            "n_candidates":       "INTEGER",
            "recruiter_id":       "STRING",   # FK → Employee
            "priority":           "STRING",   # High / Medium / Low
        },
        "unique_key": "job_id",
        "fulltext_index": ["role", "required_skill"],
    },

    # ── CROSS-DOMAIN (RH ↔ CRM ↔ ERP) ──────────────────────────────────────

    "Project": {
        "source_table": "hr_projects",
        "properties": {
            "project_id":         "STRING",   # PK — ex: PROJ001
            "project_name":       "STRING",
            "client_account_id":  "STRING",   # FK → Account (CRM)
            "department_id":      "STRING",   # FK → Department (RH)
            "start_date":         "DATE",
            "end_date":           "DATE",
            "budget":             "FLOAT",
            "status":             "STRING",   # Active / Completed / On Hold
            "project_manager_id": "STRING",   # FK → Employee
            "currency":           "STRING",
            "required_skills":    "STRING",   # comma-separated
        },
        "unique_key": "project_id",
        "fulltext_index": ["project_name", "status"],
    },

    "Milestone": {
        "source_table": "hr_project_milestones",
        "properties": {
            "milestone_id":    "STRING",
            "project_id":      "STRING",   # FK → Project
            "milestone_name":  "STRING",
            "due_date":        "DATE",
            "completion_pct":  "FLOAT",
            "status":          "STRING",
            "owner_id":        "STRING",   # FK → Employee
            "budget_allocated":"FLOAT",
            "actual_cost":     "FLOAT",
            "notes":           "STRING",
        },
        "unique_key": "milestone_id",
    },

    # ── CRM DOMAIN ───────────────────────────────────────────────────────────

    "Account": {
        "source_table": "crm_accounts",
        "properties": {
            "account_id":     "STRING",   # PK — ex: ACC001
            "name":           "STRING",
            "industry":       "STRING",
            "country":        "STRING",
            "annual_revenue": "FLOAT",
            "website":        "STRING",
            "phone":          "STRING",
            "city":           "STRING",
            "created_at":     "DATETIME",
            "updated_at":     "DATETIME",
        },
        "unique_key": "account_id",
        "fulltext_index": ["name", "industry", "country"],
    },

    "Opportunity": {
        "source_table": "crm_opportunities",
        "properties": {
            "opportunity_id":  "STRING",
            "account_id":      "STRING",   # FK → Account
            "deal_name":       "STRING",
            "stage":           "STRING",   # Prospecting / Proposal / Closed Won / etc.
            "amount":          "FLOAT",
            "probability":     "FLOAT",
            "close_date":      "DATE",
            "currency":        "STRING",
            "owner_id":        "STRING",   # FK → Employee (commercial)
            "created_at":      "DATETIME",
            "forecast_amount": "FLOAT",
            "lost_reason":     "STRING",
        },
        "unique_key": "opportunity_id",
        "fulltext_index": ["deal_name", "stage"],
    },

    # ── ERP DOMAIN ───────────────────────────────────────────────────────────

    "Customer": {
        "source_table": "erp_customers",
        "properties": {
            "customer_id":   "STRING",   # PK — ex: CUST001
            "account_id":    "STRING",   # FK → Account (CRM) — lien cross-domain
            "name":          "STRING",
            "country":       "STRING",
            "industry":      "STRING",
            "credit_limit":  "FLOAT",
            "payment_terms": "STRING",
            "tax_id":        "STRING",
            "created_at":    "DATETIME",
        },
        "unique_key": "customer_id",
    },

    "Invoice": {
        "source_table": "erp_invoices",
        "properties": {
            "invoice_id":     "STRING",
            "customer_id":    "STRING",   # FK → Customer
            "order_id":       "STRING",   # FK → SalesOrder
            "amount":         "FLOAT",
            "tax_amount":     "FLOAT",
            "issue_date":     "DATE",
            "due_date":       "DATE",
            "payment_status": "STRING",   # Paid / Pending / Overdue
            "currency":       "STRING",
        },
        "unique_key": "invoice_id",
    },

    "Supplier": {
        "source_table": "erp_suppliers",
        "properties": {
            "supplier_id":    "STRING",
            "name":           "STRING",
            "country":        "STRING",
            "category":       "STRING",
            "contact_email":  "STRING",
            "phone":          "STRING",
            "rating":         "FLOAT",
            "payment_terms":  "STRING",
            "created_at":     "DATETIME",
        },
        "unique_key": "supplier_id",
        "fulltext_index": ["name", "category"],
    },

    "Product": {
        "source_table": "erp_products",
        "properties": {
            "product_id":      "STRING",
            "name":            "STRING",
            "category":        "STRING",
            "unit_price":      "FLOAT",
            "currency":        "STRING",
            "sku":             "STRING",
            "supplier_id":     "STRING",  # FK → Supplier
            "unit_of_measure": "STRING",
            "created_at":      "DATETIME",
        },
        "unique_key": "product_id",
        "fulltext_index": ["name", "category", "sku"],
    },

    "SalesOrder": {
        "source_table": "erp_sales_orders",
        "properties": {
            "order_id":        "STRING",
            "customer_id":     "STRING",  # FK → Customer
            "order_date":      "DATE",
            "delivery_date":   "DATE",
            "amount":          "FLOAT",
            "status":          "STRING",  # Draft / Confirmed / Shipped / Delivered
            "sales_rep_id":    "STRING",  # FK → Employee
            "currency":        "STRING",
            "delivery_status": "STRING",
        },
        "unique_key": "order_id",
    },

    # ── CRM EXTENDED ─────────────────────────────────────────────────────────

    "Contact": {
        "source_table": "crm_contacts",
        "properties": {
            "contact_id":  "STRING",   # PK
            "first_name":  "STRING",
            "last_name":   "STRING",
            "email":       "STRING",
            "phone":       "STRING",
            "job_title":   "STRING",
            "country":     "STRING",
            "account_id":  "STRING",   # FK → Account
            "created_at":  "DATETIME",
        },
        "unique_key": "contact_id",
        "fulltext_index": ["first_name", "last_name", "email"],
    },

    "Activity": {
        "source_table": "crm_activities",
        "properties": {
            "activity_id":      "STRING",   # PK
            "type":             "STRING",   # Call / Email / Meeting / Demo
            "date":             "DATETIME",
            "duration_minutes": "INTEGER",
            "notes":            "STRING",
            "contact_id":       "STRING",   # FK → Contact
            "opportunity_id":   "STRING",   # FK → Opportunity
            "created_by":       "STRING",   # FK → Employee
        },
        "unique_key": "activity_id",
    },

    "RevenueHistory": {
        "source_table": "crm_revenue_history",
        "properties": {
            "revenue_id":        "STRING",   # PK
            "account_id":        "STRING",   # FK → Account
            "year_month":        "STRING",   # ex: 2024-03
            "revenue":           "FLOAT",
            "recurring_revenue": "FLOAT",
            "new_revenue":       "FLOAT",
            "currency":          "STRING",
            "source":            "STRING",
        },
        "unique_key": "revenue_id",
    },

    # ── ERP EXTENDED ─────────────────────────────────────────────────────────

    "Payment": {
        "source_table": "erp_payments",
        "properties": {
            "payment_id":     "STRING",   # PK
            "invoice_id":     "STRING",   # FK → Invoice
            "payment_date":   "DATE",
            "amount":         "FLOAT",
            "payment_method": "STRING",   # Bank Transfer / Check / Cash
            "reference":      "STRING",
            "currency":       "STRING",
            "bank_account":   "STRING",
        },
        "unique_key": "payment_id",
    },

    "PurchaseOrder": {
        "source_table": "erp_purchase_orders",
        "properties": {
            "po_id":             "STRING",   # PK
            "supplier_id":       "STRING",   # FK → Supplier
            "order_date":        "DATE",
            "expected_delivery": "DATE",
            "amount":            "FLOAT",
            "status":            "STRING",   # Draft / Confirmed / Received
            "approved_by":       "STRING",   # FK → Employee
            "currency":          "STRING",
            "warehouse":         "STRING",
        },
        "unique_key": "po_id",
    },

    "Inventory": {
        "source_table": "erp_inventory",
        "properties": {
            "inventory_id":       "STRING",   # PK
            "product_id":         "STRING",   # FK → Product
            "warehouse_location": "STRING",
            "stock_quantity":     "INTEGER",
            "reorder_level":      "INTEGER",
            "unit_cost":          "FLOAT",
            "last_updated":       "DATETIME",
        },
        "unique_key": "inventory_id",
    },
}


# ===========================================================================
# 2. RELATIONS — 20 types
# ===========================================================================

RELATIONSHIP_SCHEMA = [

    # ── RH intra-domain ─────────────────────────────────────────────────────
    {
        "type": "BELONGS_TO",
        "from": "Employee", "to": "Department",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Un employé appartient à un département",
    },
    {
        "type": "MANAGED_BY",
        "from": "Employee", "to": "Employee",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Relation hiérarchique manager → employé",
    },
    {
        "type": "HAS_SKILL",
        "from": "Employee", "to": "Skill",
        "cardinality": "ONE_TO_MANY",
        "props": {"level": "STRING", "years_experience": "FLOAT", "certified": "BOOLEAN"},
        "description": "Compétences maîtrisées par un employé",
    },
    {
        "type": "SUBMITTED_LEAVE",
        "from": "Employee", "to": "LeaveRequest",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Demandes de congé soumises",
    },
    {
        "type": "APPROVED_LEAVE",
        "from": "Employee", "to": "LeaveRequest",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Congés approuvés par un manager",
    },
    {
        "type": "HAD_REVIEW",
        "from": "Employee", "to": "PerformanceReview",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Revue de performance d'un employé",
    },
    {
        "type": "REVIEWED_BY",
        "from": "PerformanceReview", "to": "Employee",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Évaluateur de la revue",
    },
    {
        "type": "OPENS_POSITION",
        "from": "Department", "to": "JobOpening",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Poste ouvert par un département",
    },
    {
        "type": "RECRUITS_FOR",
        "from": "Employee", "to": "JobOpening",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Recruteur responsable du poste",
    },

    # ── Project (RH ↔ CRM ↔ ERP cross-domain) ──────────────────────────────
    {
        "type": "ASSIGNED_TO",
        "from": "Employee", "to": "Project",
        "cardinality": "MANY_TO_MANY",
        "props": {"role": "STRING", "allocation_pct": "FLOAT",
                  "start_date": "DATE", "end_date": "DATE"},
        "description": "Affectation employé ↔ projet (via hr_employee_projects)",
    },
    {
        "type": "MANAGES_PROJECT",
        "from": "Employee", "to": "Project",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Chef de projet",
    },
    {
        "type": "BELONGS_TO_DEPT",
        "from": "Project", "to": "Department",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Département porteur du projet",
    },
    {
        "type": "FOR_ACCOUNT",
        "from": "Project", "to": "Account",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Projet réalisé pour un compte client CRM",
    },
    {
        "type": "HAS_MILESTONE",
        "from": "Project", "to": "Milestone",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Jalons du projet",
    },
    {
        "type": "OWNS_MILESTONE",
        "from": "Employee", "to": "Milestone",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Responsable d'un jalon",
    },
    {
        "type": "LOGGED_TIME",
        "from": "Employee", "to": "Project",
        "cardinality": "MANY_TO_MANY",
        "props": {"week_start_date": "DATE", "actual_hours": "FLOAT",
                  "billable": "BOOLEAN", "timesheet_id": "STRING"},
        "description": "Feuille de temps employé ↔ projet (via hr_timesheets)",
    },

    # ── CRM intra-domain ────────────────────────────────────────────────────
    {
        "type": "HAS_CONTACT",
        "from": "Account", "to": "Contact",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Contacts rattachés à un compte",
    },
    {
        "type": "HAS_OPPORTUNITY",
        "from": "Account", "to": "Opportunity",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Opportunités commerciales d'un compte",
    },
    {
        "type": "OWNS_OPPORTUNITY",
        "from": "Employee", "to": "Opportunity",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Commercial propriétaire de l'opportunité",
    },

    # ── ERP intra-domain ────────────────────────────────────────────────────
    {
        "type": "LINKED_TO_ACCOUNT",
        "from": "Customer", "to": "Account",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Lien ERP Customer ↔ CRM Account (cross-domain clé)",
    },
    {
        "type": "PLACED_ORDER",
        "from": "Customer", "to": "SalesOrder",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Commandes d'un client ERP",
    },
    {
        "type": "HAS_INVOICE",
        "from": "Customer", "to": "Invoice",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Factures d'un client",
    },
    {
        "type": "SUPPLIES",
        "from": "Supplier", "to": "Product",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Fournisseur d'un produit",
    },
    {
        "type": "HANDLES_ORDER",
        "from": "Employee", "to": "SalesOrder",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Commercial responsable de la commande",
    },

    # ── HR — relations manquantes ────────────────────────────────────────────
    {
        "type": "HEADED_BY",
        "from": "Department", "to": "Employee",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Manager responsable du département (hr_departments.manager_id)",
    },
    {
        "type": "SUBMITTED_LEAVE",
        "from": "Employee", "to": "LeaveRequest",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Demande de congé soumise par l'employé",
    },
    {
        "type": "APPROVED_LEAVE",
        "from": "Employee", "to": "LeaveRequest",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Congé approuvé par le manager (hr_leave_requests.approved_by)",
    },
    {
        "type": "HAD_REVIEW",
        "from": "Employee", "to": "PerformanceReview",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Évaluation de performance reçue par l'employé",
    },
    {
        "type": "REVIEWED_BY",
        "from": "PerformanceReview", "to": "Employee",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Évaluateur de la revue (hr_performance_reviews.reviewer_id)",
    },
    {
        "type": "OPENS_POSITION",
        "from": "Department", "to": "JobOpening",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Poste ouvert par le département (hr_recruitment_pipeline.department_id)",
    },
    {
        "type": "RECRUITS_FOR",
        "from": "Employee", "to": "JobOpening",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Recruteur responsable du poste (hr_recruitment_pipeline.recruiter_id)",
    },
    {
        "type": "MANAGES_PROJECT",
        "from": "Employee", "to": "Project",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Chef de projet (hr_projects.project_manager_id)",
    },
    {
        "type": "BELONGS_TO_DEPT",
        "from": "Project", "to": "Department",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Département porteur du projet (hr_projects.department_id)",
    },
    {
        "type": "HAS_MILESTONE",
        "from": "Project", "to": "Milestone",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Jalons du projet (hr_project_milestones.project_id)",
    },
    {
        "type": "OWNS_MILESTONE",
        "from": "Employee", "to": "Milestone",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Responsable d'un jalon (hr_project_milestones.owner_id)",
    },
    {
        "type": "LOGGED_TIME",
        "from": "Employee", "to": "Project",
        "cardinality": "MANY_TO_MANY",
        "props": {
            "timesheet_id":    "STRING",
            "actual_hours":    "FLOAT",
            "planned_hours":   "FLOAT",
            "overtime_hours":  "FLOAT",
            "billable":        "BOOLEAN",
            "week_start_date": "DATE",
        },
        "description": "Feuille de temps employé ↔ projet (hr_timesheets)",
    },

    # ── CRM — relations manquantes ───────────────────────────────────────────
    {
        "type": "HAS_CONTACT",
        "from": "Account", "to": "Contact",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Contacts rattachés à un compte (crm_contacts.account_id)",
    },
    {
        "type": "HAS_OPPORTUNITY",
        "from": "Account", "to": "Opportunity",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Opportunités d'un compte (crm_opportunities.account_id)",
    },
    {
        "type": "OWNS_OPPORTUNITY",
        "from": "Employee", "to": "Opportunity",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Commercial owner de l'opportunité (crm_opportunities.owner_id)",
    },
    {
        "type": "HAS_REVENUE",
        "from": "Account", "to": "RevenueHistory",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Historique CA mensuel d'un compte (crm_revenue_history.account_id)",
    },
    {
        "type": "LOGGED_ACTIVITY",
        "from": "Employee", "to": "Activity",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Activité CRM créée par un commercial (crm_activities.created_by)",
    },
    {
        "type": "ACTIVITY_ON_CONTACT",
        "from": "Activity", "to": "Contact",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Activité réalisée auprès d'un contact (crm_activities.contact_id)",
    },
    {
        "type": "ACTIVITY_FOR_OPP",
        "from": "Activity", "to": "Opportunity",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Activité liée à une opportunité (crm_activities.opportunity_id)",
    },

    # ── ERP — relations manquantes ───────────────────────────────────────────
    {
        "type": "INVOICES_ORDER",
        "from": "Invoice", "to": "SalesOrder",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Facture rattachée à une commande (erp_invoices.order_id)",
    },
    {
        "type": "SETTLES",
        "from": "Payment", "to": "Invoice",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Paiement qui règle une facture (erp_payments.invoice_id)",
    },
    {
        "type": "CONTAINS_PRODUCT",
        "from": "SalesOrder", "to": "Product",
        "cardinality": "MANY_TO_MANY",
        "props": {
            "order_line_id": "STRING",
            "quantity":      "INTEGER",
            "unit_price":    "FLOAT",
            "discount_pct":  "FLOAT",
            "line_total":    "FLOAT",
            "currency":      "STRING",
        },
        "description": "Lignes de commande vente (erp_order_lines)",
    },
    {
        "type": "ORDERED_FROM",
        "from": "PurchaseOrder", "to": "Supplier",
        "cardinality": "MANY_TO_ONE",
        "props": {},
        "description": "Commande achat passée à un fournisseur (erp_purchase_orders.supplier_id)",
    },
    {
        "type": "APPROVED_PO",
        "from": "Employee", "to": "PurchaseOrder",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Employé qui a approuvé la commande achat (erp_purchase_orders.approved_by)",
    },
    {
        "type": "REQUESTS_PRODUCT",
        "from": "PurchaseOrder", "to": "Product",
        "cardinality": "MANY_TO_MANY",
        "props": {
            "po_line_id":         "STRING",
            "quantity_ordered":   "INTEGER",
            "quantity_received":  "INTEGER",
            "unit_cost":          "FLOAT",
            "line_total":         "FLOAT",
            "currency":           "STRING",
        },
        "description": "Lignes de commande achat (erp_po_lines)",
    },
    {
        "type": "HAS_STOCK",
        "from": "Product", "to": "Inventory",
        "cardinality": "ONE_TO_MANY",
        "props": {},
        "description": "Stock en entrepôt pour un produit (erp_inventory.product_id)",
    },
]


# ===========================================================================
# 3. CONTRAINTES D'UNICITÉ — Cypher DDL
# ===========================================================================

CONSTRAINTS_CYPHER = """
// ── RH ──────────────────────────────────────────────────────────────────────
CREATE CONSTRAINT c_department_id     IF NOT EXISTS
  FOR (d:Department)        REQUIRE d.department_id     IS UNIQUE;

CREATE CONSTRAINT c_employee_id       IF NOT EXISTS
  FOR (e:Employee)          REQUIRE e.employee_id       IS UNIQUE;

CREATE CONSTRAINT c_skill_id          IF NOT EXISTS
  FOR (s:Skill)             REQUIRE s.skill_id          IS UNIQUE;

CREATE CONSTRAINT c_leave_id          IF NOT EXISTS
  FOR (l:LeaveRequest)      REQUIRE l.leave_id          IS UNIQUE;

CREATE CONSTRAINT c_review_id         IF NOT EXISTS
  FOR (r:PerformanceReview) REQUIRE r.review_id         IS UNIQUE;

CREATE CONSTRAINT c_job_id            IF NOT EXISTS
  FOR (j:JobOpening)        REQUIRE j.job_id            IS UNIQUE;

// ── CROSS-DOMAIN ─────────────────────────────────────────────────────────────
CREATE CONSTRAINT c_project_id        IF NOT EXISTS
  FOR (p:Project)           REQUIRE p.project_id        IS UNIQUE;

CREATE CONSTRAINT c_milestone_id      IF NOT EXISTS
  FOR (m:Milestone)         REQUIRE m.milestone_id      IS UNIQUE;

// ── CRM ──────────────────────────────────────────────────────────────────────
CREATE CONSTRAINT c_account_id        IF NOT EXISTS
  FOR (a:Account)           REQUIRE a.account_id        IS UNIQUE;

CREATE CONSTRAINT c_opportunity_id    IF NOT EXISTS
  FOR (o:Opportunity)       REQUIRE o.opportunity_id    IS UNIQUE;

// ── ERP ──────────────────────────────────────────────────────────────────────
CREATE CONSTRAINT c_customer_id       IF NOT EXISTS
  FOR (c:Customer)          REQUIRE c.customer_id       IS UNIQUE;

CREATE CONSTRAINT c_invoice_id        IF NOT EXISTS
  FOR (i:Invoice)           REQUIRE i.invoice_id        IS UNIQUE;

CREATE CONSTRAINT c_supplier_id       IF NOT EXISTS
  FOR (s:Supplier)          REQUIRE s.supplier_id       IS UNIQUE;

CREATE CONSTRAINT c_product_id        IF NOT EXISTS
  FOR (p:Product)           REQUIRE p.product_id        IS UNIQUE;

CREATE CONSTRAINT c_order_id          IF NOT EXISTS
  FOR (o:SalesOrder)        REQUIRE o.order_id          IS UNIQUE;

// ── CRM EXTENDED ─────────────────────────────────────────────────────────────
CREATE CONSTRAINT c_contact_id        IF NOT EXISTS
  FOR (c:Contact)           REQUIRE c.contact_id        IS UNIQUE;

CREATE CONSTRAINT c_activity_id       IF NOT EXISTS
  FOR (a:Activity)          REQUIRE a.activity_id       IS UNIQUE;

CREATE CONSTRAINT c_revenue_id        IF NOT EXISTS
  FOR (r:RevenueHistory)    REQUIRE r.revenue_id        IS UNIQUE;

// ── ERP EXTENDED ─────────────────────────────────────────────────────────────
CREATE CONSTRAINT c_payment_id        IF NOT EXISTS
  FOR (p:Payment)           REQUIRE p.payment_id        IS UNIQUE;

CREATE CONSTRAINT c_po_id             IF NOT EXISTS
  FOR (p:PurchaseOrder)     REQUIRE p.po_id             IS UNIQUE;

CREATE CONSTRAINT c_inventory_id      IF NOT EXISTS
  FOR (i:Inventory)         REQUIRE i.inventory_id      IS UNIQUE;
"""


# ===========================================================================
# 4. INDEX DE PERFORMANCE — Cypher DDL
# ===========================================================================

INDEXES_CYPHER = """
// ── Recherche textuelle (fulltext) ──────────────────────────────────────────
CREATE FULLTEXT INDEX ft_employee IF NOT EXISTS
  FOR (e:Employee) ON EACH [e.first_name, e.last_name, e.role, e.email];

CREATE FULLTEXT INDEX ft_account IF NOT EXISTS
  FOR (a:Account) ON EACH [a.name, a.industry, a.country];

CREATE FULLTEXT INDEX ft_project IF NOT EXISTS
  FOR (p:Project) ON EACH [p.project_name, p.status];

CREATE FULLTEXT INDEX ft_skill IF NOT EXISTS
  FOR (s:Skill) ON EACH [s.skill_name];

CREATE FULLTEXT INDEX ft_opportunity IF NOT EXISTS
  FOR (o:Opportunity) ON EACH [o.deal_name, o.stage];

CREATE FULLTEXT INDEX ft_product IF NOT EXISTS
  FOR (p:Product) ON EACH [p.name, p.category, p.sku];

// ── Index de tri / filtre sur propriétés clés ────────────────────────────────
CREATE INDEX idx_employee_dept    IF NOT EXISTS FOR (e:Employee)      ON (e.department_id);
CREATE INDEX idx_employee_manager IF NOT EXISTS FOR (e:Employee)      ON (e.manager_id);
CREATE INDEX idx_project_status   IF NOT EXISTS FOR (p:Project)       ON (p.status);
CREATE INDEX idx_project_client   IF NOT EXISTS FOR (p:Project)       ON (p.client_account_id);
CREATE INDEX idx_leave_status     IF NOT EXISTS FOR (l:LeaveRequest)  ON (l.status);
CREATE INDEX idx_opp_stage        IF NOT EXISTS FOR (o:Opportunity)   ON (o.stage);
CREATE INDEX idx_invoice_status   IF NOT EXISTS FOR (i:Invoice)       ON (i.payment_status);
CREATE INDEX idx_order_status     IF NOT EXISTS FOR (o:SalesOrder)    ON (o.status);

// ── Index nouveaux nœuds ──────────────────────────────────────────────────────
CREATE FULLTEXT INDEX ft_contact    IF NOT EXISTS FOR (c:Contact)      ON EACH [c.first_name, c.last_name, c.email];
CREATE FULLTEXT INDEX ft_supplier   IF NOT EXISTS FOR (s:Supplier)     ON EACH [s.name, s.category];

CREATE INDEX idx_contact_account    IF NOT EXISTS FOR (c:Contact)       ON (c.account_id);
CREATE INDEX idx_activity_type      IF NOT EXISTS FOR (a:Activity)      ON (a.type);
CREATE INDEX idx_payment_method     IF NOT EXISTS FOR (p:Payment)       ON (p.payment_method);
CREATE INDEX idx_po_status          IF NOT EXISTS FOR (p:PurchaseOrder) ON (p.status);
CREATE INDEX idx_inventory_product  IF NOT EXISTS FOR (i:Inventory)     ON (i.product_id);
CREATE INDEX idx_revenue_month      IF NOT EXISTS FOR (r:RevenueHistory) ON (r.year_month);
"""


# ===========================================================================
# 5. REQUÊTES DE VALIDATION — à lancer après l'ETL
# ===========================================================================

VALIDATION_QUERIES = {

    "count_nodes": """
        MATCH (n)
        RETURN labels(n)[0] AS label, count(n) AS count
        ORDER BY count DESC
    """,

    "count_relationships": """
        MATCH ()-[r]->()
        RETURN type(r) AS rel_type, count(r) AS count
        ORDER BY count DESC
    """,

    # T-02 demo : top 5 projets par budget avec leurs employés
    "top5_projects_with_employees": """
        MATCH (e:Employee)-[:ASSIGNED_TO]->(p:Project)
        WITH p, collect(e.first_name + ' ' + e.last_name) AS team, p.budget AS budget
        ORDER BY budget DESC
        LIMIT 5
        RETURN p.project_name AS project, budget, size(team) AS team_size, team
    """,

    # Simulation : tous les projets liés à un compte client
    "projects_by_account": """
        MATCH (a:Account {name: $account_name})<-[:FOR_ACCOUNT]-(p:Project)
        OPTIONAL MATCH (e:Employee)-[:ASSIGNED_TO]->(p)
        RETURN p.project_name, p.status, p.budget,
               collect(e.first_name + ' ' + e.last_name) AS team
    """,

    # Digital Twin : propagation en cascade — impact perte d'un compte
    "impact_of_losing_account": """
        MATCH (a:Account {account_id: $account_id})
        OPTIONAL MATCH (a)<-[:FOR_ACCOUNT]-(p:Project)
        OPTIONAL MATCH (e:Employee)-[:ASSIGNED_TO]->(p)
        OPTIONAL MATCH (a)<-[:LINKED_TO_ACCOUNT]-(c:Customer)
        OPTIONAL MATCH (c)-[:HAS_INVOICE]->(i:Invoice {payment_status: 'Pending'})
        RETURN
            a.name AS account,
            collect(DISTINCT p.project_id) AS affected_projects,
            collect(DISTINCT e.employee_id) AS affected_employees,
            sum(p.budget) AS total_budget_at_risk,
            collect(DISTINCT i.invoice_id) AS pending_invoices
    """,

    # RAG context : profil complet d'un employé
    "employee_full_profile": """
        MATCH (e:Employee {employee_id: $emp_id})
        OPTIONAL MATCH (e)-[:BELONGS_TO]->(d:Department)
        OPTIONAL MATCH (e)-[:HAS_SKILL]->(s:Skill)
        OPTIONAL MATCH (e)-[:ASSIGNED_TO]->(p:Project)
        OPTIONAL MATCH (e)-[:SUBMITTED_LEAVE]->(l:LeaveRequest)
        RETURN e,
               d.department_name AS department,
               collect(DISTINCT s.skill_name + '(' + s.level + ')') AS skills,
               collect(DISTINCT p.project_name) AS projects,
               [lr IN collect(DISTINCT l) WHERE lr.status = 'Pending' | lr.leave_id] AS pending_leaves
    """,
}


# ===========================================================================
# 6. RÉSUMÉ DU SCHÉMA
# ===========================================================================

SCHEMA_SUMMARY = {
    "node_labels":          22,   # +7 : Contact, Activity, RevenueHistory, Payment, PurchaseOrder, Inventory
    "relationship_types":   38,   # +14 nouvelles + tous les existants
    "unique_constraints":   21,   # +6 nouveaux nœuds
    "fulltext_indexes":      8,   # +2 : ft_contact, ft_supplier
    "property_indexes":     14,   # +6 nouveaux
    "domains": {
        "RH":           ["Department", "Employee", "Skill", "LeaveRequest",
                         "PerformanceReview", "JobOpening"],
        "Cross-domain": ["Project", "Milestone"],
        "CRM":          ["Account", "Contact", "Opportunity", "Activity", "RevenueHistory"],
        "ERP":          ["Customer", "Invoice", "Payment", "Supplier", "Product",
                         "SalesOrder", "PurchaseOrder", "Inventory"],
    },
    "key_cross_domain_links": [
        "Project.client_account_id  → Account.account_id",
        "Customer.account_id        → Account.account_id",
        "SalesOrder.sales_rep_id    → Employee.employee_id",
        "Opportunity.owner_id       → Employee.employee_id",
        "Activity.created_by        → Employee.employee_id",
        "PurchaseOrder.approved_by  → Employee.employee_id",
        "Invoice ─[:INVOICES_ORDER]→ SalesOrder",
        "Payment ─[:SETTLES]→       Invoice",
    ],
}

if __name__ == "__main__":
    import json
    print("=== Schéma Neo4j Talan ===")
    print(f"Nœuds   : {SCHEMA_SUMMARY['node_labels']}")
    print(f"Relations: {SCHEMA_SUMMARY['relationship_types']}")
    print(f"Domaines : {json.dumps(SCHEMA_SUMMARY['domains'], indent=2, ensure_ascii=False)}")
    print("\n=== Liens cross-domain clés ===")
    for link in SCHEMA_SUMMARY["key_cross_domain_links"]:
        print(f"  • {link}")
    print("\n=== Contraintes Cypher ===")
    print(CONSTRAINTS_CYPHER)
    print("\n=== Index Cypher ===")
    print(INDEXES_CYPHER)
