from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
if str(PACKAGES) not in sys.path:
    sys.path.insert(0, str(PACKAGES))

from changjuan_core.providers.router import TaskType

from scripts.phase1_external_evidence import validate_provider

DEFAULT_PROVIDER_EVIDENCE = ROOT / "docs" / "evidence" / "phase1" / "provider-smoke.json"


@dataclass(frozen=True)
class ProviderRequirement:
    name: str
    required_env: tuple[str, ...]


@dataclass(frozen=True)
class ProviderChain:
    primary: ProviderRequirement
    backup: ProviderRequirement


@dataclass(frozen=True)
class ProviderReadiness:
    ready: bool
    missing_env: list[str]
    live_tasks: list[str]
    task_requirements: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "missing_env": self.missing_env,
            "live_tasks": self.live_tasks,
            "task_requirements": self.task_requirements,
        }


VOLCENGINE_ASR = ProviderRequirement(
    "volcengine_streaming_asr", ("VOLCENGINE_ASR_APP_ID", "VOLCENGINE_ASR_SECRET")
)
ALIYUN_PARAFORMER = ProviderRequirement(
    "aliyun_paraformer", ("ALIYUN_ASR_APP_KEY", "ALIYUN_ASR_SECRET")
)
XUNFEI_ASR = ProviderRequirement("xunfei_asr", ("XUNFEI_ASR_APP_ID", "XUNFEI_ASR_SECRET"))
TONGYI_TINGWU = ProviderRequirement("tongyi_tingwu", ("TONGYI_TINGWU_API_KEY",))
VOLCENGINE_TTS = ProviderRequirement(
    "volcengine_tts", ("VOLCENGINE_TTS_APP_ID", "VOLCENGINE_TTS_SECRET")
)
MINIMAX_TTS = ProviderRequirement("minimax_tts", ("MINIMAX_API_KEY",))
DEEPSEEK = ProviderRequirement("deepseek", ("DEEPSEEK_API_KEY",))
DOUBAO = ProviderRequirement("doubao", ("DOUBAO_API_KEY",))
QWEN3_VL = ProviderRequirement("qwen3_vl", ("QWEN_API_KEY",))
DOUBAO_VISION = ProviderRequirement("doubao_vision", ("DOUBAO_API_KEY",))


TASK_PROVIDER_REQUIREMENTS: dict[TaskType, ProviderChain] = {
    TaskType.REALTIME_STT: ProviderChain(VOLCENGINE_ASR, ALIYUN_PARAFORMER),
    TaskType.BATCH_TRANSCRIPTION: ProviderChain(XUNFEI_ASR, TONGYI_TINGWU),
    TaskType.INTERVIEWER_TTS: ProviderChain(VOLCENGINE_TTS, MINIMAX_TTS),
    TaskType.INTERVIEW_NEXT_QUESTION: ProviderChain(DEEPSEEK, DOUBAO),
    TaskType.CLAIM_EXTRACTION: ProviderChain(DEEPSEEK, DOUBAO),
    TaskType.CONTRADICTION_DETECTION: ProviderChain(DEEPSEEK, DOUBAO),
    TaskType.PHOTO_HYPOTHESIS: ProviderChain(QWEN3_VL, DOUBAO_VISION),
    TaskType.NARRATIVE_GENERATION: ProviderChain(DEEPSEEK, DOUBAO),
    TaskType.VERIFICATION: ProviderChain(DEEPSEEK, DOUBAO),
}

REQUIRED_ENV = tuple(
    sorted(
        {
            env_name
            for chain in TASK_PROVIDER_REQUIREMENTS.values()
            for provider in (chain.primary, chain.backup)
            for env_name in provider.required_env
        }
    )
)


def evaluate_provider_readiness(env: Mapping[str, str]) -> ProviderReadiness:
    missing = [env_name for env_name in REQUIRED_ENV if not env.get(env_name)]
    live_tasks: list[str] = []
    requirements: dict[str, dict[str, Any]] = {}

    for task_type, chain in TASK_PROVIDER_REQUIREMENTS.items():
        primary_ready = all(env.get(name) for name in chain.primary.required_env)
        backup_ready = all(env.get(name) for name in chain.backup.required_env)
        if primary_ready and backup_ready:
            live_tasks.append(task_type.value)
        requirements[task_type.value] = {
            "primary": {
                "name": chain.primary.name,
                "required_env": list(chain.primary.required_env),
                "ready": primary_ready,
            },
            "backup": {
                "name": chain.backup.name,
                "required_env": list(chain.backup.required_env),
                "ready": backup_ready,
            },
        }

    return ProviderReadiness(
        ready=not missing,
        missing_env=missing,
        live_tasks=live_tasks,
        task_requirements=requirements,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Phase 1 provider smoke readiness.")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit non-zero unless every Phase 1 provider credential and live provider evidence are present.",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=DEFAULT_PROVIDER_EVIDENCE,
        help="Provider evidence JSON to validate when --require-ready is set.",
    )
    args = parser.parse_args()

    readiness = evaluate_provider_readiness(os.environ)
    output = readiness.to_dict()
    exit_code = 0
    if args.require_ready:
        if not readiness.ready:
            exit_code = 2
        else:
            evidence = validate_provider(args.evidence)
            output["live_evidence"] = evidence.__dict__
            if not evidence.ok:
                exit_code = 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
