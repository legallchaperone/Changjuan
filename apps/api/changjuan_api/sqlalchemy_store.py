from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from changjuan_core.ai.contracts import CLAIM_EMBEDDING_DIMENSIONS, ClaimDraft
from changjuan_core.ai.narrative import NarrativeDraft
from changjuan_core.compliance.audit import AuditLog, AuditSink
from changjuan_core.providers.router import GenerationRun, TaskType
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.types import JSON, UserDefinedType, Uuid

from .store import (
    AdminSessionRecord,
    AdminUserRecord,
    AiCostRecord,
    AlertRecord,
    AudioChunkRecord,
    ChapterRecord,
    CitationRecord,
    ClaimCorrectionRecord,
    ConsentRecord,
    DeletionRequestRecord,
    FamilyCommentRecord,
    FeedbackRecord,
    InMemoryStore,
    InternalNoteRecord,
    ManualInterventionRecord,
    PdfExportRecord,
    PhotoAnalysisRecord,
    PhotoRecord,
    PilotWhitelistEntry,
    ProjectRecord,
    SessionRecord,
    ShareLinkRecord,
    StoryAccessLogRecord,
    StoryPageRecord,
    SupportTicketRecord,
    TranscriptSegmentRecord,
    UserRecord,
)

JSON_OBJECT = JSON().with_variant(postgresql.JSONB(), "postgresql")
THEME_LIST = JSON().with_variant(postgresql.ARRAY(String(64)), "postgresql")


class PgVector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        return f"vector({self.dimensions})"


CLAIM_EMBEDDING = PgVector(CLAIM_EMBEDDING_DIMENSIONS).with_variant(Text(), "sqlite")

PHASE1_METADATA = MetaData()

USERS = Table(
    "users",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("wx_openid", String(64), nullable=False, unique=True),
    Column("wx_unionid", String(64), nullable=True, unique=True),
    Column("phone_e164_enc", LargeBinary(), nullable=True),
    Column("phone_hash", String(64), nullable=True, index=True),
    Column("realname_enc", LargeBinary(), nullable=True),
    Column("nickname", String(64), nullable=True),
    Column("avatar_url", Text(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
)

ADMIN_USERS = Table(
    "admin_users",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("email", String(128), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("role", String(32), nullable=False),
    Column("enabled", Boolean(), nullable=False, default=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_login_at", DateTime(timezone=True), nullable=True),
)

ADMIN_SESSIONS = Table(
    "admin_sessions",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("admin_user_id", Uuid(as_uuid=True), ForeignKey("admin_users.id"), nullable=False),
    Column("token_hash", String(255), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

PILOT_WHITELIST = Table(
    "pilot_whitelist",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("phone_hash", String(64), nullable=True),
    Column("wx_openid", String(64), nullable=True),
    Column("source", String(64), nullable=True),
    Column("invited_by", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

PROJECTS = Table(
    "projects",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False),
    Column("title", String(128), nullable=False),
    Column("status", String(64), nullable=False, default="created"),
    Column("tier", String(32), nullable=False, default="standard"),
    Column("themes", THEME_LIST, nullable=False, default=list),
    Column("storyteller_profile", JSON_OBJECT, nullable=False, default=dict),
    Column("payment_status", String(32), nullable=False, default="not_required"),
    Column("payment_cents", Integer(), nullable=False, default=0),
    Column("payment_method", String(32), nullable=True),
    Column("payment_reference", String(128), nullable=True),
    Column("payment_marked_by_admin_id", Uuid(as_uuid=True), ForeignKey("admin_users.id"), nullable=True),
    Column("payment_at", DateTime(timezone=True), nullable=True),
    Column("ops_owner_id", Uuid(as_uuid=True), ForeignKey("admin_users.id"), nullable=True),
    Column("stuck_reason", Text(), nullable=True),
    Column("stuck_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("purge_after_at", DateTime(timezone=True), nullable=True),
    Column("purged_at", DateTime(timezone=True), nullable=True),
)

INTERVIEW_SESSIONS = Table(
    "interview_sessions",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("status", String(32), nullable=False, default="scheduled"),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("ended_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

PHOTOS = Table(
    "photos",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("oss_key", Text(), nullable=False),
    Column("thumbnail_oss_key", Text(), nullable=True),
    Column("caption", Text(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("purge_after_at", DateTime(timezone=True), nullable=True),
    Column("purged_at", DateTime(timezone=True), nullable=True),
)

AUDIO_RECORDINGS = Table(
    "audio_recordings",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("session_id", Uuid(as_uuid=True), ForeignKey("interview_sessions.id"), nullable=False),
    Column("sequence_number", Integer(), nullable=False),
    Column("oss_key", Text(), nullable=False),
    Column("duration_ms", Integer(), nullable=False),
    Column("duration_seconds", Integer(), nullable=False, default=0),
    Column("kms_key_id", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("purge_after_at", DateTime(timezone=True), nullable=True),
    Column("purged_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("session_id", "sequence_number", name="uq_audio_recordings_session_sequence"),
)

TRANSCRIPT_SEGMENTS = Table(
    "transcript_segments",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("audio_recording_id", Uuid(as_uuid=True), ForeignKey("audio_recordings.id"), nullable=False),
    Column("speaker", String(32), nullable=False),
    Column("text", Text(), nullable=False),
    Column("start_ms", Integer(), nullable=False),
    Column("end_ms", Integer(), nullable=False),
    Column("confidence", Numeric(4, 3), nullable=False),
    Column("low_confidence_review", Boolean(), nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("purge_after_at", DateTime(timezone=True), nullable=True),
    Column("purged_at", DateTime(timezone=True), nullable=True),
)

PHOTO_ANALYSES = Table(
    "photo_analyses",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("photo_id", Uuid(as_uuid=True), ForeignKey("photos.id"), nullable=False),
    Column("hypothesis_text", Text(), nullable=False),
    Column("confidence", Numeric(4, 3), nullable=False),
    Column("internal_only", Boolean(), nullable=False, default=True),
    Column("provider_run_id", Uuid(as_uuid=True), nullable=True),
    Column("converted_claim_id", Uuid(as_uuid=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("purge_after_at", DateTime(timezone=True), nullable=True),
    Column("purged_at", DateTime(timezone=True), nullable=True),
)

CLAIMS = Table(
    "claims",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("claim_text", Text(), nullable=False),
    Column("modified_text", Text(), nullable=True),
    Column("claim_type", String(64), nullable=False),
    Column("claim_priority", String(2), nullable=False),
    Column("entities", JSON_OBJECT, nullable=False, default=dict),
    Column("source_segment_ids", JSON_OBJECT, nullable=False, default=list),
    Column("confidence", Numeric(4, 3), nullable=False),
    Column("support_status", String(32), nullable=False),
    Column("verification_status", String(32), nullable=False, default="pending"),
    Column("sensitivity_level", String(32), nullable=False, default="normal"),
    Column("human_reviewed", Boolean(), nullable=False, default=False),
    Column("embedding", CLAIM_EMBEDDING, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("purge_after_at", DateTime(timezone=True), nullable=True),
    Column("purged_at", DateTime(timezone=True), nullable=True),
)

CLAIM_CORRECTIONS = Table(
    "claim_corrections",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("claim_id", Uuid(as_uuid=True), ForeignKey("claims.id"), nullable=False),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False),
    Column("action", String(32), nullable=False),
    Column("modified_text", Text(), nullable=True),
    Column("comment", Text(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

CLAIM_EVIDENCE = Table(
    "claim_evidence",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("claim_id", Uuid(as_uuid=True), ForeignKey("claims.id"), nullable=False),
    Column("evidence_type", String(32), nullable=False),
    Column("audio_recording_id", Uuid(as_uuid=True), ForeignKey("audio_recordings.id"), nullable=True),
    Column("transcript_segment_id", Uuid(as_uuid=True), ForeignKey("transcript_segments.id"), nullable=True),
    Column("photo_id", Uuid(as_uuid=True), ForeignKey("photos.id"), nullable=True),
    Column("user_input", Text(), nullable=True),
    Column("start_ms", Integer(), nullable=True),
    Column("end_ms", Integer(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("purge_after_at", DateTime(timezone=True), nullable=True),
    Column("purged_at", DateTime(timezone=True), nullable=True),
)

CHAPTERS = Table(
    "chapters",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("slug", String(64), nullable=False),
    Column("title", String(128), nullable=False),
    Column("body_markdown", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("purge_after_at", DateTime(timezone=True), nullable=True),
    Column("purged_at", DateTime(timezone=True), nullable=True),
)

CITATIONS = Table(
    "citations",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("chapter_id", Uuid(as_uuid=True), ForeignKey("chapters.id"), nullable=False),
    Column("claim_id", Uuid(as_uuid=True), ForeignKey("claims.id"), nullable=False),
    Column("display_label", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("purge_after_at", DateTime(timezone=True), nullable=True),
    Column("purged_at", DateTime(timezone=True), nullable=True),
)

STORY_PAGES = Table(
    "story_pages",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("enabled", Boolean(), nullable=False, default=False),
    Column("share_links_enabled", Boolean(), nullable=False, default=False),
    Column("password_hash", String(255), nullable=True),
    Column("draft", JSON_OBJECT, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("purge_after_at", DateTime(timezone=True), nullable=True),
    Column("purged_at", DateTime(timezone=True), nullable=True),
)

SHARE_LINKS = Table(
    "share_links",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("story_page_id", Uuid(as_uuid=True), ForeignKey("story_pages.id"), nullable=False),
    Column("token_hash", String(255), nullable=False),
    Column("password_hash", String(255), nullable=True),
    Column("created_by_user_id", Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True),
    Column("enabled", Boolean(), nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("reset_at", DateTime(timezone=True), nullable=True),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("purge_after_at", DateTime(timezone=True), nullable=True),
    Column("purged_at", DateTime(timezone=True), nullable=True),
)

STORY_ACCESS_LOGS = Table(
    "access_logs",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("story_page_id", Uuid(as_uuid=True), ForeignKey("story_pages.id"), nullable=False),
    Column("share_link_id", Uuid(as_uuid=True), ForeignKey("share_links.id"), nullable=True),
    Column("media_access_token_hash", String(255), nullable=True),
    Column("ip_hash", String(64), nullable=True),
    Column("user_agent", Text(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

FAMILY_COMMENTS = Table(
    "family_comments",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("story_page_id", Uuid(as_uuid=True), ForeignKey("story_pages.id"), nullable=False),
    Column("share_link_id", Uuid(as_uuid=True), ForeignKey("share_links.id"), nullable=False),
    Column("display_name", String(64), nullable=False),
    Column("body", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("purge_after_at", DateTime(timezone=True), nullable=True),
    Column("purged_at", DateTime(timezone=True), nullable=True),
)

PDF_EXPORTS = Table(
    "pdf_exports",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("story_page_id", Uuid(as_uuid=True), ForeignKey("story_pages.id"), nullable=False),
    Column("oss_key", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("purge_after_at", DateTime(timezone=True), nullable=True),
    Column("purged_at", DateTime(timezone=True), nullable=True),
)

VERIFICATION_ISSUES = Table(
    "verification_issues",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("gate", String(64), nullable=False),
    Column("severity", String(16), nullable=False),
    Column("message", Text(), nullable=False),
    Column("chapter_id", Uuid(as_uuid=True), nullable=True),
    Column("citation_id", Uuid(as_uuid=True), nullable=True),
    Column("claim_id", Uuid(as_uuid=True), nullable=True),
    Column("resolved_at", DateTime(timezone=True), nullable=True),
    Column("resolved_by_admin_id", Uuid(as_uuid=True), ForeignKey("admin_users.id"), nullable=True),
    Column("resolution_reason", Text(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

GENERATION_RUNS = Table(
    "generation_runs",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=True),
    Column("task_type", String(64), nullable=False),
    Column("provider_name", String(64), nullable=False),
    Column("prompt_version", String(64), nullable=False),
    Column("prompt_hash", String(64), nullable=False),
    Column("attempts", Integer(), nullable=False),
    Column("raw_input_oss_key", Text(), nullable=False),
    Column("raw_output_oss_key", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

AUDIT_LOGS = Table(
    "audit_logs",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("actor_id", Uuid(as_uuid=True), nullable=True),
    Column("action", String(128), nullable=False),
    Column("resource_type", String(64), nullable=False),
    Column("resource_id", Uuid(as_uuid=True), nullable=True),
    Column("reason", Text(), nullable=True),
    Column("metadata", JSON_OBJECT, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

ALERTS = Table(
    "alerts",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("path", Text(), nullable=False),
    Column("method", String(16), nullable=False),
    Column("error_type", String(128), nullable=False),
    Column("message", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

REVOKED_TOKENS = Table(
    "revoked_tokens",
    PHASE1_METADATA,
    Column("token_id", String(64), primary_key=True),
    Column("revoked_at", DateTime(timezone=True), nullable=False),
)

REVOKED_TOKEN_SESSIONS = Table(
    "revoked_token_sessions",
    PHASE1_METADATA,
    Column("session_id", String(64), primary_key=True),
    Column("revoked_at", DateTime(timezone=True), nullable=False),
)

RATE_LIMIT_HITS = Table(
    "rate_limit_hits",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("rate_limit_key", Text(), nullable=False),
    Column("hit_at", DateTime(timezone=True), nullable=False),
)

CONSENT_RECORDS = Table(
    "consent_records",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True),
    Column("consent_type", String(64), nullable=False),
    Column("method", String(32), nullable=False),
    Column("evidence_oss_key", Text(), nullable=True),
    Column("withdrawn_at", DateTime(timezone=True), nullable=True),
    Column("minimized_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

DELETION_REQUESTS = Table(
    "deletion_requests",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("requested_by_user_id", Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True),
    Column("requested_at", DateTime(timezone=True), nullable=False),
    Column("execute_after_at", DateTime(timezone=True), nullable=False),
    Column("executed_at", DateTime(timezone=True), nullable=True),
    Column("status", String(32), nullable=False),
)

INTERNAL_NOTES = Table(
    "internal_notes",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("admin_user_id", Uuid(as_uuid=True), ForeignKey("admin_users.id"), nullable=False),
    Column("note_type", String(32), nullable=False),
    Column("body", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

FEEDBACK = Table(
    "feedback",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False),
    Column("nps_score", Integer(), nullable=True),
    Column("recommend", Boolean(), nullable=True),
    Column("issue_type", String(64), nullable=True),
    Column("body", Text(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

SUPPORT_TICKETS = Table(
    "support_tickets",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("user_id", Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True),
    Column("admin_owner_id", Uuid(as_uuid=True), ForeignKey("admin_users.id"), nullable=True),
    Column("status", String(32), nullable=False),
    Column("priority", String(16), nullable=False),
    Column("category", String(64), nullable=False),
    Column("body", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

MANUAL_INTERVENTIONS = Table(
    "manual_interventions",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("admin_user_id", Uuid(as_uuid=True), ForeignKey("admin_users.id"), nullable=False),
    Column("category", String(64), nullable=False),
    Column("minutes", Integer(), nullable=False),
    Column("body", Text(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

AI_COSTS = Table(
    "ai_costs",
    PHASE1_METADATA,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("project_id", Uuid(as_uuid=True), ForeignKey("projects.id"), nullable=False),
    Column("admin_user_id", Uuid(as_uuid=True), ForeignKey("admin_users.id"), nullable=False),
    Column("task_type", String(64), nullable=False),
    Column("provider", String(64), nullable=False),
    Column("cost_cents", Integer(), nullable=False),
    Column("generation_run_id", Uuid(as_uuid=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class SqlAlchemyStore(InMemoryStore):
    def __init__(
        self,
        database_url: str,
        *,
        whitelist_openids: set[str] | None = None,
        create_schema: bool = False,
        hydrate: bool = True,
        engine: Engine | None = None,
        audio_kms_key_id: str = "kms:local-dev",
    ) -> None:
        super().__init__(whitelist_openids=whitelist_openids)
        default_admin = next(iter(self.admin_users.values()))
        configured_pilot_entries = list(self.pilot_whitelist.values())
        self.engine = engine or create_engine(database_url, future=True)
        self.audio_kms_key_id = audio_kms_key_id
        self.audit = _SqlAlchemyAuditSink(self)
        if create_schema:
            PHASE1_METADATA.create_all(self.engine)
        self._save_configured_pilot_whitelist(configured_pilot_entries)
        if hydrate:
            self.admin_users.clear()
            self.admin_sessions.clear()
            self.pilot_whitelist.clear()
            self.whitelist_openids.clear()
            self._hydrate_admin_users()
            if not self.admin_users:
                self.admin_id = default_admin.id
                self.admin_users[default_admin.id] = default_admin
                self._save_admin_user(default_admin)
            else:
                self.admin_id = next(iter(self.admin_users))
            self._hydrate_admin_sessions()
            self._hydrate_pilot_whitelist()
            self._hydrate_users()
            self._hydrate_projects()
            self._hydrate_sessions()
            self._hydrate_photos()
            self._hydrate_audio_chunks()
            self._hydrate_transcript_segments()
            self._hydrate_photo_analyses()
            self._hydrate_claims()
            self._hydrate_claim_evidence()
            self._hydrate_claim_corrections()
            self._hydrate_story_pages()
            self._hydrate_chapters()
            self._hydrate_citations()
            self._hydrate_share_links()
            self._hydrate_story_access_logs()
            self._hydrate_family_comments()
            self._hydrate_pdf_exports()
            self._hydrate_verification_issues()
            self._hydrate_generation_runs()
            self._hydrate_alerts()
            self._hydrate_revoked_tokens()
            self._hydrate_rate_limit_hits()
            self._hydrate_audit_logs()
            self._hydrate_consents()
            self._hydrate_deletion_requests()
            self._hydrate_feedback()
            self._hydrate_support_tickets()
            self._hydrate_internal_notes()
            self._hydrate_manual_interventions()
            self._hydrate_ai_costs()

    def upsert_user(
        self,
        wx_openid: str,
        nickname: str | None,
        wx_unionid: str | None = None,
        avatar_url: str | None = None,
        phone_e164: str | None = None,
        pii_encryptor=None,
    ) -> UserRecord:
        if wx_openid not in self.users_by_openid:
            self._hydrate_user_by_openid(wx_openid)
        user = super().upsert_user(
            wx_openid,
            nickname,
            wx_unionid=wx_unionid,
            avatar_url=avatar_url,
            phone_e164=phone_e164,
            pii_encryptor=pii_encryptor,
        )
        self._save_user(user)
        return user

    def create_project(self, user_id: UUID, payload: dict) -> ProjectRecord:
        project = super().create_project(user_id, payload)
        self._save_project(project)
        return project

    def touch_project(self, project_id: UUID, at: datetime | None = None) -> ProjectRecord:
        project = super().touch_project(project_id, at=at)
        self._save_project(project)
        return project

    def mark_payment(self, project_id: UUID, admin_id: UUID, payload: dict) -> ProjectRecord:
        project = super().mark_payment(project_id, admin_id, payload)
        self._save_project(project)
        return project

    def mark_project_stuck(self, project_id: UUID, owner_id: UUID, reason: str) -> ProjectRecord:
        project = super().mark_project_stuck(project_id, owner_id, reason)
        self._save_project(project)
        return project

    def create_session(self, project_id: UUID) -> SessionRecord:
        session = super().create_session(project_id)
        self._save_session(session)
        self._save_project(self.projects[project_id])
        return session

    def save_session(self, session: SessionRecord) -> SessionRecord:
        session = super().save_session(session)
        self._save_session(session)
        return session

    def record_photo(self, photo: PhotoRecord) -> PhotoRecord:
        photo = super().record_photo(photo)
        self._save_photo(photo)
        self._save_project(self.projects[photo.project_id])
        return photo

    def save_photo(self, photo: PhotoRecord) -> PhotoRecord:
        photo = super().save_photo(photo)
        self._save_photo(photo)
        return photo

    def record_audio_chunk(self, session_id: UUID, sequence_number: int, duration_ms: int, oss_key: str) -> AudioChunkRecord:
        chunk = super().record_audio_chunk(session_id, sequence_number, duration_ms, oss_key)
        self._save_audio_chunk(chunk)
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
        segment = super().record_transcript_segment(
            project_id,
            session_id,
            audio_chunk_sequence_number,
            speaker,
            text,
            confidence,
            duration_ms,
        )
        self._save_transcript_segment(segment)
        return segment

    def create_photo_analysis(self, photo_id: UUID, hypothesis_text: str, confidence: float) -> PhotoAnalysisRecord:
        analysis = super().create_photo_analysis(photo_id, hypothesis_text, confidence)
        self._save_photo_analysis(analysis)
        return analysis

    def convert_photo_analysis_to_candidate(self, analysis_id: UUID):
        claim = super().convert_photo_analysis_to_candidate(analysis_id)
        self._save_claim(self.photo_analyses[analysis_id].project_id, claim)
        self._save_photo_analysis(self.photo_analyses[analysis_id])
        return claim

    def seed_claims_for_project(self, project_id: UUID) -> list[ClaimDraft]:
        existing_ids = self.claims_by_project.get(project_id)
        claims = super().seed_claims_for_project(project_id)
        if not existing_ids:
            for claim in claims:
                self._save_claim(project_id, claim)
        return claims

    def save_claim(self, project_id: UUID, claim: ClaimDraft) -> ClaimDraft:
        claim = super().save_claim(project_id, claim)
        self._save_claim(project_id, claim)
        return claim

    def record_claim_correction(self, claim_id: UUID, user_id: UUID, payload: dict) -> ClaimCorrectionRecord:
        correction = super().record_claim_correction(claim_id, user_id, payload)
        self._save_claim_correction(correction)
        return correction

    def accept_rate_limited_request(self, key: str, limit: int = 60) -> bool:
        accepted = super().accept_rate_limited_request(key, limit=limit)
        self._replace_rate_limit_hits(key)
        return accepted

    def record_generation_run(self, run: GenerationRun) -> GenerationRun:
        run = super().record_generation_run(run)
        self._save_generation_run(run)
        return run

    def add_pilot_whitelist_entry(
        self,
        *,
        phone_hash: str | None = None,
        wx_openid: str | None = None,
        source: str | None = None,
        invited_by: str | None = None,
    ) -> PilotWhitelistEntry:
        entry = super().add_pilot_whitelist_entry(
            phone_hash=phone_hash,
            wx_openid=wx_openid,
            source=source,
            invited_by=invited_by,
        )
        self._save_pilot_whitelist_entry(entry)
        return entry

    def generate_story(self, project_id: UUID) -> StoryPageRecord:
        page = super().generate_story(project_id)
        self._save_story_page(page)
        self._replace_story_chapters(project_id)
        self._save_project(self.projects[project_id])
        return page

    def save_story_page(self, page: StoryPageRecord) -> StoryPageRecord:
        page = super().save_story_page(page)
        self._save_story_page(page)
        self._replace_story_chapters(page.project_id)
        return page

    def publish(self, project_id: UUID) -> tuple[bool, list[str]]:
        allowed, reasons = super().publish(project_id)
        self._save_project(self.projects[project_id])
        page_id = self.projects[project_id].story_page_id
        if page_id and page_id in self.story_pages:
            self._save_story_page(self.story_pages[page_id])
            for link in self.share_links.values():
                if link.story_page_id == page_id:
                    self._save_share_link(link)
        return allowed, reasons

    def create_share_link(self, story_page_id: UUID, created_by_user_id: UUID | None, password: str | None = None) -> tuple[ShareLinkRecord, str]:
        link, token = super().create_share_link(story_page_id, created_by_user_id, password=password)
        self._save_share_link(link)
        return link, token

    def revoke_share_link(self, share_link_id: UUID) -> ShareLinkRecord:
        link = super().revoke_share_link(share_link_id)
        self._save_share_link(link)
        return link

    def reset_share_link(self, share_link_id: UUID) -> tuple[ShareLinkRecord, str]:
        link, token = super().reset_share_link(share_link_id)
        self._save_share_link(link)
        return link, token

    def record_story_access(self, story_page_id: UUID, share_link_id: UUID) -> tuple[StoryAccessLogRecord, str]:
        access_log, media_access_token = super().record_story_access(story_page_id, share_link_id)
        self._save_story_access_log(access_log)
        return access_log, media_access_token

    def create_family_comment(self, story_page_id: UUID, share_link_id: UUID, display_name: str, body: str) -> FamilyCommentRecord:
        comment = super().create_family_comment(story_page_id, share_link_id, display_name, body)
        self._save_family_comment(comment)
        return comment

    def record_pdf_export(self, project_id: UUID, story_page_id: UUID) -> PdfExportRecord:
        pdf_export = super().record_pdf_export(project_id, story_page_id)
        self._save_pdf_export(pdf_export)
        return pdf_export

    def record_alert(self, path: str, method: str, error: Exception) -> AlertRecord:
        alert = super().record_alert(path, method, error)
        self._save_alert(alert)
        return alert

    def revoke_token_id(self, token_id: str | None) -> None:
        super().revoke_token_id(token_id)
        if token_id:
            self._save_revoked_token(token_id)

    def revoke_token_session(self, session_id: str | None) -> None:
        super().revoke_token_session(session_id)
        if session_id:
            self._save_revoked_token_session(session_id)

    def save_verification_issue(self, issue_id: UUID, issue: dict) -> dict:
        issue = super().save_verification_issue(issue_id, issue)
        self._save_verification_issue(issue_id, issue)
        return issue

    def verify_project(self, project_id: UUID) -> list[dict]:
        issues = super().verify_project(project_id)
        self._save_project(self.projects[project_id])
        for issue in issues:
            self._save_verification_issue(UUID(str(issue["id"])), self.verification_issues[UUID(str(issue["id"]))])
        return issues

    def record_admin_login(self, admin_user_id: UUID, access_token: str) -> AdminSessionRecord:
        session = super().record_admin_login(admin_user_id, access_token)
        self._save_admin_user(self.admin_users[admin_user_id])
        self._save_admin_session(session)
        return session

    def record_consent(self, consent: ConsentRecord) -> ConsentRecord:
        consent = super().record_consent(consent)
        self._save_consent(consent)
        self._save_project(self.projects[consent.project_id])
        return consent

    def withdraw_consent(self, project_id: UUID, consent_id: UUID) -> ConsentRecord | None:
        consent = super().withdraw_consent(project_id, consent_id)
        if consent:
            self._save_consent(consent)
            self._save_project(self.projects[project_id])
            page_id = self.projects[project_id].story_page_id
            if page_id and page_id in self.story_pages:
                self._save_story_page(self.story_pages[page_id])
                for link in self.share_links.values():
                    if link.story_page_id == page_id:
                        self._save_share_link(link)
        return consent

    def request_deletion(self, project_id: UUID, requested_by_user_id: UUID | None = None):
        deletion = super().request_deletion(project_id, requested_by_user_id=requested_by_user_id)
        self._save_project(self.projects[project_id])
        self._save_deletion_request(deletion)
        for consent in self.consent_records.values():
            if consent.project_id == project_id:
                self._save_consent(consent)
        for photo in self.photos.values():
            if photo.project_id == project_id:
                self._save_photo(photo)
        project_session_ids = {session.id for session in self.sessions.values() if session.project_id == project_id}
        for key, chunk in self.audio_chunks.items():
            if key[0] in project_session_ids:
                self._save_audio_chunk(chunk)
        for segment in self.transcript_segments.values():
            if segment.project_id == project_id:
                self._save_transcript_segment(segment)
        for analysis in self.photo_analyses.values():
            if analysis.project_id == project_id:
                self._save_photo_analysis(analysis)
        for claim_id in self.claims_by_project.get(project_id, []):
            if claim_id in self.claims:
                self._save_claim(project_id, self.claims[claim_id])
        for chapter in self.chapters.values():
            if chapter.project_id == project_id:
                self._save_chapter(chapter)
        project_chapter_ids = {chapter.id for chapter in self.chapters.values() if chapter.project_id == project_id}
        for citation in self.citations.values():
            if citation.chapter_id in project_chapter_ids:
                self._save_citation(citation)
        for page in self.story_pages.values():
            if page.project_id == project_id:
                self._save_story_page(page)
                for link in self.share_links.values():
                    if link.story_page_id == page.id:
                        self._save_share_link(link)
                for comment in self.family_comments.values():
                    if comment.story_page_id == page.id:
                        self._save_family_comment(comment)
        for pdf_export in self.pdf_exports.values():
            if pdf_export.project_id == project_id:
                self._save_pdf_export(pdf_export)
        return deletion

    def execute_due_deletion(self, deletion_request_id: UUID, at: datetime | None = None) -> dict:
        deletion = self.deletion_requests[deletion_request_id]
        project_id = deletion.project_id
        project_session_ids = {session.id for session in self.sessions.values() if session.project_id == project_id}
        audio_recording_ids = {
            _audio_recording_id(session_id, sequence_number)
            for (session_id, sequence_number), chunk in self.audio_chunks.items()
            if session_id in project_session_ids and chunk.deleted_at
        }
        transcript_segment_ids = {
            segment.id
            for segment in self.transcript_segments.values()
            if segment.project_id == project_id and segment.deleted_at
        }
        photo_ids = {photo.id for photo in self.photos.values() if photo.project_id == project_id and photo.deleted_at}
        photo_analysis_ids = {
            analysis.id
            for analysis in self.photo_analyses.values()
            if analysis.project_id == project_id and analysis.deleted_at
        }
        claim_ids = {
            claim_id
            for claim_id in self.claims_by_project.get(project_id, [])
            if (claim := self.claims.get(claim_id)) and claim.deleted_at
        }
        claim_correction_ids = {
            correction.id
            for correction in self.claim_corrections.values()
            if correction.claim_id in claim_ids
        }
        chapter_ids = {chapter.id for chapter in self.chapters.values() if chapter.project_id == project_id and chapter.deleted_at}
        citation_ids = {
            citation.id
            for citation in self.citations.values()
            if citation.chapter_id in chapter_ids and citation.deleted_at
        }
        story_page_ids = {page.id for page in self.story_pages.values() if page.project_id == project_id and page.deleted_at}
        share_link_ids = {
            link.id
            for link in self.share_links.values()
            if link.story_page_id in story_page_ids and link.deleted_at
        }
        comment_ids = {
            comment.id
            for comment in self.family_comments.values()
            if comment.story_page_id in story_page_ids and comment.deleted_at
        }
        pdf_export_ids = {
            pdf_export.id
            for pdf_export in self.pdf_exports.values()
            if pdf_export.project_id == project_id and pdf_export.deleted_at
        }

        result = super().execute_due_deletion(deletion_request_id, at=at)
        if result["status"] != "executed":
            return result

        with self.engine.begin() as connection:
            _delete_ids(connection, CITATIONS, CITATIONS.c.id, citation_ids)
            _delete_ids(connection, CLAIM_EVIDENCE, CLAIM_EVIDENCE.c.claim_id, claim_ids)
            _delete_ids(connection, CLAIM_CORRECTIONS, CLAIM_CORRECTIONS.c.id, claim_correction_ids)
            _delete_ids(connection, STORY_ACCESS_LOGS, STORY_ACCESS_LOGS.c.story_page_id, story_page_ids)
            _delete_ids(connection, FAMILY_COMMENTS, FAMILY_COMMENTS.c.id, comment_ids)
            _delete_ids(connection, SHARE_LINKS, SHARE_LINKS.c.id, share_link_ids)
            _delete_ids(connection, PDF_EXPORTS, PDF_EXPORTS.c.id, pdf_export_ids)
            _delete_ids(connection, STORY_PAGES, STORY_PAGES.c.id, story_page_ids)
            _delete_ids(connection, CHAPTERS, CHAPTERS.c.id, chapter_ids)
            _delete_ids(connection, PHOTO_ANALYSES, PHOTO_ANALYSES.c.id, photo_analysis_ids)
            _delete_ids(connection, PHOTOS, PHOTOS.c.id, photo_ids)
            _delete_ids(connection, TRANSCRIPT_SEGMENTS, TRANSCRIPT_SEGMENTS.c.id, transcript_segment_ids)
            _delete_ids(connection, AUDIO_RECORDINGS, AUDIO_RECORDINGS.c.id, audio_recording_ids)
            _delete_ids(connection, CLAIMS, CLAIMS.c.id, claim_ids)
            connection.execute(
                update(DELETION_REQUESTS)
                .where(DELETION_REQUESTS.c.id == deletion_request_id)
                .values(status=deletion.status, executed_at=deletion.executed_at)
            )
        return result

    def create_feedback(self, project_id: UUID, user_id: UUID, payload: dict) -> FeedbackRecord:
        feedback = super().create_feedback(project_id, user_id, payload)
        self._save_feedback(feedback)
        return feedback

    def create_support_ticket(
        self,
        project_id: UUID,
        user_id: UUID,
        payload: dict,
    ) -> SupportTicketRecord:
        ticket = super().create_support_ticket(project_id, user_id, payload)
        self._save_support_ticket(ticket)
        return ticket

    def save_support_ticket(self, ticket: SupportTicketRecord) -> SupportTicketRecord:
        ticket = super().save_support_ticket(ticket)
        self._save_support_ticket(ticket)
        return ticket

    def create_internal_note(self, project_id: UUID, admin_id: UUID, payload: dict) -> InternalNoteRecord:
        note = super().create_internal_note(project_id, admin_id, payload)
        self._save_internal_note(note)
        return note

    def record_manual_intervention(self, project_id: UUID, admin_id: UUID, payload: dict) -> ManualInterventionRecord:
        intervention = super().record_manual_intervention(project_id, admin_id, payload)
        self._save_manual_intervention(intervention)
        return intervention

    def record_ai_cost(self, project_id: UUID, admin_id: UUID, payload: dict) -> AiCostRecord:
        cost = super().record_ai_cost(project_id, admin_id, payload)
        self._save_ai_cost(cost)
        return cost

    def _hydrate_admin_users(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(ADMIN_USERS)).mappings().all()
        for row in rows:
            admin_user = _admin_user_from_row(row)
            self.admin_users[admin_user.id] = admin_user

    def _hydrate_admin_sessions(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(ADMIN_SESSIONS)).mappings().all()
        for row in rows:
            session = _admin_session_from_row(row)
            self.admin_sessions[session.id] = session

    def _hydrate_pilot_whitelist(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(PILOT_WHITELIST)).mappings().all()
        for row in rows:
            entry = _pilot_whitelist_entry_from_row(row)
            self.pilot_whitelist[entry.id] = entry
            if entry.wx_openid:
                self.whitelist_openids.add(entry.wx_openid)

    def _hydrate_users(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(USERS)).mappings().all()
        for row in rows:
            self._remember_user(_user_from_row(row))

    def _hydrate_user_by_openid(self, wx_openid: str) -> UserRecord | None:
        with self.engine.connect() as connection:
            row = connection.execute(select(USERS).where(USERS.c.wx_openid == wx_openid)).mappings().first()
        if not row:
            return None
        user = _user_from_row(row)
        self._remember_user(user)
        return user

    def _hydrate_projects(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(PROJECTS)).mappings().all()
        for row in rows:
            self.projects[row["id"]] = _project_from_row(row)

    def _hydrate_sessions(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(INTERVIEW_SESSIONS)).mappings().all()
        for row in rows:
            session = _session_from_row(row)
            self.sessions[session.id] = session

    def _hydrate_photos(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(PHOTOS)).mappings().all()
        for row in rows:
            photo = _photo_from_row(row)
            self.photos[photo.id] = photo

    def _hydrate_audio_chunks(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(AUDIO_RECORDINGS)).mappings().all()
        for row in rows:
            chunk = _audio_chunk_from_row(row)
            self.audio_chunks[(chunk.session_id, chunk.sequence_number)] = chunk

    def _hydrate_transcript_segments(self) -> None:
        statement = (
            select(
                TRANSCRIPT_SEGMENTS.c.id,
                TRANSCRIPT_SEGMENTS.c.project_id,
                TRANSCRIPT_SEGMENTS.c.speaker,
                TRANSCRIPT_SEGMENTS.c.text,
                TRANSCRIPT_SEGMENTS.c.start_ms,
                TRANSCRIPT_SEGMENTS.c.end_ms,
                TRANSCRIPT_SEGMENTS.c.confidence,
                TRANSCRIPT_SEGMENTS.c.low_confidence_review,
                TRANSCRIPT_SEGMENTS.c.created_at,
                TRANSCRIPT_SEGMENTS.c.deleted_at,
                TRANSCRIPT_SEGMENTS.c.purge_after_at,
                AUDIO_RECORDINGS.c.session_id.label("session_id"),
                AUDIO_RECORDINGS.c.sequence_number.label("audio_chunk_sequence_number"),
            )
            .select_from(TRANSCRIPT_SEGMENTS.join(AUDIO_RECORDINGS, TRANSCRIPT_SEGMENTS.c.audio_recording_id == AUDIO_RECORDINGS.c.id))
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        for row in rows:
            segment = _transcript_segment_from_row(row)
            self.transcript_segments[segment.id] = segment

    def _hydrate_photo_analyses(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(PHOTO_ANALYSES)).mappings().all()
        for row in rows:
            analysis = _photo_analysis_from_row(row)
            self.photo_analyses[analysis.id] = analysis

    def _hydrate_claims(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(CLAIMS)).mappings().all()
        for row in rows:
            project_id, claim = _claim_from_row(row)
            self.claims[claim.id] = claim
            self.claims_by_project.setdefault(project_id, []).append(claim.id)

    def _hydrate_claim_evidence(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(CLAIM_EVIDENCE)).mappings().all()
        for row in rows:
            evidence_id, evidence = _claim_evidence_from_row(row)
            self.claim_evidence[evidence_id] = evidence

    def _hydrate_claim_corrections(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(CLAIM_CORRECTIONS)).mappings().all()
        for row in rows:
            correction = _claim_correction_from_row(row)
            self.claim_corrections[correction.id] = correction

    def _hydrate_story_pages(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(STORY_PAGES)).mappings().all()
        for row in rows:
            page = _story_page_from_row(row)
            self.story_pages[page.id] = page
            if page.project_id in self.projects:
                self.projects[page.project_id].story_page_id = page.id

    def _hydrate_chapters(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(CHAPTERS)).mappings().all()
        for row in rows:
            chapter = _chapter_from_row(row)
            self.chapters[chapter.id] = chapter

    def _hydrate_citations(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(CITATIONS)).mappings().all()
        for row in rows:
            citation = _citation_from_row(row)
            self.citations[citation.id] = citation

    def _hydrate_share_links(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(SHARE_LINKS)).mappings().all()
        for row in rows:
            link = _share_link_from_row(row)
            self.share_links[link.id] = link

    def _hydrate_story_access_logs(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(STORY_ACCESS_LOGS)).mappings().all()
        for row in rows:
            access_log = _story_access_log_from_row(row)
            self.story_access_logs[access_log.id] = access_log

    def _hydrate_family_comments(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(FAMILY_COMMENTS)).mappings().all()
        for row in rows:
            comment = _family_comment_from_row(row)
            self.family_comments[comment.id] = comment

    def _hydrate_pdf_exports(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(PDF_EXPORTS)).mappings().all()
        for row in rows:
            pdf_export = _pdf_export_from_row(row)
            self.pdf_exports[pdf_export.id] = pdf_export

    def _hydrate_verification_issues(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(VERIFICATION_ISSUES)).mappings().all()
        for row in rows:
            issue_id, issue = _verification_issue_from_row(row)
            self.verification_issues[issue_id] = issue

    def _hydrate_generation_runs(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(GENERATION_RUNS)).mappings().all()
        for row in rows:
            run = _generation_run_from_row(row)
            self.generation_runs[run.id] = run

    def _hydrate_alerts(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(ALERTS)).mappings().all()
        for row in rows:
            alert = _alert_from_row(row)
            self.alerts[alert.id] = alert

    def _hydrate_revoked_tokens(self) -> None:
        with self.engine.connect() as connection:
            token_rows = connection.execute(select(REVOKED_TOKENS.c.token_id)).all()
            session_rows = connection.execute(select(REVOKED_TOKEN_SESSIONS.c.session_id)).all()
        self.revoked_token_ids.update(row[0] for row in token_rows)
        self.revoked_token_session_ids.update(row[0] for row in session_rows)

    def _hydrate_rate_limit_hits(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(RATE_LIMIT_HITS)).mappings().all()
        for row in rows:
            self.rate_limit_hits.setdefault(row["rate_limit_key"], []).append(_ensure_utc(row["hit_at"]))

    def _hydrate_audit_logs(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(AUDIT_LOGS)).mappings().all()
        for row in rows:
            self.audit.logs.append(_audit_log_from_row(row))

    def _hydrate_consents(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(CONSENT_RECORDS)).mappings().all()
        for row in rows:
            consent = _consent_from_row(row)
            self.consent_records[consent.id] = consent
            self._apply_consent_flags(consent)

    def _hydrate_deletion_requests(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(DELETION_REQUESTS)).mappings().all()
        for row in rows:
            deletion = _deletion_request_from_row(row)
            self.deletion_requests[deletion.id] = deletion
            if deletion.project_id in self.projects:
                self.projects[deletion.project_id].deletion_request_id = deletion.id

    def _hydrate_feedback(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(FEEDBACK)).mappings().all()
        for row in rows:
            feedback = _feedback_from_row(row)
            self.feedback[feedback.id] = feedback

    def _hydrate_support_tickets(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(SUPPORT_TICKETS)).mappings().all()
        for row in rows:
            ticket = _support_ticket_from_row(row)
            self.support_tickets[ticket.id] = ticket

    def _hydrate_internal_notes(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(INTERNAL_NOTES)).mappings().all()
        for row in rows:
            note = _internal_note_from_row(row)
            self.internal_notes[note.id] = note

    def _hydrate_manual_interventions(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(MANUAL_INTERVENTIONS)).mappings().all()
        for row in rows:
            intervention = _manual_intervention_from_row(row)
            self.manual_interventions[intervention.id] = intervention

    def _hydrate_ai_costs(self) -> None:
        with self.engine.connect() as connection:
            rows = connection.execute(select(AI_COSTS)).mappings().all()
        for row in rows:
            cost = _ai_cost_from_row(row)
            self.ai_costs[cost.id] = cost

    def _save_user(self, user: UserRecord) -> None:
        values = _user_values(user)
        with self.engine.begin() as connection:
            exists = connection.execute(select(USERS.c.id).where(USERS.c.id == user.id)).first()
            if exists:
                connection.execute(update(USERS).where(USERS.c.id == user.id).values(**values))
            else:
                connection.execute(insert(USERS).values(**values))

    def _save_project(self, project: ProjectRecord) -> None:
        values = _project_values(project)
        with self.engine.begin() as connection:
            exists = connection.execute(select(PROJECTS.c.id).where(PROJECTS.c.id == project.id)).first()
            if exists:
                connection.execute(update(PROJECTS).where(PROJECTS.c.id == project.id).values(**values))
            else:
                connection.execute(insert(PROJECTS).values(**values))

    def _save_admin_user(self, admin_user: AdminUserRecord) -> None:
        values = _admin_user_values(admin_user)
        with self.engine.begin() as connection:
            exists = connection.execute(select(ADMIN_USERS.c.id).where(ADMIN_USERS.c.id == admin_user.id)).first()
            if exists:
                connection.execute(update(ADMIN_USERS).where(ADMIN_USERS.c.id == admin_user.id).values(**values))
            else:
                connection.execute(insert(ADMIN_USERS).values(**values))

    def _save_admin_session(self, session: AdminSessionRecord) -> None:
        values = _admin_session_values(session)
        with self.engine.begin() as connection:
            exists = connection.execute(select(ADMIN_SESSIONS.c.id).where(ADMIN_SESSIONS.c.id == session.id)).first()
            if exists:
                connection.execute(update(ADMIN_SESSIONS).where(ADMIN_SESSIONS.c.id == session.id).values(**values))
            else:
                connection.execute(insert(ADMIN_SESSIONS).values(**values))

    def _save_configured_pilot_whitelist(self, entries: list[PilotWhitelistEntry]) -> None:
        for entry in entries:
            self._save_pilot_whitelist_entry(entry)

    def _save_pilot_whitelist_entry(self, entry: PilotWhitelistEntry) -> None:
        values = _pilot_whitelist_entry_values(entry)
        with self.engine.begin() as connection:
            exists = connection.execute(select(PILOT_WHITELIST.c.id).where(PILOT_WHITELIST.c.id == entry.id)).first()
            if exists:
                connection.execute(update(PILOT_WHITELIST).where(PILOT_WHITELIST.c.id == entry.id).values(**values))
            else:
                connection.execute(insert(PILOT_WHITELIST).values(**values))

    def _save_session(self, session: SessionRecord) -> None:
        values = _session_values(session)
        with self.engine.begin() as connection:
            exists = connection.execute(select(INTERVIEW_SESSIONS.c.id).where(INTERVIEW_SESSIONS.c.id == session.id)).first()
            if exists:
                connection.execute(update(INTERVIEW_SESSIONS).where(INTERVIEW_SESSIONS.c.id == session.id).values(**values))
            else:
                connection.execute(insert(INTERVIEW_SESSIONS).values(**values))

    def _save_photo(self, photo: PhotoRecord) -> None:
        values = _photo_values(photo)
        with self.engine.begin() as connection:
            exists = connection.execute(select(PHOTOS.c.id).where(PHOTOS.c.id == photo.id)).first()
            if exists:
                connection.execute(update(PHOTOS).where(PHOTOS.c.id == photo.id).values(**values))
            else:
                connection.execute(insert(PHOTOS).values(**values))

    def _save_audio_chunk(self, chunk: AudioChunkRecord) -> None:
        values = _audio_chunk_values(chunk, self.sessions[chunk.session_id].project_id, self.audio_kms_key_id)
        recording_id = values["id"]
        with self.engine.begin() as connection:
            exists = connection.execute(select(AUDIO_RECORDINGS.c.id).where(AUDIO_RECORDINGS.c.id == recording_id)).first()
            if exists:
                connection.execute(update(AUDIO_RECORDINGS).where(AUDIO_RECORDINGS.c.id == recording_id).values(**values))
            else:
                connection.execute(insert(AUDIO_RECORDINGS).values(**values))

    def _save_transcript_segment(self, segment: TranscriptSegmentRecord) -> None:
        values = _transcript_segment_values(segment)
        with self.engine.begin() as connection:
            exists = connection.execute(select(TRANSCRIPT_SEGMENTS.c.id).where(TRANSCRIPT_SEGMENTS.c.id == segment.id)).first()
            if exists:
                connection.execute(update(TRANSCRIPT_SEGMENTS).where(TRANSCRIPT_SEGMENTS.c.id == segment.id).values(**values))
            else:
                connection.execute(insert(TRANSCRIPT_SEGMENTS).values(**values))

    def _save_photo_analysis(self, analysis: PhotoAnalysisRecord) -> None:
        values = _photo_analysis_values(analysis)
        with self.engine.begin() as connection:
            exists = connection.execute(select(PHOTO_ANALYSES.c.id).where(PHOTO_ANALYSES.c.id == analysis.id)).first()
            if exists:
                connection.execute(update(PHOTO_ANALYSES).where(PHOTO_ANALYSES.c.id == analysis.id).values(**values))
            else:
                connection.execute(insert(PHOTO_ANALYSES).values(**values))

    def _save_claim(self, project_id: UUID, claim: ClaimDraft) -> None:
        values = _claim_values(project_id, claim)
        with self.engine.begin() as connection:
            exists = connection.execute(select(CLAIMS.c.id).where(CLAIMS.c.id == claim.id)).first()
            if exists:
                connection.execute(update(CLAIMS).where(CLAIMS.c.id == claim.id).values(**values))
            else:
                connection.execute(insert(CLAIMS).values(**values))
        self._sync_claim_evidence(project_id, claim)

    def _sync_claim_evidence(self, project_id: UUID, claim: ClaimDraft) -> None:
        evidence_rows = _claim_evidence_values(project_id, claim, self.transcript_segments)
        for evidence_id in [evidence_id for evidence_id, item in self.claim_evidence.items() if item["claim_id"] == claim.id]:
            del self.claim_evidence[evidence_id]
        self.claim_evidence.update({row["id"]: _claim_evidence_dict(row) for row in evidence_rows})
        with self.engine.begin() as connection:
            connection.execute(delete(CLAIM_EVIDENCE).where(CLAIM_EVIDENCE.c.claim_id == claim.id))
            if evidence_rows:
                connection.execute(insert(CLAIM_EVIDENCE), evidence_rows)

    def _save_claim_correction(self, correction: ClaimCorrectionRecord) -> None:
        values = _claim_correction_values(correction)
        with self.engine.begin() as connection:
            exists = connection.execute(select(CLAIM_CORRECTIONS.c.id).where(CLAIM_CORRECTIONS.c.id == correction.id)).first()
            if exists:
                connection.execute(update(CLAIM_CORRECTIONS).where(CLAIM_CORRECTIONS.c.id == correction.id).values(**values))
            else:
                connection.execute(insert(CLAIM_CORRECTIONS).values(**values))

    def _replace_story_chapters(self, project_id: UUID) -> None:
        project_chapter_ids = {chapter.id for chapter in self.chapters.values() if chapter.project_id == project_id}
        chapter_rows = [_chapter_values(chapter) for chapter in self.chapters.values() if chapter.project_id == project_id]
        citation_rows = [
            _citation_values(citation)
            for citation in self.citations.values()
            if citation.chapter_id in project_chapter_ids
        ]
        with self.engine.begin() as connection:
            existing_chapter_ids = [
                row[0] for row in connection.execute(select(CHAPTERS.c.id).where(CHAPTERS.c.project_id == project_id)).all()
            ]
            if existing_chapter_ids:
                connection.execute(delete(CITATIONS).where(CITATIONS.c.chapter_id.in_(existing_chapter_ids)))
                connection.execute(delete(CHAPTERS).where(CHAPTERS.c.id.in_(existing_chapter_ids)))
            if chapter_rows:
                connection.execute(insert(CHAPTERS), chapter_rows)
            if citation_rows:
                connection.execute(insert(CITATIONS), citation_rows)

    def _save_chapter(self, chapter: ChapterRecord) -> None:
        values = _chapter_values(chapter)
        with self.engine.begin() as connection:
            exists = connection.execute(select(CHAPTERS.c.id).where(CHAPTERS.c.id == chapter.id)).first()
            if exists:
                connection.execute(update(CHAPTERS).where(CHAPTERS.c.id == chapter.id).values(**values))
            else:
                connection.execute(insert(CHAPTERS).values(**values))

    def _save_citation(self, citation: CitationRecord) -> None:
        values = _citation_values(citation)
        with self.engine.begin() as connection:
            exists = connection.execute(select(CITATIONS.c.id).where(CITATIONS.c.id == citation.id)).first()
            if exists:
                connection.execute(update(CITATIONS).where(CITATIONS.c.id == citation.id).values(**values))
            else:
                connection.execute(insert(CITATIONS).values(**values))

    def _save_story_page(self, page: StoryPageRecord) -> None:
        values = _story_page_values(page)
        with self.engine.begin() as connection:
            exists = connection.execute(select(STORY_PAGES.c.id).where(STORY_PAGES.c.id == page.id)).first()
            if exists:
                connection.execute(update(STORY_PAGES).where(STORY_PAGES.c.id == page.id).values(**values))
            else:
                connection.execute(insert(STORY_PAGES).values(**values))

    def _save_share_link(self, link: ShareLinkRecord) -> None:
        values = _share_link_values(link)
        with self.engine.begin() as connection:
            exists = connection.execute(select(SHARE_LINKS.c.id).where(SHARE_LINKS.c.id == link.id)).first()
            if exists:
                connection.execute(update(SHARE_LINKS).where(SHARE_LINKS.c.id == link.id).values(**values))
            else:
                connection.execute(insert(SHARE_LINKS).values(**values))

    def _save_story_access_log(self, access_log: StoryAccessLogRecord) -> None:
        values = _story_access_log_values(access_log)
        with self.engine.begin() as connection:
            exists = connection.execute(select(STORY_ACCESS_LOGS.c.id).where(STORY_ACCESS_LOGS.c.id == access_log.id)).first()
            if exists:
                connection.execute(update(STORY_ACCESS_LOGS).where(STORY_ACCESS_LOGS.c.id == access_log.id).values(**values))
            else:
                connection.execute(insert(STORY_ACCESS_LOGS).values(**values))

    def _save_family_comment(self, comment: FamilyCommentRecord) -> None:
        values = _family_comment_values(comment)
        with self.engine.begin() as connection:
            exists = connection.execute(select(FAMILY_COMMENTS.c.id).where(FAMILY_COMMENTS.c.id == comment.id)).first()
            if exists:
                connection.execute(update(FAMILY_COMMENTS).where(FAMILY_COMMENTS.c.id == comment.id).values(**values))
            else:
                connection.execute(insert(FAMILY_COMMENTS).values(**values))

    def _save_pdf_export(self, pdf_export: PdfExportRecord) -> None:
        values = _pdf_export_values(pdf_export)
        with self.engine.begin() as connection:
            exists = connection.execute(select(PDF_EXPORTS.c.id).where(PDF_EXPORTS.c.id == pdf_export.id)).first()
            if exists:
                connection.execute(update(PDF_EXPORTS).where(PDF_EXPORTS.c.id == pdf_export.id).values(**values))
            else:
                connection.execute(insert(PDF_EXPORTS).values(**values))

    def _save_verification_issue(self, issue_id: UUID, issue: dict) -> None:
        values = _verification_issue_values(issue_id, issue)
        with self.engine.begin() as connection:
            exists = connection.execute(select(VERIFICATION_ISSUES.c.id).where(VERIFICATION_ISSUES.c.id == issue_id)).first()
            if exists:
                connection.execute(update(VERIFICATION_ISSUES).where(VERIFICATION_ISSUES.c.id == issue_id).values(**values))
            else:
                connection.execute(insert(VERIFICATION_ISSUES).values(**values))

    def _save_generation_run(self, run: GenerationRun) -> None:
        values = _generation_run_values(run)
        with self.engine.begin() as connection:
            exists = connection.execute(select(GENERATION_RUNS.c.id).where(GENERATION_RUNS.c.id == run.id)).first()
            if exists:
                connection.execute(update(GENERATION_RUNS).where(GENERATION_RUNS.c.id == run.id).values(**values))
            else:
                connection.execute(insert(GENERATION_RUNS).values(**values))

    def _save_alert(self, alert: AlertRecord) -> None:
        values = _alert_values(alert)
        with self.engine.begin() as connection:
            exists = connection.execute(select(ALERTS.c.id).where(ALERTS.c.id == alert.id)).first()
            if exists:
                connection.execute(update(ALERTS).where(ALERTS.c.id == alert.id).values(**values))
            else:
                connection.execute(insert(ALERTS).values(**values))

    def _save_audit_log(self, log: AuditLog) -> None:
        values = _audit_log_values(log)
        with self.engine.begin() as connection:
            exists = connection.execute(select(AUDIT_LOGS.c.id).where(AUDIT_LOGS.c.id == log.id)).first()
            if exists:
                connection.execute(update(AUDIT_LOGS).where(AUDIT_LOGS.c.id == log.id).values(**values))
            else:
                connection.execute(insert(AUDIT_LOGS).values(**values))

    def _save_revoked_token(self, token_id: str) -> None:
        values = {"token_id": token_id, "revoked_at": datetime.now(UTC)}
        with self.engine.begin() as connection:
            exists = connection.execute(select(REVOKED_TOKENS.c.token_id).where(REVOKED_TOKENS.c.token_id == token_id)).first()
            if not exists:
                connection.execute(insert(REVOKED_TOKENS).values(**values))

    def _save_revoked_token_session(self, session_id: str) -> None:
        values = {"session_id": session_id, "revoked_at": datetime.now(UTC)}
        with self.engine.begin() as connection:
            exists = connection.execute(
                select(REVOKED_TOKEN_SESSIONS.c.session_id).where(REVOKED_TOKEN_SESSIONS.c.session_id == session_id)
            ).first()
            if not exists:
                connection.execute(insert(REVOKED_TOKEN_SESSIONS).values(**values))

    def _replace_rate_limit_hits(self, key: str) -> None:
        rows = [
            {
                "id": _rate_limit_hit_id(key, hit_at),
                "rate_limit_key": key,
                "hit_at": hit_at,
            }
            for hit_at in self.rate_limit_hits.get(key, [])
        ]
        with self.engine.begin() as connection:
            connection.execute(delete(RATE_LIMIT_HITS).where(RATE_LIMIT_HITS.c.rate_limit_key == key))
            if rows:
                connection.execute(insert(RATE_LIMIT_HITS), rows)

    def _save_consent(self, consent: ConsentRecord) -> None:
        values = _consent_values(consent)
        with self.engine.begin() as connection:
            exists = connection.execute(select(CONSENT_RECORDS.c.id).where(CONSENT_RECORDS.c.id == consent.id)).first()
            if exists:
                connection.execute(update(CONSENT_RECORDS).where(CONSENT_RECORDS.c.id == consent.id).values(**values))
            else:
                connection.execute(insert(CONSENT_RECORDS).values(**values))

    def _save_deletion_request(self, deletion: DeletionRequestRecord) -> None:
        values = _deletion_request_values(deletion)
        with self.engine.begin() as connection:
            exists = connection.execute(select(DELETION_REQUESTS.c.id).where(DELETION_REQUESTS.c.id == deletion.id)).first()
            if exists:
                connection.execute(update(DELETION_REQUESTS).where(DELETION_REQUESTS.c.id == deletion.id).values(**values))
            else:
                connection.execute(insert(DELETION_REQUESTS).values(**values))

    def _save_feedback(self, feedback: FeedbackRecord) -> None:
        values = _feedback_values(feedback)
        with self.engine.begin() as connection:
            exists = connection.execute(select(FEEDBACK.c.id).where(FEEDBACK.c.id == feedback.id)).first()
            if exists:
                connection.execute(update(FEEDBACK).where(FEEDBACK.c.id == feedback.id).values(**values))
            else:
                connection.execute(insert(FEEDBACK).values(**values))

    def _save_support_ticket(self, ticket: SupportTicketRecord) -> None:
        values = _support_ticket_values(ticket)
        with self.engine.begin() as connection:
            exists = connection.execute(select(SUPPORT_TICKETS.c.id).where(SUPPORT_TICKETS.c.id == ticket.id)).first()
            if exists:
                connection.execute(update(SUPPORT_TICKETS).where(SUPPORT_TICKETS.c.id == ticket.id).values(**values))
            else:
                connection.execute(insert(SUPPORT_TICKETS).values(**values))

    def _save_internal_note(self, note: InternalNoteRecord) -> None:
        values = _internal_note_values(note)
        with self.engine.begin() as connection:
            exists = connection.execute(select(INTERNAL_NOTES.c.id).where(INTERNAL_NOTES.c.id == note.id)).first()
            if exists:
                connection.execute(update(INTERNAL_NOTES).where(INTERNAL_NOTES.c.id == note.id).values(**values))
            else:
                connection.execute(insert(INTERNAL_NOTES).values(**values))

    def _save_manual_intervention(self, intervention: ManualInterventionRecord) -> None:
        values = _manual_intervention_values(intervention)
        with self.engine.begin() as connection:
            exists = connection.execute(select(MANUAL_INTERVENTIONS.c.id).where(MANUAL_INTERVENTIONS.c.id == intervention.id)).first()
            if exists:
                connection.execute(update(MANUAL_INTERVENTIONS).where(MANUAL_INTERVENTIONS.c.id == intervention.id).values(**values))
            else:
                connection.execute(insert(MANUAL_INTERVENTIONS).values(**values))

    def _save_ai_cost(self, cost: AiCostRecord) -> None:
        values = _ai_cost_values(cost)
        with self.engine.begin() as connection:
            exists = connection.execute(select(AI_COSTS.c.id).where(AI_COSTS.c.id == cost.id)).first()
            if exists:
                connection.execute(update(AI_COSTS).where(AI_COSTS.c.id == cost.id).values(**values))
            else:
                connection.execute(insert(AI_COSTS).values(**values))

    def _remember_user(self, user: UserRecord) -> None:
        self.users[user.id] = user
        self.users_by_openid[user.wx_openid] = user.id

    def _apply_consent_flags(self, consent: ConsentRecord) -> None:
        if consent.withdrawn_at or consent.project_id not in self.projects:
            return
        project = self.projects[consent.project_id]
        if consent.consent_type == "interview_consent":
            project.has_interview_consent = True
        if consent.consent_type == "family_sharing":
            project.has_family_sharing_consent = True


def _user_from_row(row) -> UserRecord:
    return UserRecord(
        id=row["id"],
        wx_openid=row["wx_openid"],
        wx_unionid=row["wx_unionid"],
        nickname=row["nickname"],
        avatar_url=row["avatar_url"],
        phone_e164_enc=_decode_bytes(row["phone_e164_enc"]),
        phone_hash=row["phone_hash"],
        created_at=_ensure_utc(row["created_at"]),
        updated_at=_ensure_utc(row["updated_at"]),
        deleted_at=_ensure_utc(row["deleted_at"]),
    )


def _admin_user_from_row(row) -> AdminUserRecord:
    return AdminUserRecord(
        id=row["id"],
        email=row["email"],
        password_hash=row["password_hash"],
        role=row["role"],
        enabled=row["enabled"],
        created_at=_ensure_utc(row["created_at"]),
        last_login_at=_ensure_utc(row["last_login_at"]),
    )


def _admin_session_from_row(row) -> AdminSessionRecord:
    return AdminSessionRecord(
        id=row["id"],
        admin_user_id=row["admin_user_id"],
        token_hash=row["token_hash"],
        expires_at=_ensure_utc(row["expires_at"]),
        created_at=_ensure_utc(row["created_at"]),
    )


def _pilot_whitelist_entry_from_row(row) -> PilotWhitelistEntry:
    return PilotWhitelistEntry(
        id=row["id"],
        phone_hash=row["phone_hash"],
        wx_openid=row["wx_openid"],
        source=row["source"],
        invited_by=row["invited_by"],
        created_at=_ensure_utc(row["created_at"]),
    )


def _project_from_row(row) -> ProjectRecord:
    return ProjectRecord(
        id=row["id"],
        user_id=row["user_id"],
        title=row["title"],
        storyteller=dict(row["storyteller_profile"] or {}),
        themes=list(row["themes"] or []),
        tier=row["tier"],
        status=row["status"],
        payment_status=row["payment_status"],
        payment_cents=row["payment_cents"],
        payment_method=row["payment_method"],
        payment_reference=row["payment_reference"],
        payment_marked_by_admin_id=row["payment_marked_by_admin_id"],
        payment_at=_ensure_utc(row["payment_at"]),
        created_at=_ensure_utc(row["created_at"]),
        updated_at=_ensure_utc(row["updated_at"]),
        deleted_at=_ensure_utc(row["deleted_at"]),
        purge_after_at=_ensure_utc(row["purge_after_at"]),
        ops_owner_id=row["ops_owner_id"],
        stuck_reason=row["stuck_reason"],
        stuck_at=_ensure_utc(row["stuck_at"]),
    )


def _session_from_row(row) -> SessionRecord:
    return SessionRecord(
        id=row["id"],
        project_id=row["project_id"],
        status=row["status"],
        started_at=_ensure_utc(row["started_at"]),
        ended_at=_ensure_utc(row["ended_at"]),
        created_at=_ensure_utc(row["created_at"]),
    )


def _photo_from_row(row) -> PhotoRecord:
    return PhotoRecord(
        id=row["id"],
        project_id=row["project_id"],
        oss_key=row["oss_key"],
        thumbnail_oss_key=row["thumbnail_oss_key"],
        caption=row["caption"],
        created_at=_ensure_utc(row["created_at"]),
        deleted_at=_ensure_utc(row["deleted_at"]),
        purge_after_at=_ensure_utc(row["purge_after_at"]),
    )


def _audio_chunk_from_row(row) -> AudioChunkRecord:
    return AudioChunkRecord(
        session_id=row["session_id"],
        sequence_number=row["sequence_number"],
        duration_ms=row["duration_ms"],
        oss_key=row["oss_key"],
        received_at=_ensure_utc(row["created_at"]),
        deleted_at=_ensure_utc(row["deleted_at"]),
        purge_after_at=_ensure_utc(row["purge_after_at"]),
    )


def _transcript_segment_from_row(row) -> TranscriptSegmentRecord:
    return TranscriptSegmentRecord(
        id=row["id"],
        project_id=row["project_id"],
        session_id=row["session_id"],
        audio_chunk_sequence_number=row["audio_chunk_sequence_number"],
        speaker=row["speaker"],
        text=row["text"],
        start_ms=row["start_ms"],
        end_ms=row["end_ms"],
        confidence=float(row["confidence"]),
        low_confidence_review=row["low_confidence_review"],
        created_at=_ensure_utc(row["created_at"]),
        deleted_at=_ensure_utc(row["deleted_at"]),
        purge_after_at=_ensure_utc(row["purge_after_at"]),
    )


def _photo_analysis_from_row(row) -> PhotoAnalysisRecord:
    return PhotoAnalysisRecord(
        id=row["id"],
        project_id=row["project_id"],
        photo_id=row["photo_id"],
        hypothesis_text=row["hypothesis_text"],
        confidence=float(row["confidence"]),
        internal_only=row["internal_only"],
        converted_claim_id=row["converted_claim_id"],
        created_at=_ensure_utc(row["created_at"]),
        deleted_at=_ensure_utc(row["deleted_at"]),
        purge_after_at=_ensure_utc(row["purge_after_at"]),
    )


def _claim_from_row(row) -> tuple[UUID, ClaimDraft]:
    project_id = row["project_id"]
    claim = ClaimDraft(
        id=row["id"],
        claim_text=row["claim_text"],
        modified_text=row["modified_text"],
        claim_type=row["claim_type"],
        claim_priority=row["claim_priority"],
        entities=dict(row["entities"] or {}),
        source_segment_ids=[UUID(str(segment_id)) for segment_id in row["source_segment_ids"] or []],
        confidence=float(row["confidence"]),
        support_status=row["support_status"],
        verification_status=row["verification_status"],
        sensitivity_level=row["sensitivity_level"],
        human_reviewed=row["human_reviewed"],
        embedding=json.loads(row["embedding"]) if row["embedding"] else None,
        deleted_at=_ensure_utc(row["deleted_at"]),
        purge_after_at=_ensure_utc(row["purge_after_at"]),
    )
    return project_id, claim


def _claim_evidence_from_row(row) -> tuple[UUID, dict]:
    evidence = {
        "id": row["id"],
        "claim_id": row["claim_id"],
        "evidence_type": row["evidence_type"],
        "audio_recording_id": row["audio_recording_id"],
        "transcript_segment_id": row["transcript_segment_id"],
        "photo_id": row["photo_id"],
        "user_input": row["user_input"],
        "start_ms": row["start_ms"],
        "end_ms": row["end_ms"],
        "created_at": _ensure_utc(row["created_at"]),
        "deleted_at": _ensure_utc(row["deleted_at"]),
        "purge_after_at": _ensure_utc(row["purge_after_at"]),
    }
    return row["id"], evidence


def _claim_correction_from_row(row) -> ClaimCorrectionRecord:
    return ClaimCorrectionRecord(
        id=row["id"],
        claim_id=row["claim_id"],
        user_id=row["user_id"],
        action=row["action"],
        modified_text=row["modified_text"],
        comment=row["comment"],
        created_at=_ensure_utc(row["created_at"]),
    )


def _story_page_from_row(row) -> StoryPageRecord:
    return StoryPageRecord(
        id=row["id"],
        project_id=row["project_id"],
        enabled=row["enabled"],
        password_hash=row["password_hash"],
        share_links_enabled=row["share_links_enabled"],
        draft=NarrativeDraft.model_validate(row["draft"]) if row["draft"] else None,
        deleted_at=_ensure_utc(row["deleted_at"]),
        purge_after_at=_ensure_utc(row["purge_after_at"]),
    )


def _chapter_from_row(row) -> ChapterRecord:
    return ChapterRecord(
        id=row["id"],
        project_id=row["project_id"],
        slug=row["slug"],
        title=row["title"],
        body_markdown=row["body_markdown"],
        created_at=_ensure_utc(row["created_at"]),
        deleted_at=_ensure_utc(row["deleted_at"]),
        purge_after_at=_ensure_utc(row["purge_after_at"]),
        purged_at=_ensure_utc(row["purged_at"]),
    )


def _citation_from_row(row) -> CitationRecord:
    return CitationRecord(
        id=row["id"],
        chapter_id=row["chapter_id"],
        claim_id=row["claim_id"],
        display_label=row["display_label"],
        created_at=_ensure_utc(row["created_at"]),
        deleted_at=_ensure_utc(row["deleted_at"]),
        purge_after_at=_ensure_utc(row["purge_after_at"]),
        purged_at=_ensure_utc(row["purged_at"]),
    )


def _share_link_from_row(row) -> ShareLinkRecord:
    return ShareLinkRecord(
        id=row["id"],
        story_page_id=row["story_page_id"],
        token_hash=row["token_hash"],
        password_hash=row["password_hash"],
        created_by_user_id=row["created_by_user_id"],
        enabled=row["enabled"],
        created_at=_ensure_utc(row["created_at"]),
        revoked_at=_ensure_utc(row["revoked_at"]),
        reset_at=_ensure_utc(row["reset_at"]),
        deleted_at=_ensure_utc(row["deleted_at"]),
        purge_after_at=_ensure_utc(row["purge_after_at"]),
    )


def _story_access_log_from_row(row) -> StoryAccessLogRecord:
    return StoryAccessLogRecord(
        id=row["id"],
        story_page_id=row["story_page_id"],
        share_link_id=row["share_link_id"],
        media_access_token_hash=row["media_access_token_hash"],
        accessed_at=_ensure_utc(row["created_at"]),
    )


def _family_comment_from_row(row) -> FamilyCommentRecord:
    return FamilyCommentRecord(
        id=row["id"],
        story_page_id=row["story_page_id"],
        share_link_id=row["share_link_id"],
        display_name=row["display_name"],
        body=row["body"],
        created_at=_ensure_utc(row["created_at"]),
        deleted_at=_ensure_utc(row["deleted_at"]),
        purge_after_at=_ensure_utc(row["purge_after_at"]),
    )


def _pdf_export_from_row(row) -> PdfExportRecord:
    return PdfExportRecord(
        id=row["id"],
        project_id=row["project_id"],
        story_page_id=row["story_page_id"],
        oss_key=row["oss_key"],
        created_at=_ensure_utc(row["created_at"]),
        deleted_at=_ensure_utc(row["deleted_at"]),
        purge_after_at=_ensure_utc(row["purge_after_at"]),
    )


def _verification_issue_from_row(row) -> tuple[UUID, dict]:
    issue_id = row["id"]
    issue = {
        "id": str(issue_id),
        "project_id": str(row["project_id"]),
        "gate": row["gate"],
        "severity": row["severity"],
        "message": row["message"],
        "chapter_id": str(row["chapter_id"]) if row["chapter_id"] else None,
        "citation_id": str(row["citation_id"]) if row["citation_id"] else None,
        "claim_id": str(row["claim_id"]) if row["claim_id"] else None,
        "resolved_at": _ensure_utc(row["resolved_at"]).isoformat() if row["resolved_at"] else None,
        "resolved_by_admin_id": str(row["resolved_by_admin_id"]) if row["resolved_by_admin_id"] else None,
        "resolution_reason": row["resolution_reason"],
    }
    return issue_id, issue


def _alert_from_row(row) -> AlertRecord:
    return AlertRecord(
        id=row["id"],
        path=row["path"],
        method=row["method"],
        error_type=row["error_type"],
        message=row["message"],
        created_at=_ensure_utc(row["created_at"]),
    )


def _audit_log_from_row(row) -> AuditLog:
    return AuditLog(
        id=row["id"],
        actor_id=row["actor_id"],
        action=row["action"],
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        reason=row["reason"],
        metadata=dict(row["metadata"] or {}),
        created_at=_ensure_utc(row["created_at"]),
    )


def _consent_from_row(row) -> ConsentRecord:
    return ConsentRecord(
        id=row["id"],
        project_id=row["project_id"],
        user_id=row["user_id"],
        consent_type=row["consent_type"],
        method=row["method"],
        evidence_oss_key=row["evidence_oss_key"],
        withdrawn_at=_ensure_utc(row["withdrawn_at"]),
        minimized_at=_ensure_utc(row["minimized_at"]),
        created_at=_ensure_utc(row["created_at"]),
    )


def _deletion_request_from_row(row) -> DeletionRequestRecord:
    return DeletionRequestRecord(
        id=row["id"],
        project_id=row["project_id"],
        requested_by_user_id=row["requested_by_user_id"],
        requested_at=_ensure_utc(row["requested_at"]),
        execute_after_at=_ensure_utc(row["execute_after_at"]),
        status=row["status"],
        executed_at=_ensure_utc(row["executed_at"]),
    )


def _feedback_from_row(row) -> FeedbackRecord:
    return FeedbackRecord(
        id=row["id"],
        project_id=row["project_id"],
        user_id=row["user_id"],
        nps_score=row["nps_score"],
        recommend=row["recommend"],
        issue_type=row["issue_type"],
        body=row["body"],
        created_at=_ensure_utc(row["created_at"]),
    )


def _support_ticket_from_row(row) -> SupportTicketRecord:
    return SupportTicketRecord(
        id=row["id"],
        project_id=row["project_id"],
        user_id=row["user_id"],
        admin_owner_id=row["admin_owner_id"],
        status=row["status"],
        priority=row["priority"],
        category=row["category"],
        body=row["body"],
        created_at=_ensure_utc(row["created_at"]),
        updated_at=_ensure_utc(row["updated_at"]),
    )


def _internal_note_from_row(row) -> InternalNoteRecord:
    return InternalNoteRecord(
        id=row["id"],
        project_id=row["project_id"],
        admin_user_id=row["admin_user_id"],
        note_type=row["note_type"],
        body=row["body"],
        created_at=_ensure_utc(row["created_at"]),
    )


def _manual_intervention_from_row(row) -> ManualInterventionRecord:
    return ManualInterventionRecord(
        id=row["id"],
        project_id=row["project_id"],
        admin_user_id=row["admin_user_id"],
        category=row["category"],
        minutes=row["minutes"],
        body=row["body"],
        created_at=_ensure_utc(row["created_at"]),
    )


def _ai_cost_from_row(row) -> AiCostRecord:
    return AiCostRecord(
        id=row["id"],
        project_id=row["project_id"],
        admin_user_id=row["admin_user_id"],
        task_type=row["task_type"],
        provider=row["provider"],
        cost_cents=row["cost_cents"],
        generation_run_id=row["generation_run_id"],
        created_at=_ensure_utc(row["created_at"]),
    )


def _generation_run_from_row(row) -> GenerationRun:
    return GenerationRun(
        id=row["id"],
        project_id=row["project_id"],
        task_type=TaskType(row["task_type"]),
        provider_name=row["provider_name"],
        prompt_version=row["prompt_version"],
        prompt_hash=row["prompt_hash"],
        attempts=row["attempts"],
        raw_input_oss_key=row["raw_input_oss_key"],
        raw_output_oss_key=row["raw_output_oss_key"],
        output={},
        created_at=_ensure_utc(row["created_at"]),
    )


def _user_values(user: UserRecord) -> dict:
    return {
        "id": user.id,
        "wx_openid": user.wx_openid,
        "wx_unionid": user.wx_unionid,
        "phone_e164_enc": _encode_bytes(user.phone_e164_enc),
        "phone_hash": user.phone_hash,
        "nickname": user.nickname,
        "avatar_url": user.avatar_url,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "deleted_at": user.deleted_at,
    }


def _admin_user_values(admin_user: AdminUserRecord) -> dict:
    return {
        "id": admin_user.id,
        "email": admin_user.email,
        "password_hash": admin_user.password_hash,
        "role": admin_user.role,
        "enabled": admin_user.enabled,
        "created_at": admin_user.created_at,
        "last_login_at": admin_user.last_login_at,
    }


def _admin_session_values(session: AdminSessionRecord) -> dict:
    return {
        "id": session.id,
        "admin_user_id": session.admin_user_id,
        "token_hash": session.token_hash,
        "expires_at": session.expires_at,
        "created_at": session.created_at,
    }


def _pilot_whitelist_entry_values(entry: PilotWhitelistEntry) -> dict:
    return {
        "id": entry.id,
        "phone_hash": entry.phone_hash,
        "wx_openid": entry.wx_openid,
        "source": entry.source,
        "invited_by": entry.invited_by,
        "created_at": entry.created_at,
    }


def _session_values(session: SessionRecord) -> dict:
    return {
        "id": session.id,
        "project_id": session.project_id,
        "status": session.status,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "created_at": session.created_at,
    }


def _photo_values(photo: PhotoRecord) -> dict:
    return {
        "id": photo.id,
        "project_id": photo.project_id,
        "oss_key": photo.oss_key,
        "thumbnail_oss_key": photo.thumbnail_oss_key,
        "caption": photo.caption,
        "created_at": photo.created_at,
        "deleted_at": photo.deleted_at,
        "purge_after_at": photo.purge_after_at,
    }


def _audio_chunk_values(chunk: AudioChunkRecord, project_id: UUID, kms_key_id: str) -> dict:
    return {
        "id": _audio_recording_id(chunk.session_id, chunk.sequence_number),
        "project_id": project_id,
        "session_id": chunk.session_id,
        "sequence_number": chunk.sequence_number,
        "oss_key": chunk.oss_key,
        "duration_ms": chunk.duration_ms,
        "duration_seconds": chunk.duration_ms // 1000,
        "kms_key_id": kms_key_id,
        "created_at": chunk.received_at,
        "deleted_at": chunk.deleted_at,
        "purge_after_at": chunk.purge_after_at,
    }


def _transcript_segment_values(segment: TranscriptSegmentRecord) -> dict:
    return {
        "id": segment.id,
        "project_id": segment.project_id,
        "audio_recording_id": _audio_recording_id(segment.session_id, segment.audio_chunk_sequence_number),
        "speaker": segment.speaker,
        "text": segment.text,
        "start_ms": segment.start_ms,
        "end_ms": segment.end_ms,
        "confidence": segment.confidence,
        "low_confidence_review": segment.low_confidence_review,
        "created_at": segment.created_at,
        "deleted_at": segment.deleted_at,
        "purge_after_at": segment.purge_after_at,
    }


def _photo_analysis_values(analysis: PhotoAnalysisRecord) -> dict:
    return {
        "id": analysis.id,
        "project_id": analysis.project_id,
        "photo_id": analysis.photo_id,
        "hypothesis_text": analysis.hypothesis_text,
        "confidence": analysis.confidence,
        "internal_only": analysis.internal_only,
        "provider_run_id": None,
        "converted_claim_id": analysis.converted_claim_id,
        "created_at": analysis.created_at,
        "deleted_at": analysis.deleted_at,
        "purge_after_at": analysis.purge_after_at,
    }


def _claim_values(project_id: UUID, claim: ClaimDraft) -> dict:
    now = datetime.now(UTC)
    return {
        "id": claim.id,
        "project_id": project_id,
        "claim_text": claim.claim_text,
        "modified_text": claim.modified_text,
        "claim_type": claim.claim_type,
        "claim_priority": claim.claim_priority.value,
        "entities": claim.entities,
        "source_segment_ids": [str(segment_id) for segment_id in claim.source_segment_ids],
        "confidence": claim.confidence,
        "support_status": claim.support_status.value,
        "verification_status": claim.verification_status,
        "sensitivity_level": claim.sensitivity_level,
        "human_reviewed": claim.human_reviewed,
        "embedding": json.dumps(claim.embedding) if claim.embedding else None,
        "created_at": now,
        "updated_at": now,
        "deleted_at": claim.deleted_at,
        "purge_after_at": claim.purge_after_at,
    }


def _claim_evidence_values(project_id: UUID, claim: ClaimDraft, transcript_segments: dict[UUID, TranscriptSegmentRecord]) -> list[dict]:
    rows: list[dict] = []
    now = datetime.now(UTC)
    for segment_id in claim.source_segment_ids:
        segment = transcript_segments.get(segment_id)
        if segment:
            values = {
                "id": _claim_evidence_id(claim.id, "transcript", segment_id),
                "claim_id": claim.id,
                "evidence_type": "transcript",
                "audio_recording_id": _audio_recording_id(segment.session_id, segment.audio_chunk_sequence_number),
                "transcript_segment_id": segment.id,
                "photo_id": None,
                "user_input": None,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "created_at": now,
                "deleted_at": claim.deleted_at,
                "purge_after_at": claim.purge_after_at,
            }
        else:
            values = {
                "id": _claim_evidence_id(claim.id, "user_input", segment_id),
                "claim_id": claim.id,
                "evidence_type": "user_input",
                "audio_recording_id": None,
                "transcript_segment_id": None,
                "photo_id": None,
                "user_input": str(segment_id),
                "start_ms": None,
                "end_ms": None,
                "created_at": now,
                "deleted_at": claim.deleted_at,
                "purge_after_at": claim.purge_after_at,
            }
        rows.append(values)
    for raw_photo_id in claim.entities.get("photo_id", []):
        photo_id = UUID(str(raw_photo_id))
        rows.append(
            {
                "id": _claim_evidence_id(claim.id, "photo", photo_id),
                "claim_id": claim.id,
                "evidence_type": "photo",
                "audio_recording_id": None,
                "transcript_segment_id": None,
                "photo_id": photo_id,
                "user_input": None,
                "start_ms": None,
                "end_ms": None,
                "created_at": now,
                "deleted_at": claim.deleted_at,
                "purge_after_at": claim.purge_after_at,
            }
        )
    return rows


def _claim_evidence_dict(row: dict) -> dict:
    return {
        "id": row["id"],
        "claim_id": row["claim_id"],
        "evidence_type": row["evidence_type"],
        "audio_recording_id": row["audio_recording_id"],
        "transcript_segment_id": row["transcript_segment_id"],
        "photo_id": row["photo_id"],
        "user_input": row["user_input"],
        "start_ms": row["start_ms"],
        "end_ms": row["end_ms"],
        "created_at": row["created_at"],
        "deleted_at": row["deleted_at"],
        "purge_after_at": row["purge_after_at"],
    }


def _claim_correction_values(correction: ClaimCorrectionRecord) -> dict:
    return {
        "id": correction.id,
        "claim_id": correction.claim_id,
        "user_id": correction.user_id,
        "action": correction.action,
        "modified_text": correction.modified_text,
        "comment": correction.comment,
        "created_at": correction.created_at,
    }


def _story_page_values(page: StoryPageRecord) -> dict:
    return {
        "id": page.id,
        "project_id": page.project_id,
        "enabled": page.enabled,
        "share_links_enabled": page.share_links_enabled,
        "password_hash": page.password_hash,
        "draft": page.draft.model_dump(mode="json") if page.draft else None,
        "created_at": datetime.now(UTC),
        "deleted_at": page.deleted_at,
        "purge_after_at": page.purge_after_at,
    }


def _chapter_values(chapter: ChapterRecord) -> dict:
    return {
        "id": chapter.id,
        "project_id": chapter.project_id,
        "slug": chapter.slug,
        "title": chapter.title,
        "body_markdown": chapter.body_markdown,
        "created_at": chapter.created_at,
        "deleted_at": chapter.deleted_at,
        "purge_after_at": chapter.purge_after_at,
        "purged_at": chapter.purged_at,
    }


def _citation_values(citation: CitationRecord) -> dict:
    return {
        "id": citation.id,
        "chapter_id": citation.chapter_id,
        "claim_id": citation.claim_id,
        "display_label": citation.display_label,
        "created_at": citation.created_at,
        "deleted_at": citation.deleted_at,
        "purge_after_at": citation.purge_after_at,
        "purged_at": citation.purged_at,
    }


def _share_link_values(link: ShareLinkRecord) -> dict:
    return {
        "id": link.id,
        "story_page_id": link.story_page_id,
        "token_hash": link.token_hash,
        "password_hash": link.password_hash,
        "created_by_user_id": link.created_by_user_id,
        "enabled": link.enabled,
        "created_at": link.created_at,
        "revoked_at": link.revoked_at,
        "reset_at": link.reset_at,
        "deleted_at": link.deleted_at,
        "purge_after_at": link.purge_after_at,
    }


def _story_access_log_values(access_log: StoryAccessLogRecord) -> dict:
    return {
        "id": access_log.id,
        "story_page_id": access_log.story_page_id,
        "share_link_id": access_log.share_link_id,
        "media_access_token_hash": access_log.media_access_token_hash,
        "ip_hash": None,
        "user_agent": None,
        "created_at": access_log.accessed_at,
    }


def _family_comment_values(comment: FamilyCommentRecord) -> dict:
    return {
        "id": comment.id,
        "story_page_id": comment.story_page_id,
        "share_link_id": comment.share_link_id,
        "display_name": comment.display_name,
        "body": comment.body,
        "created_at": comment.created_at,
        "deleted_at": comment.deleted_at,
        "purge_after_at": comment.purge_after_at,
    }


def _pdf_export_values(pdf_export: PdfExportRecord) -> dict:
    return {
        "id": pdf_export.id,
        "project_id": pdf_export.project_id,
        "story_page_id": pdf_export.story_page_id,
        "oss_key": pdf_export.oss_key,
        "created_at": pdf_export.created_at,
        "deleted_at": pdf_export.deleted_at,
        "purge_after_at": pdf_export.purge_after_at,
    }


def _verification_issue_values(issue_id: UUID, issue: dict) -> dict:
    return {
        "id": issue_id,
        "project_id": UUID(str(issue["project_id"])),
        "gate": issue.get("gate") or "unknown",
        "severity": issue["severity"],
        "message": issue.get("message") or issue.get("detail") or "verification issue",
        "chapter_id": UUID(str(issue["chapter_id"])) if issue.get("chapter_id") else None,
        "citation_id": UUID(str(issue["citation_id"])) if issue.get("citation_id") else None,
        "claim_id": UUID(str(issue["claim_id"])) if issue.get("claim_id") else None,
        "resolved_at": _parse_datetime(issue.get("resolved_at")),
        "resolved_by_admin_id": UUID(str(issue["resolved_by_admin_id"])) if issue.get("resolved_by_admin_id") else None,
        "resolution_reason": issue.get("resolution_reason"),
        "created_at": _parse_datetime(issue.get("created_at")) or datetime.now(UTC),
    }


def _alert_values(alert: AlertRecord) -> dict:
    return {
        "id": alert.id,
        "path": alert.path,
        "method": alert.method,
        "error_type": alert.error_type,
        "message": alert.message,
        "created_at": alert.created_at,
    }


def _audit_log_values(log: AuditLog) -> dict:
    return {
        "id": log.id,
        "actor_id": log.actor_id,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "reason": log.reason,
        "metadata": log.metadata,
        "created_at": log.created_at,
    }


def _project_values(project: ProjectRecord) -> dict:
    return {
        "id": project.id,
        "user_id": project.user_id,
        "title": project.title,
        "status": project.status,
        "tier": project.tier,
        "themes": project.themes,
        "storyteller_profile": project.storyteller,
        "payment_status": project.payment_status,
        "payment_cents": project.payment_cents,
        "payment_method": project.payment_method,
        "payment_reference": project.payment_reference,
        "payment_marked_by_admin_id": project.payment_marked_by_admin_id,
        "payment_at": project.payment_at,
        "ops_owner_id": project.ops_owner_id,
        "stuck_reason": project.stuck_reason,
        "stuck_at": project.stuck_at,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "deleted_at": project.deleted_at,
        "purge_after_at": project.purge_after_at,
    }


def _consent_values(consent: ConsentRecord) -> dict:
    return {
        "id": consent.id,
        "project_id": consent.project_id,
        "user_id": consent.user_id,
        "consent_type": consent.consent_type,
        "method": consent.method,
        "evidence_oss_key": consent.evidence_oss_key,
        "withdrawn_at": consent.withdrawn_at,
        "minimized_at": consent.minimized_at,
        "created_at": consent.created_at,
    }


def _deletion_request_values(deletion: DeletionRequestRecord) -> dict:
    return {
        "id": deletion.id,
        "project_id": deletion.project_id,
        "requested_by_user_id": deletion.requested_by_user_id,
        "requested_at": deletion.requested_at,
        "execute_after_at": deletion.execute_after_at,
        "executed_at": deletion.executed_at,
        "status": deletion.status,
    }


def _feedback_values(feedback: FeedbackRecord) -> dict:
    return {
        "id": feedback.id,
        "project_id": feedback.project_id,
        "user_id": feedback.user_id,
        "nps_score": feedback.nps_score,
        "recommend": feedback.recommend,
        "issue_type": feedback.issue_type,
        "body": feedback.body,
        "created_at": feedback.created_at,
    }


def _support_ticket_values(ticket: SupportTicketRecord) -> dict:
    return {
        "id": ticket.id,
        "project_id": ticket.project_id,
        "user_id": ticket.user_id,
        "admin_owner_id": ticket.admin_owner_id,
        "status": ticket.status,
        "priority": ticket.priority,
        "category": ticket.category,
        "body": ticket.body,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }


def _internal_note_values(note: InternalNoteRecord) -> dict:
    return {
        "id": note.id,
        "project_id": note.project_id,
        "admin_user_id": note.admin_user_id,
        "note_type": note.note_type,
        "body": note.body,
        "created_at": note.created_at,
    }


def _manual_intervention_values(intervention: ManualInterventionRecord) -> dict:
    return {
        "id": intervention.id,
        "project_id": intervention.project_id,
        "admin_user_id": intervention.admin_user_id,
        "category": intervention.category,
        "minutes": intervention.minutes,
        "body": intervention.body,
        "created_at": intervention.created_at,
    }


def _ai_cost_values(cost: AiCostRecord) -> dict:
    return {
        "id": cost.id,
        "project_id": cost.project_id,
        "admin_user_id": cost.admin_user_id,
        "task_type": cost.task_type,
        "provider": cost.provider,
        "cost_cents": cost.cost_cents,
        "generation_run_id": cost.generation_run_id,
        "created_at": cost.created_at,
    }


def _generation_run_values(run: GenerationRun) -> dict:
    return {
        "id": run.id,
        "project_id": run.project_id,
        "task_type": run.task_type.value,
        "provider_name": run.provider_name,
        "prompt_version": run.prompt_version,
        "prompt_hash": run.prompt_hash,
        "attempts": run.attempts,
        "raw_input_oss_key": run.raw_input_oss_key,
        "raw_output_oss_key": run.raw_output_oss_key,
        "created_at": run.created_at,
    }


def _delete_ids(connection, table: Table, column, values: set) -> None:
    if values:
        connection.execute(delete(table).where(column.in_(list(values))))


def _encode_bytes(value: str | None) -> bytes | None:
    return value.encode("utf-8") if value else None


def _decode_bytes(value: bytes | memoryview | None) -> str | None:
    if value is None:
        return None
    return bytes(value).decode("utf-8")


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo:
        return value
    return value.replace(tzinfo=UTC)


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return _ensure_utc(value)
    parsed = datetime.fromisoformat(value)
    return _ensure_utc(parsed)


def _audio_recording_id(session_id: UUID, sequence_number: int) -> UUID:
    return uuid5(NAMESPACE_URL, f"changjuan:audio-recording:{session_id}:{sequence_number}")


def _claim_evidence_id(claim_id: UUID, evidence_type: str, source_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"changjuan:claim-evidence:{claim_id}:{evidence_type}:{source_id}")


def _rate_limit_hit_id(key: str, hit_at: datetime) -> UUID:
    return uuid5(NAMESPACE_URL, f"changjuan:rate-limit-hit:{key}:{hit_at.isoformat()}")


class _SqlAlchemyAuditSink(AuditSink):
    def __init__(self, store: SqlAlchemyStore) -> None:
        super().__init__()
        self.store = store

    def record(self, log: AuditLog) -> AuditLog:
        saved_log = super().record(log)
        self.store._save_audit_log(saved_log)
        return saved_log
