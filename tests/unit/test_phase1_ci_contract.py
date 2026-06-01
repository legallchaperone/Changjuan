from __future__ import annotations

import json
from pathlib import Path


def test_ci_runs_phase1_python_and_frontend_gates() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text()

    assert "uv run --extra dev pytest -q" in workflow
    assert "uv run --extra dev ruff check ." in workflow
    assert "uv lock --check" in workflow
    assert "npm run typecheck" in workflow
    assert "npm run build --workspace @changjuan/web-admin" in workflow
    assert "npm run build --workspace @changjuan/web-h5" in workflow
    assert "npm audit --audit-level=moderate" in workflow


def test_ci_validates_phase1_evidence_template_schema() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text()

    assert "scripts.phase1_external_evidence" in workflow
    assert "--allow-placeholders" in workflow
    assert "project-management.example.json" in workflow
    assert "provider-smoke.example.json" in workflow
    assert "observability.example.json" in workflow


def test_next_typecheck_generates_route_types_without_incremental_cache() -> None:
    helper = Path("scripts/next-typecheck.mjs").read_text()
    assert 'rmSync(join(process.cwd(), ".next", "types")' in helper
    assert '["typegen"]' in helper
    assert '["--noEmit", "--incremental", "false"]' in helper

    for package_path in (
        Path("apps/web-admin/package.json"),
        Path("apps/web-h5/package.json"),
    ):
        package = json.loads(package_path.read_text())
        typecheck = package["scripts"]["typecheck"]

        assert typecheck == "node ../../scripts/next-typecheck.mjs"
