"""Chat API routes — SSE streaming avec pipeline LangGraph."""

import json
import logging
import uuid
from typing import AsyncGenerator, Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_agent_graph
from app.agents.state import initial_state
from app.api.deps import get_current_user, get_hr_db
from app.core.redis_client import get_redis
from app.models.user_models import User
from app.schemas.chat_schemas import (
    ConversationHistoryResponse,
    ConversationListResponse,
    ConversationSummary,
    MessageOut,
)
from app.services import conversation_service

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
    db: AsyncSession = Depends(get_hr_db),
    redis: aioredis.Redis = Depends(get_redis),
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
    Each completed turn is persisted to PostgreSQL and cached in Redis.
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

    accumulated: list[str] = []
    detected_domain_holder: list[str] = []  # mutable container for closure

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for chunk in run_agent_graph(agent_state, conversation_id):
                raw = chunk.strip()
                if raw.startswith("data:"):
                    try:
                        event = json.loads(raw[len("data:"):].strip())
                        if event.get("type") == "token":
                            accumulated.append(event.get("content", ""))
                        elif event.get("type") == "tool_result":
                            tool = event.get("tool", "")
                            for domain in ("hr", "crm", "erp"):
                                if domain in tool:
                                    detected_domain_holder[:] = [domain]
                                    break
                    except (json.JSONDecodeError, ValueError):
                        pass
                yield chunk
        except Exception as exc:
            logger.error("SSE stream error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return  # no persistence on error

        # Stream complete — persist to DB + cache (client already received done event)
        full_response = "".join(accumulated)
        if full_response and request.message:
            try:
                await conversation_service.save_turn(
                    db,
                    redis,
                    session_id=conversation_id,
                    user_id=current_user.id,
                    user_message=request.message,
                    assistant_response=full_response,
                    detected_domain=detected_domain_holder[0] if detected_domain_holder else None,
                )
            except Exception as exc:
                logger.error("Failed to persist conversation turn: %s", exc, exc_info=True)

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
    db: AsyncSession = Depends(get_hr_db),
    redis: aioredis.Redis = Depends(get_redis),
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
    detected_domain: Optional[str] = None

    async for chunk in run_agent_graph(agent_state, conversation_id):
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
                for domain in ("hr", "crm", "erp"):
                    if domain in tool_name:
                        detected_domain = domain
                        break
        elif event_type == "error":
            logger.error("chat (non-streaming): agent error — %s", event.get("message"))

    # Persist turn
    if full_response and request.message:
        try:
            await conversation_service.save_turn(
                db,
                redis,
                session_id=conversation_id,
                user_id=current_user.id,
                user_message=request.message,
                assistant_response=full_response,
                detected_domain=detected_domain,
            )
        except Exception as exc:
            logger.error("Failed to persist conversation turn (non-streaming): %s", exc, exc_info=True)

    return {
        "reply": full_response or "Désolé, une erreur s'est produite.",
        "session_id": conversation_id,
        "sources": [],
        "agent_used": tool_names[0] if tool_names else "orchestrator",
    }


# ── History endpoints ─────────────────────────────────────────────────────────

@router.get("/history", response_model=ConversationListResponse)
async def list_history(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_hr_db),
):
    """GET /api/v1/chat/history

    List the current user's conversations, most recent first.
    Supports pagination via ``skip`` and ``limit`` query params (max 100).
    """
    if limit > 100:
        limit = 100
    convs = await conversation_service.list_conversations(
        db, user_id=current_user.id, skip=skip, limit=limit
    )
    return ConversationListResponse(
        conversations=[ConversationSummary(**c) for c in convs],
        total=len(convs),
        skip=skip,
        limit=limit,
    )


@router.get("/history/{session_id}", response_model=ConversationHistoryResponse)
async def get_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_hr_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """GET /api/v1/chat/history/{session_id}

    Returns the full message list for a conversation.
    Checks Redis first; falls back to PostgreSQL on cache miss.
    Returns 404 if not found or not owned by the current user.
    """
    messages = await conversation_service.get_messages(
        db, redis, session_id=session_id, user_id=current_user.id
    )
    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{session_id}' not found.",
        )
    return ConversationHistoryResponse(
        session_id=session_id,
        messages=[MessageOut(**m) for m in messages],
    )


@router.delete("/history/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_hr_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """DELETE /api/v1/chat/history/{session_id}

    Permanently removes a conversation and all its messages from PostgreSQL
    and invalidates the Redis cache entry.
    Returns 404 if not found or not owned by the current user.
    """
    deleted = await conversation_service.delete_conversation(
        db, redis, session_id=session_id, user_id=current_user.id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{session_id}' not found.",
        )
