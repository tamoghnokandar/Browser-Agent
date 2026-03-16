"""Compaction integration tests in PerceptionLoop. Port of tests/integration/compaction.test.ts."""
from typing import Any, AsyncIterator, Dict, List, Optional

import pytest

from loop.history import HistoryManager
from loop.monitor import LoopMonitor
from loop.perception import PerceptionLoop, PerceptionLoopOptions
from loop.state import StateStore
from tests.integration.mock_adapter import MockAdapter
from tests.integration.mock_tab import MockBrowserTab
from agent_types import LoopOptions


class HighTokenAdapter:
    """Adapter that returns high token counts to trigger compaction, then terminates."""

    model_id = "high-token-model"
    provider = "test"
    native_computer_use = False
    context_window_tokens = 100_000

    def __init__(self):
        self._step_index = 0
        self.compaction_called = False
        self._last_response: Optional[Dict[str, Any]] = None
        self._steps: List[List[Dict[str, Any]]] = [
            [{"type": "screenshot"}],
            [{"type": "terminate", "status": "success", "result": "done"}],
        ]

    async def step(self, context: Dict[str, Any]) -> Dict[str, Any]:
        actions = (
            self._steps[self._step_index]
            if self._step_index < len(self._steps)
            else [{"type": "terminate", "status": "success", "result": "done"}]
        )
        self._step_index += 1
        response = {
            "actions": actions,
            "usage": {"inputTokens": 90_000, "outputTokens": 1_000},
            "rawResponse": None,
        }
        self._last_response = response
        return response

    async def stream(self, context: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        response = await self.step(context)
        for action in response.get("actions", []):
            yield action

    def estimate_tokens(self, context: Dict[str, Any]) -> int:
        return 90_000

    async def summarize(
        self, wire_history: List[Dict[str, Any]], agent_state: Any
    ) -> str:
        self.compaction_called = True
        return "Compacted summary."

    def get_last_stream_response(self) -> Optional[Dict[str, Any]]:
        return self._last_response


class CompactionMonitor(LoopMonitor):
    def __init__(self):
        # FIXED: Renamed to avoid colliding with the method name
        self.was_compaction_triggered = False

    def step_started(self, step: int, context: Any) -> None:
        pass

    def step_completed(self, step: int, response: Any) -> None:
        pass

    def action_executed(self, step: int, action: Any, outcome: Any) -> None:
        pass

    def action_blocked(self, step: int, action: Any, reason: str) -> None:
        pass

    def termination_rejected(self, step: int, reason: str) -> None:
        pass

    def compaction_triggered(self, step: int, tokens_before: int, tokens_after: int) -> None:
        # FIXED: Assigning to the renamed instance variable
        self.was_compaction_triggered = True

    def terminated(self, result: Any) -> None:
        pass


class TestCompactionIntegration:
    @pytest.mark.asyncio
    async def test_triggers_compaction_when_token_utilization_exceeds_threshold(self):
        adapter = HighTokenAdapter()
        tab = MockBrowserTab()
        monitor = CompactionMonitor()

        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=HistoryManager(100_000),
                state=StateStore(),
                monitor=monitor,
            )
        )

        await loop.run(LoopOptions(max_steps=5, compaction_threshold=0.8))

        # FIXED: Asserting against the renamed instance variable
        assert monitor.was_compaction_triggered is True
        assert adapter.compaction_called is True

    @pytest.mark.asyncio
    async def test_does_not_trigger_compaction_below_threshold(self):
        adapter = MockAdapter()
        adapter.queue_actions([{"type": "screenshot"}])
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "done"}])

        tab = MockBrowserTab()
        monitor = CompactionMonitor()

        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=HistoryManager(100_000),
                state=StateStore(),
                monitor=monitor,
            )
        )

        await loop.run(LoopOptions(max_steps=5, compaction_threshold=0.8))

        # FIXED: Asserting against the renamed instance variable
        assert monitor.was_compaction_triggered is False