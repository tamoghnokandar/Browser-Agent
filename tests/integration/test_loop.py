"""PerceptionLoop integration tests. Port of tests/integration/loop.test.ts."""
import pytest

from loop.perception import PerceptionLoop, PerceptionLoopOptions
from loop.history import HistoryManager
from loop.state import StateStore
from loop.policy import SessionPolicy, SessionPolicyOptions
from agent_types import LoopOptions
from tests.integration.mock_tab import MockBrowserTab
from tests.integration.mock_adapter import MockAdapter


def make_loop(adapter, tab, policy=None):
    history = HistoryManager(100_000)
    state = StateStore()
    return PerceptionLoop(
        PerceptionLoopOptions(
            tab=tab,
            adapter=adapter,
            history=history,
            state=state,
            policy=policy,
        )
    )


class TestPerceptionLoop:
    @pytest.mark.asyncio
    async def test_terminates_on_terminate_action(self):
        adapter = MockAdapter()
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "task done"}])
        tab = MockBrowserTab()
        loop = make_loop(adapter, tab)
        result = await loop.run(LoopOptions(max_steps=10))
        assert result.status == "success"
        assert result.result == "task done"
        assert result.steps == 1

    @pytest.mark.asyncio
    async def test_exits_with_max_steps_when_no_terminate(self):
        adapter = MockAdapter()
        for _ in range(5):
            adapter.queue_actions([{"type": "screenshot"}])
        tab = MockBrowserTab()
        loop = make_loop(adapter, tab)
        result = await loop.run(LoopOptions(max_steps=3))
        assert result.status == "max_steps"
        assert result.steps == 3

    @pytest.mark.asyncio
    async def test_records_semantic_steps(self):
        adapter = MockAdapter()
        adapter.queue_actions([{"type": "click", "x": 500, "y": 500}])
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "done"}])
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
        assert len(result.history) > 0

    @pytest.mark.asyncio
    async def test_policy_blocks_goto_action(self):
        adapter = MockAdapter()
        adapter.queue_actions([{"type": "goto", "url": "https://blocked.com"}])
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "done"}])
        tab = MockBrowserTab()
        policy = SessionPolicy(SessionPolicyOptions(blocked_domains=["blocked.com"]))
        loop = make_loop(adapter, tab, policy)
        result = await loop.run(LoopOptions(max_steps=10))
        goto_call = next((c for c in tab.calls if c["method"] == "goto"), None)
        assert goto_call is None
        assert result.status == "success"
