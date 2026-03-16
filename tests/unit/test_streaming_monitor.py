"""Tests for StreamingMonitor. Port of tests/unit/streaming-monitor.test.ts."""
import pytest

from loop.streaming_monitor import StreamingMonitor
from agent_types import ActionExecution
from loop.perception import StepContext
from agent_types import ScreenshotResult


@pytest.fixture
def mock_screenshot():
    return ScreenshotResult(
        data=b"\x00" * 10,
        width=1280,
        height=720,
        mime_type="image/png",
    )


@pytest.fixture
def mock_context(mock_screenshot):
    return StepContext(
        screenshot=mock_screenshot,
        wire_history=[],
        agent_state={},
        step_index=0,
        max_steps=10,
        url="https://example.com",
        system_prompt=None,
    )


@pytest.fixture
def mock_response():
    return {
        "actions": [{"type": "click", "x": 500, "y": 500}],
        "usage": {"inputTokens": 100, "outputTokens": 50},
        "rawResponse": None,
    }


@pytest.fixture
def mock_result():
    return {
        "status": "success",
        "result": "done",
        "steps": 1,
        "history": [],
        "agentState": None,
        "tokenUsage": {"inputTokens": 100, "outputTokens": 50},
    }


class TestStreamingMonitor:
    @pytest.mark.asyncio
    async def test_emits_step_start_and_screenshot_on_step_started(
        self, mock_context, mock_result
    ):
        monitor = StreamingMonitor()
        monitor.step_started(0, mock_context)
        monitor.complete(mock_result)

        events = []
        async for event in monitor.events():
            events.append(event)

        types = [e.get("type") for e in events]
        assert "step_start" in types
        assert "screenshot" in types
        assert "done" in types

    @pytest.mark.asyncio
    async def test_emits_thinking_when_response_has_thinking(
        self, mock_response, mock_result
    ):
        monitor = StreamingMonitor()
        monitor.step_completed(0, {**mock_response, "thinking": "I think I should click"})
        monitor.complete(mock_result)

        events = []
        async for event in monitor.events():
            events.append(event)

        thinking_event = next((e for e in events if e.get("type") == "thinking"), None)
        assert thinking_event is not None
        assert thinking_event.get("text") == "I think I should click"

    @pytest.mark.asyncio
    async def test_does_not_emit_thinking_when_no_thinking(
        self, mock_response, mock_result
    ):
        monitor = StreamingMonitor()
        monitor.step_completed(0, mock_response)
        monitor.complete(mock_result)

        events = []
        async for event in monitor.events():
            events.append(event)

        assert next((e for e in events if e.get("type") == "thinking"), None) is None

    @pytest.mark.asyncio
    async def test_emits_action_and_action_result_on_action_executed(
        self, mock_result
    ):
        monitor = StreamingMonitor()
        action = {"type": "click", "x": 500, "y": 500}
        monitor.action_executed(0, action, ActionExecution(ok=True))
        monitor.complete(mock_result)

        events = []
        async for event in monitor.events():
            events.append(event)

        assert next((e for e in events if e.get("type") == "action"), None) is not None
        assert next((e for e in events if e.get("type") == "action_result"), None) is not None

    @pytest.mark.asyncio
    async def test_emits_state_written_when_write_state_action_executed(
        self, mock_result
    ):
        monitor = StreamingMonitor()
        action = {"type": "writeState", "data": {"min_price": "£3.49"}}
        monitor.action_executed(0, action, ActionExecution(ok=True))
        monitor.complete(mock_result)

        events = []
        async for event in monitor.events():
            events.append(event)

        state_event = next((e for e in events if e.get("type") == "state_written"), None)
        assert state_event is not None
        assert state_event.get("data") == {"min_price": "£3.49"}

    @pytest.mark.asyncio
    async def test_emits_action_blocked_on_action_blocked(self, mock_result):
        monitor = StreamingMonitor()
        action = {"type": "goto", "url": "https://evil.com"}
        monitor.action_blocked(0, action, "domain not allowed")
        monitor.complete(mock_result)

        events = []
        async for event in monitor.events():
            events.append(event)

        blocked_event = next((e for e in events if e.get("type") == "action_blocked"), None)
        assert blocked_event is not None
        assert blocked_event.get("reason") == "domain not allowed"

    @pytest.mark.asyncio
    async def test_emits_compaction_on_compaction_triggered(self, mock_result):
        monitor = StreamingMonitor()
        monitor.compaction_triggered(0, 90_000, 13_500)
        monitor.complete(mock_result)

        events = []
        async for event in monitor.events():
            events.append(event)

        compaction_event = next((e for e in events if e.get("type") == "compaction"), None)
        assert compaction_event is not None
        assert compaction_event.get("tokensBefore") == 90_000
        assert compaction_event.get("tokensAfter") == 13_500

    @pytest.mark.asyncio
    async def test_emits_done_event_with_final_result(self, mock_result):
        monitor = StreamingMonitor()
        monitor.complete(mock_result)

        events = []
        async for event in monitor.events():
            events.append(event)

        done_event = next((e for e in events if e.get("type") == "done"), None)
        assert done_event is not None
        assert done_event.get("result", {}).get("status") == "success"
        assert done_event.get("result", {}).get("result") == "done"

    @pytest.mark.asyncio
    async def test_terminates_generator_after_done_event(self, mock_result):
        monitor = StreamingMonitor()
        monitor.complete(mock_result)

        events = []
        async for event in monitor.events():
            events.append(event)

        assert events[-1].get("type") == "done"
