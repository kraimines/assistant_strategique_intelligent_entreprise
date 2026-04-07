"""Chat API routes — SSE streaming avec pipeline LangGraph."""

import json
import logging
import uuid
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.agents.state import initial_state
from app.agents.graph import run_agent_graph
from app.models.user_models import User

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Request / Response schemas ────────────────────────────────────────────────

class ChatStreamRequest(BaseModel):
    """Payload for both streaming and non-streaming chat endpoints."""

    message: str = Field(..., min_length=1, max_length=4096)
    conversation_id: Optional[str] = None


# ── SSE streaming endpoint ────────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream(
    request: ChatStreamRequest,
    current_user: User = Depends(get_current_user),
):
    """POST /api/v1/chat/stream

    Streams the AI assistant response as Server-Sent Events (text/event-stream).

    Each SSE data line carries a JSON object with a ``type`` field:

    - ``{"type": "token",       "content": "..."}``         — partial response text
    - ``{"type": "tool_call",   "tool": "name", "status": "running"}``
    - ``{"type": "tool_result", "tool": "name", "success": true}``
    - ``{"type": "done",        "conversation_id": "...", "tokens_used": 0}``
    - ``{"type": "error",       "message": "..."}``

    The ``conversation_id`` is echoed back in the ``done`` event so that the
    client can reference the same thread for follow-up turns.
    """
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # Map DB role enum value to agent role string
    user_role: str = current_user.role.value  # "admin" | "manager" | "employee"
    user_id: str = str(current_user.id)

    # Validate and build initial pipeline state
    try:
        agent_state = initial_state(
            user_id=user_id,
            user_role=user_role,
            message=request.message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for chunk in run_agent_graph(agent_state, conversation_id):
                yield chunk
        except Exception as exc:
            logger.error("SSE stream error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Non-streaming endpoint (backward-compatible) ──────────────────────────────

@router.post("")
async def chat(
    request: ChatStreamRequest,
    current_user: User = Depends(get_current_user),
):
    """POST /api/v1/chat

    Non-streaming version — collects the full assistant response before returning
    a single JSON object.  Kept for backward compatibility with clients that do
    not support SSE.

    Returns
    -------
    ``{"reply": str, "session_id": str, "sources": list, "agent_used": str}``
    """
    conversation_id = request.conversation_id or str(uuid.uuid4())
    user_role: str = current_user.role.value
    user_id: str = str(current_user.id)

    try:
        agent_state = initial_state(
            user_id=user_id,
            user_role=user_role,
            message=request.message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    full_response = ""
    tool_names: list[str] = []

    async for chunk in run_agent_graph(agent_state, conversation_id):
        # Each chunk is "data: <json>\n\n"
        raw = chunk.strip()
        if raw.startswith("data:"):
            raw = raw[len("data:"):].strip()
        try:
            event = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue

        event_type = event.get("type", "")
        if event_type == "token":
            full_response += event.get("content", "")
        elif event_type == "tool_result":
            tool_name = event.get("tool", "")
            if tool_name:
                tool_names.append(tool_name)
        elif event_type == "error":
            logger.error("chat (non-streaming): agent error — %s", event.get("message"))

    return {
        "reply": full_response or "Désolé, une erreur s'est produite.",
        "session_id": conversation_id,
        "sources": [],
        "agent_used": tool_names[0] if tool_names else "orchestrator",
    }


# ── History endpoint ──────────────────────────────────────────────────────────

@router.get("/history/{session_id}")
async def get_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """GET /api/v1/chat/history/{session_id}

    Returns the conversation history for the given session.
    Redis persistence is planned for a future sprint; for now returns an
    empty message list so the endpoint contract is stable.
    """
    return {"session_id": session_id, "messages": []}
