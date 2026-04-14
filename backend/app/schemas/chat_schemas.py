"""Pydantic schemas — Chat / IA."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role:    Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    message:  str               = Field(..., min_length=1, max_length=4096)
    history:  list[ChatMessage] = Field(default_factory=list)
    session_id: Optional[str]   = None


class ChatResponse(BaseModel):
    reply:      str
    session_id: str
    sources:    list[dict[str, Any]] = Field(default_factory=list)
    agent_used: Optional[str]        = None


# ── History response schemas ──────────────────────────────────────────────────

class MessageOut(BaseModel):
    role:       Literal["user", "assistant"]
    content:    str
    created_at: str  # ISO 8601


class ConversationSummary(BaseModel):
    session_id:      str
    title:           Optional[str]
    detected_domain: Optional[str]
    created_at:      str
    updated_at:      str


class ConversationHistoryResponse(BaseModel):
    session_id: str
    messages:   list[MessageOut]


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]
    total:         int
    skip:          int
    limit:         int


class SimulationRequest(BaseModel):
    scenario:    str
    parameters:  dict[str, Any] = Field(default_factory=dict)
    domain:      Literal["hr", "crm", "erp", "cross"] = "cross"


class SimulationResponse(BaseModel):
    scenario:    str
    result:      dict[str, Any]
    explanation: str
    confidence:  float = Field(ge=0.0, le=1.0)
