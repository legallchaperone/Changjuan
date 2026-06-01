from __future__ import annotations

import os
from collections.abc import Mapping
from typing import ClassVar
from urllib.parse import urlparse

from pydantic import BaseModel, Field


class Settings(BaseModel):
    DEFAULT_PILOT_WHITELIST_OPENIDS: ClassVar[set[str]] = {"wx_phase1", "wx_demo"}

    app_env: str = "development"
    store_backend: str = "memory"
    sqlalchemy_create_schema: bool = False
    jwt_secret: str = "phase1-local-secret-with-32-bytes-minimum"
    api_base_url: str = "https://api.changjuan.com"
    database_url: str = "postgresql+psycopg://changjuan:changjuan@localhost:5432/changjuan"
    redis_url: str = "redis://localhost:6379/0"
    manual_payment_instruction: str = "请联系内测运营完成押金支付"
    pii_kms_key_id: str = "kms:local-dev"
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]
    wechat_app_id: str | None = None
    wechat_app_secret: str | None = None
    wechat_code2session_url: str = "https://api.weixin.qq.com/sns/jscode2session"
    wechat_login_code_map: dict[str, dict[str, str | None]] = Field(default_factory=dict)
    pilot_whitelist_openids: set[str] = Field(default_factory=lambda: set(Settings.DEFAULT_PILOT_WHITELIST_OPENIDS))
    sentry_dsn: str | None = None
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "changjuan-api"
    aliyun_sls_endpoint: str | None = None
    aliyun_sls_project: str | None = None
    aliyun_sls_logstore: str | None = None
    aliyun_oss_bucket: str = "changjuan-dev"
    aliyun_oss_endpoint: str = "http://localhost:9000"
    aliyun_oss_kms_key_id: str = "kms:local-dev"

    def production_readiness_errors(self) -> list[str]:
        if self.app_env != "production":
            return []

        errors: list[str] = []
        if self.store_backend != "sqlalchemy":
            errors.append("STORE_BACKEND must be sqlalchemy in production")
        if (
            self.jwt_secret == Settings.model_fields["jwt_secret"].default
            or len(self.jwt_secret) < 32
        ):
            errors.append("JWT_SECRET must be set to a non-default production secret")
        if _is_local_url(self.database_url):
            errors.append("DATABASE_URL must not point at localhost in production")
        if _is_local_url(self.redis_url):
            errors.append("REDIS_URL must not point at localhost in production")
        if _contains_local_or_dev_token(self.pii_kms_key_id):
            errors.append("PII_KMS_KEY_ID must not use local/dev key material in production")
        if any(_is_local_url(origin) for origin in self.allowed_origins):
            errors.append("ALLOWED_ORIGINS must not include localhost in production")
        if not self.wechat_app_id:
            errors.append("WECHAT_APP_ID is required in production")
        if not self.wechat_app_secret:
            errors.append("WECHAT_APP_SECRET is required in production")
        if not self.sentry_dsn:
            errors.append("SENTRY_DSN is required in production")
        if not self.otel_exporter_otlp_endpoint:
            errors.append("OTEL_EXPORTER_OTLP_ENDPOINT is required in production")
        if not self.aliyun_sls_endpoint or not self.aliyun_sls_project or not self.aliyun_sls_logstore:
            errors.append("ALIYUN_SLS_ENDPOINT, ALIYUN_SLS_PROJECT, and ALIYUN_SLS_LOGSTORE are required in production")
        if _contains_local_or_dev_token(self.aliyun_oss_bucket):
            errors.append("ALIYUN_OSS_BUCKET must not use local/dev storage in production")
        if not _is_aliyun_https_endpoint(self.aliyun_oss_endpoint):
            errors.append("ALIYUN_OSS_ENDPOINT must use https://oss.aliyuncs.com-compatible endpoint in production")
        if _contains_local_or_dev_token(self.aliyun_oss_kms_key_id):
            errors.append("ALIYUN_OSS_KMS_KEY_ID must not use local/dev key material in production")
        if self.pilot_whitelist_openids == Settings.DEFAULT_PILOT_WHITELIST_OPENIDS:
            errors.append("PILOT_WHITELIST_OPENIDS must be explicitly configured in production")
        return errors


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = env or os.environ
    return Settings(
        app_env=env.get("APP_ENV", Settings.model_fields["app_env"].default),
        store_backend=env.get("STORE_BACKEND", Settings.model_fields["store_backend"].default).casefold(),
        sqlalchemy_create_schema=_bool(
            env.get(
                "SQLALCHEMY_CREATE_SCHEMA",
                str(Settings.model_fields["sqlalchemy_create_schema"].default),
            )
        ),
        jwt_secret=env.get("JWT_SECRET", Settings.model_fields["jwt_secret"].default),
        api_base_url=env.get("API_BASE_URL", Settings.model_fields["api_base_url"].default),
        database_url=env.get("DATABASE_URL", Settings.model_fields["database_url"].default),
        redis_url=env.get("REDIS_URL", Settings.model_fields["redis_url"].default),
        manual_payment_instruction=env.get(
            "MANUAL_PAYMENT_INSTRUCTION",
            Settings.model_fields["manual_payment_instruction"].default,
        ),
        pii_kms_key_id=env.get("PII_KMS_KEY_ID", Settings.model_fields["pii_kms_key_id"].default),
        allowed_origins=_csv(
            env.get(
                "ALLOWED_ORIGINS",
                ",".join(Settings.model_fields["allowed_origins"].default),
            )
        ),
        wechat_app_id=env.get("WECHAT_APP_ID") or None,
        wechat_app_secret=env.get("WECHAT_APP_SECRET") or None,
        wechat_code2session_url=env.get(
            "WECHAT_CODE2SESSION_URL",
            Settings.model_fields["wechat_code2session_url"].default,
        ),
        wechat_login_code_map=_wechat_login_code_map(env.get("WECHAT_LOGIN_CODE_MAP", "")),
        pilot_whitelist_openids=set(
            _csv(env.get("PILOT_WHITELIST_OPENIDS", ",".join(Settings.DEFAULT_PILOT_WHITELIST_OPENIDS)))
        ),
        sentry_dsn=env.get("SENTRY_DSN") or None,
        otel_exporter_otlp_endpoint=env.get("OTEL_EXPORTER_OTLP_ENDPOINT") or None,
        otel_service_name=env.get(
            "OTEL_SERVICE_NAME",
            Settings.model_fields["otel_service_name"].default,
        ),
        aliyun_sls_endpoint=env.get("ALIYUN_SLS_ENDPOINT") or None,
        aliyun_sls_project=env.get("ALIYUN_SLS_PROJECT") or None,
        aliyun_sls_logstore=env.get("ALIYUN_SLS_LOGSTORE") or None,
        aliyun_oss_bucket=env.get(
            "ALIYUN_OSS_BUCKET",
            Settings.model_fields["aliyun_oss_bucket"].default,
        ),
        aliyun_oss_endpoint=env.get(
            "ALIYUN_OSS_ENDPOINT",
            Settings.model_fields["aliyun_oss_endpoint"].default,
        ),
        aliyun_oss_kms_key_id=env.get("ALIYUN_OSS_KMS_KEY_ID") or env.get(
            "PII_KMS_KEY_ID",
            Settings.model_fields["aliyun_oss_kms_key_id"].default,
        ),
    )


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _wechat_login_code_map(value: str) -> dict[str, dict[str, str | None]]:
    mapping: dict[str, dict[str, str | None]] = {}
    for item in _csv(value):
        parts = [part.strip() for part in item.split(":")]
        if len(parts) not in {2, 3} or not parts[0] or not parts[1]:
            continue
        mapping[parts[0]] = {
            "openid": parts[1],
            "unionid": parts[2] if len(parts) == 3 and parts[2] else None,
        }
    return mapping


def _bool(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _is_local_url(value: str) -> bool:
    hostname = (urlparse(value).hostname or "").casefold()
    return hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".local")


def _contains_local_or_dev_token(value: str) -> bool:
    normalized = value.casefold()
    return any(token in normalized for token in ("local", "localhost", "127.0.0.1", "::1", "dev", "minio"))


def _is_aliyun_https_endpoint(value: str) -> bool:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and hostname.startswith("oss") and hostname.endswith("aliyuncs.com")


settings = load_settings()
