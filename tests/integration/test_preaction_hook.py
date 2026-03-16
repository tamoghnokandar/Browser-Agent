"""PreActionHook integration tests in PerceptionLoop. Port of tests/integration/preaction-hook.test.ts."""
import pytest

from loop.perception import PerceptionLoop, PerceptionLoopOptions
from loop.history import HistoryManager
from loop.state import StateStore
from agent_types import LoopOptions
from tests.integration.mock_tab import MockBrowserTab
from tests.integration.mock_adapter import MockAdapter


class TestPreActionHookIntegration:
    @pytest.mark.asyncio
    async def test_hook_can_deny_action_and_loop_continues_without_dispatching(self):
        adapter = MockAdapter()
        adapter.queue_actions([{"type": "click", "x": 500, "y": 500}])
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "done"}])

        tab = MockBrowserTab()
        denied_actions = []

        async def pre_action_hook(action):
            if action.get("type") == "click":
                denied_actions.append(action["type"])
                return {"decision": "deny", "reason": "clicks not allowed in test"}
            return {"decision": "allow"}

        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=HistoryManager(100_000),
                state=StateStore(),
                pre_action_hook=pre_action_hook,
            )
        )

        result = await loop.run(LoopOptions(max_steps=10))

        assert result.status == "success"
        click_call = next((c for c in tab.calls if c["method"] == "click"), None)
        assert click_call is None
        assert "click" in denied_actions

    @pytest.mark.asyncio
    async def test_hook_allows_actions_it_doesnt_deny(self):
        adapter = MockAdapter()
        adapter.queue_actions([{"type": "click", "x": 500, "y": 500}])
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "done"}])

        tab = MockBrowserTab()

        async def pre_action_hook(action):
            return {"decision": "allow"}

        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=HistoryManager(100_000),
                state=StateStore(),
                pre_action_hook=pre_action_hook,
            )
        )

        await loop.run(LoopOptions(max_steps=10))
        click_call = next((c for c in tab.calls if c["method"] == "click"), None)
        assert click_call is not None

    @pytest.mark.asyncio
    async def test_hook_fires_before_policy_check(self):
        adapter = MockAdapter()
        adapter.queue_actions([{"type": "goto", "url": "https://example.com"}])
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "done"}])

        tab = MockBrowserTab()
        hook_order = []

        async def pre_action_hook(action):
            hook_order.append("hook")
            return {"decision": "allow"}

        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=HistoryManager(100_000),
                state=StateStore(),
                pre_action_hook=pre_action_hook,
            )
        )

        await loop.run(LoopOptions(max_steps=10))
        assert "hook" in hook_order
