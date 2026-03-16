"""RepeatDetector integration tests. Port of tests/integration/repeat-detector.test.ts."""
import pytest

from loop.perception import PerceptionLoop, PerceptionLoopOptions
from loop.history import HistoryManager
from loop.state import StateStore
from agent_types import LoopOptions
from tests.integration.mock_tab import MockBrowserTab
from tests.integration.mock_adapter import MockAdapter


class TestRepeatDetectorIntegration:
    @pytest.mark.asyncio
    async def test_agent_self_corrects_after_repeat_nudge(self):
        adapter = MockAdapter()
        for _ in range(6):
            adapter.queue_actions([{"type": "click", "x": 500, "y": 500}])
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "recovered"}])

        tab = MockBrowserTab()
        history = HistoryManager(100_000)
        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=history,
                state=StateStore(),
            )
        )

        result = await loop.run(LoopOptions(max_steps=10))
        assert result.status == "success"
        assert result.result == "recovered"
        assert result.steps == 7

    @pytest.mark.asyncio
    async def test_reaches_max_steps_if_agent_never_self_corrects(self):
        adapter = MockAdapter()
        for _ in range(20):
            adapter.queue_actions([{"type": "click", "x": 500, "y": 500}])

        tab = MockBrowserTab()
        history = HistoryManager(100_000)
        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=history,
                state=StateStore(),
            )
        )

        result = await loop.run(LoopOptions(max_steps=10))
        assert result.status == "max_steps"
        assert result.steps == 10
