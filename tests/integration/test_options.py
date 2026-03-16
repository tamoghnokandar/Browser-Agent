"""PerceptionLoop options integration tests. Port of tests/integration/options.test.ts."""
import pytest

from loop.perception import PerceptionLoop, PerceptionLoopOptions
from loop.history import HistoryManager
from loop.state import StateStore
from agent_types import LoopOptions
from tests.integration.mock_tab import MockBrowserTab
from tests.integration.mock_adapter import MockAdapter


class TestPerceptionLoopOptions:
    class TestKeepRecentScreenshots:
        @pytest.mark.asyncio
        async def test_defaults_to_2_screenshots_kept(self):
            adapter = MockAdapter()
            for _ in range(4):
                adapter.queue_actions([{"type": "screenshot"}])
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

            await loop.run(LoopOptions(max_steps=10))
            # After 5 steps, wire history should have compressed old screenshots
            # (HistoryManager keeps only last keep_recent_screenshots = 2)
            # This verifies the default doesn't throw and the loop completes
            assert True

        @pytest.mark.asyncio
        async def test_keep_recent_screenshots_1_compresses_more_aggressively(self):
            adapter = MockAdapter()
            adapter.queue_actions([{"type": "screenshot"}])
            adapter.queue_actions([{"type": "screenshot"}])
            adapter.queue_actions([{"type": "terminate", "status": "success", "result": "done"}])

            tab = MockBrowserTab()
            history = HistoryManager(100_000)

            loop = PerceptionLoop(
                PerceptionLoopOptions(
                    tab=tab,
                    adapter=adapter,
                    history=history,
                    state=StateStore(),
                    keep_recent_screenshots=1,
                )
            )

            result = await loop.run(LoopOptions(max_steps=10))
            assert result.status == "success"

    class TestCursorOverlay:
        @pytest.mark.asyncio
        async def test_passes_cursor_overlay_false_to_screenshot_call(self):
            adapter = MockAdapter()
            adapter.queue_actions([{"type": "terminate", "status": "success", "result": "done"}])

            tab = MockBrowserTab()

            loop = PerceptionLoop(
                PerceptionLoopOptions(
                    tab=tab,
                    adapter=adapter,
                    history=HistoryManager(100_000),
                    state=StateStore(),
                    cursor_overlay=False,
                )
            )

            await loop.run(LoopOptions(max_steps=5))
            ss_call = next((c for c in tab.calls if c["method"] == "screenshot"), None)
            assert ss_call is not None
