# Phase 1 Completion Audit

Date: 2026-05-17

## Evidence That Exists In This Worktree

| Requirement area | Evidence |
| --- | --- |
| Spec freeze | `docs/SPEC.md` points to the Phase 1 v3 spec; ADR-001/002/003 exist. |
| Monorepo | `apps/api`, `apps/worker`, `apps/voice-pipeline`, `apps/web-admin`, `apps/web-h5`, `miniprogram`, `packages`, `infra`, `tests`; `make dev` now starts Docker dependencies plus API, worker, and admin. |
| CI | `.github/workflows/ci.yml` runs Python tests, Ruff, `uv lock --check`, deterministic frontend typecheck with fresh Next route type generation, admin/H5 builds, npm audit, and explicit placeholder-allowed external evidence template schema validation. |
| Runtime config | `.env.example` documents API/runtime settings; `changjuan_api.settings.load_settings` reads app environment, store backend, optional SQLAlchemy schema bootstrap, database URL, Redis URL, JWT, API URL, payment instruction, PII KMS key, CORS origins, WeChat AppID/secret, WeChat code2session URL, deterministic DevTools login-code mapping, pilot whitelist openids, Aliyun OSS bucket/endpoint/KMS key, and Sentry/OTEL/SLS observability settings from environment. Production readiness validation now rejects `STORE_BACKEND` values other than `sqlalchemy`, default/local secrets, localhost database/Redis/CORS values, missing WeChat credentials, missing Sentry/OTEL/SLS config, local/dev OSS/KMS values, non-Aliyun HTTPS OSS endpoints, and implicit default pilot whitelists. |
| Shared clients/types | `@changjuan/shared-types` and `@changjuan/clients` cover Phase 1 auth including `wx_code` login payloads, project CRUD, photo lifecycle, interview sessions/stream URL, audio chunk presign/upload/recovery, corrections, draft/verify/second-consent/publish, story/share/PDF/comment, admin auth, admin ops, support, alerts, and export contracts. |
| FastAPI API | `apps/api/changjuan_api`; contract tests cover WeChat login via `wx_code` mapping, production rejection of client-supplied `wx_openid`, runtime and SQLAlchemy-hydrated pilot whitelist gating, JWT access/refresh token separation, refresh-token-only refresh, logout session revocation, SQLAlchemy-backed user/project/consent/deletion-request/photo/session/audio/transcript/photo-analysis/claim/claim-evidence/chapter/citation/generation-run/story/share/comment/PDF/support/ops/verification/audit/alert/rate-limit/revocation hydration across app recreation when `STORE_BACKEND=sqlalchemy`, persisted admin sessions and last-login state, enforced active admin session lookup and role-limited RBAC for admin routes, project creation, API rate limiting, serializable request validation error envelopes, health observability/runtime dependency readiness plus degraded production readiness for unsafe local/default config, simulated 500 alerts, manual payment with ¥499+ deposit enforcement or explicit waiver, paid-deposit-only pilot deposit-rate calculation, interview consent/photo gating, OSS/KMS-configured photo and audio chunk presign headers, project-scoped photo OSS key enforcement, typed photo lifecycle/list payloads, internal-only photo hypothesis analysis, interview session transition enforcement, authenticated websocket stream audio ingestion, session/sequence-scoped audio OSS key enforcement, REST/websocket audio chunk recovery, partial transcript capture, admin audio/transcript evidence review, publish gating, admin audit logs, correction audit logs/history, project-scoped consent evidence persistence/withdrawal, claim soft delete, project export, deletion status, due deletion purge execution, and audio/transcript/PDF purge coverage. |
| Worker | `apps/worker/changjuan_worker/celery_app.py` includes transcription, extraction, verifier, deletion purge, and PDF tasks; batch transcription now returns Phase 1 `generation_run` metadata through the provider router instead of a bare provider placeholder. |
| Voice runtime | `apps/voice-pipeline/changjuan_voice/main.py` enforces 300-500ms chunk duration and 240 chunks/minute; API audio chunk presign, REST chunk metadata upload, and websocket stream persist sequence state, require audio keys to match the session/sequence claimed by the chunk, expose recovery gaps, and bypass the generic 60/min API limit in favor of the voice-specific 240/min limit. Capture policy tests cover “今天先到这里” session-end requests, refusal-driven topic switching, and non-interrupting 5-10s silence handling. |
| DDL | `infra/migrations/versions/0001_phase1.py`; unit test and generated SQL verification prove required ops tables, payment fields, stuck-owner fields, AI/manual cost tables, generation-run table, normalized claim-evidence/chapter/citation tables, pgvector-backed `claims.embedding vector(16)`, rate-limit-hit table, audio chunk sequence/duration fields, story/share/comment/PDF runtime fields, alert/revocation tables, and soft-delete/purge fields. |
| SQLAlchemy runtime persistence | `apps/api/changjuan_api/sqlalchemy_store.py` defines SQLAlchemy table mappings for the Phase 1 `users`, `admin_users`, `admin_sessions`, `pilot_whitelist`, `projects`, `consent_records`, `deletion_requests`, `photos`, `interview_sessions`, `audio_recordings`, `transcript_segments`, `photo_analyses`, `claims`, `claim_evidence`, `claim_corrections`, `chapters`, `citations`, `story_pages`, `share_links`, `access_logs`, `family_comments`, `pdf_exports`, `verification_issues`, `generation_runs`, `audit_logs`, `alerts`, `revoked_tokens`, `revoked_token_sessions`, `rate_limit_hits`, `support_tickets`, `internal_notes`, `feedback`, `manual_interventions`, and `ai_costs` tables. PostgreSQL metadata compiles `claims.embedding` as `vector(16)` with SQLite `TEXT` fallback for local tests. Tests prove SQLAlchemy-backed pilot whitelist entries, users/projects, admin login sessions, consent records/project consent flags, consent withdrawal, deletion requests, deletion-time consent evidence minimization, photo soft-delete state, photo-count interview gating, interview session status, audio chunk recovery, transcript evidence, normalized claim evidence, claim embeddings, normalized story chapters/citations, photo-analysis list/deletion state, claims/corrections, generated story drafts, share links, family comments, access logs, PDF exports, verification issue resolution state, provider generation-run metadata, audit logs, alerts, token/session revocation, rate-limit state, support ticket patch state, feedback, internal notes, manual interventions, AI costs, and due-deletion physical purge state survive store or app recreation. |
| PII | `PIIEncryptor`, `KMSPIIKeyProvider`, HMAC phone hash, redaction tests, and `wx-login` storage for Phase 1 user profile fields plus encrypted phone storage without plaintext response or record fields. Phone encryption now uses the PII KMS key provider and has a regression test proving the JWT secret cannot decrypt stored phone ciphertext. User runtime records now track `created_at`, `updated_at`, and `deleted_at` in line with the Phase 1 user schema, and profile upsert advances `updated_at`. Audit logs recursively redact local and E.164 `+86` phone/ID PII from reasons and nested metadata without flattening structured metadata. |
| Provider routing | `ProviderRouter` with 3 primary retries, backup failover, actual provider names in generation runs, project context, prompt hash, raw input/output OSS-key metadata, a storage-sink hook that writes raw input/output artifact payloads under the generation-run keys, and a generation-run sink that can persist completed runs to SQLAlchemy. |
| Claim Ledger / verifier | Claim contracts, deterministic claim embeddings, extraction, P0 entity capture, source segment evidence binding, duplicate claim evidence merge, contradiction detection, internal photo hypothesis conversion into pending correction candidates, evidence-gated narrative draft, stricter fact-sentence citation coverage, verifier gates with project-scoped unresolved block handling, publish gate, and admin sensitive review queue/action. |
| Family correction | API endpoints for pending claims, owner-scoped claim detail, owner-scoped correction actions, queryable correction history, P0 completion gate, correction audit logs, delete-as-soft-delete behavior, hidden-claim publish handling, and a draft-generation gate that blocks unprocessed P0 claims. |
| Consent / publish | Consent records validate Phase 1 consent types/methods, require audio evidence for audio consent, persist method/evidence keys, return traceable consent payloads, and audit creation/withdrawal; interview creation requires interview consent; family-sharing consent withdrawal disables story/share access; second-consent request requires a generated story with passed/resolved verifier blocks; publish gate blocks missing consent, unresolved issues, and wrong state; publish decisions are audited. |
| Deletion / export | Project deletion creates a deletion request, hides the project immediately, disables story/share access, marks related audio chunks/transcript segments/photos/claims/claim-evidence/claim-corrections/chapters/citations/comments/PDF exports for purge, minimizes consent evidence, exposes deletion status, records an audit log, and has an executable T+7 purge path that removes due DB resources/OSS keys while marking the deletion request executed in SQLAlchemy-backed storage. Project export returns traceable Phase 1 data including audio/transcript evidence, PDF exports, feedback, and support tickets. |
| Story / PDF | Story page API enforces share-token/password access, records access logs, returns audio citation URLs and family comments, supports disabled pre-publish share links that are enabled by publish, supports share-link revoke/reset, and renders PDF export for both owners and families with valid share access. |
| Admin ops | Admin login with persisted session token hash, `last_login_at`, and `admin.login` audit log, active-session/expiry/enabled-user enforcement on admin APIs, `readonly` dashboard access without mutation permission, `reviewer` review access without payment mutation permission, project list/detail, persisted notes, manual payment marking, issue resolution, sensitive review, task retry, audited simulated 500 alert readback, feedback/NPS/effective-interview/family-correction metrics, project-scoped support tickets with strict admin patching, per-household AI cost/manual work export, and stuck-project owner assignment. |
| Observability | API startup configures structlog JSON logging, optional Sentry SDK capture, OpenTelemetry FastAPI instrumentation for non-health routes, SLS readiness metadata, health readiness reporting, and admin-readable simulated 500 alerts. Production Sentry/OTEL/SLS proof still depends on external `observability.json`. |
| Storage runtime | Photo upload and audio chunk presign now use the configured Aliyun OSS endpoint/bucket and return private KMS server-side encryption headers; `/healthz` exposes configured database, Redis, and object-storage readiness metadata. Live OSS/KMS proof still depends on external `observability.json`. |
| H5 | Next.js H5 surface with openable `/entry` elder interview route, mini program interview launch URL, dedicated non-looping `/entry/fallback` H5 fallback route, project-id binding, evidence-grounded story preview, workflow, and audio citation interaction. |
| Admin UI | Next.js admin dashboard backed by `@changjuan/clients` admin APIs for pilot metrics, project queue, support tickets, stuck projects, alerts, per-household AI/manual work exports, owner coverage, and backend task retry action with explicit missing-token state. |
| Mini program | Native WeChat TypeScript surface for `wx.login` code exchange without user-entered openid, token storage/navigation, project creation, API-backed photo pick/presign/upload/complete/list/delete, API-backed interview consent/session/recovery actions, presigned OSS upload for recorded audio frame bytes, websocket-backed interview audio chunk streaming to `/api/v1/interview-sessions/{session_id}/stream` using project-scoped audio OSS keys, API-backed family correction actions, story/share/audio/PDF/second-consent actions, and API-backed privacy/export/delete/status actions. |
| E2E scenarios | `tests/e2e/test_phase1_e2e_scenarios.py` covers all 12 scenarios named in the spec. |
| Smoke harnesses | `scripts/phase1_infra_smoke.py` and `scripts/phase1_provider_smoke.py` turn infra/provider proof gates into executable checks; provider `--require-ready` now requires both credentials and a valid live `provider-smoke.json`, so env vars alone cannot satisfy the gate. |
| External completion gates | `scripts/phase1_external_evidence.py` validates project management, provider, WeChat QA, legal, pilot, production observability, and OSS/KMS proof files under `docs/evidence/phase1`; normal completion validation rejects copied template placeholders, project ticket export artifact hash mismatches, tracker export ticket-count/owner/dependency/DoD mismatches, duplicate or missing tracker ticket IDs, tracker exports with incomplete ticket statuses, tracker exports that do not cover every final Phase 1 deliverable, tracker tickets without unique matching acceptance-evidence artifacts, provider smoke report artifact hash mismatches, duplicate or missing provider live-task entries, duplicate or missing provider generation runs for Phase 1 tasks, provider runs without live success metadata, duplicate provider request IDs, mock/unapproved provider names, non-UUID provider generation-run IDs, local/mock/dev provider artifact keys, duplicate provider raw input/output OSS keys, provider runs that reuse one OSS object for both raw input and output, approved legal-copy artifact hash mismatches, reused legal-copy artifact paths, pilot export artifact hash mismatches, household-delivery audits whose JSON contents do not match declared household totals or minimum completed-household deliverables, pilot metrics exports whose JSON contents do not match declared pilot KPIs and segment mix, manual-time exports whose JSON contents do not match declared manual-time KPI, refund/abandon exports that do not classify every incomplete household, pilot retrospective artifact hash mismatches, WeChat QA report artifact hash mismatches, passing WeChat device rows that lack per-device required workflow results, invalid Sentry/OTEL trace ID formats, production observability drill report artifact hash mismatches, unsupported project trackers, non-HTTPS/non-GitHub/non-Linear tracker URLs, weak WeChat QA run proof, duplicate device matrices, timezone-less legal approvals, and local/dev production-proof values, while CI uses `--allow-placeholders` only for example schema checks. |

## Fresh Verification

Fresh verification commands run during the latest audit pass:

```text
uv run --extra dev pytest -q
210 passed in 6.16s

uv run --extra dev ruff check .
All checks passed!

uv lock --check
Resolved 119 packages in 3ms

npm run typecheck
web-admin, web-h5, shared-types, clients, and miniprogram typecheck exited 0.

npm run build --workspace @changjuan/web-admin
Compiled successfully in 568ms.

npm run build --workspace @changjuan/web-h5
Compiled successfully in 577ms.

npm audit --audit-level=moderate
found 0 vulnerabilities

uv run --extra dev pytest tests/unit/test_phase1_external_evidence.py -q
46 passed in 0.06s

uv run --extra dev python -m scripts.phase1_external_evidence --dir docs/evidence/phase1
Exited 2 because required external proof files are absent:
docs/evidence/phase1/project-management.json,
docs/evidence/phase1/provider-smoke.json,
docs/evidence/phase1/wechat-qa.json,
docs/evidence/phase1/legal-signoff.json,
docs/evidence/phase1/pilot.json,
docs/evidence/phase1/observability.json.

External evidence template validation
Copying the six `.example.json` files to a temporary evidence directory and
running `uv run --extra dev python -m scripts.phase1_external_evidence --dir <tmp> --allow-placeholders`
passed, proving the templates match the validator schema without allowing copied
template placeholders to satisfy real completion evidence, including tracker
ticket completed-status proof, per-ticket acceptance-evidence artifact
path/hash proof, ticket coverage for every final Phase 1 deliverable, and
provider live-success metadata plus per-device WeChat workflow-result proof.
Running the same
copied templates without `--allow-placeholders` exited 2 and rejected placeholder
values plus missing/mismatched external artifacts, including the provider smoke
report artifact path/hash, WeChat QA report artifact path/hash, and production
observability drill report artifact path/hash. Copied templates also now fail on
pilot household-delivery audit, metrics export, manual-time export, and
refund/abandon reason export artifact path/hash requirements, plus invalid
Sentry/OTEL placeholder ID formats in production validation mode.

uv run --extra dev python -m scripts.phase1_provider_smoke --require-ready
Exited 2 because required live provider credentials are absent; if credentials are
present, this gate also validates `docs/evidence/phase1/provider-smoke.json`
for live generation-run metadata before returning success:
ALIYUN_ASR_APP_KEY, ALIYUN_ASR_SECRET, DEEPSEEK_API_KEY, DOUBAO_API_KEY,
MINIMAX_API_KEY, QWEN_API_KEY, TONGYI_TINGWU_API_KEY, VOLCENGINE_ASR_APP_ID,
VOLCENGINE_ASR_SECRET, VOLCENGINE_TTS_APP_ID, VOLCENGINE_TTS_SECRET,
XUNFEI_ASR_APP_ID, XUNFEI_ASR_SECRET.
```

Previously recorded supporting checks retained in this worktree:

```text
make -n dev
Dry-run shows Docker dependencies plus API, Celery worker, and web-admin dev server.

PYTHONPATH=packages:apps/api:apps/worker:apps/voice-pipeline uv run --extra dev python -c "import changjuan_api.main; import changjuan_worker.celery_app; import changjuan_voice.main"
Service imports succeeded.

uv run --extra dev alembic upgrade head --sql > /tmp/changjuan_phase1_alembic.sql
rg -n "CREATE EXTENSION IF NOT EXISTS vector|embedding vector\(16\)" /tmp/changjuan_phase1_alembic.sql
wc -l /tmp/changjuan_phase1_alembic.sql
Generated the Phase 1 migration SQL successfully: 509 lines, including
`CREATE EXTENSION IF NOT EXISTS vector` and `embedding vector(16)`.

uv run --extra dev python -m scripts.phase1_infra_smoke --start --timeout 90
Passed: Docker Compose started Postgres/Redis/MinIO, MinIO health returned 200,
Alembic applied online, Postgres SELECT 1 returned (1,), Redis PING returned PONG.

uv run --extra dev python -m scripts.phase1_provider_smoke
Ran successfully and reported missing provider credentials; no live provider calls were claimed.

Local backup/restore drill
pg_dump produced /tmp/changjuan_phase1_backup.sql (38,821 bytes), restored into
temporary database changjuan_restore_check, verified 28 public tables, then
dropped the temporary database.
```

Rendered checks:

- Browser plugin verified current H5 entry rendering at `http://localhost:3001/entry?project_id=proj_phase1_001`: title `长卷`, meaningful elder-entry content, visible project binding, mini program launch/fallback entry content, no framework overlay, zero console warnings/errors, and screenshot evidence.
- Browser plugin verified current H5 fallback navigation from `http://localhost:3001/entry?project_id=proj_phase1_001` to `http://localhost:3001/entry/fallback?project_id=proj_phase1_001`: title `长卷`, meaningful fallback content, preserved visible project binding, return link to the WeChat entry, zero console warnings/errors, and screenshot evidence.
- Browser plugin verified current admin rendering at `http://localhost:3000/`: title `长卷 Admin`, meaningful dashboard content, explicit `ADMIN_API_TOKEN` empty state, retry form missing-token result, no framework overlay, and zero console warnings/errors. Browser screenshot capture failed twice with `Page.captureScreenshot` timeout, so no screenshot evidence is claimed for this run.
- Playwright fallback verified H5 audio citation interaction changes to `播放中 0:14:23`.
- Playwright fallback reported zero console errors for both checked pages after favicon routes were added.

## Not Yet Proved Complete

These items are required by the Phase 1 spec but cannot be truthfully marked complete from this local worktree alone:

| Requirement | Current status | What would prove completion |
| --- | --- | --- |
| Phase 1 tracker/spec confirmation | CI exists locally and `docs/SPEC.md` points to `phase1.md`; the external validator is missing `docs/evidence/phase1/project-management.json` and now requires a matching SHA-256 hash for the tracker ticket export artifact plus semantic validation that the export contains unique ticket IDs, the declared ticket count, owner/dependency/DoD coverage, completed ticket statuses, `deliverable_key` coverage for every final Phase 1 deliverable, and per-ticket acceptance-evidence artifact path/hash proof. | `project-management.json` proving Phase 1 was initialized in GitHub Project or Linear through an HTTPS GitHub/Linear URL, the spec was confirmed as authoritative, and every unique exported ticket has an owner, dependency status, DoD, completed status, Phase 1 deliverable mapping, and unique matching acceptance-evidence artifact backed by a tracker export artifact path, SHA-256, and matching exported ticket contents. |
| Real Volcengine/Xunfei/Aliyun/Qwen provider activation | Provider readiness smoke exists and ran; the external validator is missing `docs/evidence/phase1/provider-smoke.json` and now rejects duplicate/missing live-task entries, duplicate/missing generation runs per Phase 1 task, provider runs without live success metadata, duplicate provider request IDs, mock/unapproved provider names, non-UUID generation-run IDs, local/mock/dev artifact keys, duplicate raw input/output OSS keys, runs that reuse one OSS object for both raw input and output, and missing/mismatched provider smoke report artifacts. Provider envs are still absent: `ALIYUN_ASR_APP_KEY`, `ALIYUN_ASR_SECRET`, `DEEPSEEK_API_KEY`, `DOUBAO_API_KEY`, `MINIMAX_API_KEY`, `QWEN_API_KEY`, `TONGYI_TINGWU_API_KEY`, `VOLCENGINE_ASR_APP_ID`, `VOLCENGINE_ASR_SECRET`, `VOLCENGINE_TTS_APP_ID`, `VOLCENGINE_TTS_SECRET`, `XUNFEI_ASR_APP_ID`, `XUNFEI_ASR_SECRET`. | `provider-smoke.json` produced from successful live provider smoke tests with real credentials and exactly one live-task entry plus exactly one generation run record for every Phase 1 provider task, including an approved live provider name, UUID run ID, prompt version/hash, unique raw input/output OSS keys, separate input/output OSS objects per run, succeeded status, timezone-aware completion timestamp, positive latency, unique provider request ID, and provider smoke report artifact path/hash. |
| Real WeChat mini program MVP behavior | Native mini program source exists, typechecks, and now covers `wx.login` code exchange, token storage/navigation, project creation, photo upload lifecycle, recording/session/audio recovery, family correction, story/share/PDF/second consent, and privacy/export/delete. The API supports configured WeChat `jscode2session` plus deterministic DevTools code mapping, but the external validator is still missing `docs/evidence/phase1/wechat-qa.json` and now requires a matching SHA-256 hash for the retained QA report artifact plus per-device required workflow results for every counted passing device. | `wechat-qa.json` from WeChat DevTools build evidence with a build ID, a QA run ID, a QA report artifact path and SHA-256, and at least 3 distinct passing iOS and 3 distinct passing Android device checks whose `workflow_results` prove login, project creation, photo upload, recording permission, upload, family correction, story preview, share settings, privacy/export/delete, and navigation passed on each counted device. |
| Legal consent/privacy copy finalization | Pages and flow hooks exist; the external validator is missing `docs/evidence/phase1/legal-signoff.json` and now requires distinct approved copy artifact paths with matching SHA-256 hashes. | `legal-signoff.json` with named approvals for interview consent, second consent, privacy policy, and deletion copy, each bound to its own approved content artifact path, matching 64-character SHA-256 hash, and timezone-aware ISO 8601 approval timestamp. |
| 100-household pilot | Retrospective template and metrics endpoint exist; the metrics endpoint now excludes waived projects from the paid deposit-rate numerator; the external validator is missing `docs/evidence/phase1/pilot.json` and now requires matching SHA-256 hashes for the real household-delivery audit, metrics export, manual-time export, refund/abandon reason export, and retrospective artifacts, plus household-delivery audit JSON contents that match declared household/completed counts and prove the minimum completed-household delivery bundle, metrics-export JSON contents that match the declared KPI and segment values, manual-time export JSON contents that match the declared manual minutes per household, and refund/abandon reason categories that classify every incomplete household. | `pilot.json` from real household data proving the Phase 1 thresholds: 100 households, ≥70% completion, ≥75% effective interview completion, ≥70% family correction completion, <10% major fact complaints, ≥80% recommend rate, NPS >50, <60 manual minutes per household, ≥80% final-story evidence coverage, ≥30% deposit rate, CAC ¥200-400, required segment mix, per-household delivery audit artifact path/hash/content match/minimum-delivery proof, metrics export artifact path/hash/content match, manual-time export artifact path/hash/content match, refund/abandon reason export artifact path/hash/classification coverage, completed retrospective artifact path/hash, and Phase 2 Go decision. |
| Production security/storage/backup/restore drills | Local API observability wiring now reports Sentry/OTEL/SLS readiness when configured, simulated 500 alerts are admin-readable, and local Postgres backup/restore drill passed on 2026-05-17; the external validator is missing `docs/evidence/phase1/observability.json` and now rejects local/dev proof values, invalid Sentry/OTEL trace ID formats, and requires a matching SHA-256 hash for the retained production drill report artifact. | `observability.json` with production 32-character hex Sentry event ID, non-zero 32-character hex OTEL trace ID, Aliyun SLS project, OSS bucket, KMS key ID, KMS encryption verification, OSS backup drill ID, DB backup/restore drill ID, OSS purge drill ID, and drill report artifact path/hash from production-class infrastructure. |

The implementation is materially ahead of a skeleton, but the active goal should remain open until these proof items exist.
