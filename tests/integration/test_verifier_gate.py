"""Integration test: Verifier in PerceptionLoop. Port of tests/integration/gate.test.ts."""
import pytest

from loop.perception import PerceptionLoop, PerceptionLoopOptions
from loop.history import HistoryManager
from loop.state import StateStore
from loop.verifier import CustomGate
from tests.integration.mock_tab import MockBrowserTab
from tests.integration.mock_adapter import MockAdapter


class TestVerifierIntegration:
    @pytest.mark.asyncio
    async def test_rejects_terminate_when_verifier_fails_then_continues(self):
        adapter = MockAdapter()
        adapter.queue_actions([
            {"type": "terminate", "status": "success", "result": "done too early"}
        ])
        adapter.queue_actions([
            {"type": "terminate", "status": "success", "result": "actually done"}
        ])

        tab = MockBrowserTab()
        verifier_call_count = [0]  # use list for closure

        async def verifier_fn(screenshot, url):
            verifier_call_count[0] += 1
            return verifier_call_count[0] > 1

        verifier = CustomGate(verifier_fn, "not ready yet")

        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=HistoryManager(100_000),
                state=StateStore(),
                verifier=verifier,
            )
        )

        from agent_types import LoopOptions

        result = await loop.run(LoopOptions(max_steps=10))

        assert result.status == "success"
        assert result.result == "actually done"
        assert result.steps == 2
        assert verifier_call_count[0] == 2

    @pytest.mark.asyncio
    async def test_accepts_terminate_immediately_when_verifier_passes(self):
        adapter = MockAdapter()
        adapter.queue_actions([
            {"type": "terminate", "status": "success", "result": "task complete"}
        ])

        tab = MockBrowserTab()

        async def always_pass(screenshot, url):
            return True

        verifier = CustomGate(always_pass)

        loop = PerceptionLoop(
            PerceptionLoopOptions(
                tab=tab,
                adapter=adapter,
                history=HistoryManager(100_000),
                state=StateStore(),
                verifier=verifier,
            )
        )

        from agent_types import LoopOptions

        result = await loop.run(LoopOptions(max_steps=5))
        assert result.status == "success"
        assert result.steps == 1
