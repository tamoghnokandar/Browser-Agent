"""Tests for HistoryManager. Port of tests/unit/history.test.ts."""
import pytest

from loop.history import HistoryManager
from agent_types import SemanticStep, TokenUsage


def make_response(input_tokens: int):
    """Create a mock model response."""
    return {
        "actions": [{"type": "screenshot"}],
        "usage": {"inputTokens": input_tokens, "outputTokens": 50},
        "rawResponse": None,
    }


def make_semantic_step(step_index: int) -> SemanticStep:
    """Create a mock semantic step."""
    return SemanticStep(
        step_index=step_index,
        url="https://example.com",
        screenshot_base64="abc123",
        actions=[],
        agent_state=None,
        token_usage=TokenUsage(input_tokens=100, output_tokens=50),
        duration_ms=500,
    )


class TestHistoryManager:
    def test_starts_with_empty_wire_history(self):
        h = HistoryManager(100_000)
        assert len(h.wire_history()) == 0

    def test_token_utilization_increases_after_append_response(self):
        h = HistoryManager(100_000)
        assert h.token_utilization() == 0
        h.append_response(make_response(1000))
        assert h.token_utilization() > 0

    def test_token_utilization_is_capped_at_one(self):
        h = HistoryManager(100)
        h.append_response(make_response(500))
        assert h.token_utilization() == 1.0

    def test_compress_screenshots_replaces_beyond_keep_recent(self):
        h = HistoryManager(100_000)
        for i in range(4):
            h.append_screenshot(f"data{i}", i)
        h.compress_screenshots(2)
        wire = h.wire_history()
        assert wire[0].get("compressed") is True
        assert wire[0].get("base64") is None
        assert wire[1].get("compressed") is True
        assert wire[2].get("compressed") is False
        assert wire[2].get("base64") == "data2"
        assert wire[3].get("base64") == "data3"

    def test_to_json_from_json_round_trips(self):
        h = HistoryManager(100_000)
        h.append_response(make_response(500))
        h.append_semantic_step(make_semantic_step(0))
        state = {"min_price": "£3.49", "min_title": "Sharp Objects"}
        json_data = h.to_json(state)
        h2, s2 = HistoryManager.from_json(json_data, 100_000)
        assert len(h2.wire_history()) == len(h.wire_history())
        assert s2 == state

    def test_aggregate_token_usage_sums_semantic_steps(self):
        h = HistoryManager(100_000)
        h.append_semantic_step(make_semantic_step(0))
        h.append_semantic_step(make_semantic_step(1))
        usage = h.aggregate_token_usage()
        assert usage["inputTokens"] == 200
        assert usage["outputTokens"] == 100
