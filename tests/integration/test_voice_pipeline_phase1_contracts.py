from __future__ import annotations

from uuid import uuid4

from changjuan_voice.main import app
from fastapi.testclient import TestClient


def test_voice_pipeline_emits_session_end_request_when_storyteller_asks_to_stop() -> None:
    client = TestClient(app)

    with client.websocket_connect(f"/api/v1/interview-sessions/{uuid4()}/stream") as websocket:
        hello = websocket.receive_json()
        websocket.send_json({"duration_ms": 400, "transcript_hint": "今天先到这里吧"})
        event = websocket.receive_json()

    assert hello["chunk_duration_ms"] == "300-500"
    assert event == {
        "type": "session_end_requested",
        "status": "accepted",
        "recommended_status": "completed_short",
        "reason": "storyteller_requested_stop",
    }


def test_voice_pipeline_switches_topic_after_storyteller_refusal() -> None:
    client = TestClient(app)

    with client.websocket_connect(f"/api/v1/interview-sessions/{uuid4()}/stream") as websocket:
        websocket.receive_json()
        websocket.send_json({"duration_ms": 400, "transcript_hint": "这段我不想说，别问了"})
        event = websocket.receive_json()

    assert event == {
        "type": "capture_instruction",
        "status": "accepted",
        "action": "switch_topic",
        "reason": "storyteller_refused_topic",
        "instruction": "switch topics immediately and do not ask about this topic again",
    }
