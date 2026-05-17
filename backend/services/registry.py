from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ABORTED = "aborted"
    ERROR = "error"


@dataclass
class RunHandle:
    run_id: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    status: RunStatus = RunStatus.PENDING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    final_state: dict[str, Any] | None = None
    error: str | None = None
    task: asyncio.Task | None = None

    async def emit(self, event: dict[str, Any]) -> None:
        await self.queue.put(event)

    async def mark_running(self) -> None:
        self.status = RunStatus.RUNNING
        await self.emit({"type": "status", "status": "running"})

    async def mark_done(
        self, final_state: dict[str, Any], token_stats: dict[str, Any] | None = None
    ) -> None:
        self.status = RunStatus.DONE
        self.final_state = final_state
        event: dict[str, Any] = {"type": "done", "status": "done"}
        if token_stats is not None:
            event["token_stats"] = token_stats
        await self.emit(event)

    async def mark_error(self, message: str) -> None:
        self.status = RunStatus.ERROR
        self.error = message
        await self.emit({"type": "error", "message": message})

    async def mark_aborted(self) -> None:
        self.status = RunStatus.ABORTED
        await self.emit({"type": "aborted"})

    def is_terminal(self) -> bool:
        return self.status in {RunStatus.DONE, RunStatus.ABORTED, RunStatus.ERROR}


class RunRegistry:
    def __init__(self) -> None:
        self._handles: dict[str, RunHandle] = {}

    def register(self) -> RunHandle:
        run_id = uuid.uuid4().hex[:12]
        handle = RunHandle(run_id=run_id)
        self._handles[run_id] = handle
        return handle

    def get(self, run_id: str) -> RunHandle | None:
        return self._handles.get(run_id)

    def drop(self, run_id: str) -> None:
        self._handles.pop(run_id, None)
