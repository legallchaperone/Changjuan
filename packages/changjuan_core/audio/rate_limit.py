from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class AudioChunkPolicy:
    min_duration_ms: int = 300
    max_duration_ms: int = 500
    max_chunks_per_minute: int = 240
    _received: deque[datetime] = field(default_factory=deque)

    @property
    def chunk_count(self) -> int:
        return len(self._received)

    def accept_chunk(self, duration_ms: int, received_at: datetime) -> None:
        if duration_ms < self.min_duration_ms or duration_ms > self.max_duration_ms:
            raise ValueError("audio chunks must be 300-500ms")

        cutoff = received_at - timedelta(minutes=1)
        while self._received and self._received[0] <= cutoff:
            self._received.popleft()
        if len(self._received) >= self.max_chunks_per_minute:
            raise ValueError("audio chunk rate limit exceeded")
        self._received.append(received_at)
