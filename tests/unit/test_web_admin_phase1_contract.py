from __future__ import annotations

from pathlib import Path


def test_web_admin_dashboard_is_api_backed_for_phase1_ops() -> None:
    page = Path("apps/web-admin/app/page.tsx").read_text()
    actions = _read_optional("apps/web-admin/app/actions.ts")
    client = Path("packages/clients/src/index.ts").read_text()
    package_json = Path("apps/web-admin/package.json").read_text()

    assert "@changjuan/clients" in package_json
    assert 'from "@changjuan/clients"' in page
    assert "Promise.allSettled" in page
    assert "adminProjects()" in page
    assert "pilotMetrics()" in page
    assert "householdOpsExport()" in page
    assert "supportTickets()" in page
    assert "stuckProjects()" in page
    assert "alerts()" in page
    assert "ADMIN_API_TOKEN" in page
    assert "manual_minutes_per_household" in page
    assert "recommend_rate" in page
    assert "ai_cost_cents" in page
    assert "manual_intervention_count" in page
    assert "ops_owner_id" in page
    assert "retryTaskAction" in actions
    assert "retryTask(" in actions
    assert "async adminProjects(" in client
    assert '"/api/v1/admin/projects"' in client
    assert "async stuckProjects(" in client
    assert '"/api/v1/admin/stuck-projects"' in client
    assert "async retryTask(" in client
    assert "/api/v1/admin/tasks/${taskId}/retry" in client


def _read_optional(path: str) -> str:
    file_path = Path(path)
    return file_path.read_text() if file_path.exists() else ""
