from __future__ import annotations

from pathlib import Path


def test_make_dev_starts_phase1_local_services() -> None:
    makefile = Path("Makefile").read_text()

    assert "PYTHONPATH := packages:apps/api:apps/worker:apps/voice-pipeline" in makefile
    assert "docker compose -f infra/docker/docker-compose.yml up -d postgres redis minio" in makefile
    assert "uvicorn changjuan_api.main:app" in makefile
    assert "celery -A changjuan_worker.celery_app worker" in makefile
    assert "npm run dev --workspace @changjuan/web-admin" in makefile
