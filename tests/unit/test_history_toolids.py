"""Tests for HistoryManager tool call ID correlation. Port of tests/unit/history-toolids.test.ts."""
import pytest

from loop.history import HistoryManager
from agent_types import ActionExecution


def make_response_with_ids(actions, tool_call_ids, input_tokens=100):
    """Create response with explicit tool call IDs."""
    return {
        "actions": actions,
        "toolCallIds": tool_call_ids,
        "usage": {"inputTokens": input_tokens, "outputTokens": 50},
        "rawResponse": None,
    }


class TestHistoryManagerToolCallIds:
    def test_tool_result_references_correct_tool_call_id(self):
        h = HistoryManager(100_000)
        click_action = {"type": "click", "x": 500, "y": 500}
        response = make_response_with_ids([click_action], ["toolu_abc123"])
        h.append_response(response)
        h.append_action_outcome(click_action, ActionExecution(ok=True))

        wire = h.wire_history()
        assistant_msg = wire[0]
        tool_result_msg = wire[1]

        assert assistant_msg.get("role") == "assistant"
        assert assistant_msg.get("tool_call_ids", [])[0] == "toolu_abc123"
        assert tool_result_msg.get("role") == "tool_result"
        assert tool_result_msg.get("tool_call_id") == "toolu_abc123"

    def test_multiple_actions_each_get_own_tool_call_id(self):
        h = HistoryManager(100_000)
        click = {"type": "click", "x": 100, "y": 100}
        type_action = {"type": "type", "text": "hello"}
        response = make_response_with_ids(
            [click, type_action], ["toolu_click1", "toolu_type2"]
        )
        h.append_response(response)
        h.append_action_outcome(click, ActionExecution(ok=True))
        h.append_action_outcome(type_action, ActionExecution(ok=True))

        wire = h.wire_history()
        assert wire[1].get("tool_call_id") == "toolu_click1"
        assert wire[2].get("tool_call_id") == "toolu_type2"

    def test_falls_back_to_generated_id_when_no_tool_call_ids(self):
        h = HistoryManager(100_000)
        action = {"type": "screenshot"}
        h.append_response({
            "actions": [action],
            "usage": {"inputTokens": 100, "outputTokens": 50},
            "rawResponse": None,
        })
        h.append_action_outcome(action, ActionExecution(ok=True))

        wire = h.wire_history()
        tool_result = wire[1]
        assert tool_result.get("role") == "tool_result"
        assert isinstance(tool_result.get("tool_call_id"), str)
        assert len(tool_result.get("tool_call_id", "")) > 0
