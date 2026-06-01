# Phase 1 Smoke Checks

These commands turn the remaining completion proof items into repeatable evidence.

## Provider Readiness

```bash
uv run --extra dev python -m scripts.phase1_provider_smoke
uv run --extra dev python -m scripts.phase1_provider_smoke --require-ready
```

The first command reports missing credentials without pretending provider calls were made. The second command exits non-zero until every Phase 1 primary and backup provider credential is present.

Required credentials cover Volcengine ASR/TTS, Aliyun Paraformer, Xunfei ASR, Tongyi Tingwu, Minimax TTS, DeepSeek, Doubao, and Qwen3-VL.

## Local Infra

```bash
uv run --extra dev python -m scripts.phase1_infra_smoke --start
```

This starts `postgres`, `redis`, and `minio` from `infra/docker/docker-compose.yml`, waits for service health, applies `alembic upgrade head` online, then runs `SELECT 1` and Redis `PING`.

## Still Human-Verified

The following completion items still require external evidence:

- WeChat DevTools/device QA for the mini program.
- Legal sign-off for consent/privacy copy.
- Real 100-household pilot data and retrospective.
- Production Sentry/OTEL/SLS, backup, restore, and purge drill logs.
