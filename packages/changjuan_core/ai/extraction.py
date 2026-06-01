from __future__ import annotations

import re
from uuid import UUID

from .contracts import ClaimDraft, ClaimPriority, ExtractionAgentOutput, SupportStatus

DATE_PATTERN = re.compile(r"(19\d{2}|20\d{2})年?")
PERSON_TERMS = ("父亲", "母亲", "爸爸", "妈妈", "外婆", "外公", "爷爷", "奶奶", "配偶", "哥哥", "姐姐", "弟弟", "妹妹", "子女")
ORG_PATTERN = re.compile(
    r"(?:进入|进了|在|到|去了|调到|就职于|任职于|加入|来到)?"
    r"(?P<organization>[\u4e00-\u9fff]{0,6}(?:学校|大学|工厂|供销社|单位|医院|部队|公司))"
)
P0_PATTERNS = {
    "date": DATE_PATTERN,
    "organization": re.compile(r"(学校|大学|工厂|供销社|单位|医院|部队|公司)"),
    "place": re.compile(r"(北京|上海|广州|深圳|江苏|浙江|南通|县|村|镇|市)"),
    "relationship": re.compile(r"(父亲|母亲|爸爸|妈妈|外婆|外公|爷爷|奶奶|配偶|哥哥|姐姐|弟弟|妹妹|子女)"),
}


def extract_claims_from_segments(segments: list[dict]) -> ExtractionAgentOutput:
    claims: list[ClaimDraft] = []
    for segment in segments:
        if segment.get("speaker", "storyteller") != "storyteller":
            continue
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        segment_id = UUID(str(segment["id"]))
        sentences = [part.strip(" ，。") for part in re.split(r"[。！？]", text) if part.strip()]
        for sentence in sentences:
            priority = ClaimPriority.P0 if any(p.search(sentence) for p in P0_PATTERNS.values()) else ClaimPriority.P1
            confidence = float(segment.get("confidence", 0.8))
            claims.append(
                ClaimDraft(
                    claim_text=sentence,
                    claim_type=_classify(sentence),
                    claim_priority=priority,
                    entities=_extract_entities(sentence),
                    source_segment_ids=[segment_id],
                    confidence=confidence,
                    support_status=SupportStatus.SUPPORTED if confidence >= 0.5 else SupportStatus.NEEDS_REVIEW,
                )
            )
    return ExtractionAgentOutput(claims=dedupe_claims(claims))


def dedupe_claims(claims: list[ClaimDraft]) -> list[ClaimDraft]:
    by_key: dict[str, ClaimDraft] = {}
    deduped: list[ClaimDraft] = []
    for claim in claims:
        key = re.sub(r"\s+", "", claim.public_text)
        existing = by_key.get(key)
        if existing is None:
            deduped.append(claim)
            by_key[key] = claim
            continue

        existing.source_segment_ids = _merge_ordered(existing.source_segment_ids, claim.source_segment_ids)
        existing.entities = _merge_entities(existing.entities, claim.entities)
        existing.confidence = max(existing.confidence, claim.confidence)
        existing.support_status = _merge_support_status(existing.support_status, claim.support_status)
        existing.claim_priority = _merge_priority(existing.claim_priority, claim.claim_priority)
    return deduped


def detect_contradictions(claims: list[ClaimDraft]) -> list[dict]:
    grouped: dict[tuple[str, str], dict[str, ClaimDraft]] = {}
    for claim in claims:
        subject = _subject_key(claim.public_text)
        event = _event_key(claim.public_text)
        date = _date_key(claim.public_text)
        if not subject or not event or not date:
            continue
        grouped.setdefault((subject, event), {})[date] = claim

    contradictions: list[dict] = []
    for (subject, event), by_date in grouped.items():
        if len(by_date) > 1:
            contradictions.append(
                {
                    "field": "date",
                    "subject": subject,
                    "event": event,
                    "claim_ids": [str(claim.id) for claim in by_date.values()],
                    "values": sorted(by_date),
                }
            )
    return contradictions


def _classify(sentence: str) -> str:
    if any(word in sentence for word in ("工作", "单位", "供销社", "工厂", "公司")):
        return "work"
    if any(word in sentence for word in ("出生", "老家", "村", "县", "迁到", "来到")):
        return "migration"
    if any(word in sentence for word in ("结婚", "孩子", "父亲", "母亲", "家")):
        return "family"
    if any(word in sentence for word in ("学校", "读书", "大学")):
        return "education"
    return "life_event"


def _extract_entities(sentence: str) -> dict[str, list[str]]:
    entities: dict[str, list[str]] = {}
    for person in PERSON_TERMS:
        if person in sentence:
            _add_entity(entities, "person", person)

    for match in DATE_PATTERN.finditer(sentence):
        _add_entity(entities, "date", f"{match.group(1)}年")

    for match in ORG_PATTERN.finditer(sentence):
        organization = _normalize_organization(match.group("organization"))
        if organization:
            _add_entity(entities, "organization", organization)

    return entities


def _add_entity(entities: dict[str, list[str]], key: str, value: str) -> None:
    values = entities.setdefault(key, [])
    if value not in values:
        values.append(value)


def _merge_ordered[T](left: list[T], right: list[T]) -> list[T]:
    merged = list(left)
    for item in right:
        if item not in merged:
            merged.append(item)
    return merged


def _merge_entities(left: dict[str, list[str]], right: dict[str, list[str]]) -> dict[str, list[str]]:
    merged = {key: list(values) for key, values in left.items()}
    for key, values in right.items():
        for value in values:
            _add_entity(merged, key, value)
    return merged


def _merge_support_status(left: SupportStatus, right: SupportStatus) -> SupportStatus:
    statuses = {left, right}
    if SupportStatus.SUPPORTED in statuses:
        return SupportStatus.SUPPORTED
    if SupportStatus.CONFLICTING in statuses:
        return SupportStatus.CONFLICTING
    if SupportStatus.UNSUPPORTED in statuses:
        return SupportStatus.UNSUPPORTED
    return SupportStatus.NEEDS_REVIEW


def _merge_priority(left: ClaimPriority, right: ClaimPriority) -> ClaimPriority:
    rank = {ClaimPriority.P0: 0, ClaimPriority.P1: 1, ClaimPriority.P2: 2}
    return left if rank[left] <= rank[right] else right


def _normalize_organization(value: str) -> str:
    for marker in ("就职于", "任职于", "进入", "进了", "去了", "调到", "加入", "来到", "在", "到"):
        if marker in value:
            return value.rsplit(marker, 1)[1]
    return value


def _date_key(text: str) -> str | None:
    match = P0_PATTERNS["date"].search(text)
    return match.group(1) if match else None


def _subject_key(text: str) -> str | None:
    for subject in ("父亲", "母亲", "爸爸", "妈妈", "外婆", "外公", "爷爷", "奶奶"):
        if subject in text:
            return subject
    return None


def _event_key(text: str) -> str | None:
    if "进入" in text and ("工作" in text or "供销社" in text):
        return "entered_workplace"
    if "出生" in text:
        return "birth"
    if "结婚" in text:
        return "marriage"
    return None
