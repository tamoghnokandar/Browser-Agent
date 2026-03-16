"""Integration test: writeState in PerceptionLoop. Port of tests/integration/writestate.test.ts."""
import pytest

from loop.perception import PerceptionLoop, PerceptionLoopOptions
from loop.history import HistoryManager
from loop.state import StateStore
from tests.integration.mock_tab import MockBrowserTab
from tests.integration.mock_adapter import MockAdapter


EXAMPLE_STATE = {
    "orderId": "12345",
    "currentUrl": "https://example.com/step2",
    "nextStep": "step2",
}


class TestWriteStateIntegration:
    @pytest.mark.asyncio
    async def test_write_state_persists_state_visible_in_agent_state(self):
        adapter = MockAdapter()
        adapter.queue_actions([{"type": "writeState", "data": EXAMPLE_STATE}])
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "done"}])

        tab = MockBrowserTab()
        state_store = StateStore()

        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=HistoryManager(100_000),
                state=state_store,
            )
        )

        from agent_types import LoopOptions

        result = await loop.run(LoopOptions(max_steps=10))

        assert result.agent_state is not None
        assert result.agent_state.get("currentUrl") == "https://example.com/step2"
        assert result.agent_state.get("nextStep") == "step2"
        assert result.agent_state.get("orderId") == "12345"
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_write_state_appears_in_semantic_step_history(self):
        adapter = MockAdapter()
        adapter.queue_actions([{"type": "writeState", "data": EXAMPLE_STATE}])
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "done"}])

        tab = MockBrowserTab()

        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=HistoryManager(100_000),
                state=StateStore(),
            )
        )

        from agent_types import LoopOptions

        result = await loop.run(LoopOptions(max_steps=10))

        first_step = result.history[0] if result.history else None
        assert first_step is not None
        assert first_step.agent_state is not None
        assert first_step.agent_state.get("currentUrl") == "https://example.com/step2"
