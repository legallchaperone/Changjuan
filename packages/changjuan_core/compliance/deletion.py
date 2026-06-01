from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

SOFT_DELETE_TABLES = {
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
    "pdf_exports",
}


@dataclass(frozen=True)
class ResourceRef:
    table: str
    id: UUID
    oss_key: str | None = None


@dataclass(frozen=True)
class DeletionItem:
    resource: ResourceRef
    deleted_at: datetime
    purge_after_at: datetime

    @property
    def oss_key(self) -> str | None:
        return self.resource.oss_key


@dataclass(frozen=True)
class DeletionPlan:
    id: UUID
    project_id: UUID
    requested_at: datetime
    items: list[DeletionItem]


class DeletionPlanner:
    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        self._now = now_provider or (lambda: datetime.now(UTC))

    def plan_project_deletion(self, project_id: UUID, resources: list[ResourceRef]) -> DeletionPlan:
        now = self._now()
        items: list[DeletionItem] = []
        for resource in resources:
            if resource.table not in SOFT_DELETE_TABLES:
                raise ValueError(f"{resource.table} is not part of the Phase 1 deletion chain")
            items.append(
                DeletionItem(resource=resource, deleted_at=now, purge_after_at=now + timedelta(days=7))
            )
        return DeletionPlan(id=uuid4(), project_id=project_id, requested_at=now, items=items)

    def due_for_purge(self, deletion: DeletionPlan, at: datetime | None = None) -> list[DeletionItem]:
        at = at or self._now()
        return [item for item in deletion.items if item.purge_after_at <= at]
