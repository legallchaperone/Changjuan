from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ProjectStatus(StrEnum):
    CREATED = "created"
    PAYMENT_MARKED = "payment_marked"
    INTERVIEW_READY = "interview_ready"
    INTERVIEW_IN_PROGRESS = "interview_in_progress"
    INTERVIEW_COMPLETED = "interview_completed"
    CLAIMS_EXTRACTED = "claims_extracted"
    FAMILY_CORRECTION_PENDING = "family_correction_pending"
    FAMILY_CORRECTION_COMPLETED = "family_correction_completed"
    STORY_GENERATED = "story_generated"
    VERIFIED = "verified"
    ELDER_SECOND_CONSENT_PENDING = "elder_second_consent_pending"
    PUBLISHED = "published"


class PublishGateInput(BaseModel):
    project_status: ProjectStatus
    p0_claims_total: int
    p0_claims_processed: int
    unresolved_block_issues: int
    has_family_sharing_consent: bool
    story_page_generated: bool
    share_links_disabled: bool


class PublishGateResult(BaseModel):
    allowed: bool
    reasons: list[str]


class PublishGate:
    def evaluate(self, gate_input: PublishGateInput) -> PublishGateResult:
        reasons: list[str] = []
        if gate_input.project_status != ProjectStatus.ELDER_SECOND_CONSENT_PENDING:
            reasons.append("project must be elder_second_consent_pending")
        if gate_input.p0_claims_processed < gate_input.p0_claims_total:
            reasons.append("all P0 claims must be processed")
        if gate_input.unresolved_block_issues > 0:
            reasons.append("unresolved block-level verification issues")
        if not gate_input.has_family_sharing_consent:
            reasons.append("second consent / family sharing consent is required")
        if not gate_input.story_page_generated:
            reasons.append("story_page must be generated")
        if not gate_input.share_links_disabled:
            reasons.append("share_links must remain disabled until publish")
        return PublishGateResult(allowed=not reasons, reasons=reasons)
