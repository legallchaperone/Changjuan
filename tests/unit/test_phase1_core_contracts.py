from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from changjuan_core.ai.capture import CaptureAction, CapturePolicy
from changjuan_core.ai.contracts import ClaimDraft, ClaimPriority, SupportStatus
from changjuan_core.ai.extraction import extract_claims_from_segments
from changjuan_core.ai.narrative import generate_narrative_draft
from changjuan_core.ai.verifier import VerificationGate, Verifier
from changjuan_core.audio.rate_limit import AudioChunkPolicy
from changjuan_core.compliance.audit import AuditLog, AuditSink
from changjuan_core.compliance.deletion import DeletionPlanner, ResourceRef
from changjuan_core.compliance.encryption import EncryptedValue, KMSPIIKeyProvider, PIIEncryptor
from changjuan_core.compliance.redaction import redact_pii
from changjuan_core.providers.router import ProviderCallError, ProviderRouter, TaskType
from changjuan_core.story.publish_gate import ProjectStatus, PublishGate, PublishGateInput
from changjuan_core.story.state_machine import ProjectStateMachine


def test_pii_encryptor_never_returns_plaintext_and_hashes_are_stable() -> None:
    encryptor = PIIEncryptor(master_key="phase1-test-kms-material")

    encrypted = encryptor.encrypt("13800138000")

    assert encrypted.ciphertext != b"13800138000"
    assert encrypted.key_id == "kms:local-dev"
    assert encryptor.decrypt(encrypted) == "13800138000"
    assert encryptor.hmac_sha256("13800138000") == encryptor.hmac_sha256("13800138000")
    assert encryptor.hmac_sha256("13800138000") != encryptor.hmac_sha256("13800138001")


def test_pii_kms_provider_requires_kms_key_and_round_trips_encoded_values() -> None:
    encryptor = KMSPIIKeyProvider("kms:phase1-prod").encryptor()

    encrypted = encryptor.encrypt("+8613800138000")
    decoded = EncryptedValue.decode(encrypted.encode())

    assert decoded.key_id == "kms:phase1-prod"
    assert encryptor.decrypt(decoded) == "+8613800138000"
    with pytest.raises(ValueError, match="must reference KMS"):
        KMSPIIKeyProvider("phase1-local-secret")


def test_redaction_removes_phone_and_identity_card_values() -> None:
    message = "用户张三手机号13800138000，身份证110101199003071234，项目继续"

    redacted = redact_pii(message)

    assert "13800138000" not in redacted
    assert "110101199003071234" not in redacted
    assert "[PHONE]" in redacted
    assert "[ID_CARD]" in redacted


def test_redaction_removes_e164_china_phone_values() -> None:
    message = "用户手机号+8613800138000，备用号码+86 13900139000"

    redacted = redact_pii(message)

    assert "+8613800138000" not in redacted
    assert "+86 13900139000" not in redacted
    assert redacted.count("[PHONE]") == 2


def test_audit_sink_recursively_redacts_pii_without_flattening_metadata() -> None:
    sink = AuditSink()

    log = sink.record(
        AuditLog(
            action="admin.note",
            resource_type="project",
            reason="人工备注提到手机号13800138000",
            metadata={
                "contact": {
                    "phone": "13800138000",
                    "identity": "110101199003071234",
                },
                "history": ["复核13800138000", {"id_card": "110101199003071234"}],
            },
        )
    )

    assert log.reason == "人工备注提到手机号[PHONE]"
    assert log.metadata["contact"] == {"phone": "[PHONE]", "identity": "[ID_CARD]"}
    assert log.metadata["history"] == ["复核[PHONE]", {"id_card": "[ID_CARD]"}]


def test_project_state_machine_rejects_illegal_transition() -> None:
    machine = ProjectStateMachine()

    assert machine.transition("created", "payment_marked").value == "payment_marked"

    with pytest.raises(ValueError, match="illegal project transition"):
        machine.transition("created", "published")


def test_audio_chunk_policy_allows_300_to_500ms_and_240_chunks_per_minute() -> None:
    policy = AudioChunkPolicy()

    for _ in range(240):
        policy.accept_chunk(duration_ms=300, received_at=datetime(2026, 5, 16, tzinfo=UTC))

    with pytest.raises(ValueError, match="rate limit"):
        policy.accept_chunk(duration_ms=300, received_at=datetime(2026, 5, 16, tzinfo=UTC))

    with pytest.raises(ValueError, match="300-500ms"):
        AudioChunkPolicy().accept_chunk(
            duration_ms=100, received_at=datetime(2026, 5, 16, tzinfo=UTC)
        )


def test_capture_policy_turns_stop_phrase_into_session_end_decision() -> None:
    decision = CapturePolicy().decide(transcript_text="今天先到这里吧，我有点累了。")

    assert decision.action == CaptureAction.END_SESSION
    assert decision.recommended_session_status == "completed_short"
    assert decision.reason == "storyteller_requested_stop"


def test_capture_policy_switches_topic_after_refusal() -> None:
    decision = CapturePolicy().decide(transcript_text="这段我不想说，别问了。")

    assert decision.action == CaptureAction.SWITCH_TOPIC
    assert decision.reason == "storyteller_refused_topic"
    assert decision.follow_up_instruction == "switch topics immediately and do not ask about this topic again"


def test_capture_policy_treats_five_to_ten_second_silence_as_valid_wait_time() -> None:
    decision = CapturePolicy().decide(transcript_text="", silence_ms=7000)

    assert decision.action == CaptureAction.WAIT
    assert decision.reason == "valid_storyteller_silence"
    assert decision.follow_up_instruction == "wait without interrupting"


def test_provider_router_fails_over_after_three_primary_failures() -> None:
    calls: list[str] = []

    def primary(_: dict) -> dict:
        calls.append("primary")
        raise ProviderCallError("volcengine down")

    def backup(_: dict) -> dict:
        calls.append("backup")
        return {"ok": True}

    router = ProviderRouter()
    router.register(TaskType.REALTIME_STT, primary=primary, backup=backup)

    result = router.call(TaskType.REALTIME_STT, {"chunk": "..."}, prompt_version="stt-v1")

    assert result.output == {"ok": True}
    assert calls == ["primary", "primary", "primary", "backup"]
    assert result.provider_name == "backup"
    assert result.prompt_hash


def test_provider_router_records_actual_provider_names_in_generation_runs() -> None:
    def primary(_: dict) -> dict:
        return {"text": "1978年进了县供销社", "provider_request_id": "volcengine-live-req-001"}

    def backup(_: dict) -> dict:
        return {"text": "backup"}

    router = ProviderRouter()
    router.register(
        TaskType.REALTIME_STT,
        primary=primary,
        backup=backup,
        primary_name="volcengine_streaming_asr",
        backup_name="aliyun_paraformer",
    )

    result = router.call(TaskType.REALTIME_STT, {"chunk": "..."}, prompt_version="stt-v1")

    assert result.provider_name == "volcengine_streaming_asr"
    assert result.raw_input_oss_key.startswith(f"generation-runs/{result.id}/")
    assert result.raw_output_oss_key.startswith(f"generation-runs/{result.id}/")
    assert result.status == "succeeded"
    assert result.completed_at >= result.created_at
    assert result.latency_ms > 0
    assert result.provider_request_id == "volcengine-live-req-001"
    assert router.generation_runs == [result]


def test_provider_router_writes_raw_input_and_output_artifacts_to_storage_sink() -> None:
    stored_artifacts: dict[str, dict] = {}

    def artifact_sink(key: str, payload: dict) -> None:
        stored_artifacts[key] = payload

    router = ProviderRouter(artifact_sink=artifact_sink)
    router.register(
        TaskType.CLAIM_EXTRACTION,
        primary=lambda _: {"claims": []},
        backup=lambda _: {"claims": ["backup"]},
        primary_name="deepseek",
        backup_name="doubao",
    )

    result = router.call(
        TaskType.CLAIM_EXTRACTION,
        {"transcript_segment_ids": ["seg-1"]},
        prompt_version="extraction-agent-v1",
    )

    assert stored_artifacts[result.raw_input_oss_key] == {
        "task_type": "claim_extraction",
        "provider_name": "deepseek",
        "prompt_version": "extraction-agent-v1",
        "prompt_hash": result.prompt_hash,
        "payload": {"transcript_segment_ids": ["seg-1"]},
    }
    assert stored_artifacts[result.raw_output_oss_key] == {
        "task_type": "claim_extraction",
        "provider_name": "deepseek",
        "prompt_version": "extraction-agent-v1",
        "prompt_hash": result.prompt_hash,
        "output": {"claims": []},
    }


def test_provider_router_emits_generation_runs_to_persistence_sink() -> None:
    project_id = uuid4()
    persisted_runs = []

    router = ProviderRouter(generation_run_sink=persisted_runs.append)
    router.register(
        TaskType.NARRATIVE_GENERATION,
        primary=lambda _: {"chapters": []},
        backup=lambda _: {"chapters": ["backup"]},
        primary_name="deepseek",
        backup_name="doubao",
    )

    result = router.call(
        TaskType.NARRATIVE_GENERATION,
        {"project_id": str(project_id)},
        prompt_version="narrative-agent-v1",
        project_id=project_id,
    )

    assert result.project_id == project_id
    assert persisted_runs == [result]


def test_extraction_populates_p0_entities_and_source_evidence() -> None:
    segment_id = uuid4()

    output = extract_claims_from_segments(
        [{"id": str(segment_id), "text": "父亲1978年进入县供销社工作。", "confidence": 0.82}]
    )

    assert len(output.claims) == 1
    claim = output.claims[0]
    assert claim.claim_priority == ClaimPriority.P0
    assert claim.source_segment_ids == [segment_id]
    assert claim.entities == {
        "person": ["父亲"],
        "organization": ["县供销社"],
        "date": ["1978年"],
    }
    assert claim.embedding is not None
    assert len(claim.embedding) == 16
    assert all(-1 <= value <= 1 for value in claim.embedding)


def test_extraction_merges_duplicate_claims_without_losing_evidence() -> None:
    first_segment_id = uuid4()
    second_segment_id = uuid4()

    output = extract_claims_from_segments(
        [
            {"id": str(first_segment_id), "text": "父亲1978年进入县供销社工作。", "confidence": 0.74},
            {"id": str(second_segment_id), "text": "父亲1978年进入县供销社工作。", "confidence": 0.91},
        ]
    )

    assert len(output.claims) == 1
    claim = output.claims[0]
    assert claim.source_segment_ids == [first_segment_id, second_segment_id]
    assert claim.confidence == 0.91
    assert claim.support_status == SupportStatus.SUPPORTED


def test_verifier_blocks_unsupported_claims_and_missing_family_confirmation() -> None:
    claim_id = uuid4()
    chapter_id = uuid4()
    verifier = Verifier()

    result = verifier.verify(
        claims=[
            ClaimDraft(
                id=claim_id,
                claim_text="父亲1978年进入县供销社工作",
                claim_type="work",
                claim_priority=ClaimPriority.P0,
                source_segment_ids=[],
                confidence=0.82,
                support_status=SupportStatus.UNSUPPORTED,
                verification_status="pending",
            )
        ],
        chapters=[
            {
                "id": str(chapter_id),
                "title": "工作与迁徙",
                "body": "父亲1978年进入县供销社工作。",
                "claim_ids": [str(claim_id)],
            }
        ],
        citations=[],
    )

    gates = {issue.gate for issue in result.issues}
    assert result.passed is False
    assert VerificationGate.UNSUPPORTED_CLAIM in gates
    assert VerificationGate.FAMILY_CONFIRMATION in gates


def test_verifier_blocks_factful_sentence_without_claim_id_coverage() -> None:
    claim_id = uuid4()
    chapter_id = uuid4()

    result = Verifier().verify(
        claims=[
            ClaimDraft(
                id=claim_id,
                claim_text="父亲1978年进入县供销社工作",
                claim_type="work",
                claim_priority=ClaimPriority.P0,
                source_segment_ids=[uuid4()],
                confidence=0.86,
                support_status=SupportStatus.SUPPORTED,
                verification_status="confirmed",
            )
        ],
        chapters=[
            {
                "id": str(chapter_id),
                "title": "工作与迁徙",
                "body": "父亲1978年进入县供销社工作。父亲1980年调到上海。",
                "claim_ids": [str(claim_id)],
            }
        ],
        citations=[],
    )

    assert result.passed is False
    assert any(issue.gate == VerificationGate.CITATION_COVERAGE for issue in result.issues)


def test_narrative_uses_only_confirmed_claims_and_keeps_unsure_claims_in_appendix() -> None:
    confirmed = ClaimDraft(
        id=uuid4(),
        claim_text="父亲1978年进入县供销社工作",
        claim_type="work",
        claim_priority=ClaimPriority.P0,
        source_segment_ids=[uuid4()],
        confidence=0.9,
        support_status=SupportStatus.SUPPORTED,
        verification_status="confirmed",
    )
    unsure = ClaimDraft(
        id=uuid4(),
        claim_text="父亲可能在1981年调到上海",
        claim_type="migration",
        claim_priority=ClaimPriority.P0,
        source_segment_ids=[uuid4()],
        confidence=0.55,
        support_status=SupportStatus.SUPPORTED,
        verification_status="marked_unsure",
    )

    draft = generate_narrative_draft([confirmed, unsure])

    story_bodies = "\n".join(ch.body for ch in draft.chapters if ch.slug != "unconfirmed-appendix")
    appendix = next(ch for ch in draft.chapters if ch.slug == "unconfirmed-appendix")
    assert confirmed.claim_text in story_bodies
    assert unsure.claim_text not in story_bodies
    assert unsure.claim_text in appendix.body


def test_narrative_excludes_confirmed_claim_without_source_evidence() -> None:
    supported = ClaimDraft(
        id=uuid4(),
        claim_text="父亲1978年进入县供销社工作",
        claim_type="work",
        claim_priority=ClaimPriority.P0,
        source_segment_ids=[uuid4()],
        confidence=0.9,
        support_status=SupportStatus.SUPPORTED,
        verification_status="confirmed",
    )
    no_evidence = ClaimDraft(
        id=uuid4(),
        claim_text="父亲1980年进入另一家单位工作",
        claim_type="work",
        claim_priority=ClaimPriority.P0,
        source_segment_ids=[],
        confidence=0.9,
        support_status=SupportStatus.SUPPORTED,
        verification_status="confirmed",
    )

    draft = generate_narrative_draft([supported, no_evidence])

    story_bodies = "\n".join(ch.body for ch in draft.chapters if ch.slug != "unconfirmed-appendix")
    story_claim_ids = {claim_id for chapter in draft.chapters for claim_id in chapter.claim_ids}
    assert supported.claim_text in story_bodies
    assert no_evidence.claim_text not in story_bodies
    assert no_evidence.id not in story_claim_ids


def test_narrative_excludes_unsupported_confirmed_claim() -> None:
    unsupported = ClaimDraft(
        id=uuid4(),
        claim_text="父亲1980年进入另一家单位工作",
        claim_type="work",
        claim_priority=ClaimPriority.P0,
        source_segment_ids=[uuid4()],
        confidence=0.9,
        support_status=SupportStatus.UNSUPPORTED,
        verification_status="confirmed",
    )

    draft = generate_narrative_draft([unsupported])

    story_bodies = "\n".join(ch.body for ch in draft.chapters)
    story_claim_ids = {claim_id for chapter in draft.chapters for claim_id in chapter.claim_ids}
    assert unsupported.claim_text not in story_bodies
    assert unsupported.id not in story_claim_ids


def test_publish_gate_requires_second_consent_resolved_blocks_and_disabled_links() -> None:
    result = PublishGate().evaluate(
        PublishGateInput(
            project_status=ProjectStatus.ELDER_SECOND_CONSENT_PENDING,
            p0_claims_total=8,
            p0_claims_processed=8,
            unresolved_block_issues=0,
            has_family_sharing_consent=True,
            story_page_generated=True,
            share_links_disabled=True,
        )
    )

    assert result.allowed is True

    blocked = PublishGate().evaluate(
        PublishGateInput(
            project_status=ProjectStatus.ELDER_SECOND_CONSENT_PENDING,
            p0_claims_total=8,
            p0_claims_processed=8,
            unresolved_block_issues=1,
            has_family_sharing_consent=True,
            story_page_generated=True,
            share_links_disabled=True,
        )
    )
    assert blocked.allowed is False
    assert "unresolved block-level verification issues" in blocked.reasons

    enabled_link = PublishGate().evaluate(
        PublishGateInput(
            project_status=ProjectStatus.ELDER_SECOND_CONSENT_PENDING,
            p0_claims_total=8,
            p0_claims_processed=8,
            unresolved_block_issues=0,
            has_family_sharing_consent=True,
            story_page_generated=True,
            share_links_disabled=False,
        )
    )
    assert enabled_link.allowed is False
    assert "share_links must remain disabled until publish" in enabled_link.reasons


def test_deletion_planner_soft_deletes_now_and_purges_after_seven_days() -> None:
    now = datetime(2026, 5, 16, 12, 0, tzinfo=UTC)
    resources = [
        ResourceRef(table="audio_recordings", id=uuid4(), oss_key="audio/a.wav"),
        ResourceRef(table="photos", id=uuid4(), oss_key="photos/a.jpg"),
    ]

    plan = DeletionPlanner(now_provider=lambda: now).plan_project_deletion(uuid4(), resources)

    assert plan.requested_at == now
    assert all(item.deleted_at == now for item in plan.items)
    assert all(item.purge_after_at == now + timedelta(days=7) for item in plan.items)
    assert [item.oss_key for item in plan.items] == ["audio/a.wav", "photos/a.jpg"]
