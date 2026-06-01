from __future__ import annotations


def test_sqlalchemy_claim_embedding_type_matches_phase1_pgvector_contract() -> None:
    from changjuan_api.sqlalchemy_store import CLAIMS
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateTable

    postgresql_ddl = str(CreateTable(CLAIMS).compile(dialect=postgresql.dialect()))
    sqlite_ddl = str(CreateTable(CLAIMS).compile(dialect=sqlite.dialect()))

    assert "embedding vector(16)" in postgresql_ddl
    assert "embedding TEXT" in sqlite_ddl


def test_sqlalchemy_store_persists_pilot_whitelist_and_hydrates_login_gate(tmp_path) -> None:
    from changjuan_api.sqlalchemy_store import SqlAlchemyStore

    database_url = f"sqlite+pysqlite:///{tmp_path / 'pilot-whitelist.db'}"
    first = SqlAlchemyStore(database_url, whitelist_openids={"wx_env_phase1"}, create_schema=True)

    entry = first.add_pilot_whitelist_entry(
        wx_openid="wx_db_only",
        phone_hash="phone_hash_001",
        source="manual",
        invited_by="ops",
    )

    recreated = SqlAlchemyStore(database_url, whitelist_openids=set())

    assert "wx_env_phase1" in recreated.whitelist_openids
    assert "wx_db_only" in recreated.whitelist_openids
    assert not recreated.is_pilot_whitelisted("wx_missing")
    assert recreated.is_pilot_whitelisted("wx_db_only")
    assert recreated.pilot_whitelist[entry.id].phone_hash == "phone_hash_001"
    assert recreated.pilot_whitelist[entry.id].source == "manual"
    assert recreated.pilot_whitelist[entry.id].invited_by == "ops"


def test_sqlalchemy_store_persists_generation_runs_across_recreation(tmp_path) -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from changjuan_api.sqlalchemy_store import SqlAlchemyStore
    from changjuan_core.providers.router import GenerationRun, TaskType

    database_url = f"sqlite+pysqlite:///{tmp_path / 'generation-runs.db'}"
    first = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"}, create_schema=True)
    user = first.upsert_user("wx_phase1", "Daughter")
    project = first.create_project(
        user.id,
        {
            "title": "Father's Story",
            "storyteller": {"display_name": "Father"},
            "themes": ["work"],
            "tier": "standard",
        },
    )
    run = GenerationRun(
        id=uuid4(),
        project_id=project.id,
        task_type=TaskType.CLAIM_EXTRACTION,
        provider_name="deepseek",
        prompt_version="extraction-agent-v1",
        prompt_hash="a" * 64,
        attempts=2,
        raw_input_oss_key="generation-runs/run/input.json",
        raw_output_oss_key="generation-runs/run/output.json",
        output={"claims": []},
        created_at=datetime(2026, 5, 17, 9, 30, tzinfo=UTC),
    )

    first.record_generation_run(run)

    recreated = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"})
    persisted = recreated.generation_runs[run.id]

    assert persisted.project_id == project.id
    assert persisted.task_type == TaskType.CLAIM_EXTRACTION
    assert persisted.provider_name == "deepseek"
    assert persisted.prompt_version == "extraction-agent-v1"
    assert persisted.prompt_hash == "a" * 64
    assert persisted.attempts == 2
    assert persisted.raw_input_oss_key == "generation-runs/run/input.json"
    assert persisted.raw_output_oss_key == "generation-runs/run/output.json"
    assert persisted.created_at == datetime(2026, 5, 17, 9, 30, tzinfo=UTC)


def test_sqlalchemy_store_persists_normalized_claim_evidence_and_rate_limit_state(tmp_path) -> None:
    from changjuan_api.sqlalchemy_store import SqlAlchemyStore
    from changjuan_core.ai.contracts import ClaimDraft, ClaimPriority, SupportStatus

    database_url = f"sqlite+pysqlite:///{tmp_path / 'remaining-state.db'}"
    first = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"}, create_schema=True)
    user = first.upsert_user("wx_phase1", "Daughter")
    project = first.create_project(
        user.id,
        {
            "title": "Father's Story",
            "storyteller": {"display_name": "Father"},
            "themes": ["work"],
            "tier": "standard",
        },
    )
    session = first.create_session(project.id)
    chunk = first.record_audio_chunk(session.id, 0, 400, f"audio/{project.id}/session-0.webm")
    segment = first.record_transcript_segment(
        project.id,
        session.id,
        chunk.sequence_number,
        "elder",
        "父亲1978年进入县供销社工作。",
        0.86,
        chunk.duration_ms,
    )
    claim = ClaimDraft(
        claim_text="父亲1978年进入县供销社工作",
        claim_type="work",
        claim_priority=ClaimPriority.P0,
        source_segment_ids=[segment.id],
        confidence=0.86,
        support_status=SupportStatus.SUPPORTED,
    )
    first.save_claim(project.id, claim)
    for _ in range(60):
        assert first.accept_rate_limited_request("client:/healthz", limit=60) is True

    recreated = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"})

    evidence = [
        item
        for item in recreated.claim_evidence.values()
        if item["claim_id"] == claim.id
    ]
    assert evidence == [
        {
            **evidence[0],
            "claim_id": claim.id,
            "evidence_type": "transcript",
            "transcript_segment_id": segment.id,
            "photo_id": None,
            "start_ms": 0,
            "end_ms": 400,
        }
    ]
    assert evidence[0]["audio_recording_id"] is not None
    assert recreated.claims[claim.id].embedding is not None
    assert recreated.claims[claim.id].embedding == claim.embedding
    assert recreated.accept_rate_limited_request("client:/healthz", limit=60) is False


def test_sqlalchemy_store_persists_normalized_story_chapters_citations_and_deletion_state(tmp_path) -> None:
    from uuid import uuid4

    from changjuan_api.sqlalchemy_store import SqlAlchemyStore
    from changjuan_core.ai.contracts import ClaimDraft, ClaimPriority, SupportStatus

    database_url = f"sqlite+pysqlite:///{tmp_path / 'story-normalized.db'}"
    first = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"}, create_schema=True)
    user = first.upsert_user("wx_phase1", "Daughter")
    project = first.create_project(
        user.id,
        {
            "title": "Father's Story",
            "storyteller": {"display_name": "Father"},
            "themes": ["work"],
            "tier": "standard",
        },
    )
    claim = ClaimDraft(
        claim_text="父亲1978年进入县供销社工作",
        claim_type="work",
        claim_priority=ClaimPriority.P0,
        source_segment_ids=[uuid4()],
        confidence=0.88,
        support_status=SupportStatus.SUPPORTED,
        verification_status="confirmed",
    )
    first.save_claim(project.id, claim)
    page = first.generate_story(project.id)
    chapter = next(chapter for chapter in page.draft.chapters if claim.id in chapter.claim_ids)

    recreated = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"})
    persisted_chapter = recreated.chapters[chapter.id]
    persisted_citations = [
        citation
        for citation in recreated.citations.values()
        if citation.chapter_id == chapter.id
    ]

    assert persisted_chapter.project_id == project.id
    assert persisted_chapter.slug == chapter.slug
    assert persisted_chapter.title == chapter.title
    assert persisted_chapter.body_markdown == chapter.body
    assert persisted_chapter.deleted_at is None
    assert [(citation.claim_id, citation.display_label) for citation in persisted_citations] == [(claim.id, "[1]")]

    deletion = recreated.request_deletion(project.id, requested_by_user_id=user.id)
    after_delete = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"})

    assert after_delete.chapters[chapter.id].deleted_at is not None
    assert after_delete.chapters[chapter.id].purge_after_at == deletion.execute_after_at
    assert all(citation.deleted_at for citation in after_delete.citations.values() if citation.chapter_id == chapter.id)
    assert all(citation.purge_after_at == deletion.execute_after_at for citation in after_delete.citations.values() if citation.chapter_id == chapter.id)


def test_sqlalchemy_store_persists_due_deletion_physical_purge_across_recreation(tmp_path) -> None:
    from uuid import uuid4

    from changjuan_api.sqlalchemy_store import SqlAlchemyStore
    from changjuan_api.store import PhotoRecord
    from changjuan_core.ai.contracts import ClaimDraft, ClaimPriority, SupportStatus

    database_url = f"sqlite+pysqlite:///{tmp_path / 'purge.db'}"
    first = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"}, create_schema=True)
    user = first.upsert_user("wx_phase1", "Daughter")
    project = first.create_project(
        user.id,
        {
            "title": "Father's Story",
            "storyteller": {"display_name": "Father"},
            "themes": ["work"],
            "tier": "standard",
        },
    )
    claim = ClaimDraft(
        claim_text="父亲1978年进入县供销社工作",
        claim_type="work",
        claim_priority=ClaimPriority.P0,
        source_segment_ids=[uuid4()],
        confidence=0.88,
        support_status=SupportStatus.SUPPORTED,
        verification_status="confirmed",
    )
    first.save_claim(project.id, claim)
    correction = first.record_claim_correction(claim.id, user.id, {"action": "confirm"})
    first.generate_story(project.id)
    photo = PhotoRecord(
        id=uuid4(),
        project_id=project.id,
        oss_key=f"photos/{project.id}/family.jpg",
        thumbnail_oss_key=f"photos/{project.id}/thumbs/family.jpg",
        caption="Family photo",
    )
    first.record_photo(photo)
    deletion = first.request_deletion(project.id, requested_by_user_id=user.id)

    result = first.execute_due_deletion(deletion.id, at=deletion.execute_after_at)
    recreated = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"})

    assert result["status"] == "executed"
    assert recreated.deletion_requests[deletion.id].status == "executed"
    assert recreated.deletion_requests[deletion.id].executed_at == deletion.execute_after_at
    assert claim.id not in recreated.claims
    assert correction.id not in recreated.claim_corrections
    assert not [item for item in recreated.claim_evidence.values() if item["claim_id"] == claim.id]
    assert not [chapter for chapter in recreated.chapters.values() if chapter.project_id == project.id]
    assert not recreated.citations
    assert not [page for page in recreated.story_pages.values() if page.project_id == project.id]
    assert photo.id not in recreated.photos


def test_sqlalchemy_store_persists_support_ops_feedback_and_cost_records(tmp_path) -> None:
    from uuid import uuid4

    from changjuan_api.sqlalchemy_store import SqlAlchemyStore

    database_url = f"sqlite+pysqlite:///{tmp_path / 'ops.db'}"
    first = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"}, create_schema=True)
    user = first.upsert_user("wx_phase1", "Daughter")
    project = first.create_project(
        user.id,
        {
            "title": "Father's Story",
            "storyteller": {"display_name": "Father"},
            "themes": ["family"],
            "tier": "standard",
        },
    )
    generation_run_id = uuid4()

    feedback = first.create_feedback(
        project.id,
        user.id,
        {"nps_score": 9, "recommend": True, "issue_type": "quality", "body": "Great archive."},
    )
    ticket = first.create_support_ticket(
        project.id,
        user.id,
        {"priority": "P1", "category": "delivery", "body": "Need delivery help."},
    )
    ticket.status = "pending"
    ticket.admin_owner_id = first.admin_id
    first.save_support_ticket(ticket)
    note = first.create_internal_note(project.id, first.admin_id, {"note_type": "ops", "body": "Called family."})
    intervention = first.record_manual_intervention(
        project.id,
        first.admin_id,
        {"category": "fact_review", "minutes": 15, "body": "Checked timeline."},
    )
    cost = first.record_ai_cost(
        project.id,
        first.admin_id,
        {
            "task_type": "claim_extraction",
            "provider": "deepseek",
            "cost_cents": 88,
            "generation_run_id": generation_run_id,
        },
    )

    recreated = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"})

    assert recreated.feedback[feedback.id].project_id == project.id
    assert recreated.feedback[feedback.id].nps_score == 9
    assert recreated.feedback[feedback.id].recommend is True
    assert recreated.feedback[feedback.id].issue_type == "quality"
    assert recreated.feedback[feedback.id].body == "Great archive."
    assert recreated.support_tickets[ticket.id].status == "pending"
    assert recreated.support_tickets[ticket.id].priority == "P1"
    assert recreated.support_tickets[ticket.id].category == "delivery"
    assert recreated.support_tickets[ticket.id].admin_owner_id == first.admin_id
    assert recreated.internal_notes[note.id].body == "Called family."
    assert recreated.internal_notes[note.id].note_type == "ops"
    assert recreated.manual_interventions[intervention.id].minutes == 15
    assert recreated.manual_interventions[intervention.id].category == "fact_review"
    assert recreated.ai_costs[cost.id].provider == "deepseek"
    assert recreated.ai_costs[cost.id].cost_cents == 88
    assert recreated.ai_costs[cost.id].generation_run_id == generation_run_id


def test_sqlalchemy_store_persists_audio_transcripts_and_photo_analyses_across_recreation(tmp_path) -> None:
    from uuid import uuid4

    from changjuan_api.sqlalchemy_store import SqlAlchemyStore
    from changjuan_api.store import PhotoRecord

    database_url = f"sqlite+pysqlite:///{tmp_path / 'evidence.db'}"
    first = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"}, create_schema=True)
    user = first.upsert_user("wx_phase1", "Daughter")
    project = first.create_project(
        user.id,
        {
            "title": "Father's Story",
            "storyteller": {"display_name": "Father"},
            "themes": ["family"],
            "tier": "standard",
        },
    )
    session = first.create_session(project.id)
    chunk = first.record_audio_chunk(session.id, 2, 400, f"audio/{project.id}/chunk-2.webm")
    segment = first.record_transcript_segment(
        project.id,
        session.id,
        chunk.sequence_number,
        "elder",
        "我大约1978年去了供销社。",
        0.42,
        chunk.duration_ms,
    )
    photo = PhotoRecord(
        id=uuid4(),
        project_id=project.id,
        oss_key=f"photos/{project.id}/family.jpg",
        thumbnail_oss_key=f"photos/{project.id}/thumbnails/family.jpg",
        caption="Family photo",
    )
    first.record_photo(photo)
    analysis = first.create_photo_analysis(photo.id, "照片可能是在老家院子拍摄。", 0.73)

    deletion = first.request_deletion(project.id, requested_by_user_id=user.id)
    recreated = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"})

    assert recreated.session_recovery(session.id) == {
        "session_id": str(session.id),
        "last_accepted_sequence_number": 2,
        "missing_sequence_numbers": [0, 1],
        "buffered_chunk_count": 1,
    }
    assert recreated.audio_chunks[(session.id, 2)].oss_key == f"audio/{project.id}/chunk-2.webm"
    assert recreated.audio_chunks[(session.id, 2)].deleted_at is not None
    assert recreated.audio_chunks[(session.id, 2)].purge_after_at is not None
    assert recreated.transcript_segments[segment.id].audio_chunk_sequence_number == 2
    assert recreated.transcript_segments[segment.id].text == "我大约1978年去了供销社。"
    assert recreated.transcript_segments[segment.id].low_confidence_review is True
    assert recreated.transcript_segments[segment.id].deleted_at is not None
    assert recreated.photo_analyses[analysis.id].photo_id == photo.id
    assert recreated.photo_analyses[analysis.id].project_id == project.id
    assert recreated.photo_analyses[analysis.id].eligible_for_prompt is True
    assert recreated.photo_analyses[analysis.id].deleted_at is not None
    assert recreated.deletion_requests[deletion.id].status == "pending"


def test_sqlalchemy_store_persists_photos_and_soft_delete_across_recreation(tmp_path) -> None:
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from changjuan_api.sqlalchemy_store import SqlAlchemyStore
    from changjuan_api.store import PhotoRecord

    database_url = f"sqlite+pysqlite:///{tmp_path / 'photos.db'}"
    first = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"}, create_schema=True)
    user = first.upsert_user("wx_phase1", "Daughter")
    project = first.create_project(
        user.id,
        {
            "title": "Father's Story",
            "storyteller": {"display_name": "Father"},
            "themes": ["family"],
            "tier": "standard",
        },
    )
    photo = PhotoRecord(
        id=uuid4(),
        project_id=project.id,
        oss_key=f"photos/{project.id}/family.jpg",
        thumbnail_oss_key=f"photos/{project.id}/thumbnails/family.jpg",
        caption="Family photo",
    )

    first.record_photo(photo)
    deleted_at = datetime.now(UTC)
    photo.deleted_at = deleted_at
    photo.purge_after_at = deleted_at + timedelta(days=7)
    first.save_photo(photo)

    recreated = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"})

    assert recreated.photos[photo.id].oss_key == f"photos/{project.id}/family.jpg"
    assert recreated.photos[photo.id].thumbnail_oss_key == f"photos/{project.id}/thumbnails/family.jpg"
    assert recreated.photos[photo.id].caption == "Family photo"
    assert recreated.photos[photo.id].created_at is not None
    assert recreated.photos[photo.id].deleted_at is not None
    assert recreated.photos[photo.id].purge_after_at is not None


def test_sqlalchemy_store_persists_interview_session_status_across_recreation(tmp_path) -> None:
    from changjuan_api.sqlalchemy_store import SqlAlchemyStore

    database_url = f"sqlite+pysqlite:///{tmp_path / 'sessions.db'}"
    first = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"}, create_schema=True)
    user = first.upsert_user("wx_phase1", "Daughter")
    project = first.create_project(
        user.id,
        {
            "title": "Father's Story",
            "storyteller": {"display_name": "Father"},
            "themes": ["family"],
            "tier": "standard",
        },
    )

    session = first.create_session(project.id)
    session.status = "in_progress"
    first.save_session(session)

    recreated = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"})

    assert recreated.sessions[session.id].project_id == project.id
    assert recreated.sessions[session.id].status == "in_progress"
    assert recreated.sessions[session.id].created_at == session.created_at


def test_sqlalchemy_store_persists_consent_records_and_project_flags(tmp_path) -> None:
    from uuid import uuid4

    from changjuan_api.sqlalchemy_store import SqlAlchemyStore
    from changjuan_api.store import ConsentRecord

    database_url = f"sqlite+pysqlite:///{tmp_path / 'consent.db'}"
    first = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"}, create_schema=True)
    user = first.upsert_user("wx_phase1", "Daughter")
    project = first.create_project(
        user.id,
        {
            "title": "Father's Story",
            "storyteller": {"display_name": "Father"},
            "themes": ["work"],
            "tier": "standard",
        },
    )
    consent = ConsentRecord(
        id=uuid4(),
        project_id=project.id,
        user_id=user.id,
        consent_type="interview_consent",
        method="audio",
        evidence_oss_key="consents/interview/audio.wav",
    )

    first.record_consent(consent)

    recreated = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"})

    assert recreated.projects[project.id].has_interview_consent is True
    assert recreated.projects[project.id].has_family_sharing_consent is False
    assert recreated.consent_records[consent.id].project_id == project.id
    assert recreated.consent_records[consent.id].user_id == user.id
    assert recreated.consent_records[consent.id].consent_type == "interview_consent"
    assert recreated.consent_records[consent.id].method == "audio"
    assert recreated.consent_records[consent.id].evidence_oss_key == "consents/interview/audio.wav"


def test_sqlalchemy_store_persists_consent_withdrawal(tmp_path) -> None:
    from uuid import uuid4

    from changjuan_api.sqlalchemy_store import SqlAlchemyStore
    from changjuan_api.store import ConsentRecord

    database_url = f"sqlite+pysqlite:///{tmp_path / 'withdrawal.db'}"
    first = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"}, create_schema=True)
    user = first.upsert_user("wx_phase1", "Daughter")
    project = first.create_project(
        user.id,
        {
            "title": "Father's Story",
            "storyteller": {"display_name": "Father"},
            "themes": ["family"],
            "tier": "standard",
        },
    )
    consent = ConsentRecord(
        id=uuid4(),
        project_id=project.id,
        user_id=user.id,
        consent_type="family_sharing",
        method="text",
    )
    first.record_consent(consent)

    first.withdraw_consent(project.id, consent.id)
    recreated = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"})

    assert recreated.projects[project.id].has_family_sharing_consent is False
    assert recreated.consent_records[consent.id].withdrawn_at is not None
    assert recreated.consent_records[consent.id].minimized_at is not None


def test_sqlalchemy_store_persists_deletion_request_and_consent_minimization(tmp_path) -> None:
    from uuid import uuid4

    from changjuan_api.sqlalchemy_store import SqlAlchemyStore
    from changjuan_api.store import ConsentRecord

    database_url = f"sqlite+pysqlite:///{tmp_path / 'deletion.db'}"
    first = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"}, create_schema=True)
    user = first.upsert_user("wx_phase1", "Daughter")
    project = first.create_project(
        user.id,
        {
            "title": "Father's Story",
            "storyteller": {"display_name": "Father"},
            "themes": ["family"],
            "tier": "standard",
        },
    )
    consent = ConsentRecord(
        id=uuid4(),
        project_id=project.id,
        user_id=user.id,
        consent_type="interview_consent",
        method="audio",
        evidence_oss_key="consents/interview/audio.wav",
    )
    first.record_consent(consent)

    deletion = first.request_deletion(project.id, requested_by_user_id=user.id)
    recreated = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"})

    assert recreated.projects[project.id].deleted_at is not None
    assert recreated.projects[project.id].deletion_request_id == deletion.id
    assert recreated.deletion_requests[deletion.id].project_id == project.id
    assert recreated.deletion_requests[deletion.id].requested_by_user_id == user.id
    assert recreated.deletion_requests[deletion.id].status == "pending"
    assert recreated.consent_records[consent.id].evidence_oss_key is None
    assert recreated.consent_records[consent.id].minimized_at is not None


def test_sqlalchemy_store_persists_users_and_projects_across_store_recreation(tmp_path) -> None:
    from changjuan_api.sqlalchemy_store import SqlAlchemyStore

    database_url = f"sqlite+pysqlite:///{tmp_path / 'phase1.db'}"
    first = SqlAlchemyStore(
        database_url,
        whitelist_openids={"wx_phase1"},
        create_schema=True,
    )

    user = first.upsert_user(
        "wx_phase1",
        "Storyteller One",
        wx_unionid="union_phase1",
        avatar_url="https://cdn.example.test/avatar.png",
    )
    project = first.create_project(
        user.id,
        {
            "title": "Grandmother's Story",
            "storyteller": {"display_name": "Grandmother"},
            "themes": ["family", "migration"],
            "tier": "standard",
        },
    )

    recreated = SqlAlchemyStore(database_url, whitelist_openids={"wx_phase1"})

    assert recreated.users_by_openid["wx_phase1"] == user.id
    assert recreated.users[user.id].wx_unionid == "union_phase1"
    assert recreated.users[user.id].nickname == "Storyteller One"
    assert recreated.users[user.id].avatar_url == "https://cdn.example.test/avatar.png"
    assert recreated.projects[project.id].user_id == user.id
    assert recreated.projects[project.id].title == "Grandmother's Story"
    assert recreated.projects[project.id].storyteller == {"display_name": "Grandmother"}
    assert recreated.projects[project.id].themes == ["family", "migration"]
    assert recreated.projects[project.id].payment_status == "pending"
    assert recreated.projects[project.id].payment_cents == 49900


def test_create_app_wires_sqlalchemy_store_when_configured(monkeypatch, tmp_path) -> None:
    from changjuan_api import main as main_module
    from changjuan_api.auth import get_store
    from changjuan_api.settings import load_settings
    from changjuan_api.sqlalchemy_store import SqlAlchemyStore

    database_url = f"sqlite+pysqlite:///{tmp_path / 'api.db'}"
    monkeypatch.setattr(
        main_module,
        "settings",
        load_settings(
            {
                "STORE_BACKEND": "sqlalchemy",
                "SQLALCHEMY_CREATE_SCHEMA": "true",
                "DATABASE_URL": database_url,
            }
        ),
    )

    app = main_module.create_app()

    assert isinstance(app.dependency_overrides[get_store](), SqlAlchemyStore)


def test_sqlalchemy_store_persists_admin_login_sessions_across_store_recreation(tmp_path) -> None:
    from changjuan_api.sqlalchemy_store import SqlAlchemyStore

    database_url = f"sqlite+pysqlite:///{tmp_path / 'admin.db'}"
    first = SqlAlchemyStore(database_url, create_schema=True)

    admin = first.authenticate_admin("ops@changjuan.test", "phase1-admin")
    assert admin is not None
    first.record_admin_login(admin.id, "admin-access-token")

    recreated = SqlAlchemyStore(database_url)

    assert recreated.authenticate_admin("ops@changjuan.test", "phase1-admin").id == admin.id
    assert recreated.is_admin_session_active(admin.id, "admin-access-token") is True
