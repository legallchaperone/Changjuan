from __future__ import annotations

from enum import StrEnum


class ProjectState(StrEnum):
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
    DELETION_REQUESTED = "deletion_requested"


TRANSITIONS: dict[str, set[str]] = {
    "created": {"payment_marked", "deletion_requested"},
    "payment_marked": {"interview_ready", "deletion_requested"},
    "interview_ready": {"interview_in_progress", "deletion_requested"},
    "interview_in_progress": {"interview_completed", "deletion_requested"},
    "interview_completed": {"claims_extracted", "deletion_requested"},
    "claims_extracted": {"family_correction_pending", "deletion_requested"},
    "family_correction_pending": {"family_correction_completed", "deletion_requested"},
    "family_correction_completed": {"story_generated", "deletion_requested"},
    "story_generated": {"verified", "deletion_requested"},
    "verified": {"elder_second_consent_pending", "deletion_requested"},
    "elder_second_consent_pending": {"published", "deletion_requested"},
    "published": {"deletion_requested"},
    "deletion_requested": set(),
}


class ProjectStateMachine:
    def transition(self, current: str, target: str) -> ProjectState:
        allowed = TRANSITIONS.get(current, set())
        if target not in allowed:
            raise ValueError(f"illegal project transition: {current} -> {target}")
        return ProjectState(target)
