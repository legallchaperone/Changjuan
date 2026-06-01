from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .redaction import redact_pii


class AuditLog(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    actor_id: UUID | None = None
    action: str
    resource_type: str
    resource_id: UUID | None = None
    reason: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditSink:
    def __init__(self) -> None:
        self.logs: list[AuditLog] = []

    def record(self, log: AuditLog) -> AuditLog:
        log.metadata = {key: _redact_metadata_value(value) for key, value in log.metadata.items()}
        if log.reason:
            log.reason = redact_pii(log.reason)
        self.logs.append(log)
        return log


def _redact_metadata_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_pii(value)
    if isinstance(value, Mapping):
        return {key: _redact_metadata_value(nested_value) for key, nested_value in value.items()}
    if isinstance(value, list):
        return [_redact_metadata_value(item) for item in value]
    return redact_pii(str(value))
