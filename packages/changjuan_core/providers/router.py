from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class TaskType(StrEnum):
    REALTIME_STT = "realtime_stt"
    BATCH_TRANSCRIPTION = "batch_transcription"
    INTERVIEWER_TTS = "interviewer_tts"
    INTERVIEW_NEXT_QUESTION = "interview_next_question"
    CLAIM_EXTRACTION = "claim_extraction"
    CONTRADICTION_DETECTION = "contradiction_detection"
    PHOTO_HYPOTHESIS = "photo_hypothesis"
    NARRATIVE_GENERATION = "narrative_generation"
    VERIFICATION = "verification"


ProviderFn = Callable[[dict], dict]
ArtifactSink = Callable[[str, dict], None]
GenerationRunSink = Callable[["GenerationRun"], None]


class ProviderCallError(RuntimeError):
    pass


@dataclass(frozen=True)
class GenerationRun:
    id: UUID
    project_id: UUID | None
    task_type: TaskType
    provider_name: str
    prompt_version: str
    prompt_hash: str
    attempts: int
    raw_input_oss_key: str
    raw_output_oss_key: str
    output: dict
    created_at: datetime
    status: str = "succeeded"
    completed_at: datetime | None = None
    latency_ms: int = 0
    provider_request_id: str = ""

    def __post_init__(self) -> None:
        if self.completed_at is None:
            object.__setattr__(self, "completed_at", self.created_at)


@dataclass
class Route:
    primary: ProviderFn
    backup: ProviderFn
    primary_name: str = "primary"
    backup_name: str = "backup"


class ProviderRouter:
    def __init__(
        self,
        artifact_sink: ArtifactSink | None = None,
        generation_run_sink: GenerationRunSink | None = None,
    ) -> None:
        self._routes: dict[TaskType, Route] = {}
        self.generation_runs: list[GenerationRun] = []
        self._artifact_sink = artifact_sink
        self._generation_run_sink = generation_run_sink

    def register(
        self,
        task_type: TaskType,
        primary: ProviderFn,
        backup: ProviderFn,
        *,
        primary_name: str = "primary",
        backup_name: str = "backup",
    ) -> None:
        self._routes[task_type] = Route(
            primary=primary,
            backup=backup,
            primary_name=primary_name,
            backup_name=backup_name,
        )

    def call(
        self,
        task_type: TaskType,
        payload: dict,
        *,
        prompt_version: str = "phase1-v1",
        project_id: UUID | None = None,
    ) -> GenerationRun:
        if task_type not in self._routes:
            raise KeyError(f"no provider route registered for {task_type.value}")
        route = self._routes[task_type]
        prompt_hash = hashlib.sha256(
            json.dumps({"task": task_type.value, "payload": payload, "prompt": prompt_version}, sort_keys=True).encode()
        ).hexdigest()
        attempts = 0
        last_error: Exception | None = None
        started_at = datetime.now(UTC)
        for _ in range(3):
            attempts += 1
            try:
                output = route.primary(payload)
                return self._record(
                    task_type,
                    route.primary_name,
                    prompt_version,
                    prompt_hash,
                    attempts,
                    payload,
                    output,
                    project_id,
                    started_at,
                )
            except ProviderCallError as exc:
                last_error = exc
        attempts += 1
        try:
            output = route.backup(payload)
        except ProviderCallError as exc:
            if last_error:
                raise last_error from exc
            raise
        return self._record(
            task_type,
            route.backup_name,
            prompt_version,
            prompt_hash,
            attempts,
            payload,
            output,
            project_id,
            started_at,
        )

    def _record(
        self,
        task_type: TaskType,
        provider_name: str,
        prompt_version: str,
        prompt_hash: str,
        attempts: int,
        payload: dict,
        output: dict,
        project_id: UUID | None,
        started_at: datetime,
    ) -> GenerationRun:
        run_id = uuid4()
        completed_at = datetime.now(UTC)
        run = GenerationRun(
            id=run_id,
            project_id=project_id,
            task_type=task_type,
            provider_name=provider_name,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            attempts=attempts,
            raw_input_oss_key=f"generation-runs/{run_id}/input.json",
            raw_output_oss_key=f"generation-runs/{run_id}/output.json",
            output=output,
            created_at=started_at,
            status="succeeded",
            completed_at=completed_at,
            latency_ms=max(1, int((completed_at - started_at).total_seconds() * 1000)),
            provider_request_id=str(output.get("provider_request_id") or ""),
        )
        self._write_artifacts(run, payload, output)
        self.generation_runs.append(run)
        if self._generation_run_sink:
            self._generation_run_sink(run)
        return run

    def _write_artifacts(self, run: GenerationRun, payload: dict, output: dict) -> None:
        if not self._artifact_sink:
            return
        shared = {
            "task_type": run.task_type.value,
            "provider_name": run.provider_name,
            "prompt_version": run.prompt_version,
            "prompt_hash": run.prompt_hash,
        }
        self._artifact_sink(run.raw_input_oss_key, {**shared, "payload": payload})
        self._artifact_sink(run.raw_output_oss_key, {**shared, "output": output})
