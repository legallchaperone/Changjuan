from __future__ import annotations

from uuid import UUID

from changjuan_core.providers.router import TaskType
from changjuan_worker.celery_app import batch_transcribe


def test_batch_transcription_worker_returns_generation_run_metadata() -> None:
    result = batch_transcribe.run("audio/project-1/session-1.wav")

    generation_run = result["generation_run"]
    UUID(generation_run["id"])
    assert result["task_type"] == TaskType.BATCH_TRANSCRIPTION.value
    assert generation_run["task_type"] == TaskType.BATCH_TRANSCRIPTION.value
    assert generation_run["provider_name"] == "xunfei_asr"
    assert generation_run["prompt_version"] == "batch-transcription-v1"
    assert len(generation_run["prompt_hash"]) == 64
    assert generation_run["raw_input_oss_key"].startswith(f"generation-runs/{generation_run['id']}/")
    assert generation_run["raw_output_oss_key"].startswith(f"generation-runs/{generation_run['id']}/")
    assert generation_run["attempts"] == 1
    assert result["output"] == {
        "audio_oss_key": "audio/project-1/session-1.wav",
        "provider_status": "queued_for_live_provider",
    }
