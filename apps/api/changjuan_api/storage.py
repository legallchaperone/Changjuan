from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from .settings import Settings


@dataclass(frozen=True)
class ObjectStorageConfig:
    endpoint: str
    bucket: str
    kms_key_id: str

    @classmethod
    def from_settings(cls, settings: Settings) -> ObjectStorageConfig:
        return cls(
            endpoint=settings.aliyun_oss_endpoint.rstrip("/"),
            bucket=settings.aliyun_oss_bucket,
            kms_key_id=settings.aliyun_oss_kms_key_id,
        )

    def upload_url(self, oss_key: str) -> str:
        return f"{self.endpoint}/{self.bucket}/{quote(oss_key, safe='/')}"

    def upload_headers(self, content_type: str) -> dict[str, str]:
        return {
            "Content-Type": content_type,
            "x-oss-server-side-encryption": "KMS",
            "x-oss-server-side-encryption-key-id": self.kms_key_id,
            "x-oss-object-acl": "private",
        }

    def readiness_payload(self) -> dict[str, str]:
        return {
            "endpoint": "configured" if self.endpoint else "missing",
            "bucket": "configured" if self.bucket else "missing",
            "kms": "configured" if self.kms_key_id else "missing",
        }
