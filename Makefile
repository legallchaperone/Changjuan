PYTHON := uv run --extra dev
PYTHONPATH := packages:apps/api:apps/worker:apps/voice-pipeline
export PYTHONPATH

.PHONY: dev api worker voice admin h5 test lint migrate smoke

dev:
	docker compose -f infra/docker/docker-compose.yml up -d postgres redis minio
	@echo "Starting API, worker, and admin. Press Ctrl-C to stop all dev services."
	@$(PYTHON) uvicorn changjuan_api.main:app --reload --host 0.0.0.0 --port 8000 & \
	api_pid=$$!; \
	$(PYTHON) celery -A changjuan_worker.celery_app worker --loglevel=INFO & \
	worker_pid=$$!; \
	npm run dev --workspace @changjuan/web-admin & \
	admin_pid=$$!; \
	trap 'kill $$api_pid $$worker_pid $$admin_pid 2>/dev/null || true' INT TERM EXIT; \
	wait $$api_pid $$worker_pid $$admin_pid

api:
	$(PYTHON) uvicorn changjuan_api.main:app --reload --host 0.0.0.0 --port 8000

worker:
	$(PYTHON) celery -A changjuan_worker.celery_app worker --loglevel=INFO

voice:
	$(PYTHON) uvicorn changjuan_voice.main:app --reload --host 0.0.0.0 --port 8001

admin:
	npm run dev --workspace @changjuan/web-admin

h5:
	npm run dev --workspace @changjuan/web-h5

test:
	$(PYTHON) pytest

lint:
	$(PYTHON) ruff check .

migrate:
	$(PYTHON) alembic upgrade head

smoke:
	$(PYTHON) pytest tests/unit tests/integration -q
