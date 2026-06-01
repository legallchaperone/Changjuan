from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class ApiResponse(BaseModel):
    code: int = 0
    data: Any = Field(default_factory=dict)
    message: str = "ok"
    trace_id: UUID = Field(default_factory=uuid4)


class ErrorResponse(BaseModel):
    code: int
    data: dict = Field(default_factory=dict)
    message: str
    trace_id: UUID = Field(default_factory=uuid4)


class WxLoginRequest(BaseModel):
    wx_openid: str | None = None
    wx_code: str | None = None
    wx_unionid: str | None = None
    nickname: str | None = None
    avatar_url: str | None = None
    phone_e164: str | None = None

    @model_validator(mode="after")
    def require_wechat_identifier(self) -> WxLoginRequest:
        if not self.wx_openid and not self.wx_code:
            raise ValueError("wx_openid or wx_code required")
        return self


class StorytellerCreate(BaseModel):
    display_name: str
    relation_to_payer: str
    birth_year: int | None = None
    birth_place: str | None = None
    current_city: str | None = None
    primary_dialect: str | None = "mandarin"


class ProjectCreate(BaseModel):
    storyteller: StorytellerCreate
    title: str
    themes: list[str] = Field(default_factory=list)
    tier: str = "standard"


class ProjectPatch(BaseModel):
    title: str | None = None
    themes: list[str] | None = None


class ManualPaymentMark(BaseModel):
    MIN_PHASE1_DEPOSIT_CENTS: ClassVar[int] = 49900

    payment_cents: int = Field(ge=0)
    payment_method: Literal["manual_wechat", "manual_alipay", "waived", "free_trial"]
    payment_reference: str | None = None

    def phase1_validation_error(self) -> str | None:
        if self.payment_method in {"manual_wechat", "manual_alipay"} and self.payment_cents < self.MIN_PHASE1_DEPOSIT_CENTS:
            return "manual Phase 1 deposit must be at least 49900 cents"
        if self.payment_method in {"waived", "free_trial"} and self.payment_cents != 0:
            return "waived/free_trial Phase 1 payment must use 0 cents"
        return None


class FeedbackCreate(BaseModel):
    nps_score: int | None = Field(default=None, ge=0, le=10)
    recommend: bool | None = None
    issue_type: str | None = None
    body: str | None = None


class SupportTicketCreate(BaseModel):
    category: str
    body: str = Field(min_length=1)
    priority: Literal["P0", "P1", "P2"] = "P2"


class AdminNoteCreate(BaseModel):
    note_type: str = "ops"
    body: str


class ManualInterventionCreate(BaseModel):
    category: str
    minutes: int = Field(ge=0)
    body: str | None = None


class AiCostCreate(BaseModel):
    task_type: str
    provider: str
    cost_cents: int = Field(ge=0)
    generation_run_id: UUID | None = None


class StuckProjectAssign(BaseModel):
    owner_id: UUID
    reason: str


class PhotoPresignRequest(BaseModel):
    filename: str
    content_type: str


class PhotoCompleteRequest(BaseModel):
    oss_key: str
    caption: str | None = None


class PhotoAnalysisCreate(BaseModel):
    hypothesis_text: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class ConsentCreate(BaseModel):
    consent_type: str
    method: str = "text"
    evidence_oss_key: str | None = None


class InterviewEndRequest(BaseModel):
    status: str = "completed"


class AudioChunkPresignRequest(BaseModel):
    sequence_number: int = Field(ge=0)
    content_type: str = "audio/mpeg"


class AudioChunkUpload(BaseModel):
    sequence_number: int = Field(ge=0)
    duration_ms: int
    oss_key: str
    partial_transcript: str | None = None
    transcript_confidence: float | None = Field(default=None, ge=0, le=1)
    speaker: Literal["storyteller", "interviewer"] = "storyteller"


class CorrectionCreate(BaseModel):
    action: str
    modified_text: str | None = None
    comment: str | None = None


class StoryShareLinkCreate(BaseModel):
    password: str | None = Field(default=None, min_length=4)


class StoryCommentCreate(BaseModel):
    share_token: str | None = None
    password: str | None = None
    display_name: str = Field(min_length=1, max_length=40)
    body: str = Field(min_length=1, max_length=500)


class VerificationIssueResolve(BaseModel):
    resolution_reason: str


class SensitiveClaimReview(BaseModel):
    resolution_reason: str


class SupportTicketPatch(BaseModel):
    status: Literal["open", "pending", "resolved", "closed"] | None = None
    priority: Literal["P0", "P1", "P2"] | None = None
    admin_owner_id: UUID | None = None


def utcnow() -> datetime:
    return datetime.now(UTC)
