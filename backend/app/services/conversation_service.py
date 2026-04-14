"""Conversation persistence service — PostgreSQL (source of truth) + Redis (24h cache)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation_models import ChatMessage, Conversation

logger = logging.getLogger(__name__)

REDIS_TTL_SECONDS = 86_400  # 24 hours


def _redis_key(session_id: str) -> str:
    return f"chat:conv:{session_id}"


# ── Save one full turn (user + assistant) ─────────────────────────────────────

async def save_turn(
    db: AsyncSession,
    redis: aioredis.Redis,
    *,
    session_id: str,
    user_id: int,
    user_message: str,
    assistant_response: str,
    detected_domain: Optional[str] = None,
) -> Conversation:
    """Persist one conversation turn to Postgres and refresh Redis cache.

    - Creates the Conversation row on first call for this session_id.
    - Appends two ChatMessage rows (role="user", role="assistant").
    - Updates conversation.updated_at and detected_domain.
    - Serialises the full message list to Redis with TTL refresh.
    """
    # Upsert Conversation row
    result = await db.execute(
        select(Conversation).where(Conversation.session_id == session_id)
    )
    conv: Optional[Conversation] = result.scalar_one_or_none()

    if conv is None:
        title = user_message[:60] + ("…" if len(user_message) > 60 else "")
        conv = Conversation(
            session_id=session_id,
            user_id=user_id,
            title=title,
            detected_domain=detected_domain,
        )
        db.add(conv)
        await db.flush()  # populate conv.id within the transaction
    else:
        conv.updated_at = datetime.now(timezone.utc)
        if detected_domain:
            conv.detected_domain = detected_domain

    # Append messages
    db.add(ChatMessage(conversation_id=conv.id, role="user",      content=user_message))
    db.add(ChatMessage(conversation_id=conv.id, role="assistant", content=assistant_response))

    await db.commit()
    await db.refresh(conv)

    # Refresh Redis cache (non-fatal on failure)
    try:
        await _refresh_redis_cache(redis, session_id, conv.id, db)
    except Exception as exc:
        logger.warning("Redis cache update failed (non-fatal): %s", exc)

    return conv


async def _refresh_redis_cache(
    redis: aioredis.Redis,
    session_id: str,
    conv_id: int,
    db: AsyncSession,
) -> None:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.created_at)
    )
    messages = result.scalars().all()
    payload = [
        {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
        for m in messages
    ]
    await redis.set(_redis_key(session_id), json.dumps(payload), ex=REDIS_TTL_SECONDS)


# ── Retrieve messages for one conversation ────────────────────────────────────

async def get_messages(
    db: AsyncSession,
    redis: aioredis.Redis,
    *,
    session_id: str,
    user_id: int,
) -> Optional[list[dict]]:
    """Return messages for session_id. Redis → Postgres fallback.

    Ownership (user_id) is verified on both paths.
    Returns None if not found or not owned by user_id.
    """
    # Try Redis first
    try:
        cached = await redis.get(_redis_key(session_id))
        if cached:
            # Ownership check still requires a DB query
            row = await db.execute(
                select(Conversation.user_id).where(Conversation.session_id == session_id)
            )
            owner_row = row.first()
            if owner_row is None or owner_row[0] != user_id:
                return None
            return json.loads(cached)
    except Exception as exc:
        logger.warning("Redis GET failed, falling back to Postgres: %s", exc)

    # Fall back to Postgres
    result = await db.execute(
        select(Conversation)
        .where(Conversation.session_id == session_id)
        .options(selectinload(Conversation.messages))
    )
    conv: Optional[Conversation] = result.scalar_one_or_none()
    if conv is None or conv.user_id != user_id:
        return None

    messages = [
        {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
        for m in sorted(conv.messages, key=lambda m: m.created_at)
    ]

    # Populate Redis for next request
    try:
        await redis.set(_redis_key(session_id), json.dumps(messages), ex=REDIS_TTL_SECONDS)
    except Exception as exc:
        logger.warning("Redis SET failed (non-fatal): %s", exc)

    return messages


# ── List conversations for a user ─────────────────────────────────────────────

async def list_conversations(
    db: AsyncSession,
    *,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
) -> list[dict]:
    """Return paginated conversations for user_id, most recent first."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    convs = result.scalars().all()
    return [
        {
            "session_id":      c.session_id,
            "title":           c.title,
            "detected_domain": c.detected_domain,
            "created_at":      c.created_at.isoformat(),
            "updated_at":      c.updated_at.isoformat(),
        }
        for c in convs
    ]


# ── Delete a conversation ─────────────────────────────────────────────────────

async def delete_conversation(
    db: AsyncSession,
    redis: aioredis.Redis,
    *,
    session_id: str,
    user_id: int,
) -> bool:
    """Delete conversation and all its messages. Returns False if not found or not owned."""
    result = await db.execute(
        select(Conversation).where(Conversation.session_id == session_id)
    )
    conv: Optional[Conversation] = result.scalar_one_or_none()
    if conv is None or conv.user_id != user_id:
        return False

    await db.execute(delete(Conversation).where(Conversation.id == conv.id))
    await db.commit()

    try:
        await redis.delete(_redis_key(session_id))
    except Exception as exc:
        logger.warning("Redis DELETE failed (non-fatal): %s", exc)

    return True
