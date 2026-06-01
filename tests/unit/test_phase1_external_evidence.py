from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


def _pilot_household_delivery_audit(*, total: int = 100, completed: int = 70) -> dict:
    return {
        "name": "household_delivery_audit",
        "source": "real-pilot-export",
        "households": [
            {
                "household_id": f"HH-{index:03d}",
                "completed": index <= completed,
                "elder_count": 1,
                "interview_minutes": 16 if index <= completed else 0,
                "claim_ledger_completed": index <= completed,
                "family_correction_completed": index <= completed,
                "story_page_delivered": index <= completed,
                "pdf_delivered": index <= completed,
                "nps_followup_completed": index <= completed,
            }
            for index in range(1, total + 1)
        ],
    }


def _wechat_workflow_results(**overrides: bool) -> dict[str, bool]:
    results = {
        "devtools_build_ok": True,
        "wx_login_ok": True,
        "project_creation_ok": True,
        "photo_upload_ok": True,
        "record_permission_ok": True,
        "upload_ok": True,
        "family_correction_ok": True,
        "story_preview_ok": True,
        "share_settings_ok": True,
        "privacy_export_delete_ok": True,
        "navigation_ok": True,
    }
    results.update(overrides)
    return results


def _wechat_devices() -> list[dict]:
    return [
        {
            "name": "iPhone 13",
            "platform": "ios",
            "passed": True,
            "workflow_results": _wechat_workflow_results(),
        },
        {
            "name": "iPhone 14",
            "platform": "ios",
            "passed": True,
            "workflow_results": _wechat_workflow_results(),
        },
        {
            "name": "iPhone 15",
            "platform": "ios",
            "passed": True,
            "workflow_results": _wechat_workflow_results(),
        },
        {
            "name": "Pixel 7",
            "platform": "android",
            "passed": True,
            "workflow_results": _wechat_workflow_results(),
        },
        {
            "name": "Xiaomi 14",
            "platform": "android",
            "passed": True,
            "workflow_results": _wechat_workflow_results(),
        },
        {
            "name": "Huawei P60",
            "platform": "android",
            "passed": True,
            "workflow_results": _wechat_workflow_results(),
        },
    ]


def _phase1_ticket_export(
    total: int = 42,
    *,
    acceptance_evidence_dir: Path | None = None,
) -> dict:
    deliverables = [
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
    ]
    if acceptance_evidence_dir:
        acceptance_evidence_dir.mkdir()
    tickets = []
    for index in range(1, total + 1):
        ticket = {
            "id": f"CJ-{index:03d}",
            "owner": "ops",
            "dependency_status": "clear",
            "dod": "defined",
            "completion_status": "done",
            "deliverable_key": deliverables[(index - 1) % len(deliverables)],
        }
        if acceptance_evidence_dir:
            artifact_path = acceptance_evidence_dir / f"CJ-{index:03d}-acceptance.md"
            artifact_path.write_text(f"# CJ-{index:03d} Acceptance\n\nVerified Phase 1 deliverable.\n")
            ticket["acceptance_evidence_path"] = str(artifact_path)
            ticket["acceptance_evidence_sha256"] = hashlib.sha256(
                artifact_path.read_bytes()
            ).hexdigest()
        tickets.append(ticket)
    return {
        "tickets": tickets
    }


def test_external_evidence_validator_reports_all_missing_files(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_evidence_dir

    result = validate_evidence_dir(tmp_path)

    assert result.ok is False
    assert {item.gate for item in result.items if not item.ok} == {
        "project_management",
        "provider",
        "wechat_qa",
        "legal",
        "pilot",
        "observability",
    }


def test_external_evidence_validator_rejects_copied_template_placeholders(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import EVIDENCE_FILES, validate_evidence_dir

    evidence_dir = Path("docs/evidence/phase1")
    for filename in EVIDENCE_FILES.values():
        example_name = filename.replace(".json", ".example.json")
        shutil.copy(evidence_dir / example_name, tmp_path / filename)

    result = validate_evidence_dir(tmp_path)

    assert result.ok is False
    assert any("placeholder" in item.detail for item in result.items if not item.ok)


def test_external_evidence_validator_can_allow_placeholders_for_template_schema_check(
    tmp_path: Path,
) -> None:
    from scripts.phase1_external_evidence import EVIDENCE_FILES, validate_evidence_dir

    evidence_dir = Path("docs/evidence/phase1")
    for filename in EVIDENCE_FILES.values():
        example_name = filename.replace(".json", ".example.json")
        shutil.copy(evidence_dir / example_name, tmp_path / filename)

    result = validate_evidence_dir(tmp_path, allow_placeholders=True)

    assert result.ok is True


def test_project_management_validator_requires_phase1_ticket_proof(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_project_management

    ticket_export_path = tmp_path / "phase1-ticket-export.json"
    ticket_export_path.write_text(
        json.dumps(_phase1_ticket_export(acceptance_evidence_dir=tmp_path / "acceptance"))
    )
    project_path = tmp_path / "project-management.json"
    project_path.write_text(
        json.dumps(
            {
                "spec_confirmed": True,
                "spec_confirmed_by": ["Founder", "Ops"],
                "tracker": "linear",
                "tracker_url": "https://linear.app/changjuan/project/phase-1",
                "ticket_export_id": "linear_export_20260517",
                "ticket_export_path": str(ticket_export_path),
                "ticket_export_sha256": hashlib.sha256(ticket_export_path.read_bytes()).hexdigest(),
                "tickets_total": 42,
                "tickets_with_owner": 42,
                "tickets_with_dependency_status": 42,
                "tickets_with_dod": 42,
            }
        )
    )

    assert validate_project_management(project_path).ok is True


def test_project_management_validator_requires_ticket_export_artifact_hash(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_project_management

    ticket_export_path = tmp_path / "phase1-ticket-export.json"
    ticket_export_path.write_text('{"tickets":[{"owner":"ops","dependency_status":"clear","dod":"defined"}]}')
    project_path = tmp_path / "project-management.json"
    project_path.write_text(
        json.dumps(
            {
                "spec_confirmed": True,
                "spec_confirmed_by": ["Founder", "Ops"],
                "tracker": "linear",
                "tracker_url": "https://linear.app/changjuan/project/phase-1",
                "ticket_export_id": "linear_export_20260517",
                "ticket_export_path": str(ticket_export_path),
                "ticket_export_sha256": "1" * 64,
                "tickets_total": 42,
                "tickets_with_owner": 42,
                "tickets_with_dependency_status": 42,
                "tickets_with_dod": 42,
            }
        )
    )

    item = validate_project_management(project_path)

    assert item.ok is False
    assert "ticket_export_sha256 must match ticket_export_path content" in item.detail


def test_project_management_validator_requires_ticket_export_contents_to_match_counts(
    tmp_path: Path,
) -> None:
    from scripts.phase1_external_evidence import validate_project_management

    ticket_export_path = tmp_path / "phase1-ticket-export.json"
    ticket_export_path.write_text(
        json.dumps(
            {
                "tickets": [
                    {
                        "id": "CJ-001",
                        "owner": "ops",
                        "dependency_status": "clear",
                        "dod": "defined",
                    },
                    {"id": "CJ-002", "owner": "", "dependency_status": "blocked", "dod": ""},
                ]
            }
        )
    )
    project_path = tmp_path / "project-management.json"
    project_path.write_text(
        json.dumps(
            {
                "spec_confirmed": True,
                "spec_confirmed_by": ["Founder", "Ops"],
                "tracker": "linear",
                "tracker_url": "https://linear.app/changjuan/project/phase-1",
                "ticket_export_id": "linear_export_20260517",
                "ticket_export_path": str(ticket_export_path),
                "ticket_export_sha256": hashlib.sha256(ticket_export_path.read_bytes()).hexdigest(),
                "tickets_total": 42,
                "tickets_with_owner": 42,
                "tickets_with_dependency_status": 42,
                "tickets_with_dod": 42,
            }
        )
    )

    item = validate_project_management(project_path)

    assert item.ok is False
    assert "ticket_export_path must contain tickets_total exported tickets" in item.detail
    assert "ticket_export owner/dependency/DoD counts must match declared counts" in item.detail


def test_project_management_validator_requires_ticket_export_to_cover_phase1_deliverables(
    tmp_path: Path,
) -> None:
    from scripts.phase1_external_evidence import validate_project_management

    ticket_export_path = tmp_path / "phase1-ticket-export.json"
    ticket_export_path.write_text(
        json.dumps(
            {
                "tickets": [
                    {
                        "id": f"CJ-{index:03d}",
                        "owner": "ops",
                        "dependency_status": "clear",
                        "dod": "defined",
                        "deliverable_key": "wechat_miniprogram_mvp",
                    }
                    for index in range(1, 43)
                ]
            }
        )
    )
    project_path = tmp_path / "project-management.json"
    project_path.write_text(
        json.dumps(
            {
                "spec_confirmed": True,
                "spec_confirmed_by": ["Founder", "Ops"],
                "tracker": "linear",
                "tracker_url": "https://linear.app/changjuan/project/phase-1",
                "ticket_export_id": "linear_export_20260517",
                "ticket_export_path": str(ticket_export_path),
                "ticket_export_sha256": hashlib.sha256(ticket_export_path.read_bytes()).hexdigest(),
                "tickets_total": 42,
                "tickets_with_owner": 42,
                "tickets_with_dependency_status": 42,
                "tickets_with_dod": 42,
            }
        )
    )

    item = validate_project_management(project_path)

    assert item.ok is False
    assert "ticket_export must cover every Phase 1 deliverable" in item.detail


def test_project_management_validator_requires_ticket_export_tickets_to_be_done(
    tmp_path: Path,
) -> None:
    from scripts.phase1_external_evidence import validate_project_management

    ticket_export = _phase1_ticket_export(acceptance_evidence_dir=tmp_path / "acceptance")
    ticket_export["tickets"][0]["completion_status"] = "in_progress"
    ticket_export_path = tmp_path / "phase1-ticket-export.json"
    ticket_export_path.write_text(json.dumps(ticket_export))
    project_path = tmp_path / "project-management.json"
    project_path.write_text(
        json.dumps(
            {
                "spec_confirmed": True,
                "spec_confirmed_by": ["Founder", "Ops"],
                "tracker": "linear",
                "tracker_url": "https://linear.app/changjuan/project/phase-1",
                "ticket_export_id": "linear_export_20260517",
                "ticket_export_path": str(ticket_export_path),
                "ticket_export_sha256": hashlib.sha256(ticket_export_path.read_bytes()).hexdigest(),
                "tickets_total": 42,
                "tickets_with_owner": 42,
                "tickets_with_dependency_status": 42,
                "tickets_with_dod": 42,
            }
        )
    )

    item = validate_project_management(project_path)

    assert item.ok is False
    assert "ticket_export tickets must be complete/done" in item.detail


def test_project_management_validator_requires_ticket_acceptance_evidence_artifacts(
    tmp_path: Path,
) -> None:
    from scripts.phase1_external_evidence import validate_project_management

    ticket_export_path = tmp_path / "phase1-ticket-export.json"
    ticket_export_path.write_text(json.dumps(_phase1_ticket_export()))
    project_path = tmp_path / "project-management.json"
    project_path.write_text(
        json.dumps(
            {
                "spec_confirmed": True,
                "spec_confirmed_by": ["Founder", "Ops"],
                "tracker": "linear",
                "tracker_url": "https://linear.app/changjuan/project/phase-1",
                "ticket_export_id": "linear_export_20260517",
                "ticket_export_path": str(ticket_export_path),
                "ticket_export_sha256": hashlib.sha256(ticket_export_path.read_bytes()).hexdigest(),
                "tickets_total": 42,
                "tickets_with_owner": 42,
                "tickets_with_dependency_status": 42,
                "tickets_with_dod": 42,
            }
        )
    )

    item = validate_project_management(project_path)

    assert item.ok is False
    assert "ticket_export tickets must reference matching acceptance evidence artifacts" in item.detail


def test_project_management_validator_requires_unique_ticket_export_ids(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_project_management

    ticket_export_path = tmp_path / "phase1-ticket-export.json"
    ticket_export_path.write_text(
        json.dumps(
            {
                "tickets": [
                    {
                        "id": "CJ-001",
                        "owner": "ops",
                        "dependency_status": "clear",
                        "dod": "defined",
                    }
                    for _ in range(42)
                ]
            }
        )
    )
    project_path = tmp_path / "project-management.json"
    project_path.write_text(
        json.dumps(
            {
                "spec_confirmed": True,
                "spec_confirmed_by": ["Founder", "Ops"],
                "tracker": "linear",
                "tracker_url": "https://linear.app/changjuan/project/phase-1",
                "ticket_export_id": "linear_export_20260517",
                "ticket_export_path": str(ticket_export_path),
                "ticket_export_sha256": hashlib.sha256(ticket_export_path.read_bytes()).hexdigest(),
                "tickets_total": 42,
                "tickets_with_owner": 42,
                "tickets_with_dependency_status": 42,
                "tickets_with_dod": 42,
            }
        )
    )

    item = validate_project_management(project_path)

    assert item.ok is False
    assert "ticket_export tickets must have unique non-empty ids" in item.detail


def test_project_management_validator_rejects_incomplete_ticket_setup(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_project_management

    project_path = tmp_path / "project-management.json"
    project_path.write_text(
        json.dumps(
            {
                "spec_confirmed": False,
                "spec_confirmed_by": [],
                "tracker": "linear",
                "tracker_url": "",
                "ticket_export_id": "",
                "tickets_total": 42,
                "tickets_with_owner": 41,
                "tickets_with_dependency_status": 40,
                "tickets_with_dod": 39,
            }
        )
    )

    item = validate_project_management(project_path)

    assert item.ok is False
    assert "spec_confirmed must be true" in item.detail
    assert "tracker_url is required" in item.detail
    assert "all tickets must have owner, dependency status, and DoD" in item.detail


def test_project_management_validator_rejects_unsupported_tracker_or_weak_url(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_project_management

    project_path = tmp_path / "project-management.json"
    project_path.write_text(
        json.dumps(
            {
                "spec_confirmed": True,
                "spec_confirmed_by": ["Founder", "Ops"],
                "tracker": "spreadsheet",
                "tracker_url": "http://example.com/phase-1",
                "ticket_export_id": "linear_export_20260517",
                "tickets_total": 42,
                "tickets_with_owner": 42,
                "tickets_with_dependency_status": 42,
                "tickets_with_dod": 42,
            }
        )
    )

    item = validate_project_management(project_path)

    assert item.ok is False
    assert "tracker must be github_project or linear" in item.detail
    assert "tracker_url must be an https GitHub or Linear URL" in item.detail


def test_provider_validator_requires_generation_run_storage_metadata(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_provider

    provider_path = tmp_path / "provider-smoke.json"
    provider_path.write_text(
        json.dumps(
            {
                "ready": True,
                "missing_env": [],
                "live_tasks": [
                    "realtime_stt",
                    "batch_transcription",
                    "interviewer_tts",
                    "interview_next_question",
                    "claim_extraction",
                    "contradiction_detection",
                    "photo_hypothesis",
                    "narrative_generation",
                    "verification",
                ],
                "generation_run_ids": [
                    "uuid-for-realtime-stt",
                    "uuid-for-batch-transcription",
                    "uuid-for-interviewer-tts",
                    "uuid-for-interview-next-question",
                    "uuid-for-claim-extraction",
                    "uuid-for-contradiction-detection",
                    "uuid-for-photo-hypothesis",
                    "uuid-for-narrative-generation",
                    "uuid-for-verification",
                ],
            }
        )
    )

    item = validate_provider(provider_path)

    assert item.ok is False
    assert "generation_runs must include storage metadata for every provider task" in item.detail


def test_provider_validator_accepts_full_generation_run_metadata(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_provider

    providers = {
        "realtime_stt": "volcengine_streaming_asr",
        "batch_transcription": "xunfei_asr",
        "interviewer_tts": "volcengine_tts",
        "interview_next_question": "deepseek",
        "claim_extraction": "deepseek",
        "contradiction_detection": "deepseek",
        "photo_hypothesis": "qwen3_vl",
        "narrative_generation": "deepseek",
        "verification": "deepseek",
    }
    smoke_report_path = tmp_path / "provider-smoke-report.md"
    smoke_report_path.write_text("# Provider Smoke Report\n\nLive provider task calls and generation-run storage proof.\n")
    provider_path = tmp_path / "provider-smoke.json"
    provider_path.write_text(
        json.dumps(
            {
                "ready": True,
                "missing_env": [],
                "live_tasks": list(providers),
                "smoke_report_path": str(smoke_report_path),
                "smoke_report_sha256": hashlib.sha256(smoke_report_path.read_bytes()).hexdigest(),
                "generation_runs": [
                    {
                        "id": f"11111111-1111-4111-8111-{index:012d}",
                        "task_type": task,
                        "provider_name": provider,
                        "prompt_version": "phase1-v1",
                        "prompt_hash": "a" * 64,
                        "raw_input_oss_key": f"generation-runs/{task}/input.json",
                        "raw_output_oss_key": f"generation-runs/{task}/output.json",
                        "status": "succeeded",
                        "completed_at": "2026-05-17T10:00:00+08:00",
                        "latency_ms": 1200 + index,
                        "provider_request_id": f"volcengine-live-request-{index:03d}",
                    }
                    for index, (task, provider) in enumerate(providers.items(), start=1)
                ],
            }
        )
    )

    assert validate_provider(provider_path).ok is True


def test_provider_validator_requires_live_result_metadata_per_generation_run(
    tmp_path: Path,
) -> None:
    from scripts.phase1_external_evidence import validate_provider

    providers = {
        "realtime_stt": "volcengine_streaming_asr",
        "batch_transcription": "xunfei_asr",
        "interviewer_tts": "volcengine_tts",
        "interview_next_question": "deepseek",
        "claim_extraction": "deepseek",
        "contradiction_detection": "deepseek",
        "photo_hypothesis": "qwen3_vl",
        "narrative_generation": "deepseek",
        "verification": "deepseek",
    }
    smoke_report_path = tmp_path / "provider-smoke-report.md"
    smoke_report_path.write_text("# Provider Smoke Report\n\nLive provider task calls and generation-run storage proof.\n")
    provider_path = tmp_path / "provider-smoke.json"
    provider_path.write_text(
        json.dumps(
            {
                "ready": True,
                "missing_env": [],
                "live_tasks": list(providers),
                "smoke_report_path": str(smoke_report_path),
                "smoke_report_sha256": hashlib.sha256(smoke_report_path.read_bytes()).hexdigest(),
                "generation_runs": [
                    {
                        "id": f"11111111-1111-4111-8111-{index:012d}",
                        "task_type": task,
                        "provider_name": provider,
                        "prompt_version": "phase1-v1",
                        "prompt_hash": "a" * 64,
                        "raw_input_oss_key": f"generation-runs/{task}/input.json",
                        "raw_output_oss_key": f"generation-runs/{task}/output.json",
                    }
                    for index, (task, provider) in enumerate(providers.items(), start=1)
                ],
            }
        )
    )

    item = validate_provider(provider_path)

    assert item.ok is False
    assert "generation_runs must include live success metadata for every provider task" in item.detail


def test_provider_validator_requires_exactly_one_generation_run_per_task(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_provider

    providers = {
        "realtime_stt": "volcengine_streaming_asr",
        "batch_transcription": "xunfei_asr",
        "interviewer_tts": "volcengine_tts",
        "interview_next_question": "deepseek",
        "claim_extraction": "deepseek",
        "contradiction_detection": "deepseek",
        "photo_hypothesis": "qwen3_vl",
        "narrative_generation": "deepseek",
        "verification": "deepseek",
    }
    smoke_report_path = tmp_path / "provider-smoke-report.md"
    smoke_report_path.write_text("# Provider Smoke Report\n\nLive provider task calls and generation-run storage proof.\n")
    generation_runs = [
        {
            "id": f"11111111-1111-4111-8111-{index:012d}",
            "task_type": task,
            "provider_name": provider,
            "prompt_version": "phase1-v1",
            "prompt_hash": "a" * 64,
            "raw_input_oss_key": f"generation-runs/{task}/input.json",
            "raw_output_oss_key": f"generation-runs/{task}/output.json",
        }
        for index, (task, provider) in enumerate(providers.items(), start=1)
    ]
    generation_runs.append(
        {
            "id": "11111111-1111-4111-8111-000000000011",
            "task_type": "claim_extraction",
            "provider_name": "deepseek",
            "prompt_version": "phase1-v1",
            "prompt_hash": "a" * 64,
            "raw_input_oss_key": "generation-runs/claim-extraction-duplicate/input.json",
            "raw_output_oss_key": "generation-runs/claim-extraction-duplicate/output.json",
        }
    )
    provider_path = tmp_path / "provider-smoke.json"
    provider_path.write_text(
        json.dumps(
            {
                "ready": True,
                "missing_env": [],
                "live_tasks": list(providers),
                "smoke_report_path": str(smoke_report_path),
                "smoke_report_sha256": hashlib.sha256(smoke_report_path.read_bytes()).hexdigest(),
                "generation_runs": generation_runs,
            }
        )
    )

    item = validate_provider(provider_path)

    assert item.ok is False
    assert "generation_runs must contain exactly one run for each Phase 1 provider task" in item.detail


def test_provider_validator_requires_exactly_one_live_task_entry_per_task(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_provider

    providers = {
        "realtime_stt": "volcengine_streaming_asr",
        "batch_transcription": "xunfei_asr",
        "interviewer_tts": "volcengine_tts",
        "interview_next_question": "deepseek",
        "claim_extraction": "deepseek",
        "contradiction_detection": "deepseek",
        "photo_hypothesis": "qwen3_vl",
        "narrative_generation": "deepseek",
        "verification": "deepseek",
    }
    smoke_report_path = tmp_path / "provider-smoke-report.md"
    smoke_report_path.write_text("# Provider Smoke Report\n\nLive provider task calls and generation-run storage proof.\n")
    provider_path = tmp_path / "provider-smoke.json"
    provider_path.write_text(
        json.dumps(
            {
                "ready": True,
                "missing_env": [],
                "live_tasks": [*providers, "claim_extraction"],
                "smoke_report_path": str(smoke_report_path),
                "smoke_report_sha256": hashlib.sha256(smoke_report_path.read_bytes()).hexdigest(),
                "generation_runs": [
                    {
                        "id": f"11111111-1111-4111-8111-{index:012d}",
                        "task_type": task,
                        "provider_name": provider,
                        "prompt_version": "phase1-v1",
                        "prompt_hash": "a" * 64,
                        "raw_input_oss_key": f"generation-runs/{task}/input.json",
                        "raw_output_oss_key": f"generation-runs/{task}/output.json",
                    }
                    for index, (task, provider) in enumerate(providers.items(), start=1)
                ],
            }
        )
    )

    item = validate_provider(provider_path)

    assert item.ok is False
    assert "live_tasks must contain exactly one entry for each Phase 1 provider task" in item.detail


def test_provider_validator_requires_smoke_report_artifact_hash(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_provider

    providers = {
        "realtime_stt": "volcengine_streaming_asr",
        "batch_transcription": "xunfei_asr",
        "interviewer_tts": "volcengine_tts",
        "interview_next_question": "deepseek",
        "claim_extraction": "deepseek",
        "contradiction_detection": "deepseek",
        "photo_hypothesis": "qwen3_vl",
        "narrative_generation": "deepseek",
        "verification": "deepseek",
    }
    smoke_report_path = tmp_path / "provider-smoke-report.md"
    smoke_report_path.write_text("# Provider Smoke Report\n\nLive provider task calls and generation-run storage proof.\n")
    provider_path = tmp_path / "provider-smoke.json"
    provider_path.write_text(
        json.dumps(
            {
                "ready": True,
                "missing_env": [],
                "live_tasks": list(providers),
                "smoke_report_path": str(smoke_report_path),
                "smoke_report_sha256": "1" * 64,
                "generation_runs": [
                    {
                        "id": f"11111111-1111-4111-8111-{index:012d}",
                        "task_type": task,
                        "provider_name": provider,
                        "prompt_version": "phase1-v1",
                        "prompt_hash": "a" * 64,
                        "raw_input_oss_key": f"generation-runs/{task}/input.json",
                        "raw_output_oss_key": f"generation-runs/{task}/output.json",
                    }
                    for index, (task, provider) in enumerate(providers.items(), start=1)
                ],
            }
        )
    )

    item = validate_provider(provider_path)

    assert item.ok is False
    assert "smoke_report_sha256 must match smoke_report_path content" in item.detail


def test_provider_validator_requires_distinct_raw_artifact_keys(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_provider

    providers = {
        "realtime_stt": "volcengine_streaming_asr",
        "batch_transcription": "xunfei_asr",
        "interviewer_tts": "volcengine_tts",
        "interview_next_question": "deepseek",
        "claim_extraction": "deepseek",
        "contradiction_detection": "deepseek",
        "photo_hypothesis": "qwen3_vl",
        "narrative_generation": "deepseek",
        "verification": "deepseek",
    }
    smoke_report_path = tmp_path / "provider-smoke-report.md"
    smoke_report_path.write_text("# Provider Smoke Report\n\nLive provider task calls and generation-run storage proof.\n")
    provider_path = tmp_path / "provider-smoke.json"
    provider_path.write_text(
        json.dumps(
            {
                "ready": True,
                "missing_env": [],
                "live_tasks": list(providers),
                "smoke_report_path": str(smoke_report_path),
                "smoke_report_sha256": hashlib.sha256(smoke_report_path.read_bytes()).hexdigest(),
                "generation_runs": [
                    {
                        "id": f"11111111-1111-4111-8111-{index:012d}",
                        "task_type": task,
                        "provider_name": provider,
                        "prompt_version": "phase1-v1",
                        "prompt_hash": "a" * 64,
                        "raw_input_oss_key": "generation-runs/reused/raw.json",
                        "raw_output_oss_key": "generation-runs/reused/raw.json",
                    }
                    for index, (task, provider) in enumerate(providers.items(), start=1)
                ],
            }
        )
    )

    item = validate_provider(provider_path)

    assert item.ok is False
    assert "generation_runs raw_input_oss_key values must be unique" in item.detail
    assert "generation_runs raw_output_oss_key values must be unique" in item.detail
    assert "generation_runs raw_input_oss_key and raw_output_oss_key must be different per run" in item.detail


def test_provider_validator_rejects_non_uuid_run_ids_and_non_production_artifact_keys(
    tmp_path: Path,
) -> None:
    from scripts.phase1_external_evidence import validate_provider

    providers = {
        "realtime_stt": "volcengine_streaming_asr",
        "batch_transcription": "xunfei_asr",
        "interviewer_tts": "volcengine_tts",
        "interview_next_question": "deepseek",
        "claim_extraction": "deepseek",
        "contradiction_detection": "deepseek",
        "photo_hypothesis": "qwen3_vl",
        "narrative_generation": "deepseek",
        "verification": "deepseek",
    }
    provider_path = tmp_path / "provider-smoke.json"
    provider_path.write_text(
        json.dumps(
            {
                "ready": True,
                "missing_env": [],
                "live_tasks": list(providers),
                "generation_runs": [
                    {
                        "id": "run-claim-extraction",
                        "task_type": task,
                        "provider_name": provider,
                        "prompt_version": "phase1-v1",
                        "prompt_hash": "a" * 64,
                        "raw_input_oss_key": f"local-generation-runs/{task}/input.json",
                        "raw_output_oss_key": f"mock-generation-runs/{task}/output.json",
                    }
                    for task, provider in providers.items()
                ],
            }
        )
    )

    item = validate_provider(provider_path)

    assert item.ok is False
    assert "generation_runs.claim_extraction.id must be a UUID" in item.detail
    assert "generation_runs.claim_extraction.raw_input_oss_key contains non-production proof value" in item.detail
    assert "generation_runs.claim_extraction.raw_output_oss_key contains non-production proof value" in item.detail


def test_provider_validator_rejects_mock_or_unapproved_provider_names(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_provider

    providers = {
        "realtime_stt": "volcengine_streaming_asr",
        "batch_transcription": "xunfei_asr",
        "interviewer_tts": "volcengine_tts",
        "interview_next_question": "deepseek",
        "claim_extraction": "mock_llm",
        "contradiction_detection": "deepseek",
        "photo_hypothesis": "qwen3_vl",
        "narrative_generation": "deepseek",
        "verification": "deepseek",
    }
    provider_path = tmp_path / "provider-smoke.json"
    provider_path.write_text(
        json.dumps(
            {
                "ready": True,
                "missing_env": [],
                "live_tasks": list(providers),
                "generation_runs": [
                    {
                        "id": f"run-{task}",
                        "task_type": task,
                        "provider_name": provider,
                        "prompt_version": "phase1-v1",
                        "prompt_hash": "a" * 64,
                        "raw_input_oss_key": f"generation-runs/{task}/input.json",
                        "raw_output_oss_key": f"generation-runs/{task}/output.json",
                    }
                    for task, provider in providers.items()
                ],
            }
        )
    )

    item = validate_provider(provider_path)

    assert item.ok is False
    assert "generation_runs.claim_extraction.provider_name must be a live Phase 1 provider" in item.detail
    assert "generation_runs.claim_extraction.provider_name contains non-production proof value" in item.detail


def test_pilot_validator_enforces_phase1_go_thresholds(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_pilot

    export_paths = {
        "household_delivery_audit": tmp_path / "household-delivery-audit.json",
        "metrics_export": tmp_path / "pilot-metrics-export.json",
        "manual_time_export": tmp_path / "manual-time-export.json",
        "refund_abandon_reason_export": tmp_path / "refund-abandon-reasons.json",
    }
    export_paths["household_delivery_audit"].write_text(
        json.dumps(_pilot_household_delivery_audit())
    )
    export_paths["metrics_export"].write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 70,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.80,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )
    export_paths["manual_time_export"].write_text(
        json.dumps(
            {
                "name": "manual_time_export",
                "source": "real-pilot-export",
                "manual_minutes_per_household": 59,
            }
        )
    )
    export_paths["refund_abandon_reason_export"].write_text(
        json.dumps(
            {
                "name": "refund_abandon_reason_export",
                "source": "real-pilot-export",
                "reason_categories": {
                    "elder_declined_interview": 10,
                    "family_unavailable_for_correction": 8,
                    "refund_requested": 7,
                    "technical_onboarding_failed": 5,
                },
            }
        )
    )
    retrospective_path = tmp_path / "phase1-retrospective.md"
    retrospective_path.write_text("# Phase 1 Retrospective\n\nReal pilot outcomes.\n")
    pilot_path = tmp_path / "pilot.json"
    pilot_path.write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 70,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.80,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "household_delivery_audit_id": "household_delivery_20260517",
                "metrics_export_id": "pilot_metrics_20260517",
                "manual_time_export_id": "manual_time_20260517",
                "refund_abandon_reason_export_id": "refund_abandon_20260517",
                "household_delivery_audit_path": str(export_paths["household_delivery_audit"]),
                "household_delivery_audit_sha256": hashlib.sha256(
                    export_paths["household_delivery_audit"].read_bytes()
                ).hexdigest(),
                "metrics_export_path": str(export_paths["metrics_export"]),
                "metrics_export_sha256": hashlib.sha256(export_paths["metrics_export"].read_bytes()).hexdigest(),
                "manual_time_export_path": str(export_paths["manual_time_export"]),
                "manual_time_export_sha256": hashlib.sha256(
                    export_paths["manual_time_export"].read_bytes()
                ).hexdigest(),
                "refund_abandon_reason_export_path": str(export_paths["refund_abandon_reason_export"]),
                "refund_abandon_reason_export_sha256": hashlib.sha256(
                    export_paths["refund_abandon_reason_export"].read_bytes()
                ).hexdigest(),
                "retrospective_completed": True,
                "retrospective_path": str(retrospective_path),
                "retrospective_sha256": hashlib.sha256(retrospective_path.read_bytes()).hexdigest(),
                "phase2_decision": "go",
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )

    item = validate_pilot(pilot_path)

    assert item.ok is True


def test_pilot_validator_requires_metrics_export_contents_to_match_declared_metrics(
    tmp_path: Path,
) -> None:
    from scripts.phase1_external_evidence import validate_pilot

    export_paths = {
        "household_delivery_audit": tmp_path / "household-delivery-audit.json",
        "metrics_export": tmp_path / "pilot-metrics-export.json",
        "manual_time_export": tmp_path / "manual-time-export.json",
        "refund_abandon_reason_export": tmp_path / "refund-abandon-reasons.json",
    }
    export_paths["household_delivery_audit"].write_text(
        json.dumps({"name": "household_delivery_audit", "source": "real-pilot-export"})
    )
    export_paths["metrics_export"].write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 69,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.80,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )
    export_paths["manual_time_export"].write_text(
        json.dumps({"name": "manual_time_export", "source": "real-pilot-export"})
    )
    export_paths["refund_abandon_reason_export"].write_text(
        json.dumps({"name": "refund_abandon_reason_export", "source": "real-pilot-export"})
    )
    retrospective_path = tmp_path / "phase1-retrospective.md"
    retrospective_path.write_text("# Phase 1 Retrospective\n\nReal pilot outcomes.\n")
    pilot_path = tmp_path / "pilot.json"
    pilot_path.write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 70,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.80,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "household_delivery_audit_id": "household_delivery_20260517",
                "metrics_export_id": "pilot_metrics_20260517",
                "manual_time_export_id": "manual_time_20260517",
                "refund_abandon_reason_export_id": "refund_abandon_20260517",
                "household_delivery_audit_path": str(export_paths["household_delivery_audit"]),
                "household_delivery_audit_sha256": hashlib.sha256(
                    export_paths["household_delivery_audit"].read_bytes()
                ).hexdigest(),
                "metrics_export_path": str(export_paths["metrics_export"]),
                "metrics_export_sha256": hashlib.sha256(export_paths["metrics_export"].read_bytes()).hexdigest(),
                "manual_time_export_path": str(export_paths["manual_time_export"]),
                "manual_time_export_sha256": hashlib.sha256(
                    export_paths["manual_time_export"].read_bytes()
                ).hexdigest(),
                "refund_abandon_reason_export_path": str(export_paths["refund_abandon_reason_export"]),
                "refund_abandon_reason_export_sha256": hashlib.sha256(
                    export_paths["refund_abandon_reason_export"].read_bytes()
                ).hexdigest(),
                "retrospective_completed": True,
                "retrospective_path": str(retrospective_path),
                "retrospective_sha256": hashlib.sha256(retrospective_path.read_bytes()).hexdigest(),
                "phase2_decision": "go",
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )

    item = validate_pilot(pilot_path)

    assert item.ok is False
    assert "metrics_export_path contents must match declared pilot metrics" in item.detail


def test_pilot_validator_requires_household_delivery_audit_contents_to_match_declared_totals(
    tmp_path: Path,
) -> None:
    from scripts.phase1_external_evidence import validate_pilot

    export_paths = {
        "household_delivery_audit": tmp_path / "household-delivery-audit.json",
        "metrics_export": tmp_path / "pilot-metrics-export.json",
        "manual_time_export": tmp_path / "manual-time-export.json",
        "refund_abandon_reason_export": tmp_path / "refund-abandon-reasons.json",
    }
    export_paths["household_delivery_audit"].write_text(
        json.dumps(_pilot_household_delivery_audit(completed=69))
    )
    export_paths["metrics_export"].write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 70,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.80,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )
    export_paths["manual_time_export"].write_text(
        json.dumps(
            {
                "name": "manual_time_export",
                "source": "real-pilot-export",
                "manual_minutes_per_household": 59,
            }
        )
    )
    export_paths["refund_abandon_reason_export"].write_text(
        json.dumps(
            {
                "name": "refund_abandon_reason_export",
                "source": "real-pilot-export",
                "reason_categories": {
                    "elder_declined_interview": 10,
                    "family_unavailable_for_correction": 8,
                    "refund_requested": 7,
                    "technical_onboarding_failed": 5,
                },
            }
        )
    )
    retrospective_path = tmp_path / "phase1-retrospective.md"
    retrospective_path.write_text("# Phase 1 Retrospective\n\nReal pilot outcomes.\n")
    pilot_path = tmp_path / "pilot.json"
    pilot_path.write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 70,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.80,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "household_delivery_audit_id": "household_delivery_20260517",
                "metrics_export_id": "pilot_metrics_20260517",
                "manual_time_export_id": "manual_time_20260517",
                "refund_abandon_reason_export_id": "refund_abandon_20260517",
                "household_delivery_audit_path": str(export_paths["household_delivery_audit"]),
                "household_delivery_audit_sha256": hashlib.sha256(
                    export_paths["household_delivery_audit"].read_bytes()
                ).hexdigest(),
                "metrics_export_path": str(export_paths["metrics_export"]),
                "metrics_export_sha256": hashlib.sha256(export_paths["metrics_export"].read_bytes()).hexdigest(),
                "manual_time_export_path": str(export_paths["manual_time_export"]),
                "manual_time_export_sha256": hashlib.sha256(
                    export_paths["manual_time_export"].read_bytes()
                ).hexdigest(),
                "refund_abandon_reason_export_path": str(export_paths["refund_abandon_reason_export"]),
                "refund_abandon_reason_export_sha256": hashlib.sha256(
                    export_paths["refund_abandon_reason_export"].read_bytes()
                ).hexdigest(),
                "retrospective_completed": True,
                "retrospective_path": str(retrospective_path),
                "retrospective_sha256": hashlib.sha256(retrospective_path.read_bytes()).hexdigest(),
                "phase2_decision": "go",
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )

    item = validate_pilot(pilot_path)

    assert item.ok is False
    assert "household_delivery_audit_path contents must match declared household totals" in item.detail


def test_pilot_validator_requires_manual_time_export_contents_to_match_declared_metric(
    tmp_path: Path,
) -> None:
    from scripts.phase1_external_evidence import validate_pilot

    export_paths = {
        "household_delivery_audit": tmp_path / "household-delivery-audit.json",
        "metrics_export": tmp_path / "pilot-metrics-export.json",
        "manual_time_export": tmp_path / "manual-time-export.json",
        "refund_abandon_reason_export": tmp_path / "refund-abandon-reasons.json",
    }
    export_paths["household_delivery_audit"].write_text(
        json.dumps({"name": "household_delivery_audit", "source": "real-pilot-export"})
    )
    export_paths["metrics_export"].write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 70,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.80,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )
    export_paths["manual_time_export"].write_text(
        json.dumps(
            {
                "name": "manual_time_export",
                "source": "real-pilot-export",
                "manual_minutes_per_household": 61,
            }
        )
    )
    export_paths["refund_abandon_reason_export"].write_text(
        json.dumps({"name": "refund_abandon_reason_export", "source": "real-pilot-export"})
    )
    retrospective_path = tmp_path / "phase1-retrospective.md"
    retrospective_path.write_text("# Phase 1 Retrospective\n\nReal pilot outcomes.\n")
    pilot_path = tmp_path / "pilot.json"
    pilot_path.write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 70,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.80,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "household_delivery_audit_id": "household_delivery_20260517",
                "metrics_export_id": "pilot_metrics_20260517",
                "manual_time_export_id": "manual_time_20260517",
                "refund_abandon_reason_export_id": "refund_abandon_20260517",
                "household_delivery_audit_path": str(export_paths["household_delivery_audit"]),
                "household_delivery_audit_sha256": hashlib.sha256(
                    export_paths["household_delivery_audit"].read_bytes()
                ).hexdigest(),
                "metrics_export_path": str(export_paths["metrics_export"]),
                "metrics_export_sha256": hashlib.sha256(export_paths["metrics_export"].read_bytes()).hexdigest(),
                "manual_time_export_path": str(export_paths["manual_time_export"]),
                "manual_time_export_sha256": hashlib.sha256(
                    export_paths["manual_time_export"].read_bytes()
                ).hexdigest(),
                "refund_abandon_reason_export_path": str(export_paths["refund_abandon_reason_export"]),
                "refund_abandon_reason_export_sha256": hashlib.sha256(
                    export_paths["refund_abandon_reason_export"].read_bytes()
                ).hexdigest(),
                "retrospective_completed": True,
                "retrospective_path": str(retrospective_path),
                "retrospective_sha256": hashlib.sha256(retrospective_path.read_bytes()).hexdigest(),
                "phase2_decision": "go",
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )

    item = validate_pilot(pilot_path)

    assert item.ok is False
    assert "manual_time_export_path contents must match declared manual-time metric" in item.detail


def test_pilot_validator_requires_refund_abandon_export_reason_categories(
    tmp_path: Path,
) -> None:
    from scripts.phase1_external_evidence import validate_pilot

    export_paths = {
        "household_delivery_audit": tmp_path / "household-delivery-audit.json",
        "metrics_export": tmp_path / "pilot-metrics-export.json",
        "manual_time_export": tmp_path / "manual-time-export.json",
        "refund_abandon_reason_export": tmp_path / "refund-abandon-reasons.json",
    }
    export_paths["household_delivery_audit"].write_text(
        json.dumps({"name": "household_delivery_audit", "source": "real-pilot-export"})
    )
    export_paths["metrics_export"].write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 70,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.80,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )
    export_paths["manual_time_export"].write_text(
        json.dumps(
            {
                "name": "manual_time_export",
                "source": "real-pilot-export",
                "manual_minutes_per_household": 59,
            }
        )
    )
    export_paths["refund_abandon_reason_export"].write_text(
        json.dumps({"name": "refund_abandon_reason_export", "source": "real-pilot-export"})
    )
    retrospective_path = tmp_path / "phase1-retrospective.md"
    retrospective_path.write_text("# Phase 1 Retrospective\n\nReal pilot outcomes.\n")
    pilot_path = tmp_path / "pilot.json"
    pilot_path.write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 70,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.80,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "household_delivery_audit_id": "household_delivery_20260517",
                "metrics_export_id": "pilot_metrics_20260517",
                "manual_time_export_id": "manual_time_20260517",
                "refund_abandon_reason_export_id": "refund_abandon_20260517",
                "household_delivery_audit_path": str(export_paths["household_delivery_audit"]),
                "household_delivery_audit_sha256": hashlib.sha256(
                    export_paths["household_delivery_audit"].read_bytes()
                ).hexdigest(),
                "metrics_export_path": str(export_paths["metrics_export"]),
                "metrics_export_sha256": hashlib.sha256(export_paths["metrics_export"].read_bytes()).hexdigest(),
                "manual_time_export_path": str(export_paths["manual_time_export"]),
                "manual_time_export_sha256": hashlib.sha256(
                    export_paths["manual_time_export"].read_bytes()
                ).hexdigest(),
                "refund_abandon_reason_export_path": str(export_paths["refund_abandon_reason_export"]),
                "refund_abandon_reason_export_sha256": hashlib.sha256(
                    export_paths["refund_abandon_reason_export"].read_bytes()
                ).hexdigest(),
                "retrospective_completed": True,
                "retrospective_path": str(retrospective_path),
                "retrospective_sha256": hashlib.sha256(retrospective_path.read_bytes()).hexdigest(),
                "phase2_decision": "go",
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )

    item = validate_pilot(pilot_path)

    assert item.ok is False
    assert "refund_abandon_reason_export_path must classify all incomplete households" in item.detail


def test_pilot_validator_requires_export_artifact_hashes(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_pilot

    export_paths = {
        "household_delivery_audit": tmp_path / "household-delivery-audit.json",
        "metrics_export": tmp_path / "pilot-metrics-export.json",
        "manual_time_export": tmp_path / "manual-time-export.json",
        "refund_abandon_reason_export": tmp_path / "refund-abandon-reasons.json",
    }
    for name, export_path in export_paths.items():
        export_path.write_text(json.dumps({"name": name, "source": "real-pilot-export"}))
    retrospective_path = tmp_path / "phase1-retrospective.md"
    retrospective_path.write_text("# Phase 1 Retrospective\n\nReal pilot outcomes.\n")
    pilot_path = tmp_path / "pilot.json"
    pilot_path.write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 70,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.80,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "household_delivery_audit_id": "household_delivery_20260517",
                "metrics_export_id": "pilot_metrics_20260517",
                "manual_time_export_id": "manual_time_20260517",
                "refund_abandon_reason_export_id": "refund_abandon_20260517",
                "household_delivery_audit_path": str(export_paths["household_delivery_audit"]),
                "household_delivery_audit_sha256": hashlib.sha256(
                    export_paths["household_delivery_audit"].read_bytes()
                ).hexdigest(),
                "metrics_export_path": str(export_paths["metrics_export"]),
                "metrics_export_sha256": "1" * 64,
                "manual_time_export_path": str(export_paths["manual_time_export"]),
                "manual_time_export_sha256": hashlib.sha256(
                    export_paths["manual_time_export"].read_bytes()
                ).hexdigest(),
                "refund_abandon_reason_export_path": str(export_paths["refund_abandon_reason_export"]),
                "refund_abandon_reason_export_sha256": hashlib.sha256(
                    export_paths["refund_abandon_reason_export"].read_bytes()
                ).hexdigest(),
                "retrospective_completed": True,
                "retrospective_path": str(retrospective_path),
                "retrospective_sha256": hashlib.sha256(retrospective_path.read_bytes()).hexdigest(),
                "phase2_decision": "go",
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )

    item = validate_pilot(pilot_path)

    assert item.ok is False
    assert "metrics_export_sha256 must match metrics_export_path content" in item.detail


def test_pilot_validator_requires_retrospective_artifact_hash(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_pilot

    retrospective_path = tmp_path / "phase1-retrospective.md"
    retrospective_path.write_text("# Phase 1 Retrospective\n\nReal pilot outcomes.\n")
    pilot_path = tmp_path / "pilot.json"
    pilot_path.write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 70,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.80,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "household_delivery_audit_id": "household_delivery_20260517",
                "metrics_export_id": "pilot_metrics_20260517",
                "manual_time_export_id": "manual_time_20260517",
                "refund_abandon_reason_export_id": "refund_abandon_20260517",
                "retrospective_completed": True,
                "retrospective_path": str(retrospective_path),
                "retrospective_sha256": "0" * 64,
                "phase2_decision": "go",
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )

    item = validate_pilot(pilot_path)

    assert item.ok is False
    assert "retrospective_sha256 must match retrospective_path content" in item.detail


def test_pilot_validator_rejects_weak_or_incomplete_pilot(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_pilot

    pilot_path = tmp_path / "pilot.json"
    pilot_path.write_text(
        json.dumps(
            {
                "households_total": 99,
                "completed_households": 69,
                "effective_interview_completion_rate": 0.74,
                "family_correction_completion_rate": 0.69,
                "major_fact_error_complaint_rate": 0.10,
                "recommend_rate": 0.79,
                "nps": 50,
                "manual_minutes_per_household": 60,
                "evidence_coverage_rate": 0.79,
                "deposit_rate": 0.29,
                "cac_cents": 50000,
                "household_delivery_audit_id": "",
                "metrics_export_id": "",
                "manual_time_export_id": "",
                "refund_abandon_reason_export_id": "",
                "retrospective_completed": False,
                "phase2_decision": "no_go",
                "segment_counts": {},
            }
        )
    )

    item = validate_pilot(pilot_path)

    assert item.ok is False
    assert "households_total must be >= 100" in item.detail
    assert "nps must be > 50" in item.detail


def test_pilot_validator_requires_final_story_evidence_coverage(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_pilot

    pilot_path = tmp_path / "pilot.json"
    pilot_path.write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 70,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.79,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "household_delivery_audit_id": "household_delivery_20260517",
                "metrics_export_id": "pilot_metrics_20260517",
                "manual_time_export_id": "manual_time_20260517",
                "refund_abandon_reason_export_id": "refund_abandon_20260517",
                "retrospective_completed": True,
                "phase2_decision": "go",
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )

    item = validate_pilot(pilot_path)

    assert item.ok is False
    assert "evidence_coverage_rate must be >= 80%" in item.detail


def test_pilot_validator_requires_retrospective_exports_and_go_decision(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_pilot

    pilot_path = tmp_path / "pilot.json"
    pilot_path.write_text(
        json.dumps(
            {
                "households_total": 100,
                "completed_households": 70,
                "effective_interview_completion_rate": 0.75,
                "family_correction_completion_rate": 0.70,
                "major_fact_error_complaint_rate": 0.09,
                "recommend_rate": 0.80,
                "nps": 51,
                "manual_minutes_per_household": 59,
                "evidence_coverage_rate": 0.80,
                "deposit_rate": 0.30,
                "cac_cents": 30000,
                "segment_counts": {
                    "standard_gift": 40,
                    "birthday": 20,
                    "spring_festival": 15,
                    "light_rescue": 15,
                    "cross_city_overseas": 10,
                },
            }
        )
    )

    item = validate_pilot(pilot_path)

    assert item.ok is False
    assert "household_delivery_audit_id is required" in item.detail
    assert "refund_abandon_reason_export_id is required" in item.detail
    assert "retrospective_completed must be true" in item.detail
    assert "phase2_decision must be go" in item.detail


def test_legal_validator_requires_named_approvals_and_hashes(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_legal

    content_paths = {
        "interview_consent": tmp_path / "interview-consent.md",
        "second_consent": tmp_path / "second-consent.md",
        "privacy_policy": tmp_path / "privacy-policy.md",
        "deletion_copy": tmp_path / "deletion-copy.md",
    }
    for name, path in content_paths.items():
        path.write_text(f"# {name}\n\nApproved copy.\n")
    legal_path = tmp_path / "legal-signoff.json"
    legal_path.write_text(
        json.dumps(
            {
                "approvals": {
                    "interview_consent": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "content_path": str(content_paths["interview_consent"]),
                        "version_hash": hashlib.sha256(content_paths["interview_consent"].read_bytes()).hexdigest(),
                    },
                    "second_consent": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "content_path": str(content_paths["second_consent"]),
                        "version_hash": hashlib.sha256(content_paths["second_consent"].read_bytes()).hexdigest(),
                    },
                    "privacy_policy": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "content_path": str(content_paths["privacy_policy"]),
                        "version_hash": hashlib.sha256(content_paths["privacy_policy"].read_bytes()).hexdigest(),
                    },
                    "deletion_copy": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "content_path": str(content_paths["deletion_copy"]),
                        "version_hash": hashlib.sha256(content_paths["deletion_copy"].read_bytes()).hexdigest(),
                    },
                }
            }
        )
    )

    assert validate_legal(legal_path).ok is True


def test_legal_validator_requires_hashes_to_match_content_artifacts(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_legal

    content_path = tmp_path / "interview-consent.md"
    content_path.write_text("# Interview Consent\n\nApproved copy.\n")
    legal_path = tmp_path / "legal-signoff.json"
    legal_path.write_text(
        json.dumps(
            {
                "approvals": {
                    "interview_consent": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "content_path": str(content_path),
                        "version_hash": "1" * 64,
                    },
                    "second_consent": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "content_path": str(content_path),
                        "version_hash": hashlib.sha256(content_path.read_bytes()).hexdigest(),
                    },
                    "privacy_policy": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "content_path": str(content_path),
                        "version_hash": hashlib.sha256(content_path.read_bytes()).hexdigest(),
                    },
                    "deletion_copy": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "content_path": str(content_path),
                        "version_hash": hashlib.sha256(content_path.read_bytes()).hexdigest(),
                    },
                }
            }
        )
    )

    item = validate_legal(legal_path)

    assert item.ok is False
    assert "interview_consent.version_hash must match content_path content" in item.detail


def test_legal_validator_requires_distinct_content_artifacts(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_legal

    content_path = tmp_path / "approved-copy.md"
    content_path.write_text("# Approved Copy\n\nSingle file reused across all approvals.\n")
    version_hash = hashlib.sha256(content_path.read_bytes()).hexdigest()
    legal_path = tmp_path / "legal-signoff.json"
    legal_path.write_text(
        json.dumps(
            {
                "approvals": {
                    "interview_consent": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "content_path": str(content_path),
                        "version_hash": version_hash,
                    },
                    "second_consent": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "content_path": str(content_path),
                        "version_hash": version_hash,
                    },
                    "privacy_policy": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "content_path": str(content_path),
                        "version_hash": version_hash,
                    },
                    "deletion_copy": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "content_path": str(content_path),
                        "version_hash": version_hash,
                    },
                }
            }
        )
    )

    item = validate_legal(legal_path)

    assert item.ok is False
    assert "legal approvals must reference distinct content_path artifacts" in item.detail


def test_legal_validator_rejects_non_hex_hashes(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_legal

    legal_path = tmp_path / "legal-signoff.json"
    legal_path.write_text(
        json.dumps(
            {
                "approvals": {
                    "interview_consent": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "version_hash": "z" * 64,
                    },
                    "second_consent": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "version_hash": "b" * 64,
                    },
                    "privacy_policy": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "version_hash": "c" * 64,
                    },
                    "deletion_copy": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "version_hash": "d" * 64,
                    },
                }
            }
        )
    )

    item = validate_legal(legal_path)

    assert item.ok is False
    assert "interview_consent.version_hash must be 64 hex characters" in item.detail


def test_legal_validator_requires_timezone_aware_approval_timestamps(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_legal

    legal_path = tmp_path / "legal-signoff.json"
    legal_path.write_text(
        json.dumps(
            {
                "approvals": {
                    "interview_consent": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00",
                        "version_hash": "a" * 64,
                    },
                    "second_consent": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "version_hash": "b" * 64,
                    },
                    "privacy_policy": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "version_hash": "c" * 64,
                    },
                    "deletion_copy": {
                        "approver": "Legal Zhang",
                        "role": "legal",
                        "approved_at": "2026-05-17T10:00:00+08:00",
                        "version_hash": "d" * 64,
                    },
                }
            }
        )
    )

    item = validate_legal(legal_path)

    assert item.ok is False
    assert "interview_consent.approved_at must be ISO 8601 with timezone" in item.detail


def test_wechat_validator_requires_devtools_and_device_matrix(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_wechat_qa

    qa_report_path = tmp_path / "wechat-qa-report.md"
    qa_report_path.write_text("# WeChat QA Report\n\nReal DevTools and device run evidence.\n")
    wechat_path = tmp_path / "wechat-qa.json"
    wechat_path.write_text(
        json.dumps(
            {
                "devtools_build_ok": True,
                "devtools_build_id": "wechat_devtools_20260517_001",
                "qa_run_id": "wechat_qa_20260517_001",
                "qa_report_path": str(qa_report_path),
                "qa_report_sha256": hashlib.sha256(qa_report_path.read_bytes()).hexdigest(),
                "wx_login_ok": True,
                "project_creation_ok": True,
                "photo_upload_ok": True,
                "record_permission_ok": True,
                "upload_ok": True,
                "family_correction_ok": True,
                "story_preview_ok": True,
                "share_settings_ok": True,
                "privacy_export_delete_ok": True,
                "navigation_ok": True,
                "devices": _wechat_devices(),
            }
        )
    )

    assert validate_wechat_qa(wechat_path).ok is True


def test_wechat_validator_requires_qa_report_artifact_hash(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_wechat_qa

    qa_report_path = tmp_path / "wechat-qa-report.md"
    qa_report_path.write_text("# WeChat QA Report\n\nReal DevTools and device run evidence.\n")
    wechat_path = tmp_path / "wechat-qa.json"
    wechat_path.write_text(
        json.dumps(
            {
                "devtools_build_ok": True,
                "devtools_build_id": "wechat_devtools_20260517_001",
                "qa_run_id": "wechat_qa_20260517_001",
                "qa_report_path": str(qa_report_path),
                "qa_report_sha256": "1" * 64,
                "wx_login_ok": True,
                "project_creation_ok": True,
                "photo_upload_ok": True,
                "record_permission_ok": True,
                "upload_ok": True,
                "family_correction_ok": True,
                "story_preview_ok": True,
                "share_settings_ok": True,
                "privacy_export_delete_ok": True,
                "navigation_ok": True,
                "devices": _wechat_devices(),
            }
        )
    )

    item = validate_wechat_qa(wechat_path)

    assert item.ok is False
    assert "qa_report_sha256 must match qa_report_path content" in item.detail


def test_wechat_validator_requires_passing_devices_to_prove_workflow_results(
    tmp_path: Path,
) -> None:
    from scripts.phase1_external_evidence import validate_wechat_qa

    qa_report_path = tmp_path / "wechat-qa-report.md"
    qa_report_path.write_text("# WeChat QA Report\n\nReal DevTools and device run evidence.\n")
    wechat_path = tmp_path / "wechat-qa.json"
    wechat_path.write_text(
        json.dumps(
            {
                "devtools_build_ok": True,
                "devtools_build_id": "wechat_devtools_20260517_001",
                "qa_run_id": "wechat_qa_20260517_001",
                "qa_report_path": str(qa_report_path),
                "qa_report_sha256": hashlib.sha256(qa_report_path.read_bytes()).hexdigest(),
                "wx_login_ok": True,
                "project_creation_ok": True,
                "photo_upload_ok": True,
                "record_permission_ok": True,
                "upload_ok": True,
                "family_correction_ok": True,
                "story_preview_ok": True,
                "share_settings_ok": True,
                "privacy_export_delete_ok": True,
                "navigation_ok": True,
                "devices": [
                    {
                        "name": "iPhone 13",
                        "platform": "ios",
                        "passed": True,
                        "workflow_results": _wechat_workflow_results(),
                    },
                    {
                        "name": "iPhone 14",
                        "platform": "ios",
                        "passed": True,
                        "workflow_results": _wechat_workflow_results(wx_login_ok=False),
                    },
                    {"name": "iPhone 15", "platform": "ios", "passed": True},
                    {
                        "name": "Pixel 7",
                        "platform": "android",
                        "passed": True,
                        "workflow_results": _wechat_workflow_results(),
                    },
                    {
                        "name": "Xiaomi 14",
                        "platform": "android",
                        "passed": True,
                        "workflow_results": _wechat_workflow_results(upload_ok=False),
                    },
                    {"name": "Huawei P60", "platform": "android", "passed": True},
                ],
            }
        )
    )

    item = validate_wechat_qa(wechat_path)

    assert item.ok is False
    assert "passing devices must include all required workflow_results" in item.detail


def test_wechat_validator_requires_full_miniprogram_mvp_workflows(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_wechat_qa

    wechat_path = tmp_path / "wechat-qa.json"
    wechat_path.write_text(
        json.dumps(
            {
                "devtools_build_ok": True,
                "devtools_build_id": "wechat_devtools_20260517_001",
                "qa_run_id": "wechat_qa_20260517_001",
                "record_permission_ok": True,
                "upload_ok": True,
                "navigation_ok": True,
                "devices": _wechat_devices(),
            }
        )
    )

    item = validate_wechat_qa(wechat_path)

    assert item.ok is False
    assert "wx_login_ok must be true" in item.detail
    assert "project_creation_ok must be true" in item.detail
    assert "privacy_export_delete_ok must be true" in item.detail


def test_wechat_validator_requires_traceable_run_and_distinct_devices(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_wechat_qa

    wechat_path = tmp_path / "wechat-qa.json"
    wechat_path.write_text(
        json.dumps(
            {
                "devtools_build_ok": True,
                "wx_login_ok": True,
                "project_creation_ok": True,
                "photo_upload_ok": True,
                "record_permission_ok": True,
                "upload_ok": True,
                "family_correction_ok": True,
                "story_preview_ok": True,
                "share_settings_ok": True,
                "privacy_export_delete_ok": True,
                "navigation_ok": True,
                "devices": [
                    {
                        "name": "iPhone 15",
                        "platform": "ios",
                        "passed": True,
                        "workflow_results": _wechat_workflow_results(),
                    },
                    {
                        "name": "iPhone 15",
                        "platform": "ios",
                        "passed": True,
                        "workflow_results": _wechat_workflow_results(),
                    },
                    {
                        "name": "iPhone 15",
                        "platform": "ios",
                        "passed": True,
                        "workflow_results": _wechat_workflow_results(),
                    },
                    {
                        "name": "Xiaomi 14",
                        "platform": "android",
                        "passed": True,
                        "workflow_results": _wechat_workflow_results(),
                    },
                    {
                        "name": "Xiaomi 14",
                        "platform": "android",
                        "passed": True,
                        "workflow_results": _wechat_workflow_results(),
                    },
                    {
                        "name": "Xiaomi 14",
                        "platform": "android",
                        "passed": True,
                        "workflow_results": _wechat_workflow_results(),
                    },
                ],
            }
        )
    )

    item = validate_wechat_qa(wechat_path)

    assert item.ok is False
    assert "devtools_build_id is required" in item.detail
    assert "qa_run_id is required" in item.detail
    assert "at least 3 distinct passing iOS devices required" in item.detail
    assert "at least 3 distinct passing Android devices required" in item.detail


def test_observability_validator_requires_production_drill_ids(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_observability

    drill_report_path = tmp_path / "production-observability-drill.md"
    drill_report_path.write_text("# Production Observability Drill\n\nSentry, OTEL, SLS, OSS, KMS, backup, restore, and purge proof.\n")
    obs_path = tmp_path / "observability.json"
    obs_path.write_text(
        json.dumps(
            {
                "sentry_event_id": "0123456789abcdef0123456789abcdef",
                "otel_trace_id": "abcdef0123456789abcdef0123456789",
                "sls_project": "changjuan-prod",
                "oss_bucket": "changjuan-prod-private",
                "kms_key_id": "kms_123",
                "oss_kms_encryption_verified": True,
                "oss_backup_drill_id": "oss_backup_20260517",
                "db_backup_restore_drill_id": "restore_20260517",
                "oss_purge_drill_id": "oss_purge_20260517",
                "drill_report_path": str(drill_report_path),
                "drill_report_sha256": hashlib.sha256(drill_report_path.read_bytes()).hexdigest(),
            }
        )
    )

    assert validate_observability(obs_path).ok is True


def test_observability_validator_requires_trace_id_formats(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_observability

    drill_report_path = tmp_path / "production-observability-drill.md"
    drill_report_path.write_text("# Production Observability Drill\n\nSentry, OTEL, SLS, OSS, KMS, backup, restore, and purge proof.\n")
    obs_path = tmp_path / "observability.json"
    obs_path.write_text(
        json.dumps(
            {
                "sentry_event_id": "evt_123",
                "otel_trace_id": "trace_123",
                "sls_project": "changjuan-prod",
                "oss_bucket": "changjuan-prod-private",
                "kms_key_id": "kms_123",
                "oss_kms_encryption_verified": True,
                "oss_backup_drill_id": "oss_backup_20260517",
                "db_backup_restore_drill_id": "restore_20260517",
                "oss_purge_drill_id": "oss_purge_20260517",
                "drill_report_path": str(drill_report_path),
                "drill_report_sha256": hashlib.sha256(drill_report_path.read_bytes()).hexdigest(),
            }
        )
    )

    item = validate_observability(obs_path)

    assert item.ok is False
    assert "sentry_event_id must be a 32-character hex event ID" in item.detail
    assert "otel_trace_id must be a non-zero 32-character hex trace ID" in item.detail


def test_observability_validator_requires_drill_report_artifact_hash(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_observability

    drill_report_path = tmp_path / "production-observability-drill.md"
    drill_report_path.write_text("# Production Observability Drill\n\nSentry, OTEL, SLS, OSS, KMS, backup, restore, and purge proof.\n")
    obs_path = tmp_path / "observability.json"
    obs_path.write_text(
        json.dumps(
            {
                "sentry_event_id": "evt_123",
                "otel_trace_id": "trace_123",
                "sls_project": "changjuan-prod",
                "oss_bucket": "changjuan-prod-private",
                "kms_key_id": "kms_123",
                "oss_kms_encryption_verified": True,
                "oss_backup_drill_id": "oss_backup_20260517",
                "db_backup_restore_drill_id": "restore_20260517",
                "oss_purge_drill_id": "oss_purge_20260517",
                "drill_report_path": str(drill_report_path),
                "drill_report_sha256": "1" * 64,
            }
        )
    )

    item = validate_observability(obs_path)

    assert item.ok is False
    assert "drill_report_sha256 must match drill_report_path content" in item.detail


def test_observability_validator_rejects_local_or_dev_storage_proof(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_observability

    obs_path = tmp_path / "observability.json"
    obs_path.write_text(
        json.dumps(
            {
                "sentry_event_id": "evt_local",
                "otel_trace_id": "trace_local",
                "sls_project": "changjuan-local",
                "oss_bucket": "changjuan-dev",
                "kms_key_id": "kms:local-dev",
                "oss_kms_encryption_verified": True,
                "oss_backup_drill_id": "local_backup_20260517",
                "db_backup_restore_drill_id": "local_restore_20260517",
                "oss_purge_drill_id": "local_purge_20260517",
            }
        )
    )

    item = validate_observability(obs_path)

    assert item.ok is False
    assert "sls_project contains non-production proof value" in item.detail
    assert "oss_bucket contains non-production proof value" in item.detail
    assert "kms_key_id contains non-production proof value" in item.detail


def test_observability_validator_requires_oss_kms_and_backup_proof(tmp_path: Path) -> None:
    from scripts.phase1_external_evidence import validate_observability

    obs_path = tmp_path / "observability.json"
    obs_path.write_text(
        json.dumps(
            {
                "sentry_event_id": "evt_123",
                "otel_trace_id": "trace_123",
                "sls_project": "changjuan-prod",
                "db_backup_restore_drill_id": "restore_20260517",
                "oss_purge_drill_id": "oss_purge_20260517",
            }
        )
    )

    item = validate_observability(obs_path)

    assert item.ok is False
    assert "oss_bucket is required" in item.detail
    assert "kms_key_id is required" in item.detail
    assert "oss_kms_encryption_verified must be true" in item.detail
    assert "oss_backup_drill_id is required" in item.detail
