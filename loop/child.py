from __future__ import annotations

from typing import Any, Dict, Optional, TypedDict

from agent_types import LoopOptions, LoopResult
from .history import HistoryManager
from .perception import PerceptionLoop, PerceptionLoopOptions
from .state import StateStore


class ChildLoop:
    @staticmethod
    async def run(
        instruction: str,
        parent: Dict[str, Any],
        options: Optional[ChildLoopOptions] = None,
    ) -> ChildLoopResult:
        opts = options or {}
        max_steps = opts.get("max_steps", 20)

        parent_dict: Dict[str, Any] = parent
        adapter = parent_dict.get("adapter")
        tab = parent_dict.get("tab")
        context_window_tokens = adapter.context_window_tokens

        history = HistoryManager(context_window_tokens)
        state_store = StateStore()

        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=history,
                state=state_store,
            )
        )

        loop_result: LoopResult = await loop.run(
            LoopOptions(
                max_steps=max_steps,
                system_prompt=f"Sub-task: {instruction}\n\nCall terminate when done.",
            )
        )

        return {
            "status": loop_result.status,
            "result": loop_result.result,
            "steps": loop_result.steps,
        }


class ChildLoopOptions(TypedDict, total=False):
    """Options for ChildLoop.run()."""
    max_steps: int


class ChildLoopResult(TypedDict):
    """Result from ChildLoop.run()."""
    status: str
    result: str
    steps: int