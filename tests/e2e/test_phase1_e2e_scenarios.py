from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from changjuan_api.main import create_app
from changjuan_core.ai.contracts import ClaimDraft, ClaimPriority, SupportStatus
from changjuan_core.ai.extraction import detect_contradictions, extract_claims_from_segments
from changjuan_core.ai.verifier import Verifier
from changjuan_core.audio.rate_limit import AudioChunkPolicy
from changjuan_core.compliance.deletion import DeletionPlanner, ResourceRef
from changjuan_core.providers.router import ProviderCallError, ProviderRouter, TaskType
from changjuan_core.story.publish_gate import ProjectStatus, PublishGate, PublishGateInput
from fastapi.testclient import TestClient


def _login_user(client: TestClient) -> str:
    return client.post(
        "/api/v1/auth/wx-login",
        json={"wx_openid": "wx_phase1", "nickname": "女儿"},
    ).json()["data"]["access_token"]


def _login_admin(client: TestClient) -> str:
    return client.post(
        "/api/v1/admin/auth/login",
        json={"email": "ops@changjuan.test", "password": "phase1-admin"},
    ).json()["data"]["access_token"]


def _create_project(client: TestClient, token: str) -> str:
    return client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "storyteller": {"display_name": "爸爸", "relation_to_payer": "father"},
            "title": "爸爸的故事",
            "themes": ["work"],
            "tier": "standard",
        },
    ).json()["data"]["project_id"]


def _give_interview_consent(client: TestClient, project_id: str, token: str) -> None:
    response = client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "text"},
    )
    assert response.status_code == 200


def _upload_minimum_photos(client: TestClient, project_id: str, token: str) -> None:
    for index in range(3):
        response = client.post(
            f"/api/v1/projects/{project_id}/photos/complete",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "oss_key": f"photos/{project_id}/family-{index}.jpg",
                "caption": f"家庭照片 {index + 1}",
            },
        )
        assert response.status_code == 200


def test_e2e_happy_path_short_interview() -> None:
    client = TestClient(create_app())
    user_token = _login_user(client)
    admin_token = _login_admin(client)
    project_id = _create_project(client, user_token)

    client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    _give_interview_consent(client, project_id, user_token)
    _upload_minimum_photos(client, project_id, user_token)
    session = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {user_token}"},
        json={},
    ).json()["data"]
    client.post(
        f"/api/v1/interview-sessions/{session['session_id']}/start",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    client.post(
        f"/api/v1/interview-sessions/{session['session_id']}/end",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"status": "completed_short"},
    )
    claim_id = client.get(
        f"/api/v1/projects/{project_id}/corrections/pending",
        headers={"Authorization": f"Bearer {user_token}"},
    ).json()["data"]["claims"][0]["id"]
    client.post(
        f"/api/v1/claims/{claim_id}/corrections",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"action": "confirm"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/corrections/complete",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    draft = client.post(
        f"/api/v1/projects/{project_id}/drafts/generate",
        headers={"Authorization": f"Bearer {user_token}"},
    ).json()["data"]
    assert draft["chapters"]
    assert client.post(
        f"/api/v1/projects/{project_id}/verify",
        headers={"Authorization": f"Bearer {user_token}"},
    ).json()["data"]["issues"] == []
    client.post(
        f"/api/v1/projects/{project_id}/request-second-consent",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"consent_type": "family_sharing"},
    )
    published = client.post(
        f"/api/v1/projects/{project_id}/publish",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert published.status_code == 200
    assert published.json()["data"]["status"] == "published"


def test_e2e_storyteller_aborts_early() -> None:
    client = TestClient(create_app())
    user_token = _login_user(client)
    admin_token = _login_admin(client)
    project_id = _create_project(client, user_token)
    client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    _give_interview_consent(client, project_id, user_token)
    _upload_minimum_photos(client, project_id, user_token)
    session_id = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {user_token}"},
        json={},
    ).json()["data"]["session_id"]
    client.post(
        f"/api/v1/interview-sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    ended = client.post(
        f"/api/v1/interview-sessions/{session_id}/end",
        headers={"Authorization": f"Bearer {user_token}"},
        json={"status": "aborted_by_storyteller"},
    )
    assert ended.json()["data"]["status"] == "aborted_by_storyteller"


def test_e2e_dialect_low_confidence() -> None:
    segment_id = uuid4()
    output = extract_claims_from_segments(
        [{"id": str(segment_id), "text": "我大约1978年进了供销社。", "confidence": 0.42}]
    )

    assert output.claims[0].support_status == SupportStatus.NEEDS_REVIEW
    assert output.claims[0].claim_priority == ClaimPriority.P0


def test_e2e_contradictory_claims() -> None:
    first = ClaimDraft(
        claim_text="父亲1978年进入县供销社工作",
        claim_type="work",
        claim_priority=ClaimPriority.P0,
        source_segment_ids=[uuid4()],
        confidence=0.8,
        support_status=SupportStatus.SUPPORTED,
    )
    second = ClaimDraft(
        claim_text="父亲1980年进入县供销社工作",
        claim_type="work",
        claim_priority=ClaimPriority.P0,
        source_segment_ids=[uuid4()],
        confidence=0.8,
        support_status=SupportStatus.SUPPORTED,
    )

    contradictions = detect_contradictions([first, second])

    assert contradictions
    assert contradictions[0]["field"] == "date"


def test_e2e_manual_payment_required() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    project_id = _create_project(client, token)

    response = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert response.status_code == 409
    assert response.json()["code"] == 40901


def test_e2e_audio_chunk_rate_limit_normal_case() -> None:
    policy = AudioChunkPolicy(max_chunks_per_minute=240)
    start = datetime(2026, 5, 16, 8, 0, tzinfo=UTC)

    for index in range(200):
        policy.accept_chunk(duration_ms=300, received_at=start + timedelta(milliseconds=300 * index))

    assert policy.chunk_count == 200


def test_e2e_provider_failover() -> None:
    router = ProviderRouter()

    def primary(_: dict) -> dict:
        raise ProviderCallError("primary unavailable")

    def backup(_: dict) -> dict:
        return {"text": "backup transcript"}

    router.register(TaskType.BATCH_TRANSCRIPTION, primary=primary, backup=backup)

    result = router.call(TaskType.BATCH_TRANSCRIPTION, {"oss_key": "audio.wav"})

    assert result.output["text"] == "backup transcript"
    assert result.attempts == 4


def test_e2e_deletion_request_t_plus_7() -> None:
    now = datetime(2026, 5, 16, tzinfo=UTC)
    resource = ResourceRef(table="pdf_exports", id=uuid4(), oss_key="exports/story.pdf")
    planner = DeletionPlanner(now_provider=lambda: now)

    deletion = planner.plan_project_deletion(uuid4(), [resource])
    due = planner.due_for_purge(deletion, at=now + timedelta(days=7, seconds=1))

    assert due == deletion.items


def test_e2e_admin_cannot_force_publish() -> None:
    blocked = PublishGate().evaluate(
        PublishGateInput(
            project_status=ProjectStatus.STORY_GENERATED,
            p0_claims_total=1,
            p0_claims_processed=1,
            unresolved_block_issues=0,
            has_family_sharing_consent=False,
            story_page_generated=True,
            share_links_disabled=True,
        )
    )

    assert blocked.allowed is False
    assert "project must be elder_second_consent_pending" in blocked.reasons


def test_e2e_publish_blocked_without_second_consent() -> None:
    blocked = PublishGate().evaluate(
        PublishGateInput(
            project_status=ProjectStatus.VERIFIED,
            p0_claims_total=1,
            p0_claims_processed=1,
            unresolved_block_issues=0,
            has_family_sharing_consent=True,
            story_page_generated=True,
            share_links_disabled=True,
        )
    )

    assert blocked.allowed is False
    assert "project must be elder_second_consent_pending" in blocked.reasons


def test_e2e_publish_blocked_with_unresolved_issue() -> None:
    blocked = PublishGate().evaluate(
        PublishGateInput(
            project_status=ProjectStatus.ELDER_SECOND_CONSENT_PENDING,
            p0_claims_total=1,
            p0_claims_processed=1,
            unresolved_block_issues=1,
            has_family_sharing_consent=True,
            story_page_generated=True,
            share_links_disabled=True,
        )
    )

    assert blocked.allowed is False
    assert "unresolved block-level verification issues" in blocked.reasons


def test_e2e_sensitive_content_workflow_blocks_until_resolved() -> None:
    claim_id = uuid4()
    result = Verifier().verify(
        claims=[
            ClaimDraft(
                id=claim_id,
                claim_text="这是一条敏感家庭事件",
                claim_type="sensitive",
                claim_priority=ClaimPriority.P0,
                source_segment_ids=[uuid4()],
                confidence=0.9,
                support_status=SupportStatus.SUPPORTED,
                verification_status="confirmed",
                sensitivity_level="highly_sensitive",
                human_reviewed=False,
            )
        ],
        chapters=[],
        citations=[],
    )

    assert result.passed is False
    assert any(issue.gate.value == "sensitive_content" for issue in result.issues)
