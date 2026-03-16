"""Policy integration tests within loop. Port of tests/integration/policy-integration.test.ts."""
import pytest

from loop.perception import PerceptionLoop, PerceptionLoopOptions
from loop.history import HistoryManager
from loop.state import StateStore
from loop.policy import SessionPolicy, SessionPolicyOptions
from agent_types import LoopOptions
from tests.integration.mock_tab import MockBrowserTab
from tests.integration.mock_adapter import MockAdapter


class TestPolicyIntegration:
    @pytest.mark.asyncio
    async def test_blocked_action_is_not_dispatched_to_browser(self):
        adapter = MockAdapter()
        adapter.queue_actions([{"type": "goto", "url": "https://evil.com/page"}])
        adapter.queue_actions([{"type": "terminate", "status": "failure", "result": "could not navigate"}])
        tab = MockBrowserTab()
        policy = SessionPolicy(SessionPolicyOptions(blocked_domains=["evil.com"]))
        history = HistoryManager(100_000)
        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=history,
                state=StateStore(),
                policy=policy,
            )
        )
        await loop.run(LoopOptions(max_steps=5))
        goto_call = next((c for c in tab.calls if c["method"] == "goto"), None)
        assert goto_call is None

    @pytest.mark.asyncio
    async def test_allowed_action_passes_through_policy(self):
        adapter = MockAdapter()
        adapter.queue_actions([{"type": "goto", "url": "https://allowed.com/page"}])
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "done"}])
        tab = MockBrowserTab()
        policy = SessionPolicy(SessionPolicyOptions(allowed_domains=["allowed.com"]))
        history = HistoryManager(100_000)
        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=history,
                state=StateStore(),
                policy=policy,
            )
        )
        await loop.run(LoopOptions(max_steps=5))
        goto_call = next((c for c in tab.calls if c["method"] == "goto"), None)
        assert goto_call is not None
        assert goto_call["args"][0] == "https://allowed.com/page"
