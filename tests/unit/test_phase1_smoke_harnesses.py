from __future__ import annotations

import os
import subprocess
import sys


def test_provider_smoke_reports_missing_required_credentials(monkeypatch) -> None:
    from scripts.phase1_provider_smoke import REQUIRED_ENV, evaluate_provider_readiness

    for env_name in REQUIRED_ENV:
        monkeypatch.delenv(env_name, raising=False)

    readiness = evaluate_provider_readiness(os.environ)

    assert readiness.ready is False
    assert "VOLCENGINE_ASR_APP_ID" in readiness.missing_env
    assert "XUNFEI_ASR_SECRET" in readiness.missing_env
    assert "QWEN_API_KEY" in readiness.missing_env
    assert readiness.live_tasks == []


def test_provider_smoke_maps_every_phase1_task_type_to_provider_requirements() -> None:
    from changjuan_core.providers.router import TaskType

    from scripts.phase1_provider_smoke import TASK_PROVIDER_REQUIREMENTS

    assert set(TASK_PROVIDER_REQUIREMENTS) == set(TaskType)
    for _task_type, provider_chain in TASK_PROVIDER_REQUIREMENTS.items():
        assert provider_chain.primary.name
        assert provider_chain.backup.name
        assert provider_chain.primary.required_env
        assert provider_chain.backup.required_env


def test_provider_smoke_module_runs_from_shell_without_pythonpath() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.phase1_provider_smoke"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert '"ready": false' in completed.stdout
    assert completed.stderr == ""


def test_provider_smoke_require_ready_rejects_env_only_without_live_evidence(tmp_path) -> None:
    from scripts.phase1_provider_smoke import REQUIRED_ENV

    env = os.environ.copy()
    for env_name in REQUIRED_ENV:
        env[env_name] = "dummy-provider-secret"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.phase1_provider_smoke",
            "--require-ready",
            "--evidence",
            str(tmp_path / "provider-smoke.json"),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert '"ready": true' in completed.stdout
    assert '"live_evidence"' in completed.stdout
    assert "provider-smoke.json" in completed.stdout


def test_infra_smoke_builds_expected_docker_and_migration_commands() -> None:
    from scripts.phase1_infra_smoke import build_smoke_plan

    plan = build_smoke_plan()

    assert plan.compose_file == "infra/docker/docker-compose.yml"
    assert plan.services == ("postgres", "redis", "minio")
    assert plan.alembic_command == ("uv", "run", "--extra", "dev", "alembic", "upgrade", "head")
    assert plan.database_url.startswith("postgresql+psycopg://")


def test_infra_smoke_result_marks_missing_dependency_as_blocker() -> None:
    from scripts.phase1_infra_smoke import SmokeCheck, SmokeReport

    report = SmokeReport(checks=[SmokeCheck(name="docker", ok=False, detail="docker not found")])

    assert report.ok is False
    assert report.blockers == ["docker: docker not found"]


def test_infra_smoke_command_timeout_becomes_failed_check(monkeypatch) -> None:
    from scripts.phase1_infra_smoke import _run_command

    def fake_run(*_, **__):
        raise subprocess.TimeoutExpired(cmd=["docker", "compose"], timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    check = _run_command("docker compose up", ["docker", "compose"], timeout_seconds=1)

    assert check.ok is False
    assert "timed out after 1s" in check.detail
