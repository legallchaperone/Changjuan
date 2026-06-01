from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from changjuan_core.ai.capture import CaptureAction, CapturePolicy
from changjuan_core.audio.rate_limit import AudioChunkPolicy
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="Changjuan Voice Pipeline", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.websocket("/api/v1/interview-sessions/{session_id}/stream")
async def stream(session_id: UUID, websocket: WebSocket) -> None:
    await websocket.accept()
    policy = AudioChunkPolicy()
    capture_policy = CapturePolicy()
    await websocket.send_json(
        {
            "session_id": str(session_id),
            "chunk_duration_ms": "300-500",
            "max_chunks_per_minute": policy.max_chunks_per_minute,
        }
    )
    try:
        while True:
            message = await websocket.receive_json()
            duration_ms = int(message.get("duration_ms", 0))
            policy.accept_chunk(duration_ms=duration_ms, received_at=datetime.now(UTC))
            decision = capture_policy.decide(
                transcript_text=message.get("transcript_hint", ""),
                silence_ms=message.get("silence_ms"),
            )
            if decision.action == CaptureAction.END_SESSION:
                await websocket.send_json(
                    {
                        "type": "session_end_requested",
                        "status": "accepted",
                        "recommended_status": decision.recommended_session_status,
                        "reason": decision.reason,
                    }
                )
                continue
            if decision.action in {CaptureAction.SWITCH_TOPIC, CaptureAction.WAIT}:
                await websocket.send_json(
                    {
                        "type": "capture_instruction",
                        "status": "accepted",
                        "action": decision.action.value,
                        "reason": decision.reason,
                        "instruction": decision.follow_up_instruction,
                    }
                )
                continue
            await websocket.send_json(
                {
                    "type": "partial_transcript",
                    "status": "accepted",
                    "chunks_seen": policy.chunk_count,
                    "text": message.get("transcript_hint", ""),
                }
            )
    except WebSocketDisconnect:
        return
    except ValueError as exc:
        await websocket.send_json({"type": "error", "code": 42901, "message": str(exc)})
        await websocket.close(code=1008)
