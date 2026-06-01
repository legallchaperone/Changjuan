from __future__ import annotations

from pathlib import Path


def test_api_settings_load_phase1_environment_values() -> None:
    from changjuan_api.settings import load_settings

    settings = load_settings(
        {
            "JWT_SECRET": "env-secret-with-at-least-32-bytes",
            "APP_ENV": "production",
            "STORE_BACKEND": "sqlalchemy",
            "API_BASE_URL": "https://phase1-api.example.test",
            "DATABASE_URL": "postgresql+psycopg://phase1:secret@db.example.test:5432/changjuan",
            "REDIS_URL": "redis://redis.example.test:6379/1",
            "MANUAL_PAYMENT_INSTRUCTION": "manual transfer instructions",
            "PII_KMS_KEY_ID": "kms:phase1-prod",
            "ALLOWED_ORIGINS": "https://admin.example.test,https://h5.example.test",
            "WECHAT_APP_ID": "wx_phase1_app",
            "WECHAT_APP_SECRET": "wechat-secret",
            "WECHAT_CODE2SESSION_URL": "https://wechat.example.test/jscode2session",
            "WECHAT_LOGIN_CODE_MAP": "dev-code:wx_phase1:union_phase1,relative-code:wx_demo",
            "PILOT_WHITELIST_OPENIDS": "wx_env_phase1, wx_env_relative",
            "SENTRY_DSN": "https://public@sentry.example.test/1",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example.test/v1/traces",
            "OTEL_SERVICE_NAME": "changjuan-api-prod",
            "ALIYUN_SLS_ENDPOINT": "https://sls.cn-shanghai.aliyuncs.com",
            "ALIYUN_SLS_PROJECT": "changjuan-prod",
            "ALIYUN_SLS_LOGSTORE": "api-errors",
            "ALIYUN_OSS_BUCKET": "changjuan-prod-private",
            "ALIYUN_OSS_ENDPOINT": "https://oss-cn-shanghai.aliyuncs.com",
            "ALIYUN_OSS_KMS_KEY_ID": "kms-oss-phase1",
        }
    )

    assert settings.app_env == "production"
    assert settings.store_backend == "sqlalchemy"
    assert settings.jwt_secret == "env-secret-with-at-least-32-bytes"
    assert settings.api_base_url == "https://phase1-api.example.test"
    assert settings.database_url == "postgresql+psycopg://phase1:secret@db.example.test:5432/changjuan"
    assert settings.redis_url == "redis://redis.example.test:6379/1"
    assert settings.manual_payment_instruction == "manual transfer instructions"
    assert settings.pii_kms_key_id == "kms:phase1-prod"
    assert settings.allowed_origins == ["https://admin.example.test", "https://h5.example.test"]
    assert settings.wechat_app_id == "wx_phase1_app"
    assert settings.wechat_app_secret == "wechat-secret"
    assert settings.wechat_code2session_url == "https://wechat.example.test/jscode2session"
    assert settings.wechat_login_code_map == {
        "dev-code": {"openid": "wx_phase1", "unionid": "union_phase1"},
        "relative-code": {"openid": "wx_demo", "unionid": None},
    }
    assert settings.pilot_whitelist_openids == {"wx_env_phase1", "wx_env_relative"}
    assert settings.sentry_dsn == "https://public@sentry.example.test/1"
    assert settings.otel_exporter_otlp_endpoint == "https://otel.example.test/v1/traces"
    assert settings.otel_service_name == "changjuan-api-prod"
    assert settings.aliyun_sls_endpoint == "https://sls.cn-shanghai.aliyuncs.com"
    assert settings.aliyun_sls_project == "changjuan-prod"
    assert settings.aliyun_sls_logstore == "api-errors"
    assert settings.aliyun_oss_bucket == "changjuan-prod-private"
    assert settings.aliyun_oss_endpoint == "https://oss-cn-shanghai.aliyuncs.com"
    assert settings.aliyun_oss_kms_key_id == "kms-oss-phase1"
    assert settings.production_readiness_errors() == []


def test_production_readiness_errors_reject_default_local_runtime_values() -> None:
    from changjuan_api.settings import load_settings

    settings = load_settings({"APP_ENV": "production"})

    errors = settings.production_readiness_errors()

    assert "JWT_SECRET must be set to a non-default production secret" in errors
    assert "STORE_BACKEND must be sqlalchemy in production" in errors
    assert "DATABASE_URL must not point at localhost in production" in errors
    assert "REDIS_URL must not point at localhost in production" in errors
    assert "PII_KMS_KEY_ID must not use local/dev key material in production" in errors
    assert "ALLOWED_ORIGINS must not include localhost in production" in errors
    assert "WECHAT_APP_ID is required in production" in errors
    assert "WECHAT_APP_SECRET is required in production" in errors
    assert "ALIYUN_OSS_BUCKET must not use local/dev storage in production" in errors
    assert "ALIYUN_OSS_ENDPOINT must use https://oss.aliyuncs.com-compatible endpoint in production" in errors
    assert "ALIYUN_OSS_KMS_KEY_ID must not use local/dev key material in production" in errors


def test_env_example_documents_api_runtime_settings() -> None:
    env_example = set()
    for line in Path(".env.example").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            env_example.add(line.split("=", 1)[0])

    assert {
        "JWT_SECRET",
        "APP_ENV",
        "STORE_BACKEND",
        "API_BASE_URL",
        "DATABASE_URL",
        "REDIS_URL",
        "MANUAL_PAYMENT_INSTRUCTION",
        "PII_KMS_KEY_ID",
        "ALLOWED_ORIGINS",
        "WECHAT_APP_ID",
        "WECHAT_APP_SECRET",
        "WECHAT_CODE2SESSION_URL",
        "WECHAT_LOGIN_CODE_MAP",
        "PILOT_WHITELIST_OPENIDS",
        "SENTRY_DSN",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_SERVICE_NAME",
        "ALIYUN_SLS_ENDPOINT",
        "ALIYUN_SLS_PROJECT",
        "ALIYUN_SLS_LOGSTORE",
        "ALIYUN_OSS_BUCKET",
        "ALIYUN_OSS_ENDPOINT",
        "ALIYUN_OSS_KMS_KEY_ID",
    }.issubset(env_example)
