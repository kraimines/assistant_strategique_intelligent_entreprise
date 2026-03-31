"""Pydantic schemas — aggregated KPI responses per domain."""
from typing import Optional

from pydantic import BaseModel


class HRStats(BaseModel):
    total_employees:       int
    active_leaves:         int
    avg_performance_score: Optional[float]
    departments_count:     int

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_employees": 342,
                "active_leaves": 18,
                "avg_performance_score": 7.4,
                "departments_count": 8,
            }
        }
    }


class CRMStats(BaseModel):
    total_accounts:       int
    active_opportunities: int
    revenue_pipeline:     float
    won_deals:            int

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_accounts": 120,
                "active_opportunities": 45,
                "revenue_pipeline": 2450000.0,
                "won_deals": 32,
            }
        }
    }


class ERPStats(BaseModel):
    total_orders:    int
    total_revenue:   float
    unpaid_invoices: int
    unpaid_amount:   float

    model_config = {
        "json_schema_extra": {
            "example": {
                "total_orders": 890,
                "total_revenue": 5120000.0,
                "unpaid_invoices": 34,
                "unpaid_amount": 780000.0,
            }
        }
    }


class SyncResult(BaseModel):
    """Result of a manual Neo4j sync trigger."""
    status:  str
    counts:  dict[str, int]
    message: str
