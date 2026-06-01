# Phase 1 Delivery Map

This repository implements the Phase 1 product surface from `docs/SPEC.md`.

| Spec area | Implementation |
| --- | --- |
| FastAPI backend | `apps/api/changjuan_api` |
| Celery worker | `apps/worker/changjuan_worker` |
| Voice pipeline | `apps/voice-pipeline/changjuan_voice` |
| Admin dashboard | `apps/web-admin` |
| H5 entry/story surface | `apps/web-h5` |
| Mini program | `miniprogram` |
| Provider router | `packages/changjuan_core/providers` |
| Claim, narrative, verifier | `packages/changjuan_core/ai` |
| PII, audit, deletion | `packages/changjuan_core/compliance` |
| State machine and publish gate | `packages/changjuan_core/story` |
| Alembic DDL | `infra/migrations/versions/0001_phase1.py` |
