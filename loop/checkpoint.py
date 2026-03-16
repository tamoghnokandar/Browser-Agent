"""
CheckpointManager: browser state checkpoints. Port of src/loop/checkpoint.ts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from browser.tab import BrowserTab
from agent_types import TaskState


@dataclass
class BrowserCheckpoint:
    step: int
    url: str
    agent_state: Optional[TaskState] = None
    scroll_y: int = 0


class CheckpointManager:
    def __init__(self, interval: int = 5, max_checkpoints: int = 10) -> None:
        self._checkpoints: List[BrowserCheckpoint] = []
        self.interval = interval
        self._max_checkpoints = max_checkpoints

    async def save(
        self,
        step: int,
        url: str,
        agent_state: Optional[TaskState],
        tab: "BrowserTab",
    ) -> None:
        scroll_y = 0
        try:
            scroll_y = await tab.evaluate("window.scrollY || 0")
        except Exception:
            pass

        self._checkpoints.append(BrowserCheckpoint(
            step=step,
            url=url,
            agent_state=dict(agent_state) if agent_state else None,
            scroll_y=scroll_y,
        ))

        if len(self._checkpoints) > self._max_checkpoints:
            self._checkpoints = self._checkpoints[-self._max_checkpoints:]

    async def restore(self, tab: BrowserTab, target_step: Optional[int] = None) -> Optional[BrowserCheckpoint]:
        if not self._checkpoints:
            return None

        checkpoint = None
        if target_step is not None:
            for i in range(len(self._checkpoints) - 1, -1, -1):
                if self._checkpoints[i].step <= target_step:
                    checkpoint = self._checkpoints[i]
                    break
        else:
            checkpoint = self._checkpoints[-2] if len(self._checkpoints) >= 2 else self._checkpoints[0]

        if not checkpoint:
            return None

        try:
            await tab.goto(checkpoint.url)
            if checkpoint.scroll_y > 0:
                await tab.evaluate(f"window.scrollTo(0, {checkpoint.scroll_y})")
        except Exception:
            pass

        restore_idx = self._checkpoints.index(checkpoint)
        if restore_idx >= 0:
            self._checkpoints = self._checkpoints[: restore_idx + 1]

        return checkpoint

    def latest(self) -> Optional[BrowserCheckpoint]:
        return self._checkpoints[-1] if self._checkpoints else None

    def count(self) -> int:
        return len(self._checkpoints)
