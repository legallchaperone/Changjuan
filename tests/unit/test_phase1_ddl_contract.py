from __future__ import annotations

import subprocess
from pathlib import Path


def test_phase1_migration_contains_required_soft_delete_and_ops_tables() -> None:
    migration = Path("infra/migrations/versions/0001_phase1.py").read_text()

    for table in [
        "audio_recordings",
        "transcript_segments",
        "photos",
        "photo_analyses",
        "claims",
        "claim_evidence",
        "chapters",
        "citations",
        "story_pages",
        "share_links",
        "family_comments",
        "pdf_exports",
    ]:
        table_block_start = migration.index(f'"{table}"')
        table_block = migration[table_block_start : table_block_start + 1800]
        assert '"deleted_at"' in table_block
        assert '"purge_after_at"' in table_block
        assert '"purged_at"' in table_block

    for table in [
        "admin_users",
        "admin_sessions",
        "internal_notes",
        "pilot_whitelist",
        "feedback",
        "support_tickets",
        "manual_interventions",
        "ai_costs",
        "alerts",
        "revoked_tokens",
        "revoked_token_sessions",
        "rate_limit_hits",
        "generation_runs",
    ]:
        assert f'"{table}"' in migration

    for field in [
        "payment_status",
        "payment_cents",
        "payment_method",
        "payment_reference",
        "payment_marked_by_admin_id",
        "payment_at",
        "ops_owner_id",
        "stuck_reason",
        "stuck_at",
    ]:
        assert f'"{field}"' in migration

    audio_block_start = migration.index('"audio_recordings"')
    audio_block = migration[audio_block_start : audio_block_start + 1800]
    assert '"sequence_number"' in audio_block
    assert '"duration_ms"' in audio_block

    story_block_start = migration.index('"story_pages"')
    story_block = migration[story_block_start : story_block_start + 1800]
    assert '"share_links_enabled"' in story_block
    assert '"draft"' in story_block

    share_link_block_start = migration.index('"share_links"')
    share_link_block = migration[share_link_block_start : share_link_block_start + 1800]
    assert '"password_hash"' in share_link_block
    assert '"created_by_user_id"' in share_link_block
    assert '"reset_at"' in share_link_block

    access_log_block_start = migration.index('"access_logs"')
    access_log_block = migration[access_log_block_start : access_log_block_start + 1200]
    assert '"media_access_token_hash"' in access_log_block

    pdf_export_block_start = migration.index('"pdf_exports"')
    pdf_export_block = migration[pdf_export_block_start : pdf_export_block_start + 1200]
    assert '"project_id"' in pdf_export_block


def test_phase1_claim_embeddings_use_pgvector() -> None:
    migration = Path("infra/migrations/versions/0001_phase1.py").read_text()
    claims_block_start = migration.index('"claims"')
    claims_block = migration[claims_block_start : claims_block_start + 1800]

    assert 'op.execute("CREATE EXTENSION IF NOT EXISTS vector")' in migration
    assert 'sa.Column("embedding", PgVector(16), nullable=True)' in claims_block
    assert 'sa.Column("embedding", sa.Text(), nullable=True)' not in claims_block


def test_phase1_generated_sql_uses_pgvector_for_claim_embeddings(tmp_path: Path) -> None:
    result = subprocess.run(
        ["uv", "run", "--extra", "dev", "alembic", "upgrade", "head", "--sql"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "CREATE EXTENSION IF NOT EXISTS vector" in result.stdout
    assert "embedding vector(16)" in result.stdout
