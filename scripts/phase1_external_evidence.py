from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

EVIDENCE_FILES = {
    "project_management": "project-management.json",
    "provider": "provider-smoke.json",
    "wechat_qa": "wechat-qa.json",
    "legal": "legal-signoff.json",
    "pilot": "pilot.json",
    "observability": "observability.json",
}

REQUIRED_LEGAL_APPROVALS = (
    "interview_consent",
    "second_consent",
    "privacy_policy",
    "deletion_copy",
)

REQUIRED_WECHAT_WORKFLOWS = (
    "devtools_build_ok",
    "wx_login_ok",
    "project_creation_ok",
    "photo_upload_ok",
    "record_permission_ok",
    "upload_ok",
    "family_correction_ok",
    "story_preview_ok",
    "share_settings_ok",
    "privacy_export_delete_ok",
    "navigation_ok",
)

REQUIRED_PHASE1_DELIVERABLES = {
    "wechat_miniprogram_mvp",
    "h5_entry_page",
    "admin_dashboard",
    "fastapi_backend",
    "celery_worker",
    "voice_pipeline",
    "oss_kms_storage",
    "pii_encryption",
    "audit_logs",
    "deletion_worker",
    "claim_ledger",
    "family_correction_workflow",
    "narrative_agent",
    "verifier_agent",
    "second_consent_flow",
    "private_story_page",
    "pdf_export",
    "pilot_dashboard",
    "pilot_data_100_households",
    "phase1_retrospective",
    "phase2_go_no_go_decision",
}

REQUIRED_PILOT_SEGMENTS = {
    "standard_gift": 40,
    "birthday": 20,
    "spring_festival": 15,
    "light_rescue": 15,
    "cross_city_overseas": 10,
}

PILOT_EXPORT_ARTIFACTS = (
    "household_delivery_audit",
    "metrics_export",
    "manual_time_export",
    "refund_abandon_reason_export",
)

PILOT_METRIC_EXPORT_FIELDS = (
    "households_total",
    "completed_households",
    "effective_interview_completion_rate",
    "family_correction_completion_rate",
    "major_fact_error_complaint_rate",
    "recommend_rate",
    "nps",
    "manual_minutes_per_household",
    "evidence_coverage_rate",
    "deposit_rate",
    "cac_cents",
)

REQUIRED_PROVIDER_TASKS = {
    "realtime_stt",
    "batch_transcription",
    "interviewer_tts",
    "interview_next_question",
    "claim_extraction",
    "contradiction_detection",
    "photo_hypothesis",
    "narrative_generation",
    "verification",
}

ALLOWED_PROJECT_TRACKERS = {"github_project", "linear"}
ALLOWED_PROJECT_TRACKER_HOSTS = {"github.com", "linear.app"}
COMPLETED_PROJECT_TICKET_STATUSES = {"done", "completed", "closed"}

ALLOWED_PROVIDERS_BY_TASK = {
    "realtime_stt": {"volcengine_streaming_asr", "aliyun_paraformer"},
    "batch_transcription": {"xunfei_asr", "tongyi_tingwu"},
    "interviewer_tts": {"volcengine_tts", "minimax_tts"},
    "interview_next_question": {"deepseek", "doubao"},
    "claim_extraction": {"deepseek", "doubao"},
    "contradiction_detection": {"deepseek", "doubao"},
    "photo_hypothesis": {"qwen3_vl", "doubao_vision"},
    "narrative_generation": {"deepseek", "doubao"},
    "verification": {"deepseek", "doubao"},
}

NON_PRODUCTION_PROOF_TOKENS = (
    "mock",
    "fake",
    "stub",
    "dummy",
    "sample",
    "local",
    "localhost",
    "127.0.0.1",
    "::1",
    "dev",
    "minio",
)

OBSERVABILITY_PROOF_FIELDS = (
    "sentry_event_id",
    "otel_trace_id",
    "sls_project",
    "oss_bucket",
    "kms_key_id",
    "oss_backup_drill_id",
    "db_backup_restore_drill_id",
    "oss_purge_drill_id",
)

HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
PLACEHOLDER_TOKENS = ("...", "YYYY", "MMDD", "uuid-for-", "00000000-0000-4000-8000-")
PLACEHOLDER_VALUES = {"Name", "0" * 64}


@dataclass(frozen=True)
class EvidenceItem:
    gate: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class EvidenceResult:
    items: list[EvidenceItem]

    @property
    def ok(self) -> bool:
        return all(item.ok for item in self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "items": [item.__dict__ for item in self.items],
            "blockers": [f"{item.gate}: {item.detail}" for item in self.items if not item.ok],
        }


def validate_evidence_dir(directory: Path, *, allow_placeholders: bool = False) -> EvidenceResult:
    items = [
        validate_project_management(
            directory / EVIDENCE_FILES["project_management"],
            allow_placeholders=allow_placeholders,
        ),
        validate_provider(
            directory / EVIDENCE_FILES["provider"],
            allow_placeholders=allow_placeholders,
        ),
        validate_wechat_qa(
            directory / EVIDENCE_FILES["wechat_qa"],
            allow_placeholders=allow_placeholders,
        ),
        validate_legal(
            directory / EVIDENCE_FILES["legal"],
            allow_placeholders=allow_placeholders,
        ),
        validate_pilot(
            directory / EVIDENCE_FILES["pilot"],
            allow_placeholders=allow_placeholders,
        ),
        validate_observability(
            directory / EVIDENCE_FILES["observability"],
            allow_placeholders=allow_placeholders,
        ),
    ]
    return EvidenceResult(items=items)


def validate_project_management(path: Path, *, allow_placeholders: bool = False) -> EvidenceItem:
    payload = _load_json(path, "project_management")
    if isinstance(payload, EvidenceItem):
        return payload
    failures: list[str] = []
    if not allow_placeholders:
        failures.extend(_placeholder_failures(payload))
    if payload.get("spec_confirmed") is not True:
        failures.append("spec_confirmed must be true")
    if not payload.get("spec_confirmed_by"):
        failures.append("spec_confirmed_by is required")
    for field in ("tracker", "tracker_url", "ticket_export_id"):
        if not payload.get(field):
            failures.append(f"{field} is required")
    ticket_export_path = str(payload.get("ticket_export_path") or "")
    ticket_export_sha256 = str(payload.get("ticket_export_sha256") or "")
    if not ticket_export_path:
        failures.append("ticket_export_path is required")
    if not ticket_export_sha256:
        failures.append("ticket_export_sha256 is required")
    elif len(ticket_export_sha256) != 64 or any(char not in HEX_DIGITS for char in ticket_export_sha256):
        failures.append("ticket_export_sha256 must be 64 hex characters")
    if ticket_export_path and ticket_export_sha256 and not allow_placeholders:
        resolved_ticket_export_path = Path(ticket_export_path)
        if not resolved_ticket_export_path.is_absolute():
            resolved_ticket_export_path = Path.cwd() / resolved_ticket_export_path
        if not resolved_ticket_export_path.exists():
            failures.append("ticket_export_path must reference an existing artifact")
        else:
            ticket_export_bytes = resolved_ticket_export_path.read_bytes()
            if (
                len(ticket_export_sha256) == 64
                and all(char in HEX_DIGITS for char in ticket_export_sha256)
                and hashlib.sha256(ticket_export_bytes).hexdigest() != ticket_export_sha256
            ):
                failures.append("ticket_export_sha256 must match ticket_export_path content")
            ticket_export_failures = _ticket_export_failures(
                ticket_export_bytes,
                base_dir=resolved_ticket_export_path.parent,
                tickets_total=int(payload.get("tickets_total") or 0),
                tickets_with_owner=int(payload.get("tickets_with_owner") or 0),
                tickets_with_dependency_status=int(payload.get("tickets_with_dependency_status") or 0),
                tickets_with_dod=int(payload.get("tickets_with_dod") or 0),
            )
            failures.extend(ticket_export_failures)
    tracker = str(payload.get("tracker") or "")
    if tracker and tracker not in ALLOWED_PROJECT_TRACKERS:
        failures.append("tracker must be github_project or linear")
    tracker_url = str(payload.get("tracker_url") or "")
    if tracker_url and not _is_allowed_tracker_url(tracker_url):
        failures.append("tracker_url must be an https GitHub or Linear URL")
    tickets_total = int(payload.get("tickets_total") or 0)
    if tickets_total <= 0:
        failures.append("tickets_total must be > 0")
    ticket_proof_counts = (
        int(payload.get("tickets_with_owner") or 0),
        int(payload.get("tickets_with_dependency_status") or 0),
        int(payload.get("tickets_with_dod") or 0),
    )
    if tickets_total > 0 and any(count != tickets_total for count in ticket_proof_counts):
        failures.append("all tickets must have owner, dependency status, and DoD")
    return _item(
        "project_management",
        failures,
        "Phase 1 tracker, ticket ownership, dependencies, DoD, and spec confirmation verified",
    )


def validate_provider(path: Path, *, allow_placeholders: bool = False) -> EvidenceItem:
    payload = _load_json(path, "provider")
    if isinstance(payload, EvidenceItem):
        return payload
    failures: list[str] = []
    if not allow_placeholders:
        failures.extend(_placeholder_failures(payload))
    if payload.get("ready") is not True:
        failures.append("provider smoke must be ready=true")
    if payload.get("missing_env"):
        failures.append("missing_env must be empty")
    live_task_entries = payload.get("live_tasks") or []
    live_tasks = set(live_task_entries)
    if (
        len(live_task_entries) != len(REQUIRED_PROVIDER_TASKS)
        or len(live_tasks) != len(live_task_entries)
        or live_tasks != REQUIRED_PROVIDER_TASKS
    ):
        failures.append("live_tasks must contain exactly one entry for each Phase 1 provider task")
    if live_tasks != REQUIRED_PROVIDER_TASKS:
        failures.append("live_tasks must cover every Phase 1 provider task")
    smoke_report_path = str(payload.get("smoke_report_path") or "")
    smoke_report_sha256 = str(payload.get("smoke_report_sha256") or "")
    if not smoke_report_path:
        failures.append("smoke_report_path is required")
    if not smoke_report_sha256:
        failures.append("smoke_report_sha256 is required")
    elif len(smoke_report_sha256) != 64 or any(char not in HEX_DIGITS for char in smoke_report_sha256):
        failures.append("smoke_report_sha256 must be 64 hex characters")
    if smoke_report_path and smoke_report_sha256 and not allow_placeholders:
        resolved_smoke_report_path = Path(smoke_report_path)
        if not resolved_smoke_report_path.is_absolute():
            resolved_smoke_report_path = Path.cwd() / resolved_smoke_report_path
        if not resolved_smoke_report_path.exists():
            failures.append("smoke_report_path must reference an existing artifact")
        elif (
            len(smoke_report_sha256) == 64
            and all(char in HEX_DIGITS for char in smoke_report_sha256)
            and hashlib.sha256(resolved_smoke_report_path.read_bytes()).hexdigest()
            != smoke_report_sha256
        ):
            failures.append("smoke_report_sha256 must match smoke_report_path content")
    generation_runs = payload.get("generation_runs") or []
    generation_run_task_types = [
        run.get("task_type") for run in generation_runs if isinstance(run, dict)
    ]
    if (
        len(generation_run_task_types) != len(generation_runs)
        or len(generation_run_task_types) != len(REQUIRED_PROVIDER_TASKS)
        or len(set(generation_run_task_types)) != len(generation_run_task_types)
        or set(generation_run_task_types) != REQUIRED_PROVIDER_TASKS
    ):
        failures.append("generation_runs must contain exactly one run for each Phase 1 provider task")
    runs_by_task = {
        run.get("task_type"): run for run in generation_runs if isinstance(run, dict) and run.get("task_type")
    }
    if set(runs_by_task) != REQUIRED_PROVIDER_TASKS:
        failures.append("generation_runs must include storage metadata for every provider task")
    raw_input_oss_keys: list[str] = []
    raw_output_oss_keys: list[str] = []
    provider_request_ids: list[str] = []
    for task_type, run in runs_by_task.items():
        for field in (
            "id",
            "provider_name",
            "prompt_version",
            "prompt_hash",
            "raw_input_oss_key",
            "raw_output_oss_key",
        ):
            if not run.get(field):
                failures.append(f"generation_runs.{task_type}.{field} is required")
        if not _generation_run_has_live_success_metadata(run):
            failures.append("generation_runs must include live success metadata for every provider task")
        run_id = str(run.get("id") or "")
        if run_id and not _is_uuid(run_id):
            failures.append(f"generation_runs.{task_type}.id must be a UUID")
        provider_name = str(run.get("provider_name") or "")
        if provider_name and _contains_non_production_proof_token(provider_name):
            failures.append(f"generation_runs.{task_type}.provider_name contains non-production proof value")
        allowed_providers = ALLOWED_PROVIDERS_BY_TASK.get(str(task_type), set())
        if provider_name and provider_name not in allowed_providers:
            failures.append(f"generation_runs.{task_type}.provider_name must be a live Phase 1 provider")
        prompt_hash = str(run.get("prompt_hash", ""))
        if prompt_hash and (
            len(prompt_hash) != 64 or any(char not in HEX_DIGITS for char in prompt_hash)
        ):
            failures.append(f"generation_runs.{task_type}.prompt_hash must be 64 hex characters")
        for artifact_field in ("raw_input_oss_key", "raw_output_oss_key"):
            artifact_key = str(run.get(artifact_field) or "")
            if artifact_key and _contains_non_production_proof_token(artifact_key):
                failures.append(f"generation_runs.{task_type}.{artifact_field} contains non-production proof value")
        raw_input_oss_key = str(run.get("raw_input_oss_key") or "")
        raw_output_oss_key = str(run.get("raw_output_oss_key") or "")
        if raw_input_oss_key:
            raw_input_oss_keys.append(raw_input_oss_key)
        if raw_output_oss_key:
            raw_output_oss_keys.append(raw_output_oss_key)
        if raw_input_oss_key and raw_output_oss_key and raw_input_oss_key == raw_output_oss_key:
            failures.append("generation_runs raw_input_oss_key and raw_output_oss_key must be different per run")
        provider_request_id = str(run.get("provider_request_id") or "")
        if provider_request_id:
            provider_request_ids.append(provider_request_id)
        if provider_request_id and _contains_non_production_proof_token(provider_request_id):
            failures.append(f"generation_runs.{task_type}.provider_request_id contains non-production proof value")
    if len(set(raw_input_oss_keys)) != len(raw_input_oss_keys):
        failures.append("generation_runs raw_input_oss_key values must be unique")
    if len(set(raw_output_oss_keys)) != len(raw_output_oss_keys):
        failures.append("generation_runs raw_output_oss_key values must be unique")
    if len(set(provider_request_ids)) != len(provider_request_ids):
        failures.append("generation_runs provider_request_id values must be unique")
    return _item("provider", failures, "provider credentials and live generation runs verified")


def _generation_run_has_live_success_metadata(run: dict[str, Any]) -> bool:
    completed_at = str(run.get("completed_at") or "")
    latency_ms = run.get("latency_ms")
    provider_request_id = str(run.get("provider_request_id") or "")
    return (
        run.get("status") == "succeeded"
        and bool(provider_request_id.strip())
        and _is_timezone_aware_iso8601(completed_at)
        and _is_positive_number(latency_ms)
    )


def validate_wechat_qa(path: Path, *, allow_placeholders: bool = False) -> EvidenceItem:
    payload = _load_json(path, "wechat_qa")
    if isinstance(payload, EvidenceItem):
        return payload
    failures: list[str] = []
    if not allow_placeholders:
        failures.extend(_placeholder_failures(payload))
    for field in ("devtools_build_id", "qa_run_id"):
        if not payload.get(field):
            failures.append(f"{field} is required")
    qa_report_path = str(payload.get("qa_report_path") or "")
    qa_report_sha256 = str(payload.get("qa_report_sha256") or "")
    if not qa_report_path:
        failures.append("qa_report_path is required")
    if not qa_report_sha256:
        failures.append("qa_report_sha256 is required")
    elif len(qa_report_sha256) != 64 or any(char not in HEX_DIGITS for char in qa_report_sha256):
        failures.append("qa_report_sha256 must be 64 hex characters")
    if qa_report_path and qa_report_sha256 and not allow_placeholders:
        resolved_qa_report_path = Path(qa_report_path)
        if not resolved_qa_report_path.is_absolute():
            resolved_qa_report_path = Path.cwd() / resolved_qa_report_path
        if not resolved_qa_report_path.exists():
            failures.append("qa_report_path must reference an existing artifact")
        elif (
            len(qa_report_sha256) == 64
            and all(char in HEX_DIGITS for char in qa_report_sha256)
            and hashlib.sha256(resolved_qa_report_path.read_bytes()).hexdigest() != qa_report_sha256
        ):
            failures.append("qa_report_sha256 must match qa_report_path content")
    for key in REQUIRED_WECHAT_WORKFLOWS:
        if payload.get(key) is not True:
            failures.append(f"{key} must be true")
    devices = payload.get("devices") or []
    ios = [device for device in devices if device.get("platform") == "ios" and device.get("passed")]
    android = [
        device for device in devices if device.get("platform") == "android" and device.get("passed")
    ]
    ios_names = {str(device.get("name") or "").strip() for device in ios if device.get("name")}
    android_names = {
        str(device.get("name") or "").strip() for device in android if device.get("name")
    }
    passing_devices = [*ios, *android]
    if any(not _wechat_device_has_required_workflow_results(device) for device in passing_devices):
        failures.append("passing devices must include all required workflow_results")
    if len(ios) < 3:
        failures.append("at least 3 passing iOS devices required")
    if len(android) < 3:
        failures.append("at least 3 passing Android devices required")
    if len(ios_names) < 3:
        failures.append("at least 3 distinct passing iOS devices required")
    if len(android_names) < 3:
        failures.append("at least 3 distinct passing Android devices required")
    return _item("wechat_qa", failures, "WeChat DevTools, MVP workflows, and device matrix verified")


def _wechat_device_has_required_workflow_results(device: dict[str, Any]) -> bool:
    workflow_results = device.get("workflow_results")
    if not isinstance(workflow_results, dict):
        return False
    return all(workflow_results.get(key) is True for key in REQUIRED_WECHAT_WORKFLOWS)


def validate_legal(path: Path, *, allow_placeholders: bool = False) -> EvidenceItem:
    payload = _load_json(path, "legal")
    if isinstance(payload, EvidenceItem):
        return payload
    approvals = payload.get("approvals") or {}
    failures: list[str] = []
    if not allow_placeholders:
        failures.extend(_placeholder_failures(payload))
    content_paths: list[str] = []
    for approval_name in REQUIRED_LEGAL_APPROVALS:
        approval = approvals.get(approval_name) or {}
        for field in ("approver", "role", "approved_at", "content_path", "version_hash"):
            if not approval.get(field):
                failures.append(f"{approval_name}.{field} is required")
        approved_at = str(approval.get("approved_at") or "")
        if approved_at and not _is_timezone_aware_iso8601(approved_at):
            failures.append(f"{approval_name}.approved_at must be ISO 8601 with timezone")
        version_hash = str(approval.get("version_hash", ""))
        if version_hash and (
            len(version_hash) != 64 or any(char not in HEX_DIGITS for char in version_hash)
        ):
            failures.append(f"{approval_name}.version_hash must be 64 hex characters")
        content_path = str(approval.get("content_path") or "")
        if content_path and version_hash and not allow_placeholders:
            resolved_content_path = Path(content_path)
            if not resolved_content_path.is_absolute():
                resolved_content_path = Path.cwd() / resolved_content_path
            if not resolved_content_path.exists():
                failures.append(f"{approval_name}.content_path must reference an existing artifact")
            elif (
                len(version_hash) == 64
                and all(char in HEX_DIGITS for char in version_hash)
                and hashlib.sha256(resolved_content_path.read_bytes()).hexdigest() != version_hash
            ):
                failures.append(f"{approval_name}.version_hash must match content_path content")
        if content_path:
            content_paths.append(str(Path(content_path).expanduser()))
    if len(set(content_paths)) != len(REQUIRED_LEGAL_APPROVALS):
        failures.append("legal approvals must reference distinct content_path artifacts")
    return _item("legal", failures, "legal sign-off records verified")


def validate_pilot(path: Path, *, allow_placeholders: bool = False) -> EvidenceItem:
    payload = _load_json(path, "pilot")
    if isinstance(payload, EvidenceItem):
        return payload
    failures: list[str] = []
    if not allow_placeholders:
        failures.extend(_placeholder_failures(payload))
    households_total = int(payload.get("households_total") or 0)
    completed = int(payload.get("completed_households") or 0)
    completion_rate = completed / households_total if households_total else 0
    checks = [
        (households_total >= 100, "households_total must be >= 100"),
        (completion_rate >= 0.70, "completion_rate must be >= 70%"),
        (
            float(payload.get("effective_interview_completion_rate") or 0) >= 0.75,
            "effective_interview_completion_rate must be >= 75%",
        ),
        (
            float(payload.get("family_correction_completion_rate") or 0) >= 0.70,
            "family_correction_completion_rate must be >= 70%",
        ),
        (
            float(payload.get("major_fact_error_complaint_rate") or 1) < 0.10,
            "major_fact_error_complaint_rate must be < 10%",
        ),
        (float(payload.get("recommend_rate") or 0) >= 0.80, "recommend_rate must be >= 80%"),
        (float(payload.get("nps") or 0) > 50, "nps must be > 50"),
        (
            float(payload.get("manual_minutes_per_household") or 999) < 60,
            "manual_minutes_per_household must be < 60",
        ),
        (
            float(payload.get("evidence_coverage_rate") or 0) >= 0.80,
            "evidence_coverage_rate must be >= 80%",
        ),
        (float(payload.get("deposit_rate") or 0) >= 0.30, "deposit_rate must be >= 30%"),
        (20000 <= int(payload.get("cac_cents") or 0) <= 40000, "cac_cents must be 20000-40000"),
    ]
    failures.extend(message for passed, message in checks if not passed)
    for field in (
        "household_delivery_audit_id",
        "metrics_export_id",
        "manual_time_export_id",
        "refund_abandon_reason_export_id",
    ):
        if not payload.get(field):
            failures.append(f"{field} is required")
    for artifact_prefix in PILOT_EXPORT_ARTIFACTS:
        artifact_path = str(payload.get(f"{artifact_prefix}_path") or "")
        artifact_sha256 = str(payload.get(f"{artifact_prefix}_sha256") or "")
        if not artifact_path:
            failures.append(f"{artifact_prefix}_path is required")
        if not artifact_sha256:
            failures.append(f"{artifact_prefix}_sha256 is required")
        elif len(artifact_sha256) != 64 or any(char not in HEX_DIGITS for char in artifact_sha256):
            failures.append(f"{artifact_prefix}_sha256 must be 64 hex characters")
        if artifact_path and artifact_sha256 and not allow_placeholders:
            resolved_artifact_path = Path(artifact_path)
            if not resolved_artifact_path.is_absolute():
                resolved_artifact_path = Path.cwd() / resolved_artifact_path
            if not resolved_artifact_path.exists():
                failures.append(f"{artifact_prefix}_path must reference an existing artifact")
            else:
                artifact_bytes = resolved_artifact_path.read_bytes()
                if (
                    len(artifact_sha256) == 64
                    and all(char in HEX_DIGITS for char in artifact_sha256)
                    and hashlib.sha256(artifact_bytes).hexdigest() != artifact_sha256
                ):
                    failures.append(f"{artifact_prefix}_sha256 must match {artifact_prefix}_path content")
                if artifact_prefix == "household_delivery_audit":
                    failures.extend(_pilot_household_delivery_audit_failures(artifact_bytes, declared_payload=payload))
                if artifact_prefix == "metrics_export":
                    failures.extend(_pilot_metrics_export_failures(artifact_bytes, declared_payload=payload))
                if artifact_prefix == "manual_time_export":
                    failures.extend(_pilot_manual_time_export_failures(artifact_bytes, declared_payload=payload))
                if artifact_prefix == "refund_abandon_reason_export":
                    failures.extend(_pilot_refund_abandon_export_failures(artifact_bytes, declared_payload=payload))
    if payload.get("retrospective_completed") is not True:
        failures.append("retrospective_completed must be true")
    retrospective_path = str(payload.get("retrospective_path") or "")
    retrospective_sha256 = str(payload.get("retrospective_sha256") or "")
    if not retrospective_path:
        failures.append("retrospective_path is required")
    if not retrospective_sha256:
        failures.append("retrospective_sha256 is required")
    elif len(retrospective_sha256) != 64 or any(char not in HEX_DIGITS for char in retrospective_sha256):
        failures.append("retrospective_sha256 must be 64 hex characters")
    if retrospective_path and retrospective_sha256 and not allow_placeholders:
        resolved_retrospective_path = Path(retrospective_path)
        if not resolved_retrospective_path.is_absolute():
            resolved_retrospective_path = Path.cwd() / resolved_retrospective_path
        if not resolved_retrospective_path.exists():
            failures.append("retrospective_path must reference an existing artifact")
        elif (
            len(retrospective_sha256) == 64
            and all(char in HEX_DIGITS for char in retrospective_sha256)
            and hashlib.sha256(resolved_retrospective_path.read_bytes()).hexdigest() != retrospective_sha256
        ):
            failures.append("retrospective_sha256 must match retrospective_path content")
    if payload.get("phase2_decision") != "go":
        failures.append("phase2_decision must be go")
    segment_counts = payload.get("segment_counts") or {}
    for segment, minimum in REQUIRED_PILOT_SEGMENTS.items():
        if int(segment_counts.get(segment) or 0) < minimum:
            failures.append(f"segment_counts.{segment} must be >= {minimum}")
    return _item("pilot", failures, "100-household pilot metrics meet Go thresholds")


def validate_observability(path: Path, *, allow_placeholders: bool = False) -> EvidenceItem:
    payload = _load_json(path, "observability")
    if isinstance(payload, EvidenceItem):
        return payload
    failures: list[str] = []
    if not allow_placeholders:
        failures.extend(_placeholder_failures(payload))
    for key in OBSERVABILITY_PROOF_FIELDS:
        if not payload.get(key):
            failures.append(f"{key} is required")
        elif _contains_non_production_proof_token(str(payload[key])):
            failures.append(f"{key} contains non-production proof value")
    sentry_event_id = str(payload.get("sentry_event_id") or "")
    if (
        sentry_event_id
        and not (allow_placeholders and _looks_placeholder(sentry_event_id))
        and not _is_32_hex_id(sentry_event_id)
    ):
        failures.append("sentry_event_id must be a 32-character hex event ID")
    otel_trace_id = str(payload.get("otel_trace_id") or "")
    if (
        otel_trace_id
        and not (allow_placeholders and _looks_placeholder(otel_trace_id))
        and (not _is_32_hex_id(otel_trace_id) or set(otel_trace_id) == {"0"})
    ):
        failures.append("otel_trace_id must be a non-zero 32-character hex trace ID")
    drill_report_path = str(payload.get("drill_report_path") or "")
    drill_report_sha256 = str(payload.get("drill_report_sha256") or "")
    if not drill_report_path:
        failures.append("drill_report_path is required")
    if not drill_report_sha256:
        failures.append("drill_report_sha256 is required")
    elif len(drill_report_sha256) != 64 or any(char not in HEX_DIGITS for char in drill_report_sha256):
        failures.append("drill_report_sha256 must be 64 hex characters")
    if drill_report_path and drill_report_sha256 and not allow_placeholders:
        resolved_drill_report_path = Path(drill_report_path)
        if not resolved_drill_report_path.is_absolute():
            resolved_drill_report_path = Path.cwd() / resolved_drill_report_path
        if not resolved_drill_report_path.exists():
            failures.append("drill_report_path must reference an existing artifact")
        elif (
            len(drill_report_sha256) == 64
            and all(char in HEX_DIGITS for char in drill_report_sha256)
            and hashlib.sha256(resolved_drill_report_path.read_bytes()).hexdigest()
            != drill_report_sha256
        ):
            failures.append("drill_report_sha256 must match drill_report_path content")
    if payload.get("oss_kms_encryption_verified") is not True:
        failures.append("oss_kms_encryption_verified must be true")
    return _item("observability", failures, "production observability, storage, and purge drills verified")


def _load_json(path: Path, gate: str) -> dict[str, Any] | EvidenceItem:
    if not path.exists():
        return EvidenceItem(gate=gate, ok=False, detail=f"missing {path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return EvidenceItem(gate=gate, ok=False, detail=f"invalid JSON: {exc}")


def _item(gate: str, failures: list[str], success: str) -> EvidenceItem:
    if failures:
        return EvidenceItem(gate=gate, ok=False, detail="; ".join(failures))
    return EvidenceItem(gate=gate, ok=True, detail=success)


def _placeholder_failures(payload: Any) -> list[str]:
    failures: list[str] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{path}.{key}" if path else str(key))
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")
            return
        if isinstance(value, str) and _looks_placeholder(value):
            failures.append(f"{path} contains placeholder value")

    visit(payload, "")
    return failures


def _ticket_export_failures(
    payload_bytes: bytes,
    *,
    base_dir: Path,
    tickets_total: int,
    tickets_with_owner: int,
    tickets_with_dependency_status: int,
    tickets_with_dod: int,
) -> list[str]:
    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return ["ticket_export_path must contain valid JSON"]
    tickets = payload.get("tickets") if isinstance(payload, dict) else None
    if not isinstance(tickets, list):
        return ["ticket_export_path must contain a tickets array"]
    failures: list[str] = []
    if len(tickets) != tickets_total:
        failures.append("ticket_export_path must contain tickets_total exported tickets")
    ticket_ids = [
        str(ticket.get("id") or "").strip() for ticket in tickets if isinstance(ticket, dict)
    ]
    if len(ticket_ids) != len(tickets) or len(set(ticket_ids)) != len(ticket_ids) or any(
        not ticket_id for ticket_id in ticket_ids
    ):
        failures.append("ticket_export tickets must have unique non-empty ids")
    counts = {
        "tickets_with_owner": sum(
            1 for ticket in tickets if isinstance(ticket, dict) and str(ticket.get("owner") or "").strip()
        ),
        "tickets_with_dependency_status": sum(
            1
            for ticket in tickets
            if isinstance(ticket, dict) and str(ticket.get("dependency_status") or "").strip()
        ),
        "tickets_with_dod": sum(
            1 for ticket in tickets if isinstance(ticket, dict) and str(ticket.get("dod") or "").strip()
        ),
    }
    if counts != {
        "tickets_with_owner": tickets_with_owner,
        "tickets_with_dependency_status": tickets_with_dependency_status,
        "tickets_with_dod": tickets_with_dod,
    }:
        failures.append("ticket_export owner/dependency/DoD counts must match declared counts")
    deliverable_keys = {
        str(ticket.get("deliverable_key") or "").strip()
        for ticket in tickets
        if isinstance(ticket, dict) and ticket.get("deliverable_key")
    }
    if not REQUIRED_PHASE1_DELIVERABLES.issubset(deliverable_keys):
        failures.append("ticket_export must cover every Phase 1 deliverable")
    completion_statuses = [
        str(ticket.get("completion_status") or "").strip().casefold()
        for ticket in tickets
        if isinstance(ticket, dict)
    ]
    if (
        len(completion_statuses) != len(tickets)
        or any(status not in COMPLETED_PROJECT_TICKET_STATUSES for status in completion_statuses)
    ):
        failures.append("ticket_export tickets must be complete/done")
    if not _ticket_acceptance_evidence_is_valid(tickets, base_dir=base_dir):
        failures.append("ticket_export tickets must reference matching acceptance evidence artifacts")
    return failures


def _ticket_acceptance_evidence_is_valid(tickets: list[Any], *, base_dir: Path) -> bool:
    evidence_paths: list[str] = []
    for ticket in tickets:
        if not isinstance(ticket, dict):
            return False
        artifact_path = str(ticket.get("acceptance_evidence_path") or "")
        artifact_sha256 = str(ticket.get("acceptance_evidence_sha256") or "")
        if (
            not artifact_path
            or len(artifact_sha256) != 64
            or any(char not in HEX_DIGITS for char in artifact_sha256)
        ):
            return False
        resolved_artifact_path = Path(artifact_path)
        if not resolved_artifact_path.is_absolute():
            resolved_artifact_path = base_dir / resolved_artifact_path
        if not resolved_artifact_path.exists():
            return False
        if hashlib.sha256(resolved_artifact_path.read_bytes()).hexdigest() != artifact_sha256:
            return False
        evidence_paths.append(str(resolved_artifact_path))
    return len(set(evidence_paths)) == len(evidence_paths)


def _pilot_household_delivery_audit_failures(
    payload_bytes: bytes,
    *,
    declared_payload: dict[str, Any],
) -> list[str]:
    try:
        audit_payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return ["household_delivery_audit_path must contain valid JSON"]
    if not isinstance(audit_payload, dict):
        return ["household_delivery_audit_path must contain a JSON object"]
    households = audit_payload.get("households")
    if not isinstance(households, list):
        return ["household_delivery_audit_path must contain a households array"]
    failures: list[str] = []
    declared_total = int(declared_payload.get("households_total") or 0)
    declared_completed = int(declared_payload.get("completed_households") or 0)
    if len(households) != declared_total:
        failures.append("household_delivery_audit_path contents must match declared household totals")
    household_ids = [
        str(household.get("household_id") or "").strip()
        for household in households
        if isinstance(household, dict)
    ]
    if len(household_ids) != len(households) or len(set(household_ids)) != len(household_ids) or any(
        not household_id for household_id in household_ids
    ):
        failures.append("household_delivery_audit_path must contain unique household ids")
    completed_households = [
        household for household in households if isinstance(household, dict) and household.get("completed") is True
    ]
    if len(completed_households) != declared_completed:
        failures.append("household_delivery_audit_path contents must match declared household totals")
    for household in completed_households:
        if (
            int(household.get("elder_count") or 0) < 1
            or float(household.get("interview_minutes") or 0) < 15
            or household.get("claim_ledger_completed") is not True
            or household.get("family_correction_completed") is not True
            or household.get("story_page_delivered") is not True
            or household.get("pdf_delivered") is not True
            or household.get("nps_followup_completed") is not True
        ):
            failures.append("household_delivery_audit_path must prove minimum delivery for completed households")
            break
    return failures


def _pilot_metrics_export_failures(
    payload_bytes: bytes,
    *,
    declared_payload: dict[str, Any],
) -> list[str]:
    try:
        metrics_payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return ["metrics_export_path must contain valid JSON"]
    if not isinstance(metrics_payload, dict):
        return ["metrics_export_path must contain a JSON object"]
    metric_mismatch = False
    for field in PILOT_METRIC_EXPORT_FIELDS:
        if not _number_matches(metrics_payload.get(field), declared_payload.get(field)):
            metric_mismatch = True
    if metrics_payload.get("segment_counts") != declared_payload.get("segment_counts"):
        metric_mismatch = True
    if metric_mismatch:
        return ["metrics_export_path contents must match declared pilot metrics"]
    return []


def _pilot_manual_time_export_failures(
    payload_bytes: bytes,
    *,
    declared_payload: dict[str, Any],
) -> list[str]:
    try:
        manual_time_payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return ["manual_time_export_path must contain valid JSON"]
    if not isinstance(manual_time_payload, dict):
        return ["manual_time_export_path must contain a JSON object"]
    if not _number_matches(
        manual_time_payload.get("manual_minutes_per_household"),
        declared_payload.get("manual_minutes_per_household"),
    ):
        return ["manual_time_export_path contents must match declared manual-time metric"]
    return []


def _pilot_refund_abandon_export_failures(
    payload_bytes: bytes,
    *,
    declared_payload: dict[str, Any],
) -> list[str]:
    try:
        refund_payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        return ["refund_abandon_reason_export_path must contain valid JSON"]
    if not isinstance(refund_payload, dict):
        return ["refund_abandon_reason_export_path must contain a JSON object"]
    reason_categories = refund_payload.get("reason_categories")
    if not isinstance(reason_categories, dict) or not reason_categories:
        return ["refund_abandon_reason_export_path must classify all incomplete households"]
    category_counts: list[int | float] = []
    for category, count in reason_categories.items():
        if not str(category).strip() or not _is_non_negative_number(count):
            return ["refund_abandon_reason_export_path must classify all incomplete households"]
        category_counts.append(count)
    incomplete_households = int(declared_payload.get("households_total") or 0) - int(
        declared_payload.get("completed_households") or 0
    )
    if abs(sum(float(count) for count in category_counts) - float(incomplete_households)) > 1e-9:
        return ["refund_abandon_reason_export_path must classify all incomplete households"]
    return []


def _is_non_negative_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value >= 0


def _is_positive_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value > 0


def _number_matches(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return False
    if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
        return False
    return abs(float(actual) - float(expected)) <= 1e-9


def _looks_placeholder(value: str) -> bool:
    stripped = value.strip()
    return stripped in PLACEHOLDER_VALUES or any(token in stripped for token in PLACEHOLDER_TOKENS)


def _contains_non_production_proof_token(value: str) -> bool:
    normalized = value.strip().casefold()
    return any(token in normalized for token in NON_PRODUCTION_PROOF_TOKENS)


def _is_allowed_tracker_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_PROJECT_TRACKER_HOSTS


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _is_32_hex_id(value: str) -> bool:
    return len(value) == 32 and all(char in HEX_DIGITS for char in value)


def _is_timezone_aware_iso8601(value: str) -> bool:
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate external Phase 1 completion evidence.")
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path("docs/evidence/phase1"),
        help="Directory containing Phase 1 evidence JSON files.",
    )
    parser.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="Allow template placeholder values; use only for validating example schema files.",
    )
    args = parser.parse_args()
    result = validate_evidence_dir(args.dir, allow_placeholders=args.allow_placeholders)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
