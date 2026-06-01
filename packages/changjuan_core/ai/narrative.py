from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .contracts import ClaimDraft, SupportStatus


class ChapterDraft(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    slug: str
    title: str
    body: str
    claim_ids: list[UUID] = Field(default_factory=list)


class NarrativeDraft(BaseModel):
    chapters: list[ChapterDraft]


SECTION_MAP = {
    "family": ("family", "婚姻与子女"),
    "work": ("work-migration", "工作与迁徙"),
    "migration": ("work-migration", "工作与迁徙"),
    "education": ("education", "求学与成长"),
    "life_event": ("remembered-events", "家人记住的几件事"),
}


def generate_narrative_draft(claims: list[ClaimDraft]) -> NarrativeDraft:
    confirmed = [
        c
        for c in claims
        if c.verification_status in {"confirmed", "modified"} and _has_story_evidence(c)
    ]
    unsure = [
        c for c in claims if c.verification_status == "marked_unsure" and _has_story_evidence(c)
    ]
    buckets: dict[str, list[ClaimDraft]] = {
        "opening": [],
        "childhood-family": [],
        "education": [],
        "work-migration": [],
        "family": [],
        "remembered-events": [],
        "message-to-descendants": [],
    }

    for claim in confirmed:
        slug, _ = SECTION_MAP.get(claim.claim_type, ("remembered-events", "家人记住的几件事"))
        buckets[slug].append(claim)

    chapters = [
        _chapter("opening", "开篇：这个人是谁", buckets["opening"]),
        _chapter("childhood-family", "童年与家庭", buckets["childhood-family"]),
        _chapter("education", "求学与成长", buckets["education"]),
        _chapter("work-migration", "工作与迁徙", buckets["work-migration"]),
        _chapter("family", "婚姻与子女", buckets["family"]),
        _chapter("remembered-events", "家人记住的几件事", buckets["remembered-events"]),
        _chapter("message-to-descendants", "给后辈的话", buckets["message-to-descendants"]),
        ChapterDraft(
            slug="unconfirmed-appendix",
            title="待确认事实与原声附录",
            body="\n".join(f"- {claim.public_text}" for claim in unsure) or "暂无待确认事实。",
            claim_ids=[claim.id for claim in unsure],
        ),
    ]
    return NarrativeDraft(chapters=chapters)


def _chapter(slug: str, title: str, claims: list[ClaimDraft]) -> ChapterDraft:
    if not claims:
        return ChapterDraft(slug=slug, title=title, body="本章等待更多已核验素材。")
    body = "\n".join(f"{claim.public_text}。" for claim in claims)
    return ChapterDraft(slug=slug, title=title, body=body, claim_ids=[claim.id for claim in claims])


def _has_story_evidence(claim: ClaimDraft) -> bool:
    return bool(claim.source_segment_ids) and claim.support_status != SupportStatus.UNSUPPORTED
