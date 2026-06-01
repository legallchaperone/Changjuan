from __future__ import annotations

import re
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .contracts import ClaimDraft, ClaimPriority, SupportStatus


class VerificationGate(StrEnum):
    CITATION_COVERAGE = "citation_coverage"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    SENSITIVE_CONTENT = "sensitive_content"
    FAMILY_CONFIRMATION = "family_confirmation"


class VerificationIssue(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    gate: VerificationGate
    severity: str = "block"
    message: str
    chapter_id: UUID | None = None
    citation_id: UUID | None = None
    claim_id: UUID | None = None


class VerificationResult(BaseModel):
    passed: bool
    issues: list[VerificationIssue]


class Verifier:
    def verify(
        self,
        claims: list[ClaimDraft],
        chapters: list[dict],
        citations: list[dict],
    ) -> VerificationResult:
        issues: list[VerificationIssue] = []
        citation_claim_ids = {str(citation.get("claim_id")) for citation in citations if citation.get("claim_id")}
        claim_by_id = {str(claim.id): claim for claim in claims}

        for chapter in chapters:
            chapter_claim_ids = [str(item) for item in chapter.get("claim_ids", [])]
            body = str(chapter.get("body", ""))
            factful_sentences = _factful_sentences(body)
            if factful_sentences and not chapter_claim_ids:
                issues.append(
                    VerificationIssue(
                        gate=VerificationGate.CITATION_COVERAGE,
                        message="事实句缺少 claim_ids",
                        chapter_id=UUID(str(chapter["id"])) if chapter.get("id") else None,
                    )
                )
            elif len(factful_sentences) > len(set(chapter_claim_ids)):
                issues.append(
                    VerificationIssue(
                        gate=VerificationGate.CITATION_COVERAGE,
                        message="事实句数量超过 claim_ids 覆盖",
                        chapter_id=UUID(str(chapter["id"])) if chapter.get("id") else None,
                    )
                )
            for claim_id in chapter_claim_ids:
                claim = claim_by_id.get(claim_id)
                if claim and not claim.source_segment_ids and claim_id not in citation_claim_ids:
                    issues.append(
                        VerificationIssue(
                            gate=VerificationGate.UNSUPPORTED_CLAIM,
                            message="该句缺少音频或家人确认证据",
                            chapter_id=UUID(str(chapter["id"])) if chapter.get("id") else None,
                            claim_id=claim.id,
                        )
                    )

        for claim in claims:
            if claim.support_status == SupportStatus.UNSUPPORTED:
                issues.append(
                    VerificationIssue(
                        gate=VerificationGate.UNSUPPORTED_CLAIM,
                        message="claim 无 evidence 或 support_status=unsupported",
                        claim_id=claim.id,
                    )
                )
            if claim.claim_priority == ClaimPriority.P0 and claim.verification_status not in {
                "confirmed",
                "modified",
                "marked_unsure",
                "rejected",
                "hidden",
                "deleted",
            }:
                issues.append(
                    VerificationIssue(
                        gate=VerificationGate.FAMILY_CONFIRMATION,
                        message="P0 claims 未处理",
                        claim_id=claim.id,
                    )
                )
            if claim.sensitivity_level in {"sensitive", "highly_sensitive"} and not claim.human_reviewed:
                issues.append(
                    VerificationIssue(
                        gate=VerificationGate.SENSITIVE_CONTENT,
                        message="sensitive/highly_sensitive 未经人工审核",
                        claim_id=claim.id,
                    )
                )

        return VerificationResult(
            passed=not any(issue.severity == "block" for issue in issues), issues=issues
        )


def _looks_factful(body: str) -> bool:
    markers = ("年", "在", "进入", "出生", "结婚", "迁", "工作", "学校", "单位")
    return any(marker in body for marker in markers)


def _factful_sentences(body: str) -> list[str]:
    sentences = [sentence.strip() for sentence in re.split(r"[。！？\n]", body) if sentence.strip()]
    return [sentence for sentence in sentences if _looks_factful(sentence)]
