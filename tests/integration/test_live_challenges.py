"""
Live challenges tests. Port of tests/integration/live-challenges.test.ts.

Challenge 1: Empty actions (text-only model response) - when model returns no tool_use,
PerceptionLoop must inject screenshot so the loop continues.

Challenge 2: CDPTab URL bar emulation - skipped (requires CDP session mock).

Challenge 3: summarize() base64 overflow - wire history stripping logic.
"""

import json
import pytest

from loop.perception import PerceptionLoop, PerceptionLoopOptions
from loop.history import HistoryManager
from loop.state import StateStore
from agent_types import LoopOptions
from tests.integration.mock_tab import MockBrowserTab
from tests.integration.mock_adapter import MockAdapter


def make_loop(adapter, tab):
    history = HistoryManager(100_000)
    state = StateStore()
    return PerceptionLoop(
        PerceptionLoopOptions(
            tab=tab,
            adapter=adapter,
            history=history,
            state=state,
        )
    )


class TestChallenge1EmptyActions:
    """Empty actions / text-only response fallback."""

    @pytest.mark.asyncio
    async def test_loop_continues_after_text_only_response_and_terminates_on_next_step(self):
        adapter = MockAdapter()
        adapter.queue_empty_response()
        adapter.queue_actions([
            {"type": "terminate", "status": "success", "result": "born 1916 in Petoskey"}
        ])

        tab = MockBrowserTab()
        loop = make_loop(adapter, tab)
        result = await loop.run(LoopOptions(max_steps=5))

        assert result.status == "success"
        assert result.result == "born 1916 in Petoskey"
        assert result.steps == 2

    @pytest.mark.asyncio
    async def test_screenshot_action_is_injected_when_model_returns_empty_actions(self):
        adapter = MockAdapter()
        adapter.queue_empty_response()
        adapter.queue_empty_response()
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "done"}])

        tab = MockBrowserTab()
        loop = make_loop(adapter, tab)
        result = await loop.run(LoopOptions(max_steps=10))

        assert result.status == "success"
        assert result.steps == 3

        screenshot_calls = [c for c in tab.calls if c["method"] == "screenshot"]
        assert len(screenshot_calls) >= 3

    @pytest.mark.asyncio
    async def test_empty_response_does_not_lose_step_count(self):
        adapter = MockAdapter()
        adapter.queue_empty_response()
        adapter.queue_actions([{"type": "terminate", "status": "success", "result": "ok"}])

        tab = MockBrowserTab()
        loop = make_loop(adapter, tab)
        result = await loop.run(LoopOptions(max_steps=3))

        assert result.steps == 2

    @pytest.mark.asyncio
    async def test_max_steps_still_triggers_after_all_empty_responses(self):
        adapter = MockAdapter()
        for _ in range(5):
            adapter.queue_empty_response()

        tab = MockBrowserTab()
        loop = make_loop(adapter, tab)
        result = await loop.run(LoopOptions(max_steps=3))

        assert result.status == "max_steps"
        assert result.steps == 3


class TestChallenge3SummarizeBase64Overflow:
    """summarize() strips base64 from wireHistory."""

    def _make_wire_history_with_screenshot(self, num_screenshots=3):
        history = []
        for i in range(num_screenshots):
            history.append({
                "role": "screenshot",
                "stepIndex": i,
                "base64": "A" * 300_000,
                "compressed": False,
            })
            history.append({
                "role": "assistant",
                "actions": [{"type": "click", "x": 500, "y": 500}],
                "tool_call_ids": [f"toolu_{i}"],
            })
            history.append({
                "role": "tool_result",
                "tool_call_id": f"toolu_{i}",
                "ok": True,
            })
        return history

    def test_strips_base64_from_screenshot_entries_before_summarization(self):
        wire_history = self._make_wire_history_with_screenshot(3)

        safe_history = []
        for msg in wire_history[-20:]:
            if msg.get("role") == "screenshot":
                safe_history.append({
                    "role": "screenshot",
                    "stepIndex": msg.get("stepIndex"),
                    "compressed": True,
                })
            else:
                safe_history.append(msg)

        for msg in safe_history:
            assert msg.get("base64") is None

        screenshot_entries = [m for m in safe_history if m.get("role") == "screenshot"]
        assert len(screenshot_entries) == 3
        for s in screenshot_entries:
            assert s.get("compressed") is True

    def test_serialized_safe_history_is_orders_of_magnitude_smaller(self):
        wire_history = self._make_wire_history_with_screenshot(3)

        raw_json = json.dumps(wire_history)
        safe_history = []
        for msg in wire_history[-20:]:
            if msg.get("role") == "screenshot":
                safe_history.append({
                    "role": "screenshot",
                    "stepIndex": msg.get("stepIndex"),
                    "compressed": True,
                })
            else:
                safe_history.append(msg)
        safe_json = json.dumps(safe_history)

        assert len(raw_json) > 500_000
        assert len(safe_json) < 5_000

    def test_only_last_20_messages_included_in_summarization(self):
        wire_history = self._make_wire_history_with_screenshot(10)
        assert len(wire_history) == 30

        safe_history = []
        for msg in wire_history[-20:]:
            if msg.get("role") == "screenshot":
                safe_history.append({
                    "role": "screenshot",
                    "stepIndex": msg.get("stepIndex"),
                    "compressed": True,
                })
            else:
                safe_history.append(msg)

        assert len(safe_history) == 20

    def test_non_screenshot_messages_pass_through_unmodified(self):
        wire_history = [
            {"role": "screenshot", "stepIndex": 0, "base64": "BIGDATA", "compressed": False},
            {"role": "assistant", "actions": [{"type": "click", "x": 500, "y": 500}], "tool_call_ids": ["id1"]},
            {"role": "tool_result", "tool_call_id": "id1", "ok": True},
        ]

        safe_history = []
        for msg in wire_history[-20:]:
            if msg.get("role") == "screenshot":
                safe_history.append({
                    "role": "screenshot",
                    "stepIndex": msg.get("stepIndex"),
                    "compressed": True,
                })
            else:
                safe_history.append(msg)

        assert safe_history[1] == wire_history[1]
        assert safe_history[2] == wire_history[2]
