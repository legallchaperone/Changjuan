from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CaptureAction(StrEnum):
    CONTINUE = "continue"
    END_SESSION = "end_session"
    SWITCH_TOPIC = "switch_topic"
    WAIT = "wait"


@dataclass(frozen=True)
class CaptureDecision:
    action: CaptureAction
    reason: str
    follow_up_instruction: str | None = None
    recommended_session_status: str | None = None


class CapturePolicy:
    _STOP_PHRASES = (
        "今天先到这里",
        "先到这里",
        "到这里吧",
        "不聊了",
        "结束吧",
    )
    _REFUSAL_PHRASES = (
        "不想说",
        "不愿意说",
        "别问",
        "不要问",
        "不说这个",
    )

    def decide(self, transcript_text: str | None, silence_ms: int | None = None) -> CaptureDecision:
        text = (transcript_text or "").strip()
        normalized = text.replace(" ", "")
        if not normalized and silence_ms is not None and 5000 <= silence_ms <= 10000:
            return CaptureDecision(
                action=CaptureAction.WAIT,
                reason="valid_storyteller_silence",
                follow_up_instruction="wait without interrupting",
            )
        if any(phrase in normalized for phrase in self._STOP_PHRASES):
            return CaptureDecision(
                action=CaptureAction.END_SESSION,
                reason="storyteller_requested_stop",
                recommended_session_status="completed_short",
            )
        if any(phrase in normalized for phrase in self._REFUSAL_PHRASES):
            return CaptureDecision(
                action=CaptureAction.SWITCH_TOPIC,
                reason="storyteller_refused_topic",
                follow_up_instruction="switch topics immediately and do not ask about this topic again",
            )
        return CaptureDecision(action=CaptureAction.CONTINUE, reason="continue_interview")
