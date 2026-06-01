from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
if str(PACKAGES) not in sys.path:
    sys.path.insert(0, str(PACKAGES))


DEFAULT_DATABASE_URL = "postgresql+psycopg://changjuan:changjuan@localhost:5432/changjuan"
DEFAULT_REDIS_HOST = "localhost"
DEFAULT_REDIS_PORT = 6379
DEFAULT_MINIO_HEALTH_URL = "http://localhost:9000/minio/health/live"


@dataclass(frozen=True)
class SmokePlan:
    compose_file: str = "infra/docker/docker-compose.yml"
    services: tuple[str, ...] = ("postgres", "redis", "minio")
    alembic_command: tuple[str, ...] = ("uv", "run", "--extra", "dev", "alembic", "upgrade", "head")
    database_url: str = DEFAULT_DATABASE_URL
    redis_host: str = DEFAULT_REDIS_HOST
    redis_port: int = DEFAULT_REDIS_PORT
    minio_health_url: str = DEFAULT_MINIO_HEALTH_URL


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class SmokeReport:
    checks: list[SmokeCheck]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def blockers(self) -> list[str]:
        return [f"{check.name}: {check.detail}" for check in self.checks if not check.ok]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": [check.__dict__ for check in self.checks],
            "blockers": self.blockers,
        }


def build_smoke_plan(env: dict[str, str] | None = None) -> SmokePlan:
    env = env or os.environ
    return SmokePlan(
        database_url=env.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        redis_host=env.get("REDIS_HOST", DEFAULT_REDIS_HOST),
        redis_port=int(env.get("REDIS_PORT", str(DEFAULT_REDIS_PORT))),
        minio_health_url=env.get("MINIO_HEALTH_URL", DEFAULT_MINIO_HEALTH_URL),
    )


def run_smoke(start_services: bool = False, timeout_seconds: int = 90) -> SmokeReport:
    plan = build_smoke_plan()
    checks: list[SmokeCheck] = []

    docker = shutil.which("docker")
    if not docker:
        return SmokeReport([SmokeCheck("docker", False, "docker not found")])
    checks.append(SmokeCheck("docker", True, docker))

    if start_services:
        command = [docker, "compose", "-f", plan.compose_file, "up", "-d", *plan.services]
        checks.append(_run_command("docker compose up", command, timeout_seconds=timeout_seconds))
        if not checks[-1].ok:
            return SmokeReport(checks)

    checks.append(_wait_for_tcp("postgres tcp", "localhost", 5432, timeout_seconds))
    checks.append(_wait_for_tcp("redis tcp", plan.redis_host, plan.redis_port, timeout_seconds))
    checks.append(_wait_for_http("minio health", plan.minio_health_url, timeout_seconds))

    if all(check.ok for check in checks[-3:]):
        env = os.environ.copy()
        env["DATABASE_URL"] = plan.database_url
        checks.append(
            _run_command(
                "alembic upgrade head",
                list(plan.alembic_command),
                env=env,
                timeout_seconds=timeout_seconds,
            )
        )
        checks.append(_postgres_select_one(plan.database_url))
        checks.append(_redis_ping(plan.redis_host, plan.redis_port))

    return SmokeReport(checks)


def _run_command(
    name: str,
    command: Sequence[str],
    env: dict[str, str] | None = None,
    timeout_seconds: int = 90,
) -> SmokeCheck:
    try:
        completed = subprocess.run(
            command,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return SmokeCheck(name, False, f"timed out after {timeout_seconds}s")
    detail = completed.stdout.strip()[-1000:] or f"exit {completed.returncode}"
    return SmokeCheck(name, completed.returncode == 0, detail)


def _wait_for_tcp(name: str, host: str, port: int, timeout_seconds: int) -> SmokeCheck:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                return SmokeCheck(name, True, f"{host}:{port} accepting connections")
        except OSError as exc:
            last_error = str(exc)
            time.sleep(1)
    return SmokeCheck(name, False, last_error or "timed out")


def _wait_for_http(name: str, url: str, timeout_seconds: int) -> SmokeCheck:
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 300:
                    return SmokeCheck(name, True, f"{url} returned {response.status}")
                last_error = f"{url} returned {response.status}"
        except OSError as exc:
            last_error = str(exc)
            time.sleep(1)
    return SmokeCheck(name, False, last_error or "timed out")


def _postgres_select_one(database_url: str) -> SmokeCheck:
    try:
        import psycopg

        conninfo = database_url.replace("postgresql+psycopg://", "postgresql://")
        with psycopg.connect(conninfo) as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            value = cursor.fetchone()
        return SmokeCheck("postgres select 1", value == (1,), f"result={value}")
    except Exception as exc:  # pragma: no cover - smoke diagnostic detail
        return SmokeCheck("postgres select 1", False, str(exc))


def _redis_ping(host: str, port: int) -> SmokeCheck:
    try:
        import redis

        client = redis.Redis(host=host, port=port, socket_timeout=2)
        return SmokeCheck("redis ping", bool(client.ping()), "PONG")
    except Exception as exc:  # pragma: no cover - smoke diagnostic detail
        return SmokeCheck("redis ping", False, str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 1 local infra smoke checks.")
    parser.add_argument("--start", action="store_true", help="Start Docker Compose services first.")
    parser.add_argument("--timeout", type=int, default=90, help="TCP/HTTP readiness timeout in seconds.")
    args = parser.parse_args()

    report = run_smoke(start_services=args.start, timeout_seconds=args.timeout)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
