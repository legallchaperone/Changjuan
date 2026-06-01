from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from changjuan_api.auth import get_store
from changjuan_api.main import create_app
from changjuan_api.settings import settings
from changjuan_api.store import AdminUserRecord, _hash_secret
from changjuan_core.ai.contracts import ClaimDraft, ClaimPriority, SupportStatus
from changjuan_core.compliance.encryption import EncryptedValue, KMSPIIKeyProvider, PIIEncryptor
from cryptography.exceptions import InvalidTag
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


def _login_admin_with_role(app, client: TestClient, role: str) -> str:
    store = app.dependency_overrides[get_store]()
    admin_user_id = uuid4()
    email = f"{role}-{admin_user_id}@changjuan.test"
    store.admin_users[admin_user_id] = AdminUserRecord(
        id=admin_user_id,
        email=email,
        password_hash=_hash_secret("phase1-admin"),
        role=role,
    )
    login = client.post(
        "/api/v1/admin/auth/login",
        json={"email": email, "password": "phase1-admin"},
    )
    assert login.status_code == 200
    return login.json()["data"]["access_token"]


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


def _audio_oss_key(project_id: str, session_id: str, sequence_number: int, extension: str = "mp3") -> str:
    return f"audio/{project_id}/interview-{session_id}-{sequence_number}.{extension}"


def _published_story(client: TestClient, token: str) -> tuple[str, str]:
    project_id = _create_project(client, token)
    admin_token = _login_admin(client)
    payment = client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    assert payment.status_code == 200
    consent = client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "text"},
    )
    assert consent.status_code == 200
    claim_id = client.get(
        f"/api/v1/projects/{project_id}/corrections/pending",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["claims"][0]["id"]
    correction = client.post(
        f"/api/v1/claims/{claim_id}/corrections",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "confirm"},
    )
    assert correction.status_code == 200
    completed = client.post(
        f"/api/v1/projects/{project_id}/corrections/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert completed.status_code == 200
    draft = client.post(
        f"/api/v1/projects/{project_id}/drafts/generate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert draft.status_code == 200
    story_page_id = draft.json()["data"]["story_page_id"]
    verified = client.post(
        f"/api/v1/projects/{project_id}/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert verified.status_code == 200
    second_consent_requested = client.post(
        f"/api/v1/projects/{project_id}/request-second-consent",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert second_consent_requested.status_code == 200
    sharing_consent = client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "family_sharing", "method": "text"},
    )
    assert sharing_consent.status_code == 200
    published = client.post(
        f"/api/v1/projects/{project_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert published.status_code == 200
    return project_id, story_page_id


def _upload_minimum_photos(client: TestClient, project_id: str, token: str, count: int = 3) -> None:
    for index in range(count):
        response = client.post(
            f"/api/v1/projects/{project_id}/photos/complete",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "oss_key": f"photos/{project_id}/family-{index}.jpg",
                "caption": f"家庭照片 {index + 1}",
            },
        )
        assert response.status_code == 200


def test_create_project_returns_manual_payment_contract() -> None:
    client = TestClient(create_app())

    login = client.post("/api/v1/auth/wx-login", json={"wx_openid": "wx_phase1", "nickname": "女儿"})
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]

    response = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "storyteller": {
                "display_name": "爸爸",
                "relation_to_payer": "father",
                "birth_year": 1954,
                "birth_place": "江苏南通",
                "current_city": "上海",
                "primary_dialect": "mandarin",
            },
            "title": "爸爸的故事",
            "themes": ["childhood", "work", "family"],
            "tier": "standard",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    UUID(body["data"]["project_id"])
    assert body["data"] == {
        **body["data"],
        "status": "created",
        "payment_required": True,
        "payment_mode": "manual",
        "next_action": "complete_manual_deposit",
    }


def test_wx_login_encrypts_phone_and_stores_only_lookup_hash() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    phone = "+8613800138000"

    login = client.post(
        "/api/v1/auth/wx-login",
        json={"wx_openid": "wx_phase1", "nickname": "女儿", "phone_e164": phone},
    )

    assert login.status_code == 200
    user_id = UUID(login.json()["data"]["user_id"])
    user = store.users[user_id]
    assert getattr(user, "phone_e164_enc", None)
    assert getattr(user, "phone_hash", None)
    assert len(user.phone_hash) == 64
    assert phone not in repr(user.__dict__)
    assert "phone_e164" not in login.json()["data"]


def test_wx_login_phone_encryption_uses_pii_kms_key_not_jwt_secret() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    phone = "+8613800138000"

    login = client.post(
        "/api/v1/auth/wx-login",
        json={"wx_openid": "wx_phase1", "nickname": "女儿", "phone_e164": phone},
    )

    assert login.status_code == 200
    user = store.users[UUID(login.json()["data"]["user_id"])]
    encrypted = EncryptedValue.decode(user.phone_e164_enc)
    assert encrypted.key_id == settings.pii_kms_key_id
    assert KMSPIIKeyProvider(settings.pii_kms_key_id).encryptor().decrypt(encrypted) == phone
    with pytest.raises(InvalidTag):
        PIIEncryptor(master_key=settings.jwt_secret, key_id=settings.pii_kms_key_id).decrypt(encrypted)


def test_wx_login_persists_phase1_profile_fields() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()

    login = client.post(
        "/api/v1/auth/wx-login",
        json={
            "wx_openid": "wx_phase1",
            "wx_unionid": "union_phase1",
            "nickname": "女儿",
            "avatar_url": "https://cdn.example.test/avatar.jpg",
        },
    )

    assert login.status_code == 200
    user = store.users[UUID(login.json()["data"]["user_id"])]
    assert getattr(user, "wx_unionid", None) == "union_phase1"
    assert getattr(user, "avatar_url", None) == "https://cdn.example.test/avatar.jpg"


def test_wx_login_user_record_tracks_updated_and_deleted_schema_fields() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()

    first_login = client.post(
        "/api/v1/auth/wx-login",
        json={"wx_openid": "wx_phase1", "nickname": "女儿"},
    )
    assert first_login.status_code == 200
    user = store.users[UUID(first_login.json()["data"]["user_id"])]
    assert user.deleted_at is None
    assert user.updated_at >= user.created_at
    original_created_at = user.created_at
    user.updated_at = datetime(2026, 1, 1, tzinfo=UTC)

    second_login = client.post(
        "/api/v1/auth/wx-login",
        json={
            "wx_openid": "wx_phase1",
            "nickname": "更新后的女儿",
            "avatar_url": "https://cdn.example.test/new-avatar.jpg",
        },
    )

    assert second_login.status_code == 200
    assert second_login.json()["data"]["user_id"] == str(user.id)
    assert user.created_at == original_created_at
    assert user.updated_at > datetime(2026, 1, 1, tzinfo=UTC)
    assert user.nickname == "更新后的女儿"
    assert user.avatar_url == "https://cdn.example.test/new-avatar.jpg"


def test_wx_login_accepts_mapped_wechat_code_without_client_supplied_openid(monkeypatch) -> None:
    from changjuan_api import main as api_main

    monkeypatch.setattr(
        api_main.settings,
        "wechat_login_code_map",
        {"devtools-login-code": {"openid": "wx_phase1", "unionid": "union_from_code"}},
        raising=False,
    )
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()

    login = client.post(
        "/api/v1/auth/wx-login",
        json={"wx_code": "devtools-login-code", "nickname": "女儿"},
    )

    assert login.status_code == 200
    user = store.users[UUID(login.json()["data"]["user_id"])]
    assert user.wx_openid == "wx_phase1"
    assert user.wx_unionid == "union_from_code"


def test_wx_login_rejects_client_supplied_openid_in_production(monkeypatch) -> None:
    from changjuan_api import main as api_main

    monkeypatch.setattr(api_main.settings, "app_env", "production", raising=False)
    app = create_app()
    client = TestClient(app)

    rejected = client.post(
        "/api/v1/auth/wx-login",
        json={"wx_openid": "wx_phase1", "nickname": "女儿"},
    )

    assert rejected.status_code == 422
    assert rejected.json()["code"] == 42201
    assert "wx_code" in rejected.json()["message"]


def test_wx_login_uses_runtime_pilot_whitelist(monkeypatch) -> None:
    from changjuan_api import main as api_main

    monkeypatch.setattr(api_main.settings, "pilot_whitelist_openids", {"wx_runtime_pilot"})
    app = create_app()
    client = TestClient(app)

    accepted = client.post(
        "/api/v1/auth/wx-login",
        json={"wx_openid": "wx_runtime_pilot", "nickname": "内测用户"},
    )
    hardcoded_default = client.post(
        "/api/v1/auth/wx-login",
        json={"wx_openid": "wx_phase1", "nickname": "默认用户"},
    )

    assert accepted.status_code == 200
    assert hardcoded_default.status_code == 403
    assert hardcoded_default.json()["code"] == 40301


def test_admin_login_persists_session_and_last_login() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()

    login = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "ops@changjuan.test", "password": "phase1-admin"},
    )

    assert login.status_code == 200
    admin_user_id = UUID(login.json()["data"]["admin_user_id"])
    assert admin_user_id in store.admin_users
    assert store.admin_users[admin_user_id].last_login_at is not None
    assert len(store.admin_sessions) == 1
    session = next(iter(store.admin_sessions.values()))
    assert session.admin_user_id == admin_user_id
    assert session.token_hash
    assert login.json()["data"]["access_token"] not in session.token_hash
    assert session.expires_at > session.created_at
    login_log = next(log for log in store.audit.logs if log.action == "admin.login")
    assert login_log.actor_id == admin_user_id
    assert login_log.resource_type == "admin_session"
    assert login_log.resource_id == session.id


def test_admin_endpoints_require_persisted_active_admin_session() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    admin_token = _login_admin(client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    accepted = client.get("/api/v1/admin/projects", headers=headers)
    store.admin_sessions.clear()
    missing_session = client.get("/api/v1/admin/projects", headers=headers)

    assert accepted.status_code == 200
    assert missing_session.status_code == 401
    assert missing_session.json()["code"] == 40101


def test_admin_endpoints_reject_expired_or_disabled_admin_sessions() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()

    login = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "ops@changjuan.test", "password": "phase1-admin"},
    )
    admin_token = login.json()["data"]["access_token"]
    admin_user_id = UUID(login.json()["data"]["admin_user_id"])
    session = next(iter(store.admin_sessions.values()))
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    expired = client.get(
        "/api/v1/admin/projects",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    fresh_login = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "ops@changjuan.test", "password": "phase1-admin"},
    )
    fresh_token = fresh_login.json()["data"]["access_token"]
    store.admin_users[admin_user_id].enabled = False
    disabled = client.get(
        "/api/v1/admin/projects",
        headers={"Authorization": f"Bearer {fresh_token}"},
    )

    assert expired.status_code == 401
    assert expired.json()["code"] == 40101
    assert disabled.status_code == 401
    assert disabled.json()["code"] == 40101


def test_readonly_admin_can_read_admin_dashboard_but_cannot_write() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    user_token = _login_user(client)
    project_id = _create_project(client, user_token)
    readonly_token = _login_admin_with_role(app, client, "readonly")
    readonly_headers = {"Authorization": f"Bearer {readonly_token}"}

    projects = client.get("/api/v1/admin/projects", headers=readonly_headers)
    note = client.post(
        f"/api/v1/admin/projects/{project_id}/notes",
        headers=readonly_headers,
        json={"note_type": "ops", "body": "readonly should not mutate project state"},
    )

    assert projects.status_code == 200
    assert note.status_code == 403
    assert note.json()["code"] == 40301
    assert store.internal_notes == {}
    assert "admin.note" not in {log.action for log in store.audit.logs}


def test_reviewer_admin_can_resolve_sensitive_review_but_cannot_mark_payment() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    user_token = _login_user(client)
    project_id = _create_project(client, user_token)
    reviewer_token = _login_admin_with_role(app, client, "reviewer")
    reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}
    sensitive_claim = ClaimDraft(
        claim_text="家里有一段需要人工敏感审核的经历",
        claim_type="sensitive",
        claim_priority=ClaimPriority.P0,
        source_segment_ids=[uuid4()],
        confidence=0.91,
        support_status=SupportStatus.SUPPORTED,
        verification_status="confirmed",
        sensitivity_level="highly_sensitive",
        human_reviewed=False,
    )
    store.claims[sensitive_claim.id] = sensitive_claim
    store.claims_by_project[UUID(project_id)] = [sensitive_claim.id]

    payment = client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers=reviewer_headers,
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    review = client.post(
        f"/api/v1/admin/claims/{sensitive_claim.id}/sensitive-review",
        headers=reviewer_headers,
        json={"resolution_reason": "reviewed by Phase 1 reviewer role"},
    )

    assert payment.status_code == 403
    assert payment.json()["code"] == 40301
    assert store.projects[UUID(project_id)].payment_status == "pending"
    assert review.status_code == 200
    assert store.claims[sensitive_claim.id].human_reviewed is True
    assert "admin.sensitive_review" in {log.action for log in store.audit.logs}
    assert "admin.mark_payment" not in {log.action for log in store.audit.logs}


def test_logout_revokes_current_token_without_blocking_new_login() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    project_id = _create_project(client, token)

    before_logout = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    after_logout = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    refresh_after_logout = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )
    new_token = _login_user(client)
    after_new_login = client.get(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {new_token}"},
    )

    assert before_logout.status_code == 200
    assert logout.status_code == 200
    assert logout.json()["data"]["revoked"] is True
    assert after_logout.status_code == 401
    assert after_logout.json()["code"] == 40101
    assert refresh_after_logout.status_code == 401
    assert after_new_login.status_code == 200
    assert after_new_login.json()["data"]["project_id"] == project_id


def test_refresh_requires_refresh_token_and_logout_revokes_token_session() -> None:
    client = TestClient(create_app())
    login = client.post(
        "/api/v1/auth/wx-login",
        json={"wx_openid": "wx_phase1", "nickname": "女儿"},
    )
    access_token = login.json()["data"]["access_token"]
    refresh_token = login.json()["data"]["refresh_token"]

    access_refresh = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    refreshed = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    refreshed_access_token = refreshed.json()["data"]["access_token"]
    refreshed_access = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {refreshed_access_token}"},
    )
    refresh_as_access = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    refresh_after_logout = client.post(
        "/api/v1/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    refreshed_access_after_logout = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {refreshed_access_token}"},
    )

    assert login.status_code == 200
    assert access_token != refresh_token
    assert access_refresh.status_code == 401
    assert refreshed.status_code == 200
    assert refreshed.json()["data"]["refresh_token"] == refresh_token
    assert refreshed_access.status_code == 200
    assert refresh_as_access.status_code == 401
    assert logout.status_code == 200
    assert refresh_after_logout.status_code == 401
    assert refreshed_access_after_logout.status_code == 401


def test_api_rate_limit_returns_42901() -> None:
    client = TestClient(create_app())

    responses = [
        client.get("/healthz", headers={"X-Forwarded-For": "rate-limit-test"})
        for _ in range(61)
    ]

    assert responses[-1].status_code == 429
    assert responses[-1].json()["code"] == 42901
    assert "rate limit" in responses[-1].json()["message"]


def test_request_validation_errors_return_phase1_error_envelope() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/auth/wx-login", json={"nickname": "缺少 openid"})

    assert response.status_code == 422
    assert response.json()["code"] == 42201
    assert response.json()["message"] == "validation error"
    assert response.json()["data"]["errors"]


def test_healthz_reports_phase1_observability_configuration(monkeypatch, tmp_path) -> None:
    from changjuan_api import main as main_module
    from changjuan_api.settings import load_settings

    database_url = f"sqlite+pysqlite:///{tmp_path / 'healthz.db'}"
    monkeypatch.setattr(
        main_module,
        "settings",
        load_settings(
            {
                "APP_ENV": "production",
                "STORE_BACKEND": "sqlalchemy",
                "SQLALCHEMY_CREATE_SCHEMA": "true",
                "JWT_SECRET": "prod-secret-with-at-least-32-bytes",
                "DATABASE_URL": database_url,
                "REDIS_URL": "redis://redis.example.test:6379/1",
                "PII_KMS_KEY_ID": "kms:phase1-prod",
                "ALLOWED_ORIGINS": "https://admin.example.test,https://h5.example.test",
                "WECHAT_APP_ID": "wx_phase1_app",
                "WECHAT_APP_SECRET": "wechat-secret",
                "PILOT_WHITELIST_OPENIDS": "wx_env_phase1,wx_env_relative",
                "SENTRY_DSN": "https://public@sentry.example.test/1",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example.test/v1/traces",
                "OTEL_SERVICE_NAME": "changjuan-api-prod",
                "ALIYUN_SLS_ENDPOINT": "https://sls.cn-shanghai.aliyuncs.com",
                "ALIYUN_SLS_PROJECT": "changjuan-prod",
                "ALIYUN_SLS_LOGSTORE": "api-errors",
                "ALIYUN_OSS_ENDPOINT": "https://oss-cn-shanghai.aliyuncs.com",
                "ALIYUN_OSS_BUCKET": "changjuan-prod-private",
                "ALIYUN_OSS_KMS_KEY_ID": "kms-oss-phase1",
            }
        ),
    )
    app = main_module.create_app()
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ok"
    assert data["production_readiness"] == {"ready": True, "errors": []}
    observability = data["observability"]
    assert observability == {
        "environment": "production",
        "service_name": "changjuan-api-prod",
        "sentry": "configured",
        "otel": "configured",
        "sls": "configured",
    }
    assert data["runtime_dependencies"] == {
        "database": "configured",
        "redis": "configured",
        "object_storage": {
            "endpoint": "configured",
            "bucket": "configured",
            "kms": "configured",
        },
    }


def test_healthz_marks_production_degraded_for_local_default_runtime(monkeypatch) -> None:
    from changjuan_api import main as main_module
    from changjuan_api.settings import load_settings

    monkeypatch.setattr(main_module, "settings", load_settings({"APP_ENV": "production"}))
    app = main_module.create_app()
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    readiness = response.json()["data"]["production_readiness"]
    assert response.json()["data"]["status"] == "degraded"
    assert readiness["ready"] is False
    assert "JWT_SECRET must be set to a non-default production secret" in readiness["errors"]
    assert "STORE_BACKEND must be sqlalchemy in production" in readiness["errors"]
    assert "DATABASE_URL must not point at localhost in production" in readiness["errors"]
    assert "WECHAT_APP_SECRET is required in production" in readiness["errors"]


def test_sqlalchemy_api_persists_user_project_across_app_recreation(monkeypatch, tmp_path) -> None:
    from changjuan_api import main as main_module
    from changjuan_api.settings import load_settings

    database_url = f"sqlite+pysqlite:///{tmp_path / 'api-persistence.db'}"
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
    first_app = main_module.create_app()
    first_client = TestClient(first_app)
    token = _login_user(first_client)
    project_id = _create_project(first_client, token)

    recreated_app = main_module.create_app()
    recreated_client = TestClient(recreated_app)

    response = recreated_client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert [project["project_id"] for project in response.json()["data"]["projects"]] == [project_id]


def test_sqlalchemy_api_persists_consent_evidence_across_app_recreation(monkeypatch, tmp_path) -> None:
    from changjuan_api import main as main_module
    from changjuan_api.settings import load_settings

    database_url = f"sqlite+pysqlite:///{tmp_path / 'api-consent.db'}"
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
    first_app = main_module.create_app()
    first_client = TestClient(first_app)
    token = _login_user(first_client)
    project_id = _create_project(first_client, token)
    consent = first_client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "consent_type": "interview_consent",
            "method": "audio",
            "evidence_oss_key": f"consents/{project_id}/interview/audio.wav",
        },
    )
    assert consent.status_code == 200

    recreated_app = main_module.create_app()
    recreated_client = TestClient(recreated_app)
    export = recreated_client.get(
        f"/api/v1/projects/{project_id}/export",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert export.status_code == 200
    assert export.json()["data"]["consents"] == [
        {
            **export.json()["data"]["consents"][0],
            "consent_id": consent.json()["data"]["consent_id"],
            "project_id": project_id,
            "consent_type": "interview_consent",
            "method": "audio",
            "evidence_oss_key": f"consents/{project_id}/interview/audio.wav",
            "withdrawn_at": None,
            "minimized_at": None,
        }
    ]


def test_sqlalchemy_api_persists_deletion_request_across_app_recreation(monkeypatch, tmp_path) -> None:
    from changjuan_api import main as main_module
    from changjuan_api.settings import load_settings

    database_url = f"sqlite+pysqlite:///{tmp_path / 'api-deletion.db'}"
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
    first_app = main_module.create_app()
    first_client = TestClient(first_app)
    token = _login_user(first_client)
    project_id = _create_project(first_client, token)
    consent = first_client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "consent_type": "interview_consent",
            "method": "audio",
            "evidence_oss_key": f"consents/{project_id}/interview/audio.wav",
        },
    )
    deleted = first_client.delete(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert consent.status_code == 200
    assert deleted.status_code == 200

    recreated_app = main_module.create_app()
    recreated_client = TestClient(recreated_app)
    status = recreated_client.get(
        f"/api/v1/projects/{project_id}/deletion-request",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert status.status_code == 200
    assert status.json()["data"]["deletion_request_id"] == deleted.json()["data"]["deletion_request_id"]
    assert status.json()["data"]["status"] == "pending"


def test_sqlalchemy_api_persists_photos_and_session_status_across_app_recreation(monkeypatch, tmp_path) -> None:
    from changjuan_api import main as main_module
    from changjuan_api.settings import load_settings

    database_url = f"sqlite+pysqlite:///{tmp_path / 'api-media.db'}"
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
    first_app = main_module.create_app()
    first_client = TestClient(first_app)
    token = _login_user(first_client)
    admin_token = _login_admin(first_client)
    project_id = _create_project(first_client, token)
    paid = first_client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    consent = first_client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "text"},
    )
    _upload_minimum_photos(first_client, project_id, token)
    assert [paid.status_code, consent.status_code] == [200, 200]

    recreated_app = main_module.create_app()
    recreated_client = TestClient(recreated_app)
    created = recreated_client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert created.status_code == 200
    session_id = created.json()["data"]["session_id"]
    started = recreated_client.post(
        f"/api/v1/interview-sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert started.status_code == 200

    second_recreated_app = main_module.create_app()
    second_recreated_client = TestClient(second_recreated_app)
    session = second_recreated_client.get(
        f"/api/v1/interview-sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert session.status_code == 200
    assert session.json()["data"] == {"session_id": session_id, "status": "in_progress"}


def test_sqlalchemy_api_persists_support_ops_records_across_app_recreation(monkeypatch, tmp_path) -> None:
    from changjuan_api import main as main_module
    from changjuan_api.settings import load_settings

    database_url = f"sqlite+pysqlite:///{tmp_path / 'api-ops.db'}"
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
    first_app = main_module.create_app()
    first_client = TestClient(first_app)
    token = _login_user(first_client)
    admin_token = _login_admin(first_client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    project_id = _create_project(first_client, token)
    owner_id = str(first_app.dependency_overrides[get_store]().admin_id)
    generation_run_id = str(uuid4())

    feedback = first_client.post(
        f"/api/v1/projects/{project_id}/feedback",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "nps_score": 8,
            "recommend": False,
            "issue_type": "major_fact_error",
            "body": "年份需要再复核",
        },
    )
    ticket = first_client.post(
        f"/api/v1/projects/{project_id}/support-tickets",
        headers={"Authorization": f"Bearer {token}"},
        json={"category": "story_correction", "priority": "P2", "body": "请人工处理这处修改"},
    )
    note = first_client.post(
        f"/api/v1/admin/projects/{project_id}/notes",
        headers=admin_headers,
        json={"note_type": "ops", "body": "家属已确认可以延期"},
    )
    manual = first_client.post(
        f"/api/v1/admin/projects/{project_id}/manual-interventions",
        headers=admin_headers,
        json={"category": "fact_review", "minutes": 21, "body": "核对老照片说明"},
    )
    ai_cost = first_client.post(
        f"/api/v1/admin/projects/{project_id}/ai-costs",
        headers=admin_headers,
        json={
            "task_type": "verification",
            "provider": "qwen",
            "cost_cents": 43,
            "generation_run_id": generation_run_id,
        },
    )
    assert [response.status_code for response in (feedback, ticket, note, manual, ai_cost)] == [200, 200, 200, 200, 200]

    ticket_id = ticket.json()["data"]["ticket_id"]
    patched = first_client.patch(
        f"/api/v1/admin/support-tickets/{ticket_id}",
        headers=admin_headers,
        json={"status": "pending", "priority": "P0", "admin_owner_id": owner_id},
    )
    assert patched.status_code == 200

    recreated_app = main_module.create_app()
    recreated_client = TestClient(recreated_app)
    detail = recreated_client.get(f"/api/v1/admin/projects/{project_id}", headers=admin_headers)
    tickets = recreated_client.get("/api/v1/admin/support-tickets", headers=admin_headers)
    metrics = recreated_client.get("/api/v1/admin/metrics/pilot", headers=admin_headers)
    ops_export = recreated_client.get("/api/v1/admin/exports/household-ops", headers=admin_headers)
    user_export = recreated_client.get(
        f"/api/v1/projects/{project_id}/export",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert [response.status_code for response in (detail, tickets, metrics, ops_export, user_export)] == [200, 200, 200, 200, 200]
    detail_data = detail.json()["data"]
    assert detail_data["internal_notes"][0]["body"] == "家属已确认可以延期"
    assert detail_data["manual_interventions"][0]["minutes"] == 21
    assert detail_data["ai_costs"][0] == {
        **detail_data["ai_costs"][0],
        "provider": "qwen",
        "cost_cents": 43,
        "generation_run_id": generation_run_id,
    }
    assert tickets.json()["data"]["support_tickets"][0] == {
        **tickets.json()["data"]["support_tickets"][0],
        "ticket_id": ticket_id,
        "status": "pending",
        "priority": "P0",
        "admin_owner_id": owner_id,
    }
    assert metrics.json()["data"]["feedback_count"] == 1
    assert metrics.json()["data"]["nps"] == 8
    assert metrics.json()["data"]["major_fact_error_complaint_rate"] == 1
    assert ops_export.json()["data"]["households"][0] == {
        **ops_export.json()["data"]["households"][0],
        "project_id": project_id,
        "ai_cost_cents": 43,
        "manual_intervention_count": 1,
        "manual_minutes": 21,
    }
    assert user_export.json()["data"]["feedback"][0]["body"] == "年份需要再复核"
    assert user_export.json()["data"]["support_tickets"][0]["body"] == "请人工处理这处修改"


def test_sqlalchemy_api_persists_audio_transcripts_and_photo_analyses_across_app_recreation(monkeypatch, tmp_path) -> None:
    from changjuan_api import main as main_module
    from changjuan_api.settings import load_settings

    database_url = f"sqlite+pysqlite:///{tmp_path / 'api-evidence.db'}"
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
    first_app = main_module.create_app()
    first_client = TestClient(first_app)
    token = _login_user(first_client)
    admin_token = _login_admin(first_client)
    project_id = _create_project(first_client, token)
    paid = first_client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    consent = first_client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "text"},
    )
    first_photo = first_client.post(
        f"/api/v1/projects/{project_id}/photos/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"oss_key": f"photos/{project_id}/family-0.jpg", "caption": "全家福"},
    )
    for index in range(1, 3):
        uploaded = first_client.post(
            f"/api/v1/projects/{project_id}/photos/complete",
            headers={"Authorization": f"Bearer {token}"},
            json={"oss_key": f"photos/{project_id}/family-{index}.jpg", "caption": f"家庭照片 {index + 1}"},
        )
        assert uploaded.status_code == 200
    assert [paid.status_code, consent.status_code, first_photo.status_code] == [200, 200, 200]

    session = first_client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = session.json()["data"]["session_id"]
    started = first_client.post(
        f"/api/v1/interview-sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    audio = first_client.post(
        f"/api/v1/interview-sessions/{session_id}/audio-chunks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "sequence_number": 0,
            "duration_ms": 400,
            "oss_key": _audio_oss_key(project_id, session_id, 0),
            "partial_transcript": "我大约1978年进了供销社。",
            "transcript_confidence": 0.42,
        },
    )
    analysis = first_client.post(
        f"/api/v1/admin/photos/{first_photo.json()['data']['photo_id']}/analysis",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hypothesis_text": "照片可能是在老家院子拍摄。", "confidence": 0.73},
    )
    assert [session.status_code, started.status_code, audio.status_code, analysis.status_code] == [200, 200, 200, 200]

    recreated_app = main_module.create_app()
    recreated_client = TestClient(recreated_app)
    recovery = recreated_client.get(
        f"/api/v1/interview-sessions/{session_id}/recovery",
        headers={"Authorization": f"Bearer {token}"},
    )
    detail = recreated_client.get(
        f"/api/v1/admin/projects/{project_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    photo_analyses = recreated_client.get(
        f"/api/v1/admin/projects/{project_id}/photo-analyses",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    export = recreated_client.get(
        f"/api/v1/projects/{project_id}/export",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert [response.status_code for response in (recovery, detail, photo_analyses, export)] == [200, 200, 200, 200]
    assert recovery.json()["data"] == {
        "session_id": session_id,
        "last_accepted_sequence_number": 0,
        "missing_sequence_numbers": [],
        "buffered_chunk_count": 1,
    }
    assert detail.json()["data"]["audio_chunks"][0]["oss_key"] == _audio_oss_key(project_id, session_id, 0)
    assert detail.json()["data"]["transcript_segments"][0]["text"] == "我大约1978年进了供销社。"
    assert detail.json()["data"]["transcript_segments"][0]["low_confidence_review"] is True
    assert photo_analyses.json()["data"]["photo_analyses"][0] == {
        **photo_analyses.json()["data"]["photo_analyses"][0],
        "photo_analysis_id": analysis.json()["data"]["photo_analysis_id"],
        "hypothesis_text": "照片可能是在老家院子拍摄。",
        "eligible_for_prompt": True,
    }
    assert export.json()["data"]["audio_chunks"][0]["sequence_number"] == 0
    assert export.json()["data"]["transcript_segments"][0]["confidence"] == 0.42


def test_sqlalchemy_api_persists_story_share_comment_and_pdf_state_across_app_recreation(monkeypatch, tmp_path) -> None:
    from changjuan_api import main as main_module
    from changjuan_api.settings import load_settings

    database_url = f"sqlite+pysqlite:///{tmp_path / 'api-story.db'}"
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
    first_app = main_module.create_app()
    first_client = TestClient(first_app)
    token = _login_user(first_client)
    project_id, story_page_id = _published_story(first_client, token)
    share = first_client.post(
        f"/api/v1/story-pages/{story_page_id}/share-links",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "family-code"},
    )
    share_data = share.json()["data"]
    story = first_client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": share_data["share_token"], "password": "family-code"},
    )
    comment = first_client.post(
        f"/api/v1/story-pages/{story_page_id}/comments",
        json={
            "share_token": share_data["share_token"],
            "password": "family-code",
            "display_name": "小姨",
            "body": "这一段很像外公说话的样子。",
        },
    )
    pdf = first_client.post(
        f"/api/v1/story-pages/{story_page_id}/pdf-export",
        params={"share_token": share_data["share_token"], "password": "family-code"},
    )
    assert [share.status_code, story.status_code, comment.status_code, pdf.status_code] == [200, 200, 200, 200]

    recreated_app = main_module.create_app()
    recreated_client = TestClient(recreated_app)
    drafts = recreated_client.get(
        f"/api/v1/projects/{project_id}/drafts",
        headers={"Authorization": f"Bearer {token}"},
    )
    story_after_recreate = recreated_client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": share_data["share_token"], "password": "family-code"},
    )
    export = recreated_client.get(
        f"/api/v1/projects/{project_id}/export",
        headers={"Authorization": f"Bearer {token}"},
    )
    second_pdf = recreated_client.post(
        f"/api/v1/story-pages/{story_page_id}/pdf-export",
        params={"share_token": share_data["share_token"], "password": "family-code"},
    )

    assert [response.status_code for response in (drafts, story_after_recreate, export, second_pdf)] == [200, 200, 200, 200]
    assert drafts.json()["data"]["chapters"]
    story_data = story_after_recreate.json()["data"]
    assert story_data["story_page_id"] == story_page_id
    assert story_data["comments"][0] == comment.json()["data"]
    audio_url = next(
        citation["audio_url"]
        for chapter in story_data["chapters"]
        for citation in chapter["audio_citations"]
    )
    audio = recreated_client.get(audio_url)
    assert audio.status_code == 200
    export_data = export.json()["data"]
    assert export_data["story_page"]["story_page_id"] == story_page_id
    assert export_data["share_links"][0]["share_link_id"] == share_data["share_link_id"]
    assert export_data["family_comments"][0] == comment.json()["data"]
    assert len(export_data["pdf_exports"]) == 1
    assert second_pdf.content.startswith(b"%PDF")


def test_sqlalchemy_api_persists_stateful_security_review_and_observability_gates(monkeypatch, tmp_path) -> None:
    from changjuan_api import main as main_module
    from changjuan_api.settings import load_settings

    database_url = f"sqlite+pysqlite:///{tmp_path / 'api-stateful-gates.db'}"
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
    first_app = main_module.create_app()
    first_client = TestClient(first_app)
    login = first_client.post("/api/v1/auth/wx-login", json={"wx_openid": "wx_phase1", "nickname": "女儿"})
    token = login.json()["data"]["access_token"]
    refresh_token = login.json()["data"]["refresh_token"]
    admin_token = _login_admin(first_client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    project_id = _create_project(first_client, token)
    issue_id = uuid4()

    note = first_client.post(
        f"/api/v1/admin/projects/{project_id}/notes",
        headers=admin_headers,
        json={"note_type": "ops", "body": "stateful gate audit"},
    )
    first_app.dependency_overrides[get_store]().save_verification_issue(
        issue_id,
        {
            "id": str(issue_id),
            "project_id": project_id,
            "gate": "story_evidence",
            "severity": "block",
            "message": "missing citation",
            "resolved_at": None,
            "resolution_reason": None,
        },
    )
    simulated = first_client.post("/api/v1/admin/alerts/simulate-500", headers=admin_headers)
    logout = first_client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert [note.status_code, simulated.status_code, logout.status_code] == [200, 500, 200]

    recreated_app = main_module.create_app()
    recreated_client = TestClient(recreated_app)
    revoked_access = recreated_client.get("/api/v1/projects", headers={"Authorization": f"Bearer {token}"})
    revoked_refresh = recreated_client.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"})
    alerts = recreated_client.get("/api/v1/admin/alerts", headers=admin_headers)
    recreated_store = recreated_app.dependency_overrides[get_store]()
    resolve = recreated_client.post(
        f"/api/v1/admin/verification-issues/{issue_id}/resolve",
        headers=admin_headers,
        json={"resolution_reason": "family confirmed citation"},
    )

    assert revoked_access.status_code == 401
    assert revoked_refresh.status_code == 401
    assert alerts.status_code == 200
    assert alerts.json()["data"]["alerts"][0]["path"] == "/api/v1/admin/alerts/simulate-500"
    assert any(log.action == "admin.note" and log.resource_id == UUID(project_id) for log in recreated_store.audit.logs)
    assert recreated_store.verification_issues[issue_id]["message"] == "missing citation"
    assert resolve.status_code == 200

    second_recreated_app = main_module.create_app()
    second_recreated_store = second_recreated_app.dependency_overrides[get_store]()
    assert second_recreated_store.verification_issues[issue_id]["resolved_at"] is not None
    assert second_recreated_store.verification_issues[issue_id]["resolution_reason"] == "family confirmed citation"


def test_interview_requires_manual_payment_before_session_creation() -> None:
    client = TestClient(create_app())
    token = client.post(
        "/api/v1/auth/wx-login", json={"wx_openid": "wx_phase1", "nickname": "女儿"}
    ).json()["data"]["access_token"]
    project_id = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "storyteller": {"display_name": "妈妈", "relation_to_payer": "mother"},
            "title": "妈妈的故事",
            "themes": ["family"],
            "tier": "standard",
        },
    ).json()["data"]["project_id"]

    blocked = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == 40901

    admin_login = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "ops@changjuan.test", "password": "phase1-admin"},
    )
    admin_token = admin_login.json()["data"]["access_token"]
    paid = client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "payment_cents": 49900,
            "payment_method": "manual_wechat",
            "payment_reference": "wx-transfer-001",
        },
    )
    assert paid.status_code == 200

    missing_consent = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert missing_consent.status_code == 422
    assert missing_consent.json()["code"] == 42201
    assert "interview consent" in missing_consent.json()["message"]

    consent = client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "text"},
    )
    assert consent.status_code == 200

    not_enough_photos = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert not_enough_photos.status_code == 422
    assert "at least 3 photos" in not_enough_photos.json()["message"]

    _upload_minimum_photos(client, project_id, token)

    created = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert created.status_code == 200
    assert created.json()["data"]["status"] == "scheduled"


def test_admin_mark_payment_requires_phase1_deposit_or_explicit_waiver() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    admin_token = _login_admin(client)
    insufficient_project_id = _create_project(client, token)
    waived_project_id = _create_project(client, token)

    insufficient = client.post(
        f"/api/v1/admin/projects/{insufficient_project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "payment_cents": 100,
            "payment_method": "manual_wechat",
            "payment_reference": "wx-transfer-too-low",
        },
    )
    waived = client.post(
        f"/api/v1/admin/projects/{waived_project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 0, "payment_method": "waived", "payment_reference": "pilot-waiver"},
    )

    assert insufficient.status_code == 422
    assert insufficient.json()["code"] == 42201
    assert store.projects[UUID(insufficient_project_id)].payment_status == "pending"
    assert waived.status_code == 200
    assert waived.json()["data"]["payment_status"] == "waived"


def test_project_updated_at_advances_and_is_exposed_on_state_mutations() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    admin_token = _login_admin(client)
    project_id = _create_project(client, token)
    project = store.projects[UUID(project_id)]
    stale = datetime(2026, 1, 1, tzinfo=UTC)

    project.updated_at = stale
    patched = client.patch(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "爸爸的故事新版"},
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["created_at"]
    assert patched.json()["data"]["updated_at"]
    assert store.projects[UUID(project_id)].updated_at > stale

    store.projects[UUID(project_id)].updated_at = stale
    paid = client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    assert paid.status_code == 200
    assert store.projects[UUID(project_id)].updated_at > stale

    store.projects[UUID(project_id)].updated_at = stale
    consent = client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "text"},
    )
    assert consent.status_code == 200
    assert store.projects[UUID(project_id)].updated_at > stale


def test_photo_upload_generates_thumbnail_and_enforces_ten_photo_cap() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    project_id = _create_project(client, token)

    uploaded = []
    for index in range(10):
        response = client.post(
            f"/api/v1/projects/{project_id}/photos/complete",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "oss_key": f"photos/{project_id}/family-{index}.jpg",
                "caption": f"照片 {index + 1}",
            },
        )
        assert response.status_code == 200
        uploaded.append(response.json()["data"])

    assert uploaded[0]["photo_count"] == 1
    assert uploaded[-1]["photo_count"] == 10
    assert uploaded[0]["thumbnail_oss_key"].startswith(f"photos/{project_id}/thumbnails/")
    assert uploaded[0]["internal_photo_hypothesis_only"] is True
    listed = client.get(
        f"/api/v1/projects/{project_id}/photos",
        headers={"Authorization": f"Bearer {token}"},
    )
    first_photo = listed.json()["data"]["photos"][0]
    assert listed.status_code == 200
    assert first_photo == {
        **first_photo,
        "photo_id": uploaded[0]["photo_id"],
        "project_id": project_id,
        "oss_key": f"photos/{project_id}/family-0.jpg",
        "thumbnail_oss_key": uploaded[0]["thumbnail_oss_key"],
        "caption": "照片 1",
        "deleted_at": None,
        "purge_after_at": None,
    }
    assert "id" not in first_photo

    wrong_project_key = client.post(
        f"/api/v1/projects/{project_id}/photos/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"oss_key": f"photos/{uuid4()}/other-family.jpg", "caption": "错项目照片"},
    )
    too_many = client.post(
        f"/api/v1/projects/{project_id}/photos/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"oss_key": f"photos/{project_id}/family-10.jpg", "caption": "第 11 张"},
    )
    assert wrong_project_key.status_code == 422
    assert "photo oss_key must be under the project photo prefix" in wrong_project_key.json()["message"]
    assert too_many.status_code == 409
    assert "maximum 10 photos" in too_many.json()["message"]


def test_photo_presign_uses_configured_oss_bucket_and_kms_headers(monkeypatch) -> None:
    from urllib.parse import quote

    from changjuan_api import main as main_module
    from changjuan_api.settings import load_settings

    monkeypatch.setattr(
        main_module,
        "settings",
        load_settings(
            {
                "ALIYUN_OSS_ENDPOINT": "https://oss-cn-shanghai.aliyuncs.com",
                "ALIYUN_OSS_BUCKET": "changjuan-prod-private",
                "ALIYUN_OSS_KMS_KEY_ID": "kms-oss-phase1",
            }
        ),
    )
    app = main_module.create_app()
    client = TestClient(app)
    token = _login_user(client)
    project_id = _create_project(client, token)

    response = client.post(
        f"/api/v1/projects/{project_id}/photos/presign",
        headers={"Authorization": f"Bearer {token}"},
        json={"filename": "全家福.jpg", "content_type": "image/jpeg"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["oss_key"].startswith(f"photos/{project_id}/")
    assert data["oss_key"].endswith("-全家福.jpg")
    assert data["upload_url"] == (
        f"https://oss-cn-shanghai.aliyuncs.com/changjuan-prod-private/"
        f"{quote(data['oss_key'], safe='/')}"
    )
    assert data["headers"] == {
        "Content-Type": "image/jpeg",
        "x-oss-server-side-encryption": "KMS",
        "x-oss-server-side-encryption-key-id": "kms-oss-phase1",
        "x-oss-object-acl": "private",
    }


def test_audio_chunk_presign_uses_session_project_prefix_and_kms_headers(monkeypatch) -> None:
    from urllib.parse import quote

    from changjuan_api import main as main_module
    from changjuan_api.settings import load_settings

    monkeypatch.setattr(
        main_module,
        "settings",
        load_settings(
            {
                "ALIYUN_OSS_ENDPOINT": "https://oss-cn-shanghai.aliyuncs.com",
                "ALIYUN_OSS_BUCKET": "changjuan-prod-private",
                "ALIYUN_OSS_KMS_KEY_ID": "kms-oss-phase1",
            }
        ),
    )
    app = main_module.create_app()
    client = TestClient(app)
    token = _login_user(client)
    admin_token = _login_admin(client)
    project_id = _create_project(client, token)
    client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "text"},
    )
    _upload_minimum_photos(client, project_id, token)
    session_id = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["session_id"]

    scheduled_presign = client.post(
        f"/api/v1/interview-sessions/{session_id}/audio-chunks/presign",
        headers={"Authorization": f"Bearer {token}"},
        json={"sequence_number": 0, "content_type": "audio/mpeg"},
    )
    client.post(
        f"/api/v1/interview-sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    response = client.post(
        f"/api/v1/interview-sessions/{session_id}/audio-chunks/presign",
        headers={"Authorization": f"Bearer {token}"},
        json={"sequence_number": 0, "content_type": "audio/mpeg"},
    )

    assert scheduled_presign.status_code == 409
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["oss_key"] == f"audio/{project_id}/interview-{session_id}-0.mp3"
    assert data["upload_url"] == (
        f"https://oss-cn-shanghai.aliyuncs.com/changjuan-prod-private/"
        f"{quote(data['oss_key'], safe='/')}"
    )
    assert data["headers"] == {
        "Content-Type": "audio/mpeg",
        "x-oss-server-side-encryption": "KMS",
        "x-oss-server-side-encryption-key-id": "kms-oss-phase1",
        "x-oss-object-acl": "private",
    }


def test_photo_hypothesis_is_admin_only_uncertain_and_convertible_to_correction_candidate() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    admin_token = _login_admin(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    project_id = _create_project(client, token)
    uploaded = client.post(
        f"/api/v1/projects/{project_id}/photos/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"oss_key": f"photos/{project_id}/old-photo.jpg", "caption": "老照片"},
    )
    photo_id = uploaded.json()["data"]["photo_id"]

    overconfident = client.post(
        f"/api/v1/admin/photos/{photo_id}/analysis",
        headers=admin_headers,
        json={"hypothesis_text": "父亲在供销社门口", "confidence": 0.84},
    )
    low_confidence = client.post(
        f"/api/v1/admin/photos/{photo_id}/analysis",
        headers=admin_headers,
        json={"hypothesis_text": "可能是父亲在供销社门口", "confidence": 0.42},
    )
    eligible = client.post(
        f"/api/v1/admin/photos/{photo_id}/analysis",
        headers=admin_headers,
        json={"hypothesis_text": "可能是父亲在供销社门口", "confidence": 0.84},
    )
    user_photos = client.get(
        f"/api/v1/projects/{project_id}/photos",
        headers={"Authorization": f"Bearer {token}"},
    )
    admin_analyses = client.get(
        f"/api/v1/admin/projects/{project_id}/photo-analyses",
        headers=admin_headers,
    )
    low_conversion = client.post(
        f"/api/v1/admin/photo-analyses/{low_confidence.json()['data']['photo_analysis_id']}/correction-candidate",
        headers=admin_headers,
    )
    conversion = client.post(
        f"/api/v1/admin/photo-analyses/{eligible.json()['data']['photo_analysis_id']}/correction-candidate",
        headers=admin_headers,
    )

    assert overconfident.status_code == 422
    assert "uncertainty marker" in overconfident.json()["message"]
    assert low_confidence.status_code == 200
    assert low_confidence.json()["data"]["eligible_for_prompt"] is False
    assert low_confidence.json()["data"]["internal_only"] is True
    assert eligible.status_code == 200
    assert eligible.json()["data"]["eligible_for_prompt"] is True
    assert "hypothesis_text" not in user_photos.json()["data"]["photos"][0]
    assert admin_analyses.status_code == 200
    assert len(admin_analyses.json()["data"]["photo_analyses"]) == 2
    assert low_conversion.status_code == 422
    assert "eligible" in low_conversion.json()["message"]
    assert conversion.status_code == 200
    converted_claim = conversion.json()["data"]["claim"]
    assert converted_claim["claim_text"] == "可能是父亲在供销社门口"
    assert converted_claim["claim_type"] == "photo_hypothesis"
    assert converted_claim["claim_priority"] == "P2"
    assert converted_claim["support_status"] == "needs_review"
    assert converted_claim["verification_status"] == "pending"
    assert converted_claim["entities"]["photo_id"] == [photo_id]
    assert store.photo_analyses[UUID(eligible.json()["data"]["photo_analysis_id"])].converted_claim_id == UUID(converted_claim["id"])
    assert "admin.photo_analysis.create" in {log.action for log in store.audit.logs}
    assert "admin.photo_analysis.convert_to_candidate" in {log.action for log in store.audit.logs}


def test_interview_audio_chunks_support_recovery_and_duration_validation() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    admin_token = _login_admin(client)
    project_id = _create_project(client, token)
    client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "text"},
    )
    _upload_minimum_photos(client, project_id, token)
    session_id = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["session_id"]
    client.post(
        f"/api/v1/interview-sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )

    first = client.post(
        f"/api/v1/interview-sessions/{session_id}/audio-chunks",
        headers={"Authorization": f"Bearer {token}"},
        json={"sequence_number": 0, "duration_ms": 300, "oss_key": _audio_oss_key(project_id, session_id, 0)},
    )
    third = client.post(
        f"/api/v1/interview-sessions/{session_id}/audio-chunks",
        headers={"Authorization": f"Bearer {token}"},
        json={"sequence_number": 2, "duration_ms": 400, "oss_key": _audio_oss_key(project_id, session_id, 2)},
    )
    wrong_project_audio_key = client.post(
        f"/api/v1/interview-sessions/{session_id}/audio-chunks",
        headers={"Authorization": f"Bearer {token}"},
        json={"sequence_number": 4, "duration_ms": 400, "oss_key": f"audio/{uuid4()}/interview-{session_id}-4.mp3"},
    )
    wrong_session_audio_key = client.post(
        f"/api/v1/interview-sessions/{session_id}/audio-chunks",
        headers={"Authorization": f"Bearer {token}"},
        json={"sequence_number": 5, "duration_ms": 400, "oss_key": f"audio/{project_id}/detached-5.mp3"},
    )
    recovery = client.get(
        f"/api/v1/interview-sessions/{session_id}/recovery",
        headers={"Authorization": f"Bearer {token}"},
    )
    invalid_duration = client.post(
        f"/api/v1/interview-sessions/{session_id}/audio-chunks",
        headers={"Authorization": f"Bearer {token}"},
        json={"sequence_number": 3, "duration_ms": 250, "oss_key": _audio_oss_key(project_id, session_id, 3)},
    )
    recovered = client.post(
        f"/api/v1/interview-sessions/{session_id}/audio-chunks",
        headers={"Authorization": f"Bearer {token}"},
        json={"sequence_number": 1, "duration_ms": 500, "oss_key": _audio_oss_key(project_id, session_id, 1)},
    )
    recovery_after = client.get(
        f"/api/v1/interview-sessions/{session_id}/recovery",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert first.status_code == 200
    assert third.status_code == 200
    assert wrong_project_audio_key.status_code == 422
    assert "audio oss_key must be under the project audio prefix" in wrong_project_audio_key.json()["message"]
    assert wrong_session_audio_key.status_code == 422
    assert "audio oss_key must match the interview session and sequence" in wrong_session_audio_key.json()["message"]
    assert recovery.json()["data"] == {
        "session_id": session_id,
        "last_accepted_sequence_number": 2,
        "missing_sequence_numbers": [1],
        "buffered_chunk_count": 2,
    }
    assert invalid_duration.status_code == 422
    assert "300-500ms" in invalid_duration.json()["message"]
    assert recovered.status_code == 200
    assert recovery_after.json()["data"]["missing_sequence_numbers"] == []


def test_interview_websocket_stream_persists_audio_chunks_and_transcripts() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    admin_token = _login_admin(client)
    project_id = _create_project(client, token)
    client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "text"},
    )
    _upload_minimum_photos(client, project_id, token)
    session_id = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["session_id"]
    client.post(
        f"/api/v1/interview-sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )

    with client.websocket_connect(
        f"/api/v1/interview-sessions/{session_id}/stream",
        headers={"Authorization": f"Bearer {token}"},
    ) as websocket:
        hello = websocket.receive_json()
        websocket.send_json(
            {
                "sequence_number": 0,
                "duration_ms": 400,
                "oss_key": _audio_oss_key(project_id, session_id, 0),
                "partial_transcript": "我大约1978年进了供销社。",
                "transcript_confidence": 0.42,
                "speaker": "storyteller",
            }
        )
        accepted = websocket.receive_json()

    assert hello == {"session_id": session_id, "chunk_duration_ms": "300-500", "max_chunks_per_minute": 240}
    assert accepted["accepted"] is True
    assert accepted["sequence_number"] == 0
    assert accepted["last_accepted_sequence_number"] == 0
    assert accepted["missing_sequence_numbers"] == []
    assert UUID(accepted["transcript_segment_id"])
    assert (UUID(session_id), 0) in store.audio_chunks
    assert any(segment.text == "我大约1978年进了供销社。" for segment in store.transcript_segments.values())


def test_admin_project_detail_exposes_audio_chunks_and_low_confidence_transcripts() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    admin_token = _login_admin(client)
    project_id = _create_project(client, token)
    client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "text"},
    )
    _upload_minimum_photos(client, project_id, token)
    session_id = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["session_id"]
    client.post(
        f"/api/v1/interview-sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )

    chunk = client.post(
        f"/api/v1/interview-sessions/{session_id}/audio-chunks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "sequence_number": 0,
            "duration_ms": 400,
            "oss_key": _audio_oss_key(project_id, session_id, 0),
            "partial_transcript": "我大约1978年进了供销社。",
            "transcript_confidence": 0.42,
            "speaker": "storyteller",
        },
    )
    detail = client.get(
        f"/api/v1/admin/projects/{project_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert chunk.status_code == 200
    assert UUID(chunk.json()["data"]["transcript_segment_id"])
    assert detail.status_code == 200
    assert detail.json()["data"]["audio_chunks"] == [
        {
            "session_id": session_id,
            "sequence_number": 0,
            "duration_ms": 400,
            "oss_key": _audio_oss_key(project_id, session_id, 0),
            "received_at": detail.json()["data"]["audio_chunks"][0]["received_at"],
            "deleted_at": None,
            "purge_after_at": None,
        }
    ]
    assert detail.json()["data"]["transcript_segments"] == [
        {
            "transcript_segment_id": chunk.json()["data"]["transcript_segment_id"],
            "project_id": project_id,
            "session_id": session_id,
            "audio_chunk_sequence_number": 0,
            "speaker": "storyteller",
            "text": "我大约1978年进了供销社。",
            "start_ms": 0,
            "end_ms": 400,
            "confidence": 0.42,
            "low_confidence_review": True,
            "created_at": detail.json()["data"]["transcript_segments"][0]["created_at"],
            "deleted_at": None,
            "purge_after_at": None,
        }
    ]


def test_interview_session_rejects_illegal_state_transitions() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    admin_token = _login_admin(client)
    project_id = _create_project(client, token)
    client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "text"},
    )
    _upload_minimum_photos(client, project_id, token)
    session_id = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["session_id"]

    end_before_start = client.post(
        f"/api/v1/interview-sessions/{session_id}/end",
        headers={"Authorization": f"Bearer {token}"},
    )
    started = client.post(
        f"/api/v1/interview-sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    start_again = client.post(
        f"/api/v1/interview-sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    ended = client.post(
        f"/api/v1/interview-sessions/{session_id}/end",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "completed"},
    )
    end_again = client.post(
        f"/api/v1/interview-sessions/{session_id}/end",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "completed"},
    )
    project = client.get(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert end_before_start.status_code == 409
    assert end_before_start.json()["code"] == 40901
    assert "session must be in_progress" in end_before_start.json()["message"]
    assert started.status_code == 200
    assert started.json()["data"]["status"] == "in_progress"
    assert start_again.status_code == 409
    assert "session must be scheduled" in start_again.json()["message"]
    assert ended.status_code == 200
    assert ended.json()["data"]["status"] == "completed"
    assert end_again.status_code == 409
    assert project.json()["data"]["status"] == "interview_completed"


def test_audio_chunk_upload_uses_voice_specific_240_per_minute_limit() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    admin_token = _login_admin(client)
    project_id = _create_project(client, token)
    paid = client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    consent = client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "text"},
    )
    _upload_minimum_photos(client, project_id, token)
    session = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = session.json()["data"]["session_id"]
    started = client.post(
        f"/api/v1/interview-sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )

    responses = [
        client.post(
            f"/api/v1/interview-sessions/{session_id}/audio-chunks",
            headers={"Authorization": f"Bearer {token}"},
            json={"sequence_number": sequence, "duration_ms": 500, "oss_key": _audio_oss_key(project_id, session_id, sequence)},
        )
        for sequence in range(61)
    ]

    assert [paid.status_code, consent.status_code, session.status_code, started.status_code] == [200, 200, 200, 200]
    assert responses[-1].status_code == 200
    assert responses[-1].json()["data"]["sequence_number"] == 60


def test_publish_endpoint_blocks_without_second_consent() -> None:
    client = TestClient(create_app())
    token = client.post(
        "/api/v1/auth/wx-login", json={"wx_openid": "wx_phase1", "nickname": "女儿"}
    ).json()["data"]["access_token"]
    project_id = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "storyteller": {"display_name": "爸爸", "relation_to_payer": "father"},
            "title": "爸爸的故事",
            "themes": ["work"],
            "tier": "standard",
        },
    ).json()["data"]["project_id"]

    response = client.post(
        f"/api/v1/projects/{project_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == 42201
    assert "second consent" in response.json()["message"]


def test_second_consent_requires_generated_story_and_passed_verifier() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    premature_project_id = _create_project(client, token)
    verified_project_id = _create_project(client, token)

    premature = client.post(
        f"/api/v1/projects/{premature_project_id}/request-second-consent",
        headers={"Authorization": f"Bearer {token}"},
    )
    claim_id = client.get(
        f"/api/v1/projects/{verified_project_id}/corrections/pending",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["claims"][0]["id"]
    corrected = client.post(
        f"/api/v1/claims/{claim_id}/corrections",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "confirm"},
    )
    completed = client.post(
        f"/api/v1/projects/{verified_project_id}/corrections/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    draft = client.post(
        f"/api/v1/projects/{verified_project_id}/drafts/generate",
        headers={"Authorization": f"Bearer {token}"},
    )
    verified = client.post(
        f"/api/v1/projects/{verified_project_id}/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    second_consent = client.post(
        f"/api/v1/projects/{verified_project_id}/request-second-consent",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert premature.status_code == 422
    assert premature.json()["code"] == 42201
    assert "verifier" in premature.json()["message"]
    assert [corrected.status_code, completed.status_code, draft.status_code, verified.status_code] == [200, 200, 200, 200]
    assert second_consent.status_code == 200


def test_publish_endpoint_records_allowed_and_blocked_publish_decision_audit_logs() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)

    blocked_project_id = _create_project(client, token)
    blocked = client.post(
        f"/api/v1/projects/{blocked_project_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert blocked.status_code == 422

    published_project_id, story_page_id = _published_story(client, token)

    publish_logs = [log for log in store.audit.logs if log.action == "story.publish_decision"]
    assert len(publish_logs) == 2
    blocked_log = next(log for log in publish_logs if log.resource_id == UUID(blocked_project_id))
    allowed_log = next(log for log in publish_logs if log.resource_id == UUID(published_project_id))
    assert blocked_log.metadata["allowed"] == "False"
    assert "second consent" in blocked_log.metadata["reasons"]
    assert allowed_log.metadata == {
        "allowed": "True",
        "reasons": "",
        "story_page_id": story_page_id,
    }


def test_share_link_defaults_disabled_before_publish_and_is_enabled_by_publish() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    project_id = _create_project(client, token)
    claim_id = client.get(
        f"/api/v1/projects/{project_id}/corrections/pending",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["claims"][0]["id"]
    client.post(
        f"/api/v1/claims/{claim_id}/corrections",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "confirm"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/corrections/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    draft = client.post(
        f"/api/v1/projects/{project_id}/drafts/generate",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    story_page_id = draft["story_page_id"]
    prepublish_link = client.post(
        f"/api/v1/story-pages/{story_page_id}/share-links",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "family-code"},
    )
    assert prepublish_link.status_code == 200
    assert prepublish_link.json()["data"]["enabled"] is False
    share_token = prepublish_link.json()["data"]["share_token"]
    blocked_story = client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": share_token, "password": "family-code"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/request-second-consent",
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "family_sharing"},
    )
    published = client.post(
        f"/api/v1/projects/{project_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    postpublish_story = client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": share_token, "password": "family-code"},
    )

    assert share_token
    assert blocked_story.status_code == 404
    assert published.status_code == 200
    assert postpublish_story.status_code == 200


def test_consent_endpoint_persists_traceable_consent_evidence() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()

    token = client.post(
        "/api/v1/auth/wx-login", json={"wx_openid": "wx_phase1", "nickname": "女儿"}
    ).json()["data"]["access_token"]
    project_id = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "storyteller": {"display_name": "爸爸", "relation_to_payer": "father"},
            "title": "爸爸的故事",
            "themes": ["work"],
            "tier": "standard",
        },
    ).json()["data"]["project_id"]

    response = client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "consent_type": "interview_consent",
            "method": "audio",
            "evidence_oss_key": f"consents/{project_id}/interview/audio.wav",
        },
    )

    assert response.status_code == 200
    consent_data = response.json()["data"]
    consent_id = UUID(consent_data["consent_id"])
    consent = store.consent_records[consent_id]
    assert consent_data == {
        **consent_data,
        "project_id": project_id,
        "user_id": response.json()["data"]["user_id"],
        "consent_type": "interview_consent",
        "method": "audio",
        "evidence_oss_key": f"consents/{project_id}/interview/audio.wav",
        "withdrawn_at": None,
        "minimized_at": None,
    }
    assert consent.project_id == UUID(project_id)
    assert consent.consent_type == "interview_consent"
    assert consent.method == "audio"
    assert consent.evidence_oss_key == f"consents/{project_id}/interview/audio.wav"
    consent_log = next(log for log in store.audit.logs if log.action == "consent.create")
    assert consent_log.resource_id == consent_id
    assert consent_log.metadata == {
        "consent_type": "interview_consent",
        "method": "audio",
        "evidence_oss_key": f"consents/{project_id}/interview/audio.wav",
    }


def test_consent_endpoint_rejects_invalid_or_untraceable_consent() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    project_id = _create_project(client, token)

    invalid_type = client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "marketing_opt_in", "method": "text"},
    )
    invalid_method = client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "sms"},
    )
    missing_audio_evidence = client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "audio"},
    )
    wrong_project_audio_evidence = client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "consent_type": "interview_consent",
            "method": "audio",
            "evidence_oss_key": f"consents/{uuid4()}/interview/audio.wav",
        },
    )

    assert [
        invalid_type.status_code,
        invalid_method.status_code,
        missing_audio_evidence.status_code,
        wrong_project_audio_evidence.status_code,
    ] == [422, 422, 422, 422]
    assert invalid_type.json()["code"] == 42201
    assert "unsupported consent_type" in invalid_type.json()["message"]
    assert "unsupported consent method" in invalid_method.json()["message"]
    assert "audio consent evidence" in missing_audio_evidence.json()["message"]
    assert "consent evidence oss_key must be under the project consent prefix" in wrong_project_audio_evidence.json()["message"]
    assert store.consent_records == {}


def test_family_sharing_consent_withdrawal_disables_story_access_and_records_audit() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    project_id, story_page_id = _published_story(client, token)
    share = client.post(
        f"/api/v1/story-pages/{story_page_id}/share-links",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    ).json()["data"]
    before_withdrawal = client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": share["share_token"]},
    )
    assert before_withdrawal.status_code == 200
    consent_id = next(
        consent.id
        for consent in store.consent_records.values()
        if str(consent.project_id) == project_id and consent.consent_type == "family_sharing"
    )

    withdrawn = client.post(
        f"/api/v1/projects/{project_id}/consents/{consent_id}/withdraw",
        headers={"Authorization": f"Bearer {token}"},
    )
    after_withdrawal = client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": share["share_token"]},
    )

    assert withdrawn.status_code == 200
    assert withdrawn.json()["data"]["withdrawn_at"]
    assert store.projects[UUID(project_id)].has_family_sharing_consent is False
    assert store.story_pages[UUID(story_page_id)].enabled is False
    assert store.share_links[UUID(share["share_link_id"])].enabled is False
    assert after_withdrawal.status_code == 404
    assert "consent.withdraw" in {log.action for log in store.audit.logs}


def test_admin_write_endpoints_record_audit_logs() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()

    token = client.post(
        "/api/v1/auth/wx-login", json={"wx_openid": "wx_phase1", "nickname": "女儿"}
    ).json()["data"]["access_token"]
    project_id = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "storyteller": {"display_name": "爸爸", "relation_to_payer": "father"},
            "title": "爸爸的故事",
            "themes": ["work"],
            "tier": "standard",
        },
    ).json()["data"]["project_id"]

    admin_token = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "ops@changjuan.test", "password": "phase1-admin"},
    ).json()["data"]["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    note = client.post(
        f"/api/v1/admin/projects/{project_id}/notes",
        headers=admin_headers,
        json={"body": "call family"},
    )
    payment = client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers=admin_headers,
        json={
            "payment_cents": 49900,
            "payment_method": "manual_wechat",
            "payment_reference": "wx-transfer-002",
        },
    )
    issue_id = uuid4()
    store.verification_issues[issue_id] = {
        "id": str(issue_id),
        "severity": "block",
        "resolved_at": None,
        "resolution_reason": None,
    }
    resolve = client.post(
        f"/api/v1/admin/verification-issues/{issue_id}/resolve",
        headers=admin_headers,
        json={"resolution_reason": "family corrected claim"},
    )
    task_id = uuid4()
    retry = client.post(f"/api/v1/admin/tasks/{task_id}/retry", headers=admin_headers)
    ticket_create = client.post(
        f"/api/v1/projects/{project_id}/support-tickets",
        headers={"Authorization": f"Bearer {token}"},
        json={"category": "general", "body": "需要人工协助"},
    )
    ticket_id = ticket_create.json()["data"]["ticket_id"]
    ticket = client.patch(
        f"/api/v1/admin/support-tickets/{ticket_id}",
        headers=admin_headers,
        json={"status": "pending", "priority": "P1"},
    )

    assert [response.status_code for response in (note, payment, resolve, retry, ticket)] == [
        200,
        200,
        200,
        200,
        200,
    ]
    audit_actions = {log.action for log in store.audit.logs}
    assert {
        "admin.note",
        "admin.mark_payment",
        "admin.resolve_verification_issue",
        "admin.retry_task",
        "admin.patch_support_ticket",
    }.issubset(audit_actions)


def test_support_ticket_create_is_project_scoped_and_visible_to_admin() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    admin_token = _login_admin(client)
    project_id = _create_project(client, token)

    created = client.post(
        f"/api/v1/projects/{project_id}/support-tickets",
        headers={"Authorization": f"Bearer {token}"},
        json={"category": "story_correction", "priority": "P1", "body": "需要人工帮忙核对年份"},
    )
    tickets = client.get(
        "/api/v1/admin/support-tickets",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert created.status_code == 200
    ticket_data = created.json()["data"]
    assert ticket_data == {
        **ticket_data,
        "project_id": project_id,
        "user_id": str(store.projects[UUID(project_id)].user_id),
        "status": "open",
        "priority": "P1",
        "category": "story_correction",
        "body": "需要人工帮忙核对年份",
    }
    assert tickets.status_code == 200
    assert tickets.json()["data"]["support_tickets"][0]["ticket_id"] == ticket_data["ticket_id"]
    assert "support_ticket.create" in {log.action for log in store.audit.logs}


def test_admin_support_ticket_patch_requires_existing_ticket() -> None:
    client = TestClient(create_app())
    admin_token = _login_admin(client)

    patched = client.patch(
        f"/api/v1/admin/support-tickets/{uuid4()}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "pending", "priority": "P1"},
    )

    assert patched.status_code == 404
    assert patched.json()["code"] == 40401


def test_support_ticket_patch_advances_updated_at() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    admin_token = _login_admin(client)
    project_id = _create_project(client, token)
    created = client.post(
        f"/api/v1/projects/{project_id}/support-tickets",
        headers={"Authorization": f"Bearer {token}"},
        json={"category": "story_correction", "priority": "P2", "body": "请协助核对照片说明"},
    )
    assert created.status_code == 200
    ticket_id = UUID(created.json()["data"]["ticket_id"])
    stale = datetime(2026, 1, 1, tzinfo=UTC)
    store.support_tickets[ticket_id].updated_at = stale

    patched = client.patch(
        f"/api/v1/admin/support-tickets/{ticket_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "pending", "priority": "P1"},
    )

    assert patched.status_code == 200
    assert store.support_tickets[ticket_id].updated_at > stale
    assert patched.json()["data"]["updated_at"] != stale.isoformat()


def test_admin_ops_tracks_feedback_costs_manual_work_and_stuck_owner_exports() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    admin_token = _login_admin(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    project_id = _create_project(client, token)

    feedback = client.post(
        f"/api/v1/projects/{project_id}/feedback",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "nps_score": 9,
            "recommend": True,
            "issue_type": "major_fact_error",
            "body": "有一处年份需要人工复核",
        },
    )
    note = client.post(
        f"/api/v1/admin/projects/{project_id}/notes",
        headers=admin_headers,
        json={"note_type": "ops", "body": "已电话确认年份"},
    )
    manual = client.post(
        f"/api/v1/admin/projects/{project_id}/manual-interventions",
        headers=admin_headers,
        json={"category": "fact_review", "minutes": 18, "body": "核对供销社年份"},
    )
    ai_cost = client.post(
        f"/api/v1/admin/projects/{project_id}/ai-costs",
        headers=admin_headers,
        json={
            "task_type": "verification",
            "provider": "qwen",
            "cost_cents": 37,
            "generation_run_id": str(uuid4()),
        },
    )
    owner_id = UUID(client.post(
        "/api/v1/admin/auth/login",
        json={"email": "ops@changjuan.test", "password": "phase1-admin"},
    ).json()["data"]["admin_user_id"])
    stuck = client.post(
        f"/api/v1/admin/projects/{project_id}/stuck",
        headers=admin_headers,
        json={"owner_id": str(owner_id), "reason": "等待家人补充二次确认"},
    )
    metrics = client.get("/api/v1/admin/metrics/pilot", headers=admin_headers)
    ops_export = client.get("/api/v1/admin/exports/household-ops", headers=admin_headers)
    stuck_projects = client.get("/api/v1/admin/stuck-projects", headers=admin_headers)
    detail = client.get(f"/api/v1/admin/projects/{project_id}", headers=admin_headers)

    assert [response.status_code for response in (feedback, note, manual, ai_cost, stuck)] == [200, 200, 200, 200, 200]
    assert len(store.internal_notes) == 1
    assert len(store.feedback) == 1
    assert metrics.json()["data"]["feedback_count"] == 1
    assert metrics.json()["data"]["nps"] == 9
    assert metrics.json()["data"]["recommend_rate"] == 1
    assert metrics.json()["data"]["major_fact_error_complaint_rate"] == 1
    row = ops_export.json()["data"]["households"][0]
    assert row == {
        **row,
        "project_id": project_id,
        "ai_cost_cents": 37,
        "manual_intervention_count": 1,
        "manual_minutes": 18,
        "ops_owner_id": str(owner_id),
        "stuck_reason": "等待家人补充二次确认",
    }
    assert stuck_projects.json()["data"]["projects"][0]["project_id"] == project_id
    assert detail.json()["data"]["internal_notes"][0]["body"] == "已电话确认年份"
    assert {
        "feedback.create",
        "admin.manual_intervention",
        "admin.record_ai_cost",
        "admin.assign_stuck_project",
    }.issubset({log.action for log in store.audit.logs})


def test_pilot_metrics_count_effective_interview_and_family_correction_completion() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    admin_token = _login_admin(client)
    project_id = _create_project(client, token)

    paid = client.post(
        f"/api/v1/admin/projects/{project_id}/mark-payment",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    consent = client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "interview_consent", "method": "text"},
    )
    _upload_minimum_photos(client, project_id, token)
    session = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    session_id = session.json()["data"]["session_id"]
    started = client.post(
        f"/api/v1/interview-sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    ended = client.post(
        f"/api/v1/interview-sessions/{session_id}/end",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "completed"},
    )
    claim_id = client.get(
        f"/api/v1/projects/{project_id}/corrections/pending",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["claims"][0]["id"]
    corrected = client.post(
        f"/api/v1/claims/{claim_id}/corrections",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "confirm"},
    )
    corrections_complete = client.post(
        f"/api/v1/projects/{project_id}/corrections/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    metrics = client.get(
        "/api/v1/admin/metrics/pilot",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert [response.status_code for response in (paid, consent, session, started, ended, corrected, corrections_complete)] == [200, 200, 200, 200, 200, 200, 200]
    assert metrics.status_code == 200
    assert metrics.json()["data"]["effective_interview_completion_rate"] == 1
    assert metrics.json()["data"]["family_correction_completion_rate"] == 1


def test_pilot_metrics_deposit_rate_counts_paid_deposits_not_waivers() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    admin_token = _login_admin(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    paid_project_id = _create_project(client, token)
    waived_project_id = _create_project(client, token)

    paid = client.post(
        f"/api/v1/admin/projects/{paid_project_id}/mark-payment",
        headers=admin_headers,
        json={"payment_cents": 49900, "payment_method": "manual_wechat"},
    )
    waived = client.post(
        f"/api/v1/admin/projects/{waived_project_id}/mark-payment",
        headers=admin_headers,
        json={"payment_cents": 0, "payment_method": "waived", "payment_reference": "pilot-waiver"},
    )
    metrics = client.get("/api/v1/admin/metrics/pilot", headers=admin_headers)

    assert [paid.status_code, waived.status_code, metrics.status_code] == [200, 200, 200]
    assert metrics.json()["data"]["households_total"] == 2
    assert metrics.json()["data"]["deposit_rate"] == 0.5


def test_admin_sensitive_review_queue_marks_claim_reviewed_and_resolves_block_issue() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    admin_token = _login_admin(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    project_id = _create_project(client, token)
    sensitive_claim = ClaimDraft(
        claim_text="家族中有一段高度敏感事件",
        claim_type="sensitive",
        claim_priority=ClaimPriority.P0,
        source_segment_ids=[uuid4()],
        confidence=0.91,
        support_status=SupportStatus.SUPPORTED,
        verification_status="confirmed",
        sensitivity_level="highly_sensitive",
        human_reviewed=False,
    )
    store.claims[sensitive_claim.id] = sensitive_claim
    store.claims_by_project[UUID(project_id)] = [sensitive_claim.id]

    draft = client.post(
        f"/api/v1/projects/{project_id}/drafts/generate",
        headers={"Authorization": f"Bearer {token}"},
    )
    verify = client.post(
        f"/api/v1/projects/{project_id}/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    blocked_second_consent = client.post(
        f"/api/v1/projects/{project_id}/request-second-consent",
        headers={"Authorization": f"Bearer {token}"},
    )
    queue = client.get("/api/v1/admin/sensitive-claims", headers=admin_headers)
    review = client.post(
        f"/api/v1/admin/claims/{sensitive_claim.id}/sensitive-review",
        headers=admin_headers,
        json={"resolution_reason": "reviewed with family, allowed for internal story workflow"},
    )
    second_consent = client.post(
        f"/api/v1/projects/{project_id}/request-second-consent",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert draft.status_code == 200
    assert verify.status_code == 200
    assert blocked_second_consent.status_code == 422
    assert "unresolved block issue" in blocked_second_consent.json()["message"]
    queued_claim = queue.json()["data"]["claims"][0]
    assert queued_claim["claim_id"] == str(sensitive_claim.id)
    assert queued_claim["project_id"] == project_id
    assert queued_claim["sensitivity_level"] == "highly_sensitive"
    assert review.status_code == 200
    assert review.json()["data"]["human_reviewed"] is True
    assert store.claims[sensitive_claim.id].human_reviewed is True
    assert all(
        issue["resolved_at"]
        for issue in store.verification_issues.values()
        if issue.get("claim_id") == str(sensitive_claim.id) and issue.get("gate") == "sensitive_content"
    )
    assert second_consent.status_code == 200
    assert "admin.sensitive_review" in {log.action for log in store.audit.logs}


def test_unresolved_verification_blocks_are_scoped_to_their_project() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    blocked_project_id = _create_project(client, token)
    clean_project_id = _create_project(client, token)
    sensitive_claim = ClaimDraft(
        claim_text="另一个家庭的敏感事实",
        claim_type="sensitive",
        claim_priority=ClaimPriority.P0,
        source_segment_ids=[uuid4()],
        confidence=0.91,
        support_status=SupportStatus.SUPPORTED,
        verification_status="confirmed",
        sensitivity_level="highly_sensitive",
        human_reviewed=False,
    )
    store.claims[sensitive_claim.id] = sensitive_claim
    store.claims_by_project[UUID(blocked_project_id)] = [sensitive_claim.id]
    clean_claim_id = client.get(
        f"/api/v1/projects/{clean_project_id}/corrections/pending",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["claims"][0]["id"]

    blocked_verify = client.post(
        f"/api/v1/projects/{blocked_project_id}/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    clean_correction = client.post(
        f"/api/v1/claims/{clean_claim_id}/corrections",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "confirm"},
    )
    clean_complete = client.post(
        f"/api/v1/projects/{clean_project_id}/corrections/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    clean_draft = client.post(
        f"/api/v1/projects/{clean_project_id}/drafts/generate",
        headers={"Authorization": f"Bearer {token}"},
    )
    clean_verify = client.post(
        f"/api/v1/projects/{clean_project_id}/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    clean_second_consent = client.post(
        f"/api/v1/projects/{clean_project_id}/request-second-consent",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert blocked_verify.status_code == 200
    assert blocked_verify.json()["data"]["issues"][0]["project_id"] == blocked_project_id
    assert [clean_correction.status_code, clean_complete.status_code, clean_draft.status_code, clean_verify.status_code] == [200, 200, 200, 200]
    assert clean_second_consent.status_code == 200
    assert clean_second_consent.json()["data"]["status"] == "elder_second_consent_pending"


def test_admin_simulated_500_records_alert() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    admin_token = _login_admin(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    simulated = client.post("/api/v1/admin/alerts/simulate-500", headers=admin_headers)
    alerts = client.get("/api/v1/admin/alerts", headers=admin_headers)

    assert simulated.status_code == 500
    assert simulated.json()["code"] == 50001
    alert = alerts.json()["data"]["alerts"][0]
    assert alert["path"] == "/api/v1/admin/alerts/simulate-500"
    assert alert["method"] == "POST"
    assert alert["error_type"] == "RuntimeError"
    assert "admin.simulate_500" in {log.action for log in store.audit.logs}


def test_family_corrections_record_audit_logs() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()

    token = client.post(
        "/api/v1/auth/wx-login", json={"wx_openid": "wx_phase1", "nickname": "女儿"}
    ).json()["data"]["access_token"]
    project_id = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "storyteller": {"display_name": "爸爸", "relation_to_payer": "father"},
            "title": "爸爸的故事",
            "themes": ["work"],
            "tier": "standard",
        },
    ).json()["data"]["project_id"]

    claims = client.get(
        f"/api/v1/projects/{project_id}/corrections/pending",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["claims"]
    claim_id = claims[0]["id"]

    correction = client.post(
        f"/api/v1/claims/{claim_id}/corrections",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "confirm", "comment": "looks right"},
    )
    complete = client.post(
        f"/api/v1/projects/{project_id}/corrections/complete",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert correction.status_code == 200
    assert complete.status_code == 200
    audit_actions = {log.action for log in store.audit.logs}
    assert {"claim.correction", "corrections.complete"}.issubset(audit_actions)


def test_claim_correction_history_is_persisted_and_queryable() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    project_id = _create_project(client, token)
    claim_id = client.get(
        f"/api/v1/projects/{project_id}/corrections/pending",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["claims"][0]["id"]

    correction = client.post(
        f"/api/v1/claims/{claim_id}/corrections",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "modify", "modified_text": "父亲1979年进入县供销社工作", "comment": "家人修正年份"},
    )
    history = client.get(
        f"/api/v1/claims/{claim_id}/corrections",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert correction.status_code == 200
    assert history.status_code == 200
    entries = history.json()["data"]["corrections"]
    assert len(entries) == 1
    assert entries[0] == {
        **entries[0],
        "claim_id": claim_id,
        "action": "modify",
        "modified_text": "父亲1979年进入县供销社工作",
        "comment": "家人修正年份",
    }


def test_claim_detail_is_scoped_to_project_owner() -> None:
    client = TestClient(create_app())
    owner_token = _login_user(client)
    other_token = client.post(
        "/api/v1/auth/wx-login",
        json={"wx_openid": "wx_demo", "nickname": "亲属"},
    ).json()["data"]["access_token"]
    project_id = _create_project(client, owner_token)
    claim_id = client.get(
        f"/api/v1/projects/{project_id}/corrections/pending",
        headers={"Authorization": f"Bearer {owner_token}"},
    ).json()["data"]["claims"][0]["id"]

    owner_response = client.get(
        f"/api/v1/claims/{claim_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    other_response = client.get(
        f"/api/v1/claims/{claim_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert owner_response.status_code == 200
    assert owner_response.json()["data"]["id"] == claim_id
    assert other_response.status_code == 404
    assert other_response.json()["code"] == 40401


def test_claim_correction_is_scoped_to_project_owner() -> None:
    client = TestClient(create_app())
    owner_token = _login_user(client)
    other_token = client.post(
        "/api/v1/auth/wx-login",
        json={"wx_openid": "wx_demo", "nickname": "亲属"},
    ).json()["data"]["access_token"]
    project_id = _create_project(client, owner_token)
    claim_id = client.get(
        f"/api/v1/projects/{project_id}/corrections/pending",
        headers={"Authorization": f"Bearer {owner_token}"},
    ).json()["data"]["claims"][0]["id"]

    other_response = client.post(
        f"/api/v1/claims/{claim_id}/corrections",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"action": "delete", "comment": "not my family"},
    )
    owner_response = client.get(
        f"/api/v1/claims/{claim_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert other_response.status_code == 404
    assert other_response.json()["code"] == 40401
    assert owner_response.json()["data"]["verification_status"] == "pending"


def test_claim_delete_correction_soft_deletes_and_removes_claim_from_story_flow() -> None:
    client = TestClient(create_app())

    token = client.post(
        "/api/v1/auth/wx-login", json={"wx_openid": "wx_phase1", "nickname": "女儿"}
    ).json()["data"]["access_token"]
    project_id = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "storyteller": {"display_name": "爸爸", "relation_to_payer": "father"},
            "title": "爸爸的故事",
            "themes": ["work"],
            "tier": "standard",
        },
    ).json()["data"]["project_id"]

    pending_before = client.get(
        f"/api/v1/projects/{project_id}/corrections/pending",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["claims"]
    claim_id = pending_before[0]["id"]
    claim_text = pending_before[0]["claim_text"]

    deleted = client.post(
        f"/api/v1/claims/{claim_id}/corrections",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "delete", "comment": "family requested removal"},
    )
    pending_after = client.get(
        f"/api/v1/projects/{project_id}/corrections/pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    completed = client.post(
        f"/api/v1/projects/{project_id}/corrections/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    draft = client.post(
        f"/api/v1/projects/{project_id}/drafts/generate",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]

    assert deleted.status_code == 200
    deleted_claim = deleted.json()["data"]
    assert deleted_claim["verification_status"] == "deleted"
    assert deleted_claim["deleted_at"]
    assert deleted_claim["purge_after_at"]
    assert pending_after.json()["data"]["claims"] == []
    assert completed.status_code == 200
    assert claim_text not in "\n".join(chapter["body"] for chapter in draft["chapters"])


def test_draft_generation_blocks_until_p0_claims_are_processed() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    project_id = _create_project(client, token)

    blocked = client.post(
        f"/api/v1/projects/{project_id}/drafts/generate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert blocked.status_code == 422
    assert "P0 claims must be processed" in blocked.json()["message"]


def test_hide_from_family_claim_counts_as_processed_without_leaking_to_story() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    project_id = _create_project(client, token)
    pending_before = client.get(
        f"/api/v1/projects/{project_id}/corrections/pending",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["claims"]
    claim_id = pending_before[0]["id"]
    claim_text = pending_before[0]["claim_text"]

    hidden = client.post(
        f"/api/v1/claims/{claim_id}/corrections",
        headers={"Authorization": f"Bearer {token}"},
        json={"action": "hide_from_family", "comment": "只保留在后台，不进入公开故事"},
    )
    completed = client.post(
        f"/api/v1/projects/{project_id}/corrections/complete",
        headers={"Authorization": f"Bearer {token}"},
    )
    draft = client.post(
        f"/api/v1/projects/{project_id}/drafts/generate",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]
    verified = client.post(
        f"/api/v1/projects/{project_id}/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    second_consent = client.post(
        f"/api/v1/projects/{project_id}/request-second-consent",
        headers={"Authorization": f"Bearer {token}"},
    )
    sharing_consent = client.post(
        f"/api/v1/projects/{project_id}/consents",
        headers={"Authorization": f"Bearer {token}"},
        json={"consent_type": "family_sharing"},
    )
    published = client.post(
        f"/api/v1/projects/{project_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert hidden.status_code == 200
    assert hidden.json()["data"]["verification_status"] == "hidden"
    assert completed.status_code == 200
    assert claim_text not in "\n".join(chapter["body"] for chapter in draft["chapters"])
    assert verified.status_code == 200
    assert second_consent.status_code == 200
    assert sharing_consent.status_code == 200
    assert published.status_code == 200


def test_project_delete_creates_queryable_deletion_request_and_hides_project() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()

    token = client.post(
        "/api/v1/auth/wx-login", json={"wx_openid": "wx_phase1", "nickname": "女儿"}
    ).json()["data"]["access_token"]
    project_id = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "storyteller": {"display_name": "爸爸", "relation_to_payer": "father"},
            "title": "爸爸的故事",
            "themes": ["work"],
            "tier": "standard",
        },
    ).json()["data"]["project_id"]

    deleted = client.delete(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    visible_projects = client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    status = client.get(
        f"/api/v1/projects/{project_id}/deletion-request",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert deleted.status_code == 200
    deletion_request_id = UUID(deleted.json()["data"]["deletion_request_id"])
    assert deletion_request_id in store.deletion_requests
    assert deleted.json()["data"]["status"] == "pending"
    assert visible_projects.json()["data"]["projects"] == []
    assert status.status_code == 200
    assert status.json()["data"]["deletion_request_id"] == str(deletion_request_id)
    assert status.json()["data"]["execute_after_at"]
    assert "deletion.request" in {log.action for log in store.audit.logs}


def test_project_delete_disables_story_access_and_soft_deletes_related_resources() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    project_id, story_page_id = _published_story(client, token)
    photo = client.post(
        f"/api/v1/projects/{project_id}/photos/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"oss_key": f"photos/{project_id}/family.jpg", "caption": "全家福"},
    )
    assert photo.status_code == 200
    share = client.post(
        f"/api/v1/story-pages/{story_page_id}/share-links",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    ).json()["data"]
    before_delete = client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": share["share_token"]},
    )
    assert before_delete.status_code == 200

    deleted = client.delete(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    after_delete = client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": share["share_token"]},
    )

    assert deleted.status_code == 200
    assert after_delete.status_code == 404
    page = store.story_pages[UUID(story_page_id)]
    link = store.share_links[UUID(share["share_link_id"])]
    assert page.enabled is False
    assert page.share_links_enabled is False
    assert link.enabled is False
    assert link.revoked_at
    project_chapters = [chapter for chapter in store.chapters.values() if str(chapter.project_id) == project_id]
    assert project_chapters
    assert all(chapter.deleted_at and chapter.purge_after_at for chapter in project_chapters)
    project_chapter_ids = {chapter.id for chapter in project_chapters}
    project_citations = [citation for citation in store.citations.values() if citation.chapter_id in project_chapter_ids]
    assert project_citations
    assert all(citation.deleted_at and citation.purge_after_at for citation in project_citations)
    project_photos = [photo for photo in store.photos.values() if str(photo.project_id) == project_id]
    assert project_photos
    assert all(photo.deleted_at and photo.purge_after_at for photo in project_photos)


def test_due_deletion_purge_physically_removes_resources_and_marks_request_executed() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    project_id, story_page_id = _published_story(client, token)
    photo = client.post(
        f"/api/v1/projects/{project_id}/photos/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"oss_key": f"photos/{project_id}/family.jpg", "caption": "全家福"},
    )
    thumbnail_oss_key = photo.json()["data"]["thumbnail_oss_key"]
    share = client.post(
        f"/api/v1/story-pages/{story_page_id}/share-links",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    ).json()["data"]
    deleted = client.delete(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    deletion_request_id = UUID(deleted.json()["data"]["deletion_request_id"])
    deletion_request = store.deletion_requests[deletion_request_id]
    project_chapter_ids = {chapter.id for chapter in store.chapters.values() if str(chapter.project_id) == project_id}

    result = store.execute_due_deletion(deletion_request_id, at=deletion_request.execute_after_at)

    assert photo.status_code == 200
    assert result["deletion_request_id"] == str(deletion_request_id)
    assert result["status"] == "executed"
    assert result["db_records_purged"] >= 13
    assert result["oss_objects_purged"] == [f"photos/{project_id}/family.jpg", thumbnail_oss_key]
    assert store.deletion_requests[deletion_request_id].executed_at
    assert UUID(story_page_id) not in store.story_pages
    assert UUID(share["share_link_id"]) not in store.share_links
    assert not [chapter for chapter in store.chapters.values() if str(chapter.project_id) == project_id]
    assert not [citation for citation in store.citations.values() if citation.chapter_id in project_chapter_ids]
    assert not [photo for photo in store.photos.values() if str(photo.project_id) == project_id]
    assert not [claim_id for claim_id in store.claims_by_project.get(UUID(project_id), []) if claim_id in store.claims]


def test_due_deletion_purge_includes_audio_chunks_and_pdf_exports() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    project_id, story_page_id = _published_story(client, token)
    _upload_minimum_photos(client, project_id, token)
    session = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = session.json()["data"]["session_id"]
    started = client.post(
        f"/api/v1/interview-sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    audio_oss_key = _audio_oss_key(project_id, session_id, 0)
    audio = client.post(
        f"/api/v1/interview-sessions/{session_id}/audio-chunks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "sequence_number": 0,
            "duration_ms": 400,
            "oss_key": audio_oss_key,
            "partial_transcript": "我大约1978年进了供销社。",
            "transcript_confidence": 0.42,
        },
    )
    exported = client.post(
        f"/api/v1/story-pages/{story_page_id}/pdf-export",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert [session.status_code, started.status_code, audio.status_code, exported.status_code] == [200, 200, 200, 200]
    pdf_export = next(export for export in store.pdf_exports.values() if str(export.project_id) == project_id)
    deleted = client.delete(
        f"/api/v1/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    deletion_request_id = UUID(deleted.json()["data"]["deletion_request_id"])
    deletion_request = store.deletion_requests[deletion_request_id]

    assert next(iter(store.audio_chunks.values())).deleted_at
    transcript_segment = next(iter(store.transcript_segments.values()))
    assert transcript_segment.deleted_at
    assert transcript_segment.purge_after_at
    assert pdf_export.deleted_at
    result = store.execute_due_deletion(deletion_request_id, at=deletion_request.execute_after_at)

    assert result["status"] == "executed"
    assert result["db_records_purged"] >= 6
    assert audio_oss_key in result["oss_objects_purged"]
    assert pdf_export.oss_key in result["oss_objects_purged"]
    assert store.audio_chunks == {}
    assert store.transcript_segments == {}
    assert store.pdf_exports == {}


def test_project_export_returns_traceable_phase1_data_and_records_audit_log() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    project_id, story_page_id = _published_story(client, token)
    photo = client.post(
        f"/api/v1/projects/{project_id}/photos/complete",
        headers={"Authorization": f"Bearer {token}"},
        json={"oss_key": f"photos/{project_id}/family.jpg", "caption": "全家福"},
    )
    assert photo.status_code == 200
    share = client.post(
        f"/api/v1/story-pages/{story_page_id}/share-links",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    ).json()["data"]
    comment = client.post(
        f"/api/v1/story-pages/{story_page_id}/comments",
        json={
            "share_token": share["share_token"],
            "display_name": "小姨",
            "body": "这一段可以保留。",
        },
    )
    feedback = client.post(
        f"/api/v1/projects/{project_id}/feedback",
        headers={"Authorization": f"Bearer {token}"},
        json={"nps_score": 10, "recommend": True, "body": "推荐给亲戚"},
    )
    support = client.post(
        f"/api/v1/projects/{project_id}/support-tickets",
        headers={"Authorization": f"Bearer {token}"},
        json={"category": "export_question", "body": "导出前请帮我确认资料完整"},
    )
    _upload_minimum_photos(client, project_id, token)
    session_id = client.post(
        f"/api/v1/projects/{project_id}/interview-sessions",
        headers={"Authorization": f"Bearer {token}"},
    ).json()["data"]["session_id"]
    client.post(
        f"/api/v1/interview-sessions/{session_id}/start",
        headers={"Authorization": f"Bearer {token}"},
    )
    audio = client.post(
        f"/api/v1/interview-sessions/{session_id}/audio-chunks",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "sequence_number": 0,
            "duration_ms": 400,
            "oss_key": _audio_oss_key(project_id, session_id, 0),
            "partial_transcript": "我大约1978年进了供销社。",
            "transcript_confidence": 0.42,
        },
    )
    assert comment.status_code == 200
    assert feedback.status_code == 200
    assert support.status_code == 200
    assert audio.status_code == 200

    exported = client.get(
        f"/api/v1/projects/{project_id}/export",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert exported.status_code == 200
    export_data = exported.json()["data"]
    assert export_data["project"]["project_id"] == project_id
    assert export_data["story_page"]["story_page_id"] == story_page_id
    assert export_data["story_page"]["chapters"]
    assert export_data["photos"][0]["oss_key"] == f"photos/{project_id}/family.jpg"
    assert export_data["claims"][0]["source_segment_ids"]
    assert export_data["audio_chunks"][0]["oss_key"] == _audio_oss_key(project_id, session_id, 0)
    assert export_data["transcript_segments"][0]["text"] == "我大约1978年进了供销社。"
    assert export_data["transcript_segments"][0]["low_confidence_review"] is True
    assert {consent["consent_type"] for consent in export_data["consents"]} == {
        "interview_consent",
        "family_sharing",
    }
    assert export_data["family_comments"][0]["body"] == "这一段可以保留。"
    assert export_data["feedback"][0]["body"] == "推荐给亲戚"
    assert export_data["support_tickets"][0]["body"] == "导出前请帮我确认资料完整"
    export_log = next(log for log in store.audit.logs if log.action == "project.export")
    assert export_log.resource_id == UUID(project_id)


def test_story_page_requires_password_protected_share_link_and_records_access_log() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()

    token = _login_user(client)
    _, story_page_id = _published_story(client, token)

    no_share_token = client.get(f"/api/v1/story-pages/{story_page_id}")
    assert no_share_token.status_code == 403

    share = client.post(
        f"/api/v1/story-pages/{story_page_id}/share-links",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "family-code"},
    )
    assert share.status_code == 200
    share_data = share.json()["data"]
    UUID(share_data["share_link_id"])
    assert share_data["enabled"] is True
    assert share_data["password_protected"] is True
    assert share_data["share_token"]
    assert share_data["share_url"].endswith(f"share_token={share_data['share_token']}")

    missing_password = client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": share_data["share_token"]},
    )
    assert missing_password.status_code == 403

    story = client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": share_data["share_token"], "password": "family-code"},
    )
    assert story.status_code == 200
    story_data = story.json()["data"]
    assert story_data["story_page_id"] == story_page_id
    assert story_data["chapters"]
    assert any(chapter["audio_citations"] for chapter in story_data["chapters"])
    audio_url = next(
        citation["audio_url"]
        for chapter in story_data["chapters"]
        for citation in chapter["audio_citations"]
    )
    assert "access_token=" in audio_url
    audio = client.get(audio_url)
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/mpeg"
    assert len(store.story_access_logs) == 1
    access_log = next(iter(store.story_access_logs.values()))
    assert str(access_log.story_page_id) == story_page_id
    assert str(access_log.share_link_id) == share_data["share_link_id"]


def test_family_pdf_export_requires_valid_share_access() -> None:
    client = TestClient(create_app())
    token = _login_user(client)
    _, story_page_id = _published_story(client, token)
    share = client.post(
        f"/api/v1/story-pages/{story_page_id}/share-links",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "family-code"},
    ).json()["data"]

    missing_password = client.post(
        f"/api/v1/story-pages/{story_page_id}/pdf-export",
        params={"share_token": share["share_token"]},
    )
    exported = client.post(
        f"/api/v1/story-pages/{story_page_id}/pdf-export",
        params={"share_token": share["share_token"], "password": "family-code"},
    )
    revoked = client.delete(
        f"/api/v1/story-pages/{story_page_id}/share-links/{share['share_link_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    after_revoke = client.post(
        f"/api/v1/story-pages/{story_page_id}/pdf-export",
        params={"share_token": share["share_token"], "password": "family-code"},
    )

    assert missing_password.status_code == 403
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/pdf"
    assert exported.content.startswith(b"%PDF")
    assert revoked.status_code == 200
    assert after_revoke.status_code == 403


def test_story_share_link_can_be_revoked_and_reset() -> None:
    app = create_app()
    client = TestClient(app)
    token = _login_user(client)
    _, story_page_id = _published_story(client, token)

    share = client.post(
        f"/api/v1/story-pages/{story_page_id}/share-links",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    ).json()["data"]
    original_token = share["share_token"]
    link_id = share["share_link_id"]

    revoked = client.delete(
        f"/api/v1/story-pages/{story_page_id}/share-links/{link_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["data"]["enabled"] is False
    rejected_after_revoke = client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": original_token},
    )
    assert rejected_after_revoke.status_code == 403

    reset = client.post(
        f"/api/v1/story-pages/{story_page_id}/share-links/{link_id}/reset",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert reset.status_code == 200
    reset_data = reset.json()["data"]
    assert reset_data["enabled"] is True
    assert reset_data["share_token"] != original_token
    old_token_rejected = client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": original_token},
    )
    new_token_accepted = client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": reset_data["share_token"]},
    )
    assert old_token_rejected.status_code == 403
    assert new_token_accepted.status_code == 200


def test_family_comments_require_valid_story_access_and_are_returned_with_story() -> None:
    app = create_app()
    client = TestClient(app)
    store = app.dependency_overrides[get_store]()
    token = _login_user(client)
    _, story_page_id = _published_story(client, token)
    share = client.post(
        f"/api/v1/story-pages/{story_page_id}/share-links",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "family-code"},
    ).json()["data"]

    blocked = client.post(
        f"/api/v1/story-pages/{story_page_id}/comments",
        json={"display_name": "小姨", "body": "这一段很像外公说话的样子。"},
    )
    assert blocked.status_code == 403

    created = client.post(
        f"/api/v1/story-pages/{story_page_id}/comments",
        json={
            "share_token": share["share_token"],
            "password": "family-code",
            "display_name": "小姨",
            "body": "这一段很像外公说话的样子。",
        },
    )
    assert created.status_code == 200
    comment = created.json()["data"]
    UUID(comment["comment_id"])
    assert comment["display_name"] == "小姨"
    assert len(store.family_comments) == 1

    story = client.get(
        f"/api/v1/story-pages/{story_page_id}",
        params={"share_token": share["share_token"], "password": "family-code"},
    )
    assert story.status_code == 200
    assert story.json()["data"]["comments"] == [comment]
