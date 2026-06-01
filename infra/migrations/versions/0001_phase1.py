"""phase 1 v3 schema

Revision ID: 0001_phase1
Revises:
Create Date: 2026-05-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_phase1"
down_revision = None
branch_labels = None
depends_on = None


class PgVector(sa.types.UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        return f"vector({self.dimensions})"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("wx_openid", sa.String(64), nullable=False, unique=True),
        sa.Column("wx_unionid", sa.String(64), nullable=True, unique=True),
        sa.Column("phone_e164_enc", sa.LargeBinary(), nullable=True),
        sa.Column("phone_hash", sa.String(64), nullable=True, index=True),
        sa.Column("realname_enc", sa.LargeBinary(), nullable=True),
        sa.Column("nickname", sa.String(64), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(128), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "admin_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("admin_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("status", sa.String(64), nullable=False, server_default="created"),
        sa.Column("tier", sa.String(32), nullable=False, server_default="standard"),
        sa.Column("themes", postgresql.ARRAY(sa.String(64)), nullable=False, server_default="{}"),
        sa.Column("storyteller_profile", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("payment_status", sa.String(32), nullable=False, server_default="not_required"),
        sa.Column("payment_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payment_method", sa.String(32), nullable=True),
        sa.Column("payment_reference", sa.String(128), nullable=True),
        sa.Column("payment_marked_by_admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("payment_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ops_owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("stuck_reason", sa.Text(), nullable=True),
        sa.Column("stuck_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "interview_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="scheduled"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('scheduled','in_progress','completed','aborted_by_storyteller','aborted_technical','completed_short')",
            name="ck_interview_sessions_status",
        ),
    )

    op.create_table(
        "audio_recordings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("interview_sessions.id"), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("oss_key", sa.Text(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kms_key_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "sequence_number", name="uq_audio_recordings_session_sequence"),
    )
    op.create_table(
        "transcript_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("audio_recording_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("audio_recordings.id"), nullable=False),
        sa.Column("speaker", sa.String(32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("low_confidence_review", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("oss_key", sa.Text(), nullable=False),
        sa.Column("thumbnail_oss_key", sa.Text(), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "photo_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("photo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("photos.id"), nullable=False),
        sa.Column("hypothesis_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("internal_only", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("provider_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("converted_claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("modified_text", sa.Text(), nullable=True),
        sa.Column("claim_type", sa.String(64), nullable=False),
        sa.Column("claim_priority", sa.String(2), nullable=False),
        sa.Column("entities", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_segment_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("support_status", sa.String(32), nullable=False),
        sa.Column("verification_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("sensitivity_level", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("human_reviewed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("embedding", PgVector(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "claim_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("evidence_type", sa.String(32), nullable=False),
        sa.Column("audio_recording_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("audio_recordings.id"), nullable=True),
        sa.Column("transcript_segment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("transcript_segments.id"), nullable=True),
        sa.Column("photo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("photos.id"), nullable=True),
        sa.Column("user_input", sa.Text(), nullable=True),
        sa.Column("start_ms", sa.Integer(), nullable=True),
        sa.Column("end_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "claim_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("modified_text", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "chapters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "citations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chapters.id"), nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("display_label", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "story_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("share_links_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("draft", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "share_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("story_page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("story_pages.id"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "family_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("story_page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("story_pages.id"), nullable=False),
        sa.Column("share_link_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("share_links.id"), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "pdf_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("story_page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("story_pages.id"), nullable=False),
        sa.Column("oss_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "consent_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("consent_type", sa.String(64), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("evidence_oss_key", sa.Text(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("minimized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "verification_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("gate", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("chapter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("citation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_admin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "generation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("provider_name", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("raw_input_oss_key", sa.Text(), nullable=False),
        sa.Column("raw_output_oss_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "internal_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("admin_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("note_type", sa.String(32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "pilot_whitelist",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone_hash", sa.String(64), nullable=True),
        sa.Column("wx_openid", sa.String(64), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("invited_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("nps_score", sa.Integer(), nullable=True),
        sa.Column("recommend", sa.Boolean(), nullable=True),
        sa.Column("issue_type", sa.String(64), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "support_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("admin_owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "manual_interventions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("admin_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ai_costs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("admin_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("cost_cents", sa.Integer(), nullable=False),
        sa.Column("generation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("error_type", sa.String(128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "revoked_tokens",
        sa.Column("token_id", sa.String(64), primary_key=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "revoked_token_sessions",
        sa.Column("session_id", sa.String(64), primary_key=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "rate_limit_hits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rate_limit_key", sa.Text(), nullable=False),
        sa.Column("hit_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "deletion_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("execute_after_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
    )

    op.create_table(
        "access_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("story_page_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("story_pages.id"), nullable=False),
        sa.Column("share_link_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("share_links.id"), nullable=True),
        sa.Column("media_access_token_hash", sa.String(255), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in [
        "access_logs",
        "deletion_requests",
        "rate_limit_hits",
        "revoked_token_sessions",
        "revoked_tokens",
        "alerts",
        "audit_logs",
        "ai_costs",
        "manual_interventions",
        "support_tickets",
        "feedback",
        "pilot_whitelist",
        "internal_notes",
        "generation_runs",
        "verification_issues",
        "consent_records",
        "family_comments",
        "pdf_exports",
        "share_links",
        "story_pages",
        "citations",
        "chapters",
        "claim_corrections",
        "claim_evidence",
        "claims",
        "photo_analyses",
        "photos",
        "transcript_segments",
        "audio_recordings",
        "interview_sessions",
        "projects",
        "admin_sessions",
        "admin_users",
        "users",
    ]:
        op.drop_table(table)
