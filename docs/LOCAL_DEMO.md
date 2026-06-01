# Local Demo

This script is intended for a short recruiter or interviewer walkthrough.

## 1. Start Dependencies

```bash
cp .env.example .env
uv sync --extra dev
npm ci
docker compose -f infra/docker/docker-compose.yml up -d postgres redis minio
make migrate
```

## 2. Start the Apps

Terminal A:

```bash
make api
```

Terminal B:

```bash
make admin
```

Terminal C:

```bash
make h5
```

## 3. Open Demo Surfaces

- API health: `http://localhost:8000/healthz`
- Admin dashboard: `http://localhost:3000`
- H5 story preview: `http://localhost:3001`
- Elder entry: `http://localhost:3001/entry?project_id=proj_phase1_001`
- H5 fallback entry:
  `http://localhost:3001/entry/fallback?project_id=proj_phase1_001`

## 4. Walkthrough Talking Points

1. Start with the product problem: families need a way to preserve elder stories
   without publishing unverified AI hallucinations.
2. Show the admin dashboard and explain the operational gates: completion metrics,
   stuck owners, support, alerts, manual work, and retry.
3. Show H5 story/audio citation behavior and explain the evidence ledger.
4. Open `docs/ARCHITECTURE.md` and explain the API, worker, provider router,
   mini program, and compliance boundaries.
5. End with verification: CI, tests, migrations, production readiness checks, and
   external evidence gates.

## 5. Verification Commands

```bash
make test
make lint
npm run typecheck
npm run build
```

Expected high-level result: Python tests and lint pass, TypeScript typecheck
passes, and both Next.js apps build successfully.
