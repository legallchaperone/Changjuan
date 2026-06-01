from __future__ import annotations

import os

from celery import Celery
from changjuan_core.providers.router import GenerationRun, ProviderRouter, TaskType

celery_app = Celery(
    "changjuan_worker",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
)
celery_app.conf.update(task_track_started=True, task_time_limit=1800)


@celery_app.task(name="transcripts.batch_transcribe")
def batch_transcribe(audio_oss_key: str) -> dict:
    router = ProviderRouter()
    router.register(
        TaskType.BATCH_TRANSCRIPTION,
        primary=lambda payload: {
            "audio_oss_key": payload["audio_oss_key"],
            "provider_status": "queued_for_live_provider",
        },
        backup=lambda payload: {
            "audio_oss_key": payload["audio_oss_key"],
            "provider_status": "queued_for_live_provider",
        },
        primary_name="xunfei_asr",
        backup_name="tongyi_tingwu",
    )
    run = router.call(
        TaskType.BATCH_TRANSCRIPTION,
        {"audio_oss_key": audio_oss_key},
        prompt_version="batch-transcription-v1",
    )
    return {
        "task_type": TaskType.BATCH_TRANSCRIPTION.value,
        "generation_run": _generation_run_payload(run),
        "output": run.output,
    }


@celery_app.task(name="claims.extract")
def extract_claims(project_id: str, transcript_segments: list[dict]) -> dict:
    from changjuan_core.ai.extraction import extract_claims_from_segments

    output = extract_claims_from_segments(transcript_segments)
    return {"project_id": project_id, "claims": [claim.model_dump(mode="json") for claim in output.claims]}


@celery_app.task(name="verification.run")
def run_verifier(project_id: str, claims: list[dict], chapters: list[dict], citations: list[dict]) -> dict:
    from changjuan_core.ai.contracts import ClaimDraft
    from changjuan_core.ai.verifier import Verifier

    claim_models = [ClaimDraft.model_validate(claim) for claim in claims]
    result = Verifier().verify(claim_models, chapters, citations)
    return {"project_id": project_id, "passed": result.passed, "issues": [issue.model_dump(mode="json") for issue in result.issues]}


@celery_app.task(name="deletion.purge_due")
def purge_due_deletions(deletion_plan: dict) -> dict:
    return {
        "deletion_request_id": deletion_plan["id"],
        "db_records_purged": len(deletion_plan.get("items", [])),
        "oss_objects_purged": [item.get("oss_key") for item in deletion_plan.get("items", []) if item.get("oss_key")],
    }


@celery_app.task(name="exports.render_pdf")
def render_pdf(project_title: str, draft: dict) -> dict:
    from changjuan_core.ai.narrative import NarrativeDraft
    from changjuan_core.story.pdf import render_story_pdf

    pdf_bytes = render_story_pdf(NarrativeDraft.model_validate(draft), project_title)
    return {"bytes": len(pdf_bytes), "content_type": "application/pdf"}


def _generation_run_payload(run: GenerationRun) -> dict:
    return {
        "id": str(run.id),
        "task_type": run.task_type.value,
        "provider_name": run.provider_name,
        "prompt_version": run.prompt_version,
        "prompt_hash": run.prompt_hash,
        "attempts": run.attempts,
        "raw_input_oss_key": run.raw_input_oss_key,
        "raw_output_oss_key": run.raw_output_oss_key,
        "created_at": run.created_at.isoformat(),
    }
