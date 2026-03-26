"""Chat API routes — point d'entrée pour l'assistant IA."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.schemas.chat_schemas import ChatRequest, ChatResponse

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Envoie un message à l'assistant IA.

    Le message est routé vers l'agent spécialisé (HR, CRM, ERP, RAG)
    selon l'intention détectée par l'orchestrateur LangGraph.
    """
    session_id = request.session_id or str(uuid.uuid4())

    # TODO Sprint 1 : brancher l'orchestrateur LangGraph
    # from app.agents.orchestrator import run_agent
    # result = await run_agent(request.message, request.history, current_user)

    # Réponse temporaire pour valider l'endpoint
    return ChatResponse(
        reply=f"[Assistant] Message reçu : « {request.message} » — implémentation de l'agent en cours.",
        session_id=session_id,
        sources=[],
        agent_used="stub",
    )


@router.get("/history/{session_id}")
async def get_history(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Retourne l'historique de conversation d'une session (via Redis)."""
    # TODO Sprint 1 : lire depuis Redis
    return {"session_id": session_id, "messages": []}
