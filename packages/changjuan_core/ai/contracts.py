from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

CLAIM_EMBEDDING_DIMENSIONS = 16


def embed_claim_text(text: str) -> list[float]:
    normalized = " ".join(text.strip().split())
    digest = sha256(normalized.encode("utf-8")).digest()
    return [round((digest[index] / 127.5) - 1, 6) for index in range(CLAIM_EMBEDDING_DIMENSIONS)]


class ClaimPriority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class SupportStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"
    NEEDS_REVIEW = "needs_review"


class CorrectionAction(StrEnum):
    CONFIRM = "confirm"
    MODIFY = "modify"
    UNSURE = "unsure"
    HIDE_FROM_FAMILY = "hide_from_family"
    DELETE = "delete"


class ClaimDraft(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    claim_text: str
    claim_type: str
    claim_priority: ClaimPriority = ClaimPriority.P1
    entities: dict[str, list[str]] = Field(default_factory=dict)
    source_segment_ids: list[UUID] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    support_status: SupportStatus = SupportStatus.SUPPORTED
    verification_status: str = "pending"
    sensitivity_level: str = "normal"
    human_reviewed: bool = False
    modified_text: str | None = None
    embedding: list[float] | None = None
    deleted_at: datetime | None = None
    purge_after_at: datetime | None = None

    @model_validator(mode="after")
    def ensure_embedding(self) -> ClaimDraft:
        if self.embedding is None:
            self.embedding = embed_claim_text(self.public_text)
        return self

    @property
    def public_text(self) -> str:
        return self.modified_text or self.claim_text

    @property
    def is_p0(self) -> bool:
        return self.claim_priority == ClaimPriority.P0


class CaptureAgentInput(BaseModel):
    project_context: dict = Field(default_factory=dict)
    storyteller_profile: dict = Field(default_factory=dict)
    themes: list[str] = Field(default_factory=list)
    confirmed_photo_captions: list[str] = Field(default_factory=list)
    recent_transcript: list[str] = Field(default_factory=list)
    session_state: dict = Field(default_factory=dict)


class CaptureAgentOutput(BaseModel):
    next_utterance: str
    action: str
    topic: str
    safety_flag: str = "none"


class ExtractionAgentOutput(BaseModel):
    claims: list[ClaimDraft]


class PhotoHypothesis(BaseModel):
    photo_id: UUID
    hypothesis_text: str
    confidence: float = Field(ge=0, le=1)
    internal_only: bool = True

    def eligible_for_prompt(self) -> bool:
        return self.internal_only and self.confidence >= 0.5 and self._has_uncertainty_marker()

    def _has_uncertainty_marker(self) -> bool:
        return any(marker in self.hypothesis_text for marker in ("可能", "大约", "推测"))
