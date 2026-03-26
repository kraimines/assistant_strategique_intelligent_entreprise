"""Simulation / Digital Twin API routes."""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, require_role
from app.schemas.chat_schemas import SimulationRequest, SimulationResponse

router = APIRouter()


@router.post("", response_model=SimulationResponse)
async def run_simulation(
    request: SimulationRequest,
    current_user: dict = Depends(require_role("manager", "director", "admin")),
):
    """
    Lance une simulation stratégique sur le digital twin.

    Accès restreint aux rôles : manager, director, admin.
    """
    # TODO Sprint 2 : brancher simulation/metamodel.py + LangGraph simulator_agent
    return SimulationResponse(
        scenario=request.scenario,
        result={"message": "Simulation en cours d'implémentation", "parameters": request.parameters},
        explanation="Le moteur de simulation sera disponible en Sprint 2.",
        confidence=0.0,
    )


@router.get("/scenarios")
async def list_scenarios(
    current_user: dict = Depends(require_role("manager", "director", "admin")),
):
    """Retourne les scénarios de simulation prédéfinis."""
    return {
        "scenarios": [
            {"id": "turnover_impact",   "name": "Impact du turnover RH",         "domain": "hr"},
            {"id": "pipeline_forecast", "name": "Prévision pipeline commercial",  "domain": "crm"},
            {"id": "cash_flow",         "name": "Simulation trésorerie",          "domain": "erp"},
            {"id": "cross_domain",      "name": "Analyse croisée RH/CRM/ERP",     "domain": "cross"},
        ]
    }
