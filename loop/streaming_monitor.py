"""
StreamingMonitor: enqueues StreamEvents. Port of src/loop/streaming-monitor.ts.
"""
from __future__ import annotations

import asyncio
import base64
from typing import Any, AsyncIterator, Dict, List, Optional

from agent_types import Action, ActionExecution


class StreamingMonitor:
    """LoopMonitor that enqueues StreamEvent objects onto an internal queue."""

    def __init__(self) -> None:
        self._queue: List[dict] = []
        self._resolver: Optional[asyncio.Future] = None
        self._finished = False
        self._final_result: Optional[Any] = None

    def _notify(self) -> None:
        if self._resolver and not self._resolver.done():
            self._resolver.set_result(None)
            self._resolver = None

    def _enqueue(self, event: dict) -> None:
        self._queue.append(event)
        self._notify()

    def complete(self, result: Any) -> None:
        self._final_result = result
        self._finished = True
        self._enqueue({"type": "done", "result": result})
        self._notify()

    def step_started(self, step: int, context: Any) -> None:
        max_steps = context.max_steps
        url = context.url
        self._enqueue({"type": "step_start", "step": step, "max_steps": max_steps, "url": url})
        screenshot = context.screenshot
        data = screenshot.data if hasattr(screenshot, "data") else screenshot.get("data", b"")
        b64 = base64.b64encode(data).decode("utf-8") if isinstance(data, bytes) else str(data)
        self._enqueue({"type": "screenshot", "step": step, "imageBase64": b64})

    def step_completed(self, step: int, response: Dict[str, Any]) -> None:
        thinking = response.get("thinking")
        if thinking:
            self._enqueue({"type": "thinking", "step": step, "text": thinking})

    def action_executed(self, step: int, action: Action, outcome: ActionExecution) -> None:
        self._enqueue({"type": "action", "step": step, "action": action})
        self._enqueue({"type": "action_result", "step": step, "action": action, "ok": outcome.ok, "error": outcome.error})
        if action.get("type") == "writeState":
            self._enqueue({"type": "state_written", "step": step, "data": action.get("data", {})})

    def action_blocked(self, step: int, action: Action, reason: str) -> None:
        self._enqueue({"type": "action_blocked", "step": step, "action": action, "reason": reason})

    def termination_rejected(self, step: int, reason: str) -> None:
        self._enqueue({"type": "termination_rejected", "step": step, "reason": reason})

    def compaction_triggered(self, step: int, tokens_before: int, tokens_after: int) -> None:
        self._enqueue({"type": "compaction", "step": step, "tokensBefore": tokens_before, "tokensAfter": tokens_after})

    def terminated(self, result: Any) -> None:
        pass

    def error(self, err: Exception) -> None:
        pass

    async def events(self) -> AsyncIterator[dict]:
        while True:
            while self._queue:
                event = self._queue.pop(0)
                yield event
                if event.get("type") == "done":
                    return

            if self._finished:
                return

            future = asyncio.get_event_loop().create_future()
            self._resolver = future
            # Re-check queue/finished after setting resolver (matches TS behavior)
            if self._queue or self._finished:
                self._resolver = None
                future.set_result(None)
            await future
            if self._queue or self._finished:
                self._resolver = None
