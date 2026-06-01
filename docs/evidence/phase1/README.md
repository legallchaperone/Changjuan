# Phase 1 External Evidence

This directory is intentionally evidence-first. Phase 1 is not complete until the JSON files below are filled from real external proof and pass:

```bash
uv run --extra dev python -m scripts.phase1_external_evidence --dir docs/evidence/phase1
```

Required files:

- `project-management.json`
- `provider-smoke.json`
- `wechat-qa.json`
- `legal-signoff.json`
- `pilot.json`
- `observability.json`

Validation is intentionally strict:

- Project management proof must use `github_project` or `linear`, an HTTPS GitHub or Linear URL, and a tracker ticket export artifact whose SHA-256 hash matches the file content. The export must contain a `tickets` array with unique non-empty ticket IDs, length, owner count, dependency-status count, and DoD count that match the declared evidence totals. Every ticket row must have `completion_status` set to `done`, `completed`, or `closed`; use `deliverable_key` values that cover every item in the Phase 1 final delivery checklist; and reference a unique acceptance-evidence artifact path with a matching SHA-256 hash.
- Provider proof must include exactly one live-task entry and exactly one generation run for every Phase 1 provider task, approved live provider names, UUID generation-run IDs, prompt hashes, unique raw input/output OSS keys without local/mock/dev proof values, separate input/output objects per run, live success metadata (`status=succeeded`, timezone-aware `completed_at`, positive `latency_ms`, and unique provider request IDs), and a provider smoke report artifact whose SHA-256 hash matches the file content.
- Pilot proof must include real household-delivery audit, metrics export, manual-time export, refund/abandon reason export, and retrospective artifact paths with SHA-256 hashes that match the file contents. The household-delivery audit must be JSON with unique household IDs, declared household/completed counts, and minimum completed-household delivery proof: elder, >=15 interview minutes, Claim Ledger, family correction, story page, PDF, and NPS/recommendation follow-up. The metrics export must be JSON whose household counts, KPI values, CAC, and segment mix match the declared `pilot.json` metrics. The manual-time export must be JSON whose `manual_minutes_per_household` matches the declared metric. The refund/abandon export must include non-empty `reason_categories` whose counts classify every incomplete household.
- WeChat QA proof must include a DevTools build ID, a QA run ID, a QA report artifact whose SHA-256 hash matches the file content, and at least 3 distinct passing iOS devices plus 3 distinct passing Android devices. Every passing device row must include `workflow_results` proving all required Mini Program workflows passed on that device.
- Legal approvals must include named approvers, timezone-aware ISO 8601 approval timestamps, and distinct approved copy artifact paths whose SHA-256 hashes match the file content.
- Production observability/storage proof must include a 32-character hex Sentry event ID, a non-zero 32-character hex OTEL trace ID, Aliyun SLS, OSS, KMS, backup, restore, and purge drill IDs plus a drill report artifact whose SHA-256 hash matches the file content.

Do not fill these with estimates or sample data. The validator is meant to block false completion claims.
