"""Conversation and ChatMessage ORM models — stored in talan_hr."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Conversation(Base):
    __tablename__ = "chat_conversations"

    id:              Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    session_id:      Mapped[str]           = mapped_column(String(36), unique=True, nullable=False, index=True)
    user_id:         Mapped[int]           = mapped_column(Integer, nullable=False, index=True)
    title:           Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    detected_domain: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at:      Mapped[datetime]      = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at:      Mapped[datetime]      = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    messages: Mapped[List["ChatMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    __table_args__ = (
        Index("ix_chat_conv_user_updated", "user_id", "updated_at"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id:              Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role:       Mapped[str]      = mapped_column(String(20), nullable=False)  # "user" | "assistant"
    content:    Mapped[str]      = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
