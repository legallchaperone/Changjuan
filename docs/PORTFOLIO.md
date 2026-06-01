# Portfolio Notes

## One-Sentence Summary

Built Changjuan, an evidence-grounded family story platform that turns elder
interviews into private, consent-gated stories with traceable claims, family
corrections, admin operations, and AI pipeline guardrails.

## Resume Bullets

- Built a full-stack monorepo for an AI-assisted family storytelling product:
  FastAPI, Celery, SQLAlchemy, Alembic, Redis, PostgreSQL, Next.js, React,
  TypeScript, WeChat mini program pages, and shared typed clients.
- Designed an evidence ledger for AI-generated stories, including claim extraction,
  source binding, family correction, verifier gates, second consent, private share
  links, PDF export, and publish-state enforcement.
- Implemented operational and compliance workflows: admin queue, support tickets,
  stuck-project owner assignment, alerts, rate limits, audit logs, PII encryption,
  redaction, data export, deletion requests, and T+7 purge execution.
- Added provider-routing boundaries for ASR, extraction, verification, and narrative
  generation with retry/failover hooks, prompt versioning, generation-run metadata,
  and raw input/output artifact tracing.
- Hardened project quality with pytest, Ruff, TypeScript workspace checks, Next.js
  production builds, lockfile validation, evidence-template validators, npm audit,
  and GitHub Actions CI.

## Interview Explanation

The core technical decision was to model family stories as evidence-bound workflows
instead of treating LLM output as the source of truth. The system stores claims,
claim evidence, corrections, citations, consent records, verification issues, and
generation runs as separate records. This makes it possible to block publication
when unresolved high-priority facts exist, hide deleted claims from the final story,
and explain where each fact came from.

The product also needed operational tooling because a pilot workflow is not only a
consumer UI. The admin dashboard exposes project state, support issues, stuck-owner
assignment, manual work, AI cost, alerts, and retry actions. That makes the project
look closer to a real launch system than a demo app.

## Best Files to Show

- `README.md` for the project overview.
- `docs/ARCHITECTURE.md` for system design.
- `apps/api/changjuan_api/main.py` for API boundaries and workflow enforcement.
- `apps/api/changjuan_api/sqlalchemy_store.py` for persistence coverage.
- `packages/changjuan_core/ai` for AI contracts and verifier behavior.
- `packages/changjuan_core/compliance` for PII, audit, redaction, and deletion.
- `apps/web-admin/app/page.tsx` for operational dashboard surface.
- `tests/e2e/test_phase1_e2e_scenarios.py` for end-to-end product scenarios.
- `.github/workflows/ci.yml` for CI quality gates.

## Honest Status Framing

Use this wording when asked about production readiness:

> The codebase implements the Phase 1 workflows and local verification gates. The
> remaining completion gates are external proof artifacts: live provider smoke
> results, WeChat device QA, legal signoff, pilot metrics, and production-class
> observability/storage drills.

That framing is stronger than overclaiming because it shows that the project has
clear readiness criteria and does not confuse local tests with production proof.
