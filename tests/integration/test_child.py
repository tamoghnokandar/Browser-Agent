"""ChildLoop integration tests. Port of tests/integration/child.test.ts."""
import pytest

from loop.child import ChildLoop
from tests.integration.mock_tab import MockBrowserTab
from tests.integration.mock_adapter import MockAdapter


class TestChildLoop:
    @pytest.mark.asyncio
    async def test_returns_success_when_child_terminates_successfully(self):
        adapter = MockAdapter()
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "subtask done"}])
        tab = MockBrowserTab()

        result = await ChildLoop.run(
            "Do subtask",
            {"tab": tab, "adapter": adapter},
            {"max_steps": 5},
        )

        assert result["status"] == "success"
        assert result["steps"] == 1

    @pytest.mark.asyncio
    async def test_max_steps_status_when_child_does_not_terminate(self):
        adapter = MockAdapter()
        for _ in range(3):
            adapter.queue_actions([{"type": "screenshot"}])
        tab = MockBrowserTab()

        result = await ChildLoop.run(
            "Never terminate",
            {"tab": tab, "adapter": adapter},
            {"max_steps": 2},
        )

        assert result["status"] == "max_steps"
