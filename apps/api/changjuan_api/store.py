from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from changjuan_core.ai.contracts import ClaimDraft, ClaimPriority, SupportStatus, embed_claim_text
from changjuan_core.ai.narrative import NarrativeDraft, generate_narrative_draft
from changjuan_core.ai.verifier import Verifier
from changjuan_core.audio.rate_limit import AudioChunkPolicy
from changjuan_core.compliance.audit import AuditLog, AuditSink
from changjuan_core.compliance.encryption import PIIEncryptor
from changjuan_core.providers.router import GenerationRun
from changjuan_core.story.publish_gate import ProjectStatus, PublishGate, PublishGateInput


@dataclass
class UserRecord:
    id: UUID
    wx_openid: str
    wx_unionid: str | None = None
    nickname: str | None = None
    avatar_url: str | None = None
    phone_e164_enc: str | None = None
    phone_hash: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None


@dataclass
class AdminUserRecord:
    id: UUID
    email: str
    password_hash: str
    role: str
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_login_at: datetime | None = None


@dataclass
class AdminSessionRecord:
    id: UUID
    admin_user_id: UUID
    token_hash: str
    expires_at: datetime
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PilotWhitelistEntry:
    id: UUID
    phone_hash: str | None = None
    wx_openid: str | None = None
    source: str | None = None
    invited_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ProjectRecord:
    id: UUID
    user_id: UUID
    title: str
    storyteller: dict
    themes: list[str]
    tier: str
    status: str = "created"
    payment_status: str = "not_required"
    payment_cents: int = 0
    payment_method: str | None = None
    payment_reference: str | None = None
    payment_marked_by_admin_id: UUID | None = None
    payment_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None
    purge_after_at: datetime | None = None
    deletion_request_id: UUID | None = None
    story_page_id: UUID | None = None
    has_interview_consent: bool = False
    has_family_sharing_consent: bool = False
    ops_owner_id: UUID | None = None
    stuck_reason: str | None = None
    stuck_at: datetime | None = None


@dataclass
class SessionRecord:
    id: UUID
    project_id: UUID
    status: str = "scheduled"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AudioChunkRecord:
    session_id: UUID
    sequence_number: int
    duration_ms: int
    oss_key: str
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None
    purge_after_at: datetime | None = None


@dataclass
class TranscriptSegmentRecord:
    id: UUID
    project_id: UUID
    session_id: UUID
    audio_chunk_sequence_number: int
    speaker: str
    text: str
    start_ms: int
    end_ms: int
    confidence: float
    low_confidence_review: bool
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None
    purge_after_at: datetime | None = None


@dataclass
class PhotoRecord:
    id: UUID
    project_id: UUID
    oss_key: str
    thumbnail_oss_key: str
    caption: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None
    purge_after_at: datetime | None = None


@dataclass
class PhotoAnalysisRecord:
    id: UUID
    project_id: UUID
    photo_id: UUID
    hypothesis_text: str
    confidence: float
    internal_only: bool = True
    converted_claim_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None
    purge_after_at: datetime | None = None

    @property
    def eligible_for_prompt(self) -> bool:
        return self.internal_only and self.confidence >= 0.5 and _has_photo_uncertainty(self.hypothesis_text)


@dataclass
class StoryPageRecord:
    id: UUID
    project_id: UUID
    enabled: bool = False
    password_hash: str | None = None
    share_links_enabled: bool = False
    draft: NarrativeDraft | None = None
    deleted_at: datetime | None = None
    purge_after_at: datetime | None = None


@dataclass
class ChapterRecord:
    id: UUID
    project_id: UUID
    slug: str
    title: str
    body_markdown: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None
    purge_after_at: datetime | None = None
    purged_at: datetime | None = None


@dataclass
class CitationRecord:
    id: UUID
    chapter_id: UUID
    claim_id: UUID
    display_label: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None
    purge_after_at: datetime | None = None
    purged_at: datetime | None = None


@dataclass
class ShareLinkRecord:
    id: UUID
    story_page_id: UUID
    token_hash: str
    password_hash: str | None
    created_by_user_id: UUID | None
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    revoked_at: datetime | None = None
    reset_at: datetime | None = None
    deleted_at: datetime | None = None
    purge_after_at: datetime | None = None


@dataclass
class StoryAccessLogRecord:
    id: UUID
    story_page_id: UUID
    share_link_id: UUID
    media_access_token_hash: str
    accessed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class FamilyCommentRecord:
    id: UUID
    story_page_id: UUID
    share_link_id: UUID
    display_name: str
    body: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None
    purge_after_at: datetime | None = None


@dataclass
class PdfExportRecord:
    id: UUID
    project_id: UUID
    story_page_id: UUID
    oss_key: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None
    purge_after_at: datetime | None = None


@dataclass
class ConsentRecord:
    id: UUID
    project_id: UUID
    user_id: UUID | None
    consent_type: str
    method: str
    evidence_oss_key: str | None = None
    withdrawn_at: datetime | None = None
    minimized_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class DeletionRequestRecord:
    id: UUID
    project_id: UUID
    requested_by_user_id: UUID | None
    requested_at: datetime
    execute_after_at: datetime
    status: str = "pending"
    executed_at: datetime | None = None


@dataclass
class SupportTicketRecord:
    id: UUID
    project_id: UUID
    user_id: UUID | None
    status: str
    priority: str
    category: str
    body: str
    admin_owner_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class InternalNoteRecord:
    id: UUID
    project_id: UUID
    admin_user_id: UUID
    note_type: str
    body: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class FeedbackRecord:
    id: UUID
    project_id: UUID
    user_id: UUID
    nps_score: int | None
    recommend: bool | None
    issue_type: str | None
    body: str | None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ClaimCorrectionRecord:
    id: UUID
    claim_id: UUID
    user_id: UUID
    action: str
    modified_text: str | None = None
    comment: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ManualInterventionRecord:
    id: UUID
    project_id: UUID
    admin_user_id: UUID
    category: str
    minutes: int
    body: str | None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AiCostRecord:
    id: UUID
    project_id: UUID
    admin_user_id: UUID
    task_type: str
    provider: str
    cost_cents: int
    generation_run_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AlertRecord:
    id: UUID
    path: str
    method: str
    error_type: str
    message: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class InMemoryStore:
    def __init__(self, whitelist_openids: set[str] | None = None) -> None:
        self.users: dict[UUID, UserRecord] = {}
        self.users_by_openid: dict[str, UUID] = {}
        self.projects: dict[UUID, ProjectRecord] = {}
        self.sessions: dict[UUID, SessionRecord] = {}
        self.audio_chunks: dict[tuple[UUID, int], AudioChunkRecord] = {}
        self.audio_chunk_policies: dict[UUID, AudioChunkPolicy] = {}
        self.transcript_segments: dict[UUID, TranscriptSegmentRecord] = {}
        self.photos: dict[UUID, PhotoRecord] = {}
        self.photo_analyses: dict[UUID, PhotoAnalysisRecord] = {}
        self.claims: dict[UUID, ClaimDraft] = {}
        self.claims_by_project: dict[UUID, list[UUID]] = {}
        self.claim_evidence: dict[UUID, dict] = {}
        self.claim_corrections: dict[UUID, ClaimCorrectionRecord] = {}
        self.verification_issues: dict[UUID, dict] = {}
        self.story_pages: dict[UUID, StoryPageRecord] = {}
        self.chapters: dict[UUID, ChapterRecord] = {}
        self.citations: dict[UUID, CitationRecord] = {}
        self.share_links: dict[UUID, ShareLinkRecord] = {}
        self.story_access_logs: dict[UUID, StoryAccessLogRecord] = {}
        self.family_comments: dict[UUID, FamilyCommentRecord] = {}
        self.pdf_exports: dict[UUID, PdfExportRecord] = {}
        self.consent_records: dict[UUID, ConsentRecord] = {}
        self.deletion_requests: dict[UUID, DeletionRequestRecord] = {}
        self.support_tickets: dict[UUID, SupportTicketRecord] = {}
        self.internal_notes: dict[UUID, InternalNoteRecord] = {}
        self.feedback: dict[UUID, FeedbackRecord] = {}
        self.manual_interventions: dict[UUID, ManualInterventionRecord] = {}
        self.ai_costs: dict[UUID, AiCostRecord] = {}
        self.generation_runs: dict[UUID, GenerationRun] = {}
        self.rate_limit_hits: dict[str, list[datetime]] = {}
        self.alerts: dict[UUID, AlertRecord] = {}
        self.audit = AuditSink()
        self.admin_id = uuid4()
        self.admin_users: dict[UUID, AdminUserRecord] = {
            self.admin_id: AdminUserRecord(
                id=self.admin_id,
                email="ops@changjuan.test",
                password_hash=_hash_secret("phase1-admin"),
                role="ops",
            )
        }
        self.admin_sessions: dict[UUID, AdminSessionRecord] = {}
        self.revoked_token_ids: set[str] = set()
        self.revoked_token_session_ids: set[str] = set()
        self.pilot_whitelist: dict[UUID, PilotWhitelistEntry] = {}
        self.whitelist_openids = set()
        for openid in (whitelist_openids if whitelist_openids is not None else {"wx_phase1", "wx_demo"}):
            entry = PilotWhitelistEntry(
                id=_pilot_whitelist_id(wx_openid=openid),
                wx_openid=openid,
                source="config",
            )
            self.pilot_whitelist[entry.id] = entry
            self.whitelist_openids.add(openid)

    def record_generation_run(self, run: GenerationRun) -> GenerationRun:
        self.generation_runs[run.id] = run
        return run

    def add_pilot_whitelist_entry(
        self,
        *,
        phone_hash: str | None = None,
        wx_openid: str | None = None,
        source: str | None = None,
        invited_by: str | None = None,
    ) -> PilotWhitelistEntry:
        entry_id = _pilot_whitelist_id(wx_openid=wx_openid, phone_hash=phone_hash)
        existing = self.pilot_whitelist.get(entry_id)
        entry = PilotWhitelistEntry(
            id=entry_id,
            phone_hash=phone_hash,
            wx_openid=wx_openid,
            source=source,
            invited_by=invited_by,
            created_at=existing.created_at if existing else datetime.now(UTC),
        )
        self.pilot_whitelist[entry.id] = entry
        if wx_openid:
            self.whitelist_openids.add(wx_openid)
        return entry

    def is_pilot_whitelisted(self, wx_openid: str) -> bool:
        return wx_openid in self.whitelist_openids

    def revoke_token_id(self, token_id: str | None) -> None:
        if token_id:
            self.revoked_token_ids.add(token_id)

    def revoke_token_session(self, session_id: str | None) -> None:
        if session_id:
            self.revoked_token_session_ids.add(session_id)

    def is_token_revoked(self, token_id: str | None) -> bool:
        return bool(token_id and token_id in self.revoked_token_ids)

    def is_token_session_revoked(self, session_id: str | None) -> bool:
        return bool(session_id and session_id in self.revoked_token_session_ids)

    def authenticate_admin(self, email: str | None, password: str | None) -> AdminUserRecord | None:
        for admin_user in self.admin_users.values():
            if (
                admin_user.email == email
                and admin_user.enabled
                and admin_user.password_hash == _hash_secret(password or "")
            ):
                return admin_user
        return None

    def record_admin_login(self, admin_user_id: UUID, access_token: str) -> AdminSessionRecord:
        now = datetime.now(UTC)
        admin_user = self.admin_users[admin_user_id]
        admin_user.last_login_at = now
        session = AdminSessionRecord(
            id=uuid4(),
            admin_user_id=admin_user_id,
            token_hash=_hash_secret(access_token),
            expires_at=now + timedelta(days=7),
            created_at=now,
        )
        self.admin_sessions[session.id] = session
        self.audit.record(
            AuditLog(
                actor_id=admin_user_id,
                action="admin.login",
                resource_type="admin_session",
                resource_id=session.id,
            )
        )
        return session

    def is_admin_session_active(self, admin_user_id: UUID, access_token: str | None) -> bool:
        admin_user = self.admin_users.get(admin_user_id)
        if not admin_user or not admin_user.enabled or not access_token:
            return False
        token_hash = _hash_secret(access_token)
        now = datetime.now(UTC)
        return any(
            session.admin_user_id == admin_user_id
            and session.token_hash == token_hash
            and session.expires_at > now
            for session in self.admin_sessions.values()
        )

    def upsert_user(
        self,
        wx_openid: str,
        nickname: str | None,
        wx_unionid: str | None = None,
        avatar_url: str | None = None,
        phone_e164: str | None = None,
        pii_encryptor: PIIEncryptor | None = None,
    ) -> UserRecord:
        if wx_openid in self.users_by_openid:
            user = self.users[self.users_by_openid[wx_openid]]
            user.nickname = nickname or user.nickname
            user.wx_unionid = wx_unionid or user.wx_unionid
            user.avatar_url = avatar_url or user.avatar_url
            self._store_user_phone(user, phone_e164, pii_encryptor)
            user.updated_at = datetime.now(UTC)
            return user
        user = UserRecord(
            id=uuid4(),
            wx_openid=wx_openid,
            wx_unionid=wx_unionid,
            nickname=nickname,
            avatar_url=avatar_url,
        )
        self._store_user_phone(user, phone_e164, pii_encryptor)
        self.users[user.id] = user
        self.users_by_openid[wx_openid] = user.id
        return user

    def _store_user_phone(
        self,
        user: UserRecord,
        phone_e164: str | None,
        pii_encryptor: PIIEncryptor | None,
    ) -> None:
        if not phone_e164 or not pii_encryptor:
            return
        user.phone_e164_enc = pii_encryptor.encrypt(phone_e164).encode()
        user.phone_hash = pii_encryptor.hmac_sha256(phone_e164)

    def accept_rate_limited_request(self, key: str, limit: int = 60) -> bool:
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=1)
        hits = [hit for hit in self.rate_limit_hits.get(key, []) if hit > cutoff]
        if len(hits) >= limit:
            self.rate_limit_hits[key] = hits
            return False
        hits.append(now)
        self.rate_limit_hits[key] = hits
        return True

    def record_alert(self, path: str, method: str, error: Exception) -> AlertRecord:
        alert = AlertRecord(
            id=uuid4(),
            path=path,
            method=method,
            error_type=type(error).__name__,
            message=str(error),
        )
        self.alerts[alert.id] = alert
        return alert

    def save_verification_issue(self, issue_id: UUID, issue: dict) -> dict:
        self.verification_issues[issue_id] = issue
        return issue

    def touch_project(self, project_id: UUID, at: datetime | None = None) -> ProjectRecord:
        project = self.projects[project_id]
        project.updated_at = at or datetime.now(UTC)
        return project

    def create_project(self, user_id: UUID, payload: dict) -> ProjectRecord:
        project = ProjectRecord(
            id=uuid4(),
            user_id=user_id,
            title=payload["title"],
            storyteller=payload["storyteller"],
            themes=payload.get("themes", []),
            tier=payload.get("tier", "standard"),
            payment_status="pending",
            payment_cents=49900 if payload.get("tier", "standard") == "standard" else 0,
        )
        self.projects[project.id] = project
        self.audit.record(
            AuditLog(
                actor_id=user_id,
                action="project.create",
                resource_type="project",
                resource_id=project.id,
                metadata={"title": project.title},
            )
        )
        return project

    def mark_payment(self, project_id: UUID, admin_id: UUID, payload: dict) -> ProjectRecord:
        project = self.projects[project_id]
        now = datetime.now(UTC)
        project.payment_status = "paid" if payload["payment_cents"] > 0 else "waived"
        project.payment_cents = payload["payment_cents"]
        project.payment_method = payload["payment_method"]
        project.payment_reference = payload.get("payment_reference")
        project.payment_marked_by_admin_id = admin_id
        project.payment_at = now
        project.status = "payment_marked"
        project.updated_at = now
        self.audit.record(
            AuditLog(
                actor_id=admin_id,
                action="admin.mark_payment",
                resource_type="project",
                resource_id=project.id,
                metadata={"payment_method": project.payment_method, "reference": project.payment_reference},
            )
        )
        return project

    def create_feedback(self, project_id: UUID, user_id: UUID, payload: dict) -> FeedbackRecord:
        feedback = FeedbackRecord(
            id=uuid4(),
            project_id=project_id,
            user_id=user_id,
            nps_score=payload.get("nps_score"),
            recommend=payload.get("recommend"),
            issue_type=payload.get("issue_type"),
            body=payload.get("body"),
        )
        self.feedback[feedback.id] = feedback
        return feedback

    def create_support_ticket(
        self,
        project_id: UUID,
        user_id: UUID,
        payload: dict,
    ) -> SupportTicketRecord:
        ticket = SupportTicketRecord(
            id=uuid4(),
            project_id=project_id,
            user_id=user_id,
            status="open",
            priority=payload.get("priority") or "P2",
            category=payload["category"],
            body=payload["body"],
        )
        self.support_tickets[ticket.id] = ticket
        return ticket

    def save_support_ticket(self, ticket: SupportTicketRecord) -> SupportTicketRecord:
        self.support_tickets[ticket.id] = ticket
        return ticket

    def record_consent(self, consent: ConsentRecord) -> ConsentRecord:
        self.consent_records[consent.id] = consent
        project = self.projects[consent.project_id]
        if not consent.withdrawn_at:
            if consent.consent_type == "interview_consent":
                project.has_interview_consent = True
            if consent.consent_type == "family_sharing":
                project.has_family_sharing_consent = True
        self.touch_project(project.id)
        return consent

    def create_internal_note(self, project_id: UUID, admin_id: UUID, payload: dict) -> InternalNoteRecord:
        note = InternalNoteRecord(
            id=uuid4(),
            project_id=project_id,
            admin_user_id=admin_id,
            note_type=payload.get("note_type") or "ops",
            body=payload["body"],
        )
        self.internal_notes[note.id] = note
        return note

    def record_manual_intervention(self, project_id: UUID, admin_id: UUID, payload: dict) -> ManualInterventionRecord:
        intervention = ManualInterventionRecord(
            id=uuid4(),
            project_id=project_id,
            admin_user_id=admin_id,
            category=payload["category"],
            minutes=payload["minutes"],
            body=payload.get("body"),
        )
        self.manual_interventions[intervention.id] = intervention
        return intervention

    def record_ai_cost(self, project_id: UUID, admin_id: UUID, payload: dict) -> AiCostRecord:
        cost = AiCostRecord(
            id=uuid4(),
            project_id=project_id,
            admin_user_id=admin_id,
            task_type=payload["task_type"],
            provider=payload["provider"],
            cost_cents=payload["cost_cents"],
            generation_run_id=payload.get("generation_run_id"),
        )
        self.ai_costs[cost.id] = cost
        return cost

    def mark_project_stuck(self, project_id: UUID, owner_id: UUID, reason: str) -> ProjectRecord:
        project = self.projects[project_id]
        now = datetime.now(UTC)
        project.ops_owner_id = owner_id
        project.stuck_reason = reason
        project.stuck_at = now
        project.updated_at = now
        return project

    def record_claim_correction(self, claim_id: UUID, user_id: UUID, payload: dict) -> ClaimCorrectionRecord:
        correction = ClaimCorrectionRecord(
            id=uuid4(),
            claim_id=claim_id,
            user_id=user_id,
            action=payload["action"],
            modified_text=payload.get("modified_text"),
            comment=payload.get("comment"),
        )
        self.claim_corrections[correction.id] = correction
        return correction

    def save_claim(self, project_id: UUID, claim: ClaimDraft) -> ClaimDraft:
        claim.embedding = embed_claim_text(claim.public_text)
        self.claims[claim.id] = claim
        self.claims_by_project.setdefault(project_id, [])
        if claim.id not in self.claims_by_project[project_id]:
            self.claims_by_project[project_id].append(claim.id)
        return claim

    def save_story_page(self, page: StoryPageRecord) -> StoryPageRecord:
        self.story_pages[page.id] = page
        if page.draft:
            self._sync_story_chapters(page.project_id, page.draft)
        return page

    def create_session(self, project_id: UUID) -> SessionRecord:
        session = SessionRecord(id=uuid4(), project_id=project_id)
        self.sessions[session.id] = session
        project = self.projects[project_id]
        project.status = "interview_ready"
        self.touch_project(project_id)
        return session

    def save_session(self, session: SessionRecord) -> SessionRecord:
        self.sessions[session.id] = session
        return session

    def record_photo(self, photo: PhotoRecord) -> PhotoRecord:
        self.photos[photo.id] = photo
        self.touch_project(photo.project_id)
        return photo

    def save_photo(self, photo: PhotoRecord) -> PhotoRecord:
        self.photos[photo.id] = photo
        return photo

    def record_audio_chunk(self, session_id: UUID, sequence_number: int, duration_ms: int, oss_key: str) -> AudioChunkRecord:
        key = (session_id, sequence_number)
        if key in self.audio_chunks:
            return self.audio_chunks[key]
        policy = self.audio_chunk_policies.setdefault(session_id, AudioChunkPolicy())
        received_at = datetime.now(UTC)
        policy.accept_chunk(duration_ms, received_at)
        chunk = AudioChunkRecord(
            session_id=session_id,
            sequence_number=sequence_number,
            duration_ms=duration_ms,
            oss_key=oss_key,
            received_at=received_at,
        )
        self.audio_chunks[key] = chunk
        return chunk

    def record_transcript_segment(
        self,
        project_id: UUID,
        session_id: UUID,
        audio_chunk_sequence_number: int,
        speaker: str,
        text: str,
        confidence: float,
        duration_ms: int,
    ) -> TranscriptSegmentRecord:
        for segment in self.transcript_segments.values():
            if segment.session_id == session_id and segment.audio_chunk_sequence_number == audio_chunk_sequence_number:
                return segment
        start_ms = audio_chunk_sequence_number * duration_ms
        segment = TranscriptSegmentRecord(
            id=uuid4(),
            project_id=project_id,
            session_id=session_id,
            audio_chunk_sequence_number=audio_chunk_sequence_number,
            speaker=speaker,
            text=text,
            start_ms=start_ms,
            end_ms=start_ms + duration_ms,
            confidence=confidence,
            low_confidence_review=confidence < 0.5,
        )
        self.transcript_segments[segment.id] = segment
        return segment

    def session_recovery(self, session_id: UUID) -> dict:
        sequences = sorted(sequence for chunk_session_id, sequence in self.audio_chunks if chunk_session_id == session_id)
        last_sequence = sequences[-1] if sequences else None
        missing = []
        if last_sequence is not None:
            present = set(sequences)
            missing = [sequence for sequence in range(last_sequence + 1) if sequence not in present]
        return {
            "session_id": str(session_id),
            "last_accepted_sequence_number": last_sequence,
            "missing_sequence_numbers": missing,
            "buffered_chunk_count": len(sequences),
        }

    def create_photo_analysis(self, photo_id: UUID, hypothesis_text: str, confidence: float) -> PhotoAnalysisRecord:
        photo = self.photos[photo_id]
        analysis = PhotoAnalysisRecord(
            id=uuid4(),
            project_id=photo.project_id,
            photo_id=photo.id,
            hypothesis_text=hypothesis_text,
            confidence=confidence,
        )
        self.photo_analyses[analysis.id] = analysis
        return analysis

    def convert_photo_analysis_to_candidate(self, analysis_id: UUID) -> ClaimDraft:
        analysis = self.photo_analyses[analysis_id]
        if analysis.converted_claim_id and analysis.converted_claim_id in self.claims:
            return self.claims[analysis.converted_claim_id]
        claim = ClaimDraft(
            id=analysis.converted_claim_id or uuid4(),
            claim_text=analysis.hypothesis_text,
            claim_type="photo_hypothesis",
            claim_priority=ClaimPriority.P2,
            entities={"photo_id": [str(analysis.photo_id)], "source": ["photo_hypothesis"]},
            confidence=analysis.confidence,
            support_status=SupportStatus.NEEDS_REVIEW,
            verification_status="pending",
        )
        self.claims[claim.id] = claim
        self.claims_by_project.setdefault(analysis.project_id, [])
        self.claims_by_project[analysis.project_id].append(claim.id)
        analysis.converted_claim_id = claim.id
        return claim

    def seed_claims_for_project(self, project_id: UUID) -> list[ClaimDraft]:
        if project_id in self.claims_by_project:
            return [self.claims[cid] for cid in self.claims_by_project[project_id]]
        claim = ClaimDraft(
            claim_text="父亲1978年进入县供销社工作",
            claim_type="work",
            claim_priority=ClaimPriority.P0,
            source_segment_ids=[uuid4()],
            confidence=0.86,
            support_status=SupportStatus.SUPPORTED,
        )
        self.claims[claim.id] = claim
        self.claims_by_project[project_id] = [claim.id]
        return [claim]

    def complete_corrections(self, project_id: UUID) -> None:
        for claim in self.seed_claims_for_project(project_id):
            if claim.verification_status == "pending":
                raise ValueError("P0 claims must be processed")
        project = self.projects[project_id]
        project.status = "family_correction_completed"
        self.touch_project(project_id)

    def generate_story(self, project_id: UUID) -> StoryPageRecord:
        claims = [claim for claim in self.seed_claims_for_project(project_id) if not claim.deleted_at]
        unprocessed_p0 = [
            claim
            for claim in claims
            if claim.is_p0
            and claim.verification_status not in {"confirmed", "modified", "marked_unsure", "hidden", "deleted", "rejected"}
        ]
        if unprocessed_p0:
            raise ValueError("P0 claims must be processed before narrative generation")
        draft = generate_narrative_draft(claims)
        page = StoryPageRecord(id=uuid4(), project_id=project_id, draft=draft)
        self.story_pages[page.id] = page
        self._sync_story_chapters(project_id, draft)
        project = self.projects[project_id]
        project.story_page_id = page.id
        project.status = "story_generated"
        self.touch_project(project_id)
        return page

    def verify_project(self, project_id: UUID) -> list[dict]:
        project = self.projects[project_id]
        claims = [claim for claim in self.seed_claims_for_project(project_id) if not claim.deleted_at]
        page = self.story_pages.get(project.story_page_id) if project.story_page_id else None
        chapters = []
        if page and page.draft:
            chapters = [
                {"id": str(chapter.id), "body": chapter.body, "claim_ids": [str(cid) for cid in chapter.claim_ids]}
                for chapter in page.draft.chapters
            ]
        result = Verifier().verify(claims=claims, chapters=chapters, citations=[])
        issue_payloads = [issue.model_dump(mode="json") for issue in result.issues]
        for issue in issue_payloads:
            issue["project_id"] = str(project_id)
            self.verification_issues[UUID(issue["id"])] = issue | {"resolved_at": None}
        if result.passed:
            project.status = "verified"
        self.touch_project(project_id)
        return issue_payloads

    def request_second_consent(self, project_id: UUID) -> None:
        project = self.projects[project_id]
        unresolved_blocks = self._unresolved_block_count(project_id)
        if unresolved_blocks:
            raise ValueError("unresolved block issue")
        if project.status != "verified":
            raise ValueError("project must pass verifier before second consent")
        project.status = "elder_second_consent_pending"
        self.touch_project(project_id)

    def publish(self, project_id: UUID) -> tuple[bool, list[str]]:
        project = self.projects[project_id]
        claims = self.seed_claims_for_project(project_id)
        p0_total = sum(1 for claim in claims if claim.is_p0)
        p0_processed = sum(
            1
            for claim in claims
                if claim.is_p0
            and claim.verification_status in {"confirmed", "modified", "marked_unsure", "hidden", "deleted", "rejected"}
        )
        unresolved_blocks = self._unresolved_block_count(project_id)
        result = PublishGate().evaluate(
            PublishGateInput(
                project_status=ProjectStatus(project.status),
                p0_claims_total=p0_total,
                p0_claims_processed=p0_processed,
                unresolved_block_issues=unresolved_blocks,
                has_family_sharing_consent=project.has_family_sharing_consent,
                story_page_generated=project.story_page_id is not None,
                share_links_disabled=self._share_links_disabled(project.story_page_id),
            )
        )
        if result.allowed:
            project.status = "published"
            self.touch_project(project_id)
            if project.story_page_id:
                page = self.story_pages[project.story_page_id]
                page.enabled = True
                page.share_links_enabled = True
                for link in self.share_links.values():
                    if link.story_page_id == page.id and not link.revoked_at and not link.deleted_at:
                        link.enabled = True
        return result.allowed, result.reasons

    def _share_links_disabled(self, story_page_id: UUID | None) -> bool:
        if not story_page_id:
            return True
        return all(
            not link.enabled
            for link in self.share_links.values()
            if link.story_page_id == story_page_id and not link.deleted_at
        )

    def _unresolved_block_count(self, project_id: UUID) -> int:
        return sum(
            1
            for issue in self.verification_issues.values()
            if issue.get("project_id") == str(project_id)
            and issue["severity"] == "block"
            and not issue["resolved_at"]
        )

    def mark_verified_if_no_unresolved_blocks(self, project_id: UUID) -> None:
        project = self.projects.get(project_id)
        if project and project.story_page_id and self._unresolved_block_count(project_id) == 0:
            project.status = "verified"
            self.touch_project(project_id)

    def create_share_link(self, story_page_id: UUID, created_by_user_id: UUID | None, password: str | None = None) -> tuple[ShareLinkRecord, str]:
        token = _new_secret()
        page = self.story_pages[story_page_id]
        link = ShareLinkRecord(
            id=uuid4(),
            story_page_id=story_page_id,
            token_hash=_hash_secret(token),
            password_hash=_hash_secret(password) if password else None,
            created_by_user_id=created_by_user_id,
            enabled=page.enabled and page.share_links_enabled,
        )
        self.share_links[link.id] = link
        return link, token

    def active_share_link(self, story_page_id: UUID, token: str | None, password: str | None = None) -> ShareLinkRecord | None:
        if not token:
            return None
        token_hash = _hash_secret(token)
        for link in self.share_links.values():
            if link.story_page_id != story_page_id or not link.enabled or link.revoked_at or link.deleted_at:
                continue
            if link.token_hash != token_hash:
                continue
            if link.password_hash and link.password_hash != _hash_secret(password or ""):
                return None
            return link
        return None

    def revoke_share_link(self, share_link_id: UUID) -> ShareLinkRecord:
        link = self.share_links[share_link_id]
        link.enabled = False
        link.revoked_at = datetime.now(UTC)
        return link

    def reset_share_link(self, share_link_id: UUID) -> tuple[ShareLinkRecord, str]:
        link = self.share_links[share_link_id]
        token = _new_secret()
        page = self.story_pages[link.story_page_id]
        link.token_hash = _hash_secret(token)
        link.enabled = page.enabled and page.share_links_enabled
        link.revoked_at = None
        link.reset_at = datetime.now(UTC)
        return link, token

    def record_story_access(self, story_page_id: UUID, share_link_id: UUID) -> tuple[StoryAccessLogRecord, str]:
        media_access_token = _new_secret()
        access_log = StoryAccessLogRecord(
            id=uuid4(),
            story_page_id=story_page_id,
            share_link_id=share_link_id,
            media_access_token_hash=_hash_secret(media_access_token),
        )
        self.story_access_logs[access_log.id] = access_log
        return access_log, media_access_token

    def has_media_access(self, story_page_id: UUID, access_token: str | None) -> bool:
        if not access_token:
            return False
        token_hash = _hash_secret(access_token)
        return any(
            access.story_page_id == story_page_id and access.media_access_token_hash == token_hash
            for access in self.story_access_logs.values()
        )

    def create_family_comment(self, story_page_id: UUID, share_link_id: UUID, display_name: str, body: str) -> FamilyCommentRecord:
        comment = FamilyCommentRecord(
            id=uuid4(),
            story_page_id=story_page_id,
            share_link_id=share_link_id,
            display_name=display_name,
            body=body,
        )
        self.family_comments[comment.id] = comment
        return comment

    def record_pdf_export(self, project_id: UUID, story_page_id: UUID) -> PdfExportRecord:
        export_id = uuid4()
        pdf_export = PdfExportRecord(
            id=export_id,
            project_id=project_id,
            story_page_id=story_page_id,
            oss_key=f"pdf_exports/{project_id}/{export_id}.pdf",
        )
        self.pdf_exports[pdf_export.id] = pdf_export
        return pdf_export

    def withdraw_consent(self, project_id: UUID, consent_id: UUID) -> ConsentRecord | None:
        consent = self.consent_records.get(consent_id)
        if not consent or consent.project_id != project_id:
            return None
        now = datetime.now(UTC)
        consent.withdrawn_at = consent.withdrawn_at or now
        consent.evidence_oss_key = None
        consent.minimized_at = consent.minimized_at or now
        project = self.projects[project_id]
        if consent.consent_type == "interview_consent":
            project.has_interview_consent = False
        if consent.consent_type == "family_sharing":
            project.has_family_sharing_consent = False
            if project.story_page_id:
                page = self.story_pages[project.story_page_id]
                page.enabled = False
                page.share_links_enabled = False
                for link in self.share_links.values():
                    if link.story_page_id == page.id:
                        link.enabled = False
                        link.revoked_at = link.revoked_at or now
        project.updated_at = now
        return consent

    def request_deletion(self, project_id: UUID, requested_by_user_id: UUID | None = None) -> DeletionRequestRecord:
        project = self.projects[project_id]
        now = datetime.now(UTC)
        project.deleted_at = now
        project.purge_after_at = now + timedelta(days=7)
        project.status = "deletion_requested"
        project.updated_at = now
        project_session_ids = {session.id for session in self.sessions.values() if session.project_id == project_id}
        for key, chunk in self.audio_chunks.items():
            if key[0] in project_session_ids:
                chunk.deleted_at = chunk.deleted_at or now
                chunk.purge_after_at = chunk.purge_after_at or now + timedelta(days=7)
        for segment in self.transcript_segments.values():
            if segment.project_id == project_id:
                segment.deleted_at = segment.deleted_at or now
                segment.purge_after_at = segment.purge_after_at or now + timedelta(days=7)
        for photo in self.photos.values():
            if photo.project_id == project_id:
                photo.deleted_at = photo.deleted_at or now
                photo.purge_after_at = photo.purge_after_at or now + timedelta(days=7)
        for analysis in self.photo_analyses.values():
            if analysis.project_id == project_id:
                analysis.deleted_at = analysis.deleted_at or now
                analysis.purge_after_at = analysis.purge_after_at or now + timedelta(days=7)
        for claim_id in self.claims_by_project.get(project_id, []):
            claim = self.claims[claim_id]
            claim.deleted_at = claim.deleted_at or now
            claim.purge_after_at = claim.purge_after_at or now + timedelta(days=7)
        project_chapter_ids = {chapter.id for chapter in self.chapters.values() if chapter.project_id == project_id}
        for chapter in self.chapters.values():
            if chapter.project_id == project_id:
                chapter.deleted_at = chapter.deleted_at or now
                chapter.purge_after_at = chapter.purge_after_at or now + timedelta(days=7)
        for citation in self.citations.values():
            if citation.chapter_id in project_chapter_ids:
                citation.deleted_at = citation.deleted_at or now
                citation.purge_after_at = citation.purge_after_at or now + timedelta(days=7)
        for page in self.story_pages.values():
            if page.project_id != project_id:
                continue
            page.enabled = False
            page.share_links_enabled = False
            page.deleted_at = page.deleted_at or now
            page.purge_after_at = page.purge_after_at or now + timedelta(days=7)
            for link in self.share_links.values():
                if link.story_page_id != page.id:
                    continue
                link.enabled = False
                link.revoked_at = link.revoked_at or now
                link.deleted_at = link.deleted_at or now
                link.purge_after_at = link.purge_after_at or now + timedelta(days=7)
            for comment in self.family_comments.values():
                if comment.story_page_id == page.id:
                    comment.deleted_at = comment.deleted_at or now
                    comment.purge_after_at = comment.purge_after_at or now + timedelta(days=7)
        for pdf_export in self.pdf_exports.values():
            if pdf_export.project_id == project_id:
                pdf_export.deleted_at = pdf_export.deleted_at or now
                pdf_export.purge_after_at = pdf_export.purge_after_at or now + timedelta(days=7)
        for consent in self.consent_records.values():
            if consent.project_id == project_id:
                consent.evidence_oss_key = None
                consent.minimized_at = consent.minimized_at or now
        deletion = DeletionRequestRecord(
            id=uuid4(),
            project_id=project_id,
            requested_by_user_id=requested_by_user_id,
            requested_at=now,
            execute_after_at=project.purge_after_at,
        )
        project.deletion_request_id = deletion.id
        self.deletion_requests[deletion.id] = deletion
        return deletion

    def execute_due_deletion(self, deletion_request_id: UUID, at: datetime | None = None) -> dict:
        deletion = self.deletion_requests[deletion_request_id]
        at = at or datetime.now(UTC)
        if deletion.executed_at:
            return {
                "deletion_request_id": str(deletion.id),
                "status": "executed",
                "db_records_purged": 0,
                "oss_objects_purged": [],
            }
        if at < deletion.execute_after_at:
            return {
                "deletion_request_id": str(deletion.id),
                "status": "pending",
                "db_records_purged": 0,
                "oss_objects_purged": [],
            }

        project_id = deletion.project_id
        purged = 0
        oss_keys: list[str] = []
        project_session_ids = {session.id for session in self.sessions.values() if session.project_id == project_id}

        for key, chunk in list(self.audio_chunks.items()):
            if key[0] in project_session_ids and chunk.deleted_at:
                oss_keys.append(chunk.oss_key)
                del self.audio_chunks[key]
                purged += 1
        for segment_id, segment in list(self.transcript_segments.items()):
            if segment.project_id == project_id and segment.deleted_at:
                del self.transcript_segments[segment_id]
                purged += 1
        for photo_id, photo in list(self.photos.items()):
            if photo.project_id == project_id and photo.deleted_at:
                oss_keys.extend([photo.oss_key, photo.thumbnail_oss_key])
                del self.photos[photo_id]
                purged += 1
        for analysis_id, analysis in list(self.photo_analyses.items()):
            if analysis.project_id == project_id and analysis.deleted_at:
                del self.photo_analyses[analysis_id]
                purged += 1
        for claim_id in list(self.claims_by_project.get(project_id, [])):
            claim = self.claims.get(claim_id)
            if claim and claim.deleted_at:
                del self.claims[claim_id]
                purged += 1
        for evidence_id, evidence in list(self.claim_evidence.items()):
            if evidence["claim_id"] not in self.claims:
                del self.claim_evidence[evidence_id]
                purged += 1
        for correction_id, correction in list(self.claim_corrections.items()):
            if correction.claim_id not in self.claims:
                del self.claim_corrections[correction_id]
                purged += 1
        self.claims_by_project[project_id] = [
            claim_id for claim_id in self.claims_by_project.get(project_id, []) if claim_id in self.claims
        ]
        project_chapter_ids = {chapter.id for chapter in self.chapters.values() if chapter.project_id == project_id}
        for citation_id, citation in list(self.citations.items()):
            if citation.chapter_id in project_chapter_ids and citation.deleted_at:
                del self.citations[citation_id]
                purged += 1
        for chapter_id, chapter in list(self.chapters.items()):
            if chapter.project_id == project_id and chapter.deleted_at:
                del self.chapters[chapter_id]
                purged += 1
        for page_id, page in list(self.story_pages.items()):
            if page.project_id != project_id or not page.deleted_at:
                continue
            for link_id, link in list(self.share_links.items()):
                if link.story_page_id == page.id and link.deleted_at:
                    del self.share_links[link_id]
                    purged += 1
            for comment_id, comment in list(self.family_comments.items()):
                if comment.story_page_id == page.id and comment.deleted_at:
                    del self.family_comments[comment_id]
                    purged += 1
            del self.story_pages[page_id]
            purged += 1
        for export_id, pdf_export in list(self.pdf_exports.items()):
            if pdf_export.project_id == project_id and pdf_export.deleted_at:
                oss_keys.append(pdf_export.oss_key)
                del self.pdf_exports[export_id]
                purged += 1

        deletion.executed_at = at
        deletion.status = "executed"
        return {
            "deletion_request_id": str(deletion.id),
            "status": deletion.status,
            "db_records_purged": purged,
            "oss_objects_purged": oss_keys,
        }

    def _sync_story_chapters(self, project_id: UUID, draft: NarrativeDraft) -> None:
        previous_chapter_ids = {chapter.id for chapter in self.chapters.values() if chapter.project_id == project_id}
        current_chapter_ids = {chapter.id for chapter in draft.chapters}
        stale_chapter_ids = previous_chapter_ids - current_chapter_ids
        for citation_id, citation in list(self.citations.items()):
            if citation.chapter_id in stale_chapter_ids:
                del self.citations[citation_id]
        for chapter_id in stale_chapter_ids:
            del self.chapters[chapter_id]

        for chapter in draft.chapters:
            existing = self.chapters.get(chapter.id)
            self.chapters[chapter.id] = ChapterRecord(
                id=chapter.id,
                project_id=project_id,
                slug=chapter.slug,
                title=chapter.title,
                body_markdown=chapter.body,
                created_at=existing.created_at if existing else datetime.now(UTC),
                deleted_at=existing.deleted_at if existing else None,
                purge_after_at=existing.purge_after_at if existing else None,
                purged_at=existing.purged_at if existing else None,
            )
            current_citation_ids = set()
            for index, claim_id in enumerate(chapter.claim_ids, start=1):
                citation_id = _story_citation_id(chapter.id, claim_id)
                current_citation_ids.add(citation_id)
                existing_citation = self.citations.get(citation_id)
                self.citations[citation_id] = CitationRecord(
                    id=citation_id,
                    chapter_id=chapter.id,
                    claim_id=claim_id,
                    display_label=f"[{index}]",
                    created_at=existing_citation.created_at if existing_citation else datetime.now(UTC),
                    deleted_at=existing_citation.deleted_at if existing_citation else None,
                    purge_after_at=existing_citation.purge_after_at if existing_citation else None,
                    purged_at=existing_citation.purged_at if existing_citation else None,
                )
            for citation_id, citation in list(self.citations.items()):
                if citation.chapter_id == chapter.id and citation_id not in current_citation_ids:
                    del self.citations[citation_id]


def _new_secret() -> str:
    return secrets.token_urlsafe(32)


def _hash_secret(secret: str) -> str:
    return sha256(secret.encode("utf-8")).hexdigest()


def _story_citation_id(chapter_id: UUID, claim_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"changjuan:story-citation:{chapter_id}:{claim_id}")


def _pilot_whitelist_id(*, wx_openid: str | None = None, phone_hash: str | None = None) -> UUID:
    if wx_openid:
        return uuid5(NAMESPACE_URL, f"changjuan:pilot-whitelist:openid:{wx_openid}")
    if phone_hash:
        return uuid5(NAMESPACE_URL, f"changjuan:pilot-whitelist:phone:{phone_hash}")
    raise ValueError("pilot whitelist entry requires wx_openid or phone_hash")


def _has_photo_uncertainty(text: str) -> bool:
    return any(marker in text for marker in ("可能", "大约", "推测"))
